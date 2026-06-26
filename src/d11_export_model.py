"""
D11: Train deployable model and export parameters for ESP32 MicroPython.

Strategy:
- Use ALL non-FFT features (184: time + magnitude + correlation + composite)
  All computable on ESP32 without scipy/numpy FFT
- Train LogisticRegression (OVR, C=1.0) + export coef_ + intercept_
- Also export StandardScaler mean/std + calibration params
- ESP32 inference: standardize → dot(W, x) + b → softmax → argmax
  184 × 7 weights = 1288 multiplies → < 2ms on ESP32-S3 240MHz

Usage: python src/d11_export_model.py
Output: firmware/realtime_inference/model_params.py
"""

import json
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.base import clone
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import LeaveOneGroupOut
from sklearn.impute import SimpleImputer
from sklearn.feature_selection import VarianceThreshold
from sklearn.metrics import accuracy_score, f1_score, classification_report

ROOT = Path(__file__).parent.parent
FEAT_PATH = ROOT / "data" / "features" / "feature_matrix.csv"
CALIB_PATH = ROOT / "calib" / "calib_params.json"
OUT_DIR = ROOT / "firmware" / "realtime_inference"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Use clean data only (first 566 rows — S01+S02 without NaN contamination)
# The last 283 rows are from a corrupted S03 merge and contain NaN features
CLEAN_ROWS = 566

ACTIVITIES = {0: "sit", 1: "stand", 2: "walk", 3: "run",
              4: "upstairs", 5: "downstairs", 6: "fall"}
CLASS_NAMES = [ACTIVITIES[i] for i in range(7)]
N_CLASSES = 7

# Frequency-domain suffixes to EXCLUDE (require numpy FFT)
FFT_SUFFIXES = [
    "dominant_freq", "spectral_centroid", "spectral_entropy",
    "energy_low", "energy_mid", "energy_high",
    "bandwidth", "flatness", "rolloff", "peak_count",
]


def select_non_fft_features(df):
    """Select all features computable without FFT (184 of 294)."""
    exclude = ["label", "subject_id"]
    all_feat = [c for c in df.columns if c not in exclude]
    non_fft = [c for c in all_feat
               if not any(fft in c for fft in FFT_SUFFIXES)]
    print(f"Non-FFT features: {len(non_fft)} "
          f"(FFT excluded: {len(all_feat) - len(non_fft)})")
    return non_fft


# Exact time-domain feature names computed by ESP32 firmware
TIME_STATS = [
    "mean", "std", "var", "rms", "peak_to_peak", "max", "min",
    "median", "skew", "kurtosis", "zero_cross_rate", "sma",
    "iqr", "autocorr_lag1",
]
TIME_AXES = ["ax", "ay", "az", "gx", "gy", "gz"]  # 6ch only, no magnetometer


def select_esp32_time_features(feat_names):
    """Keep ONLY the 126 time-domain features computable on ESP32.
    The firmware computes 14 time stats x 9 axes = 126 features.
    No magnitudes, correlations, jerk, or ratios.
    """
    esp32_feats = [c for c in feat_names
                   if any(c == f"{a}_{s}" for a in TIME_AXES for s in TIME_STATS)]
    print(f"ESP32 time-only features: {len(esp32_feats)} "
          f"(excluded: {len(feat_names) - len(esp32_feats)})")
    return esp32_feats


def train_and_eval(X, y, groups):
    """Train LR and report both LOSO and full-data accuracy."""
    model = Pipeline([
        ("scaler", StandardScaler()),
        ("clf", LogisticRegression(
            C=1.0, max_iter=3000, multi_class="ovr", random_state=42,
        )),
    ])

    # Full-data training (for self-demo: user trained on their own data)
    model.fit(X, y)
    full_acc = accuracy_score(y, model.predict(X))
    full_f1 = f1_score(y, model.predict(X), average="macro")

    # LOSO (cross-subject generalization reference)
    unique_groups = set(groups)
    if len(unique_groups) >= 2:
        logo = LeaveOneGroupOut()
        yt, yp = [], []
        for train_idx, test_idx in logo.split(X, y, groups):
            m = clone(model)
            m.fit(X[train_idx], y[train_idx])
            yp.extend(m.predict(X[test_idx]))
            yt.extend(y[test_idx])
        loso_acc = accuracy_score(yt, yp)
        loso_f1 = f1_score(yt, yp, average="macro")
    else:
        loso_acc, loso_f1 = 0.0, 0.0

    return model, loso_acc, loso_f1, full_acc, full_f1


