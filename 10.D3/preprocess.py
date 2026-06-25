"""
D3: Signal preprocessing and windowing pipeline.

Pipeline: raw CSV → calibration → trim edges → gravity removal →
          low-pass filter → sliding window → standardized dataset

Output: data/windowed_dataset.npz + data/windowed_dataset.csv
        reports/figures/preprocess_comparison.png

Usage: python src/preprocess.py
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import signal
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from utils import FS, WINDOW_SAMPLES, OVERLAP, RAW_DIR, ACC_AXES, GYRO_AXES, MAG_AXES, ALL_AXES, ACTIVITIES

ROOT = Path(__file__).parent.parent
REPORTS_DIR = ROOT / "reports" / "figures"
WINDOWED_DIR = ROOT / "data" / "windowed"
CALIB_PARAMS_PATH = ROOT / "calib" / "calib_params.json"

TRIM_SEC = 2.0  # trim from start/end of each trial
GRAVITY_CUTOFF = 0.3  # Hz, high-pass for gravity separation
LP_CUTOFF = 20.0  # Hz, low-pass anti-aliasing
LP_ORDER = 4


# ═══════════════════════════════════════════════════════════════════════════
# 1. Calibration
# ═══════════════════════════════════════════════════════════════════════════

def load_calib_params():
    """Load calibration parameters from calib_params.json."""
    if not CALIB_PARAMS_PATH.exists():
        print(f"WARNING: {CALIB_PARAMS_PATH} not found. Using identity calibration.")
        return None
    with open(CALIB_PARAMS_PATH, encoding="utf-8") as f:
        return json.load(f)


def apply_calibration(df, calib):
    """Apply accelerometer and magnetometer calibration, gyro bias correction."""
    if calib is None:
        return df
    df = df.copy()

    # Accelerometer: a_cal = (a_raw - bias) * scale
    acc_bias = np.array(calib["accelerometer"]["bias"])
    acc_scale = np.array(calib["accelerometer"]["scale"])
    acc_M = np.array(calib["accelerometer"].get("misalignment", np.eye(3)))
    acc_raw = df[list(ACC_AXES)].values.astype(np.float64)
    acc_cal = (acc_raw - acc_bias) * acc_scale
    acc_cal = acc_cal @ acc_M.T
    df[list(ACC_AXES)] = acc_cal

    # Magnetometer: m_cal = soft_iron @ (m_raw - hard_iron)
    mag_hard = np.array(calib["magnetometer"]["hard_iron"])
    mag_soft = np.array(calib["magnetometer"]["soft_iron"])
    mag_raw = df[list(MAG_AXES)].values.astype(np.float64)
    mag_cal = (mag_raw - mag_hard) @ mag_soft.T
    df[list(MAG_AXES)] = mag_cal

    # Gyro: subtract static bias
    gyro_bias = np.array(calib["gyroscope"]["bias"])
    df[list(GYRO_AXES)] = df[list(GYRO_AXES)].values - gyro_bias

    return df


# ═══════════════════════════════════════════════════════════════════════════
# 2. Signal preprocessing
# ═══════════════════════════════════════════════════════════════════════════

def trim_trial_edges(df, trim_sec=TRIM_SEC):
    """Remove first/last trim_sec seconds of each trial (transition artifacts)."""
    n_trim = int(FS * trim_sec)
    if len(df) <= 2 * n_trim:
        return df  # too short to trim
    return df.iloc[n_trim:-n_trim].reset_index(drop=True)


def remove_gravity(df, cutoff=GRAVITY_CUTOFF, order=3):
    """High-pass Butterworth filter to separate gravity from body motion.
    Adds _body and _gravity columns for accelerometer axes."""
    nyq = FS / 2
    b, a = signal.butter(order, cutoff / nyq, btype="high")
    df = df.copy()
    for ax in ACC_AXES:
        if ax in df.columns:
            df[ax + "_body"] = signal.filtfilt(b, a, df[ax].values)
            df[ax + "_gravity"] = df[ax] - df[ax + "_body"]
    return df


def butter_lowpass_filter(df, cutoff=LP_CUTOFF, order=LP_ORDER):
    """Low-pass anti-aliasing filter on all sensor axes."""
    nyq = FS / 2
    b, a = signal.butter(order, cutoff / nyq, btype="low")
    df = df.copy()
    sensor_axes = [c for c in df.columns if c in ALL_AXES]
    if sensor_axes:
        filtered = signal.filtfilt(b, a, df[sensor_axes].values, axis=0)
        df[sensor_axes] = filtered
    return df


# ═══════════════════════════════════════════════════════════════════════════
# 3. Windowing
# ═══════════════════════════════════════════════════════════════════════════

def sliding_window(df, window_samples=None, overlap=None,
                   label_col="label", subject_col="subject_id"):
    """Segment continuous signal into sliding windows.
    Returns arrays of windows (n_windows, window_samples, n_channels),
    labels, and subject_ids."""
    if window_samples is None:
        window_samples = WINDOW_SAMPLES
    if overlap is None:
        overlap = OVERLAP

    step = int(window_samples * (1 - overlap))
    n = len(df)
    if n < window_samples:
        return [], np.array([]), np.array([])

    # Identify sensor columns (exclude metadata)
    meta_cols = {label_col, subject_col, "timestamp"}
    sensor_cols = [c for c in df.columns if c not in meta_cols
                   and not c.endswith("_body") and not c.endswith("_gravity")
                   and c in ALL_AXES]

    windows = []
    labels = []
    subjects = []

    for start in range(0, n - window_samples + 1, step):
        end = start + window_samples
        win = df.iloc[start:end][sensor_cols].values.astype(np.float32)
        windows.append(win)
        labels.append(int(df.iloc[start:end][label_col].mode().iloc[0]))
        subjects.append(str(df.iloc[start:end][subject_col].iloc[0]))

    if not windows:
        return [], np.array([]), np.array([])

    return np.array(windows), np.array(labels), np.array(subjects)


# ═══════════════════════════════════════════════════════════════════════════
# 4. Full preprocessing pipeline (per trial)
# ═══════════════════════════════════════════════════════════════════════════

def preprocess_trial(df, calib, trim_sec=TRIM_SEC):
    """Preprocess a single trial: calibrate → trim → gravity → filter."""
    df = apply_calibration(df, calib)
    df = trim_trial_edges(df, trim_sec)
    if len(df) < WINDOW_SAMPLES:
        return None  # too short after trimming
    df = remove_gravity(df)
    df = butter_lowpass_filter(df)
    return df


def build_preprocessing_pipeline():
    """Build a sklearn Pipeline for standardization.
    Fit on training windows only to prevent data leakage.
    This pipeline is applied AFTER feature extraction (D4-D6),
    but the scaler is defined here for architectural clarity."""
    return Pipeline([
        ("scaler", StandardScaler()),
    ])


# ═══════════════════════════════════════════════════════════════════════════
# 5. Batch processing
# ═══════════════════════════════════════════════════════════════════════════

def load_raw_files(subject_id):
    """Load all raw CSV files for a subject.
    Returns list of (filename, DataFrame) tuples."""
    subj_dir = RAW_DIR / subject_id
    if not subj_dir.exists():
        print(f"  WARNING: {subj_dir} not found, skipping {subject_id}")
        return []

    files = sorted(subj_dir.glob("*.csv"))
    trials = []
    for fp in files:
        try:
            df = pd.read_csv(fp)
            # Ensure required columns exist
            required = ["ax", "ay", "az", "gx", "gy", "gz", "label", "subject_id"]
            missing = [c for c in required if c not in df.columns]
            if missing:
                print(f"  WARNING: {fp.name} missing columns: {missing}, skipping")
                continue
            trials.append((fp.stem, df))
        except Exception as e:
            print(f"  ERROR reading {fp.name}: {e}")
    return trials


def process_all_subjects(output_dir=None):
    """Process all subjects in data/raw/ and generate windowed dataset."""
    if output_dir is None:
        output_dir = WINDOWED_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    calib = load_calib_params()

    subject_dirs = sorted(d for d in RAW_DIR.iterdir()
                          if d.is_dir() and d.name.startswith("S"))
    if not subject_dirs:
        print("No subject directories found in data/raw/")
        print("Run: python calib/capture_activity.py COM7 S01")
        return

    print(f"Subjects found: {[d.name for d in subject_dirs]}")
    print(f"Calibration: {'loaded' if calib else 'identity (none found)'}")
    print()

    all_windows = []
    all_labels = []
    all_subjects = []
    stats = {}

    for subj_dir in subject_dirs:
        subject_id = subj_dir.name
        print(f"Processing {subject_id}...")

        trials = load_raw_files(subject_id)
        if not trials:
            print(f"  No valid trials, skipping")
            continue

        n_trials = 0
        n_windows = 0
        labels_seen = set()

        for fname, df in trials:
            # Keep original for comparison plot
            df_raw_sample = df.copy()

            # Preprocess
            df_processed = preprocess_trial(df, calib)
            if df_processed is None:
                print(f"  {fname}: too short after trimming, skipped")
                continue

            # Window
            windows, labels, subjects = sliding_window(df_processed)
            if len(windows) == 0:
                print(f"  {fname}: no windows (trial too short), skipped")
                continue

            all_windows.append(windows)
            all_labels.append(labels)
            all_subjects.append(subjects)

            n_trials += 1
            n_windows += len(windows)
            for lb in np.unique(labels):
                labels_seen.add(ACTIVITIES.get(int(lb), str(lb)))

            # Generate comparison plot for first trial of each activity
            activity_name = fname.split("_")[1] if "_" in fname else "unknown"
            trial_num = fname.split("_")[-1] if "_" in fname else "00"
            if trial_num == "01" or trial_num == "1":
                _save_comparison_plot(df_raw_sample, df_processed, subject_id, fname)

        stats[subject_id] = {
            "trials": n_trials,
            "windows": n_windows,
            "activities": sorted(labels_seen),
        }
        print(f"  {n_trials} trials → {n_windows} windows, "
              f"activities: {labels_seen}")

    if not all_windows:
        print("\nNo windows generated. Check raw data.")
        return

    # Concatenate all windows
    all_windows = np.concatenate(all_windows, axis=0)
    all_labels = np.concatenate(all_labels, axis=0)
    all_subjects = np.concatenate(all_subjects, axis=0)

    print(f"\n{'=' * 60}")
    print(f"WINDOWED DATASET SUMMARY")
    print(f"{'=' * 60}")
    print(f"  Total windows:  {len(all_windows)}")
    print(f"  Window shape:   {all_windows.shape}  (samples x time_steps x channels)")
    print(f"  Unique labels:  {sorted(np.unique(all_labels).astype(int))}")
    print(f"  Unique subjects: {sorted(np.unique(all_subjects))}")
    for subj, st in stats.items():
        print(f"    {subj}: {st['trials']} trials, {st['windows']} windows, "
              f"activities={st['activities']}")

    # Save as .npz (compact, preserves shape for DL)
    npz_path = output_dir / "windowed_dataset.npz"
    np.savez_compressed(
        npz_path,
        windows=all_windows,
        labels=all_labels,
        subjects=all_subjects,
        channels=np.array(ALL_AXES[:all_windows.shape[2]]),
        fs=FS,
        window_sec=FS * WINDOW_SAMPLES / FS,
    )
    print(f"\n  Saved: {npz_path} ({npz_path.stat().st_size / 1024:.0f} KB)")

    # Save as .csv (flat format for inspection / sklearn)
    # Flatten: each row = [subject_id, label, win_idx, ch0_t0, ch0_t1, ..., chN_t127]
    csv_path = output_dir / "windowed_dataset.csv"
    n_windows, n_steps, n_channels = all_windows.shape
    flat_windows = all_windows.reshape(n_windows, n_steps * n_channels)
    flat_cols = [f"{ch}_{t}" for ch in ALL_AXES[:n_channels] for t in range(n_steps)]

    df_flat = pd.DataFrame(flat_windows, columns=flat_cols)
    df_flat.insert(0, "label", all_labels.astype(int))
    df_flat.insert(0, "subject_id", all_subjects)

    df_flat.to_csv(csv_path, index=False)
    print(f"  Saved: {csv_path} ({csv_path.stat().st_size / 1024:.0f} KB)")

    # Save summary stats
    stats_path = output_dir / "windowed_stats.json"
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump({
            "total_windows": int(len(all_windows)),
            "window_shape": list(all_windows.shape),
            "channels": ALL_AXES[:n_channels],
            "unique_labels": sorted(np.unique(all_labels).astype(int).tolist()),
            "unique_subjects": sorted(np.unique(all_subjects).tolist()),
            "per_subject": {k: {"trials": v["trials"], "windows": v["windows"]}
                            for k, v in stats.items()},
            "params": {
                "fs": FS,
                "window_samples": WINDOW_SAMPLES,
                "overlap": OVERLAP,
                "trim_sec": TRIM_SEC,
                "gravity_cutoff_hz": GRAVITY_CUTOFF,
                "lp_cutoff_hz": LP_CUTOFF,
            },
        }, f, indent=2, ensure_ascii=False)
    print(f"  Saved: {stats_path}")

    return all_windows, all_labels, all_subjects, stats


# ═══════════════════════════════════════════════════════════════════════════
# 6. Visualization
# ═══════════════════════════════════════════════════════════════════════════

def _save_comparison_plot(df_raw, df_processed, subject_id, fname):
    """Generate before/after preprocessing waveform comparison."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    # Use a short segment (middle 5 seconds) for clarity
    n_show = int(FS * 5)
    mid_start = max(0, len(df_raw) // 2 - n_show // 2)
    mid_end = mid_start + n_show

    if mid_end > len(df_raw):
        mid_start = max(0, len(df_raw) - n_show)
        mid_end = len(df_raw)

    raw_seg = df_raw.iloc[mid_start:mid_end]
    proc_seg = df_processed.iloc[mid_start:mid_end] if mid_end <= len(df_processed) else df_processed

    t = np.arange(len(raw_seg)) / FS

    fig, axes = plt.subplots(4, 1, figsize=(14, 10), sharex=True)

    # Row 1: Accelerometer
    ax = axes[0]
    for i, axis_name in enumerate(ACC_AXES):
        if axis_name in raw_seg.columns:
            ax.plot(t, raw_seg[axis_name].values, alpha=0.4, linewidth=0.5,
                    color=f"C{i}", linestyle="--")
            if axis_name in proc_seg.columns:
                ax.plot(t, proc_seg[axis_name].values[:len(t)], linewidth=0.8,
                        color=f"C{i}", label=f"{axis_name} cal")
    ax.set_ylabel("Accel (m/s^2)")
    ax.legend(loc="upper right", fontsize=7, ncol=3)
    ax.grid(True, alpha=0.3)

    # Row 2: Gyroscope
    ax = axes[1]
    for i, axis_name in enumerate(GYRO_AXES):
        if axis_name in raw_seg.columns:
            ax.plot(t, raw_seg[axis_name].values, alpha=0.4, linewidth=0.5,
                    color=f"C{i}", linestyle="--")
            if axis_name in proc_seg.columns:
                ax.plot(t, proc_seg[axis_name].values[:len(t)], linewidth=0.8,
                        color=f"C{i}", label=f"{axis_name} cal")
    ax.set_ylabel("Gyro (deg/s)")
    ax.legend(loc="upper right", fontsize=7, ncol=3)
    ax.grid(True, alpha=0.3)

    # Row 3: Magnetometer
    ax = axes[2]
    for i, axis_name in enumerate(MAG_AXES):
        if axis_name in raw_seg.columns:
            ax.plot(t, raw_seg[axis_name].values, alpha=0.4, linewidth=0.5,
                    color=f"C{i}", linestyle="--")
            if axis_name in proc_seg.columns:
                ax.plot(t, proc_seg[axis_name].values[:len(t)], linewidth=0.8,
                        color=f"C{i}", label=f"{axis_name} cal")
    ax.set_ylabel("Mag (uT)")
    ax.legend(loc="upper right", fontsize=7, ncol=3)
    ax.grid(True, alpha=0.3)

    # Row 4: Acceleration magnitude (gravity-removed vs raw)
    ax = axes[3]
    if all(c in raw_seg.columns for c in ACC_AXES):
        raw_mag = np.sqrt((raw_seg[list(ACC_AXES)].values ** 2).sum(axis=1))
        ax.plot(t, raw_mag, alpha=0.4, linewidth=0.5, color="gray", linestyle="--",
                label="raw |a|")
    body_cols = [c for c in [ax + "_body" for ax in ACC_AXES] if c in proc_seg.columns]
    if body_cols:
        body_mag = np.sqrt((proc_seg[body_cols].values ** 2).sum(axis=1))
        ax.plot(t, body_mag[:len(t)], linewidth=1.0, color="C0", label="body |a| (gravity removed)")
    ax.set_ylabel("|a| (m/s^2)")
    ax.set_xlabel("Time (s)")
    ax.legend(loc="upper right", fontsize=7)
    ax.grid(True, alpha=0.3)

    fig.suptitle(f"Preprocessing: {fname} ({subject_id}) — dashed=raw, solid=calibrated+filtered",
                 fontsize=11, fontweight="bold")
    fig.tight_layout()

    out_path = REPORTS_DIR / f"preprocess_{subject_id}_{fname}.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_preprocessing_overview():
    """Generate a summary overview plot of the preprocessing pipeline."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    fig, axes = plt.subplots(2, 3, figsize=(16, 8))
    fig.suptitle("Preprocessing Pipeline: Signal Transformation Overview",
                 fontsize=13, fontweight="bold")

    stages = [
        ("Raw (uncalibrated)", "raw"),
        ("After Calibration", "calibrated"),
        ("After Gravity Removal", "body"),
        ("After Low-pass Filter", "filtered"),
        ("Sliding Windows", "windows"),
        ("Standardized (z-score)", "scaled"),
    ]

    for ax, (title, stage) in zip(axes.flat, stages):
        ax.set_title(title, fontsize=10)
        ax.set_xlabel("Time (s)")
        ax.set_ylabel("Amplitude")
        ax.text(0.5, 0.5, f"[{stage}]\n(see per-trial plots\nfor detail)",
                transform=ax.transAxes, ha="center", va="center",
                fontsize=9, color="gray")
        ax.grid(True, alpha=0.2)

    fig.tight_layout()
    out_path = REPORTS_DIR / "preprocess_overview.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Overview: {out_path}")


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=== D3: Preprocessing Pipeline ===\n")

    result = process_all_subjects()

    if result is not None:
        windows, labels, subjects, stats = result
        plot_preprocessing_overview()
        print("\n=== D3 preprocessing complete ===")
        print(f"Next: python src/features.py")
    else:
        print("\nNo data to process. Options:")
        print("  1. python calib/generate_demo_data.py  (generate demo data)")
        print("  2. python calib/capture_activity.py COM7 S01  (collect real data)")
