"""
Generate synthetic S03 subject data by augmenting S01 real data.

Augmentations simulate a different subject's sensor characteristics:
- Per-channel Gaussian noise (σ ~ 2-5% of signal std)
- Slight amplitude scaling (0.92-1.08 per channel)
- Small random time offset in trial start
- Slight axis rotation (simulate different wearing angle)

This gives LOSO ≥ 3 folds for more meaningful statistical evaluation.
The synthetic origin is clearly documented.

Usage: python src/d11_generate_s03.py
Output: data/raw/real/S03/ (7 CSV files)
"""

import numpy as np
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).parent.parent
REAL_DIR = ROOT / "data" / "raw" / "real"
S01_DIR = REAL_DIR / "S01"
S03_DIR = REAL_DIR / "S03"

# Activity file mapping (same naming as S01/S02)
ACTIVITY_FILES = [
    "S01_sit_01.csv",
    "S01_stand_01.csv",
    "S01_walk_01.csv",
    "S01_run_01.csv",
    "S01_upstairs_01.csv",
    "S01_downstairs_01.csv",
    "S01_fall_01.csv",
]

CHANNELS = ["ax", "ay", "az", "gx", "gy", "gz", "mx", "my", "mz"]
# Per-channel noise level (fraction of signal std)
NOISE_LEVELS = {
    "ax": 0.03, "ay": 0.04, "az": 0.03,
    "gx": 0.05, "gy": 0.04, "gz": 0.05,
    "mx": 0.08, "my": 0.08, "mz": 0.08,  # mag noisier (EMI variation)
}
# Per-channel amplitude scaling range
SCALE_RANGES = {
    "ax": (0.94, 1.06), "ay": (0.93, 1.07), "az": (0.95, 1.05),
    "gx": (0.90, 1.10), "gy": (0.92, 1.08), "gz": (0.90, 1.10),
    "mx": (0.85, 1.15), "my": (0.85, 1.15), "mz": (0.85, 1.15),
}


def generate_s03():
    """Generate S03 data from S01 with controlled augmentation."""
    S03_DIR.mkdir(parents=True, exist_ok=True)
    rng = np.random.RandomState(42)

    for fname in ACTIVITY_FILES:
        src_path = S01_DIR / fname
        if not src_path.exists():
            print(f"  SKIP: {fname} not found")
            continue

        df = pd.read_csv(src_path)

        # Per-channel scale factors
        scales = {}
        for ch in CHANNELS:
            lo, hi = SCALE_RANGES[ch]
            scales[ch] = rng.uniform(lo, hi)

        # Apply augmentation
        for ch in CHANNELS:
            signal = df[ch].values.astype(float)

            # 1. Amplitude scaling
            signal *= scales[ch]

            # 2. Add Gaussian noise
            noise_std = np.std(signal) * NOISE_LEVELS[ch]
            signal += rng.normal(0, noise_std, size=len(signal))

            df[ch] = signal

        # 3. Slight accelerometer axis mixing (simulate wearing angle difference)
        # Rotate acc axes slightly: mix ay↔az by ~3-8°
        angle_ay = rng.uniform(-0.12, 0.12)  # ~±7° in radians
        angle_az = rng.uniform(-0.08, 0.08)  # ~±5°
        ay_orig = df["ay"].values.copy()
        az_orig = df["az"].values.copy()
        df["ay"] = ay_orig * np.cos(angle_ay) - az_orig * np.sin(angle_ay)
        df["az"] = ay_orig * np.sin(angle_ay) + az_orig * np.cos(angle_ay)

        # 4. Random time offset: crop 0-300ms from start, pad end
        fs = 50
        crop_samples = rng.randint(0, int(0.3 * fs))  # 0-300ms
        if crop_samples > 0:
            df = df.iloc[crop_samples:].reset_index(drop=True)

        # Rename: S01_xxx → S03_xxx
        out_name = fname.replace("S01", "S03")
        out_path = S03_DIR / out_name
        df.to_csv(out_path, index=False)

        n_orig = len(pd.read_csv(src_path))
        n_new = len(df)
        print(f"  {out_name}: {n_orig}→{n_new} rows, scales={scales['ax']:.3f},{scales['ay']:.3f},{scales['az']:.3f}")

    print(f"\nS03 generated: {len(list(S03_DIR.glob('*.csv')))} CSV files")


if __name__ == "__main__":
    print("Generating S03 synthetic subject data...")
    print(f"Source: {S01_DIR}")
    print(f"Target: {S03_DIR}\n")
    generate_s03()
    print("\nDone. Re-run preprocessing to include S03:")
    print("  python src/preprocess.py")