def export_model(model, feature_names, calib_data, out_path):
    """Export as MicroPython .py module."""
    scaler = model.named_steps["scaler"]
    clf = model.named_steps["clf"]
    coef = clf.coef_
    intercept = clf.intercept_
    mean = scaler.mean_.tolist()
    scale = scaler.scale_.tolist()

    # Format arrays for MicroPython
    def fmt_1d(arr):
        return ", ".join(f"{v:.8f}" for v in arr)

    def fmt_2d(rows):
        lines = []
        for row in rows:
            vals = ", ".join(f"{v:12.8f}" for v in row)
            lines.append(f"        [{vals}],")
        return "\n".join(lines)

    act_map = ",\n    ".join(f'{i}: "{ACTIVITIES[i]}"' for i in range(N_CLASSES))

    acc = calib_data.get("accelerometer", {})
    bias = acc.get("bias", [0, 0, 0])
    ascale = acc.get("scale", [1, 1, 1])

    code = f'''# Auto-generated model for ESP32 real-time HAR inference.
# Model: LogisticRegression (OVR)
# Features: {len(feature_names)} non-FFT
# See export script output for accuracy metrics.

N_CLASSES = {N_CLASSES}
N_FEATURES = {len(feature_names)}
ACTIVITIES = {{ {act_map} }}

# Weights: shape (N_CLASSES, N_FEATURES)
COEF = [
{fmt_2d(coef.tolist())}
]

# Intercept: shape (N_CLASSES,)
INTERCEPT = [{fmt_1d(intercept.tolist())}]

# StandardScaler: x_scaled = (x - mean) / std
SCALER_MEAN = [{fmt_1d(mean)}]
SCALER_STD = [{fmt_1d(scale)}]

# Accelerometer calibration
ACC_BIAS = [{bias[0]:.6f}, {bias[1]:.6f}, {bias[2]:.6f}]
ACC_SCALE = [{ascale[0]:.6f}, {ascale[1]:.6f}, {ascale[2]:.6f}]
GRAVITY = 9.80665

# Feature names for reference
FEATURE_NAMES = {feature_names}
'''
    out_path.write_text(code, encoding="utf-8")
    return len(feature_names)


def main():
    print("=" * 60)
    print("D11: Export model for ESP32 real-time inference")
    print("=" * 60)

    df = pd.read_csv(FEAT_PATH)
    # Use only clean rows (S01+S02 without NaN contamination from broken S03)
    df = df.iloc[:CLEAN_ROWS].copy()
    print(f"Using {len(df)} clean rows (S01+S02 only)")

    # Replace median with mean, IQR with 1.349*std
    # (matches MicroPython firmware which can't use sorted())
    for axis in ['ax','ay','az','gx','gy','gz','mx','my','mz',
                 'acc_mag','gyro_mag','mag_mag']:
        med_col = f'{axis}_median'
        iqr_col = f'{axis}_iqr'
        mean_col = f'{axis}_mean'
        std_col = f'{axis}_std'
        if med_col in df.columns and mean_col in df.columns:
            df[med_col] = df[mean_col]
        if iqr_col in df.columns and std_col in df.columns:
            df[iqr_col] = 1.349 * df[std_col]
    print("Applied median/IQR approximations (sorted-free)")

    y = df["label"].values.astype(int)
    groups = df["subject_id"].values

    feat_cols = select_non_fft_features(df)
    feat_cols = select_esp32_time_features(feat_cols)  # Keep only 126 ESP32-computable
    X = df[feat_cols].values.astype(np.float64)

    if np.any(np.isnan(X)):
        X = SimpleImputer(strategy="median").fit_transform(X)
    var_mask = VarianceThreshold(threshold=0.0).fit(X).get_support()
    if not var_mask.all():
        X = X[:, var_mask]
        feat_cols = [c for c, m in zip(feat_cols, var_mask) if m]
        print(f"After variance filter: {len(feat_cols)} features")

    print(f"Training: {X.shape[0]} samples × {X.shape[1]} features\n")

    model, loso_acc, loso_f1, full_acc, full_f1 = train_and_eval(X, y, groups)

    print(f"LogisticRegression (84 time-domain features, C=1.0):")
    print(f"  Full-data (self-demo): acc={full_acc:.4f}, f1={full_f1:.4f}")
    if loso_acc > 0:
        print(f"  LOSO: acc={loso_acc:.4f}, f1={loso_f1:.4f}")
    else:
        print(f"  LOSO: N/A (single subject)")
    print(f"\n  Full-data per-class:")
    print(classification_report(y, model.predict(X),
          target_names=CLASS_NAMES, zero_division=0))

    calib = {}
    if CALIB_PATH.exists():
        with open(CALIB_PATH, encoding="utf-8") as f:
            calib = json.load(f)

    out_path = OUT_DIR / "model_params.py"
    n_feat = export_model(model, feat_cols, calib, out_path)

    print(f"\nExported: {n_feat} features → {out_path}")
    print(f"Model size: ~{n_feat * N_CLASSES} weights + scaler")
    print("\nUpload firmware/realtime_inference/ to ESP32.")


if __name__ == "__main__":
    main()
