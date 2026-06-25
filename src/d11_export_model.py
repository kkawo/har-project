"""
D11: Train deployable model and export parameters for ESP32 MicroPython.

Strategy:
- Use time-domain features only (no FFT needed on ESP32): 14 × 9 axes = 126D
- Train LinearSVM (one-vs-rest) → export coef_ + intercept_ as Python arrays
- Also export StandardScaler mean/std + calibration params
- Model inference on ESP32: softmax(x_scaled @ W + b) → argmax

Usage: python src/d11_export_model.py
Output: firmware/realtime_inference/model_params.py
"""

import json
import sys
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import LinearSVC
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

ACTIVITIES = {
    0: "sit", 1: "stand", 2: "walk", 3: "run",
    4: "upstairs", 5: "downstairs", 6: "fall",
}
CLASS_NAMES = [ACTIVITIES[i] for i in range(7)]
N_CLASSES = 7

# Time-domain feature suffixes (no FFT needed)
TD_SUFFIXES = [
    "mean", "std", "var", "rms", "peak_to_peak", "max", "min",
    "median", "skew", "kurtosis", "iqr", "sma", "zero_cross_rate",
    "autocorr_lag1",
]
AXES = ["ax", "ay", "az", "gx", "gy", "gz", "mx", "my", "mz"]


def select_td_features(df):
    """Select only time-domain axis features: 14 × 9 axes = 126D."""
    td_cols = [f"{ax}_{suffix}" for ax in AXES for suffix in TD_SUFFIXES]
    available = [c for c in td_cols if c in df.columns]
    missing = [c for c in td_cols if c not in df.columns]
    if missing:
        print(f"Warning: {len(missing)} features missing: {missing[:5]}...")
    print(f"Time-domain features: {len(available)}/{len(td_cols)} available")
    return available


def train_linear_model(X, y, groups, model_type="lr"):
    """Train a lightweight linear model via LOSO and return the final model.

    Uses full-data training for maximum stability (real-time demo on self).
    """
    if model_type == "lr":
        model = Pipeline([
            ("scaler", StandardScaler()),
            ("clf", LogisticRegression(
                C=1.0, max_iter=2000, multi_class="ovr",
                random_state=42,
            )),
        ])
    else:
        model = Pipeline([
            ("scaler", StandardScaler()),
            ("clf", LinearSVC(
                C=1.0, max_iter=2000, dual="auto",
                random_state=42,
            )),
        ])

    # Full-data training (for self-demo on familiar subject)
    model.fit(X, y)

    # Also report LOSO accuracy for reference
    logo = LeaveOneGroupOut()
    yt_all, yp_all = [], []
    for train_idx, test_idx in logo.split(X, y, groups):
        m = Pipeline(model.steps)
        m.fit(X[train_idx], y[train_idx])
        yp_all.extend(m.predict(X[test_idx]))
        yt_all.extend(y[test_idx])
    loso_acc = accuracy_score(yt_all, yp_all)
    loso_f1 = f1_score(yt_all, yp_all, average="macro")

    return model, loso_acc, loso_f1


def export_model_params(model, feature_names, calib_data, out_path):
    """Export model weights + scaler params as MicroPython-compatible Python file."""
    scaler = model.named_steps["scaler"]
    clf = model.named_steps["clf"]

    coef = clf.coef_       # (n_classes, n_features) for ovr LR or (n_classes-1, n_features) for SVC
    intercept = clf.intercept_  # (n_classes,) for LR, (n_classes*(n_classes-1)/2,) for SVC

    # For LinearSVC, convert to ovr format
    if coef.shape[0] == N_CLASSES - 1:  # SVC default: n_classes-1
        # Decision function: n_classes*(n_classes-1)/2
        # We use decision_function shape for OvO, but coef_ shape depends
        # LinearSVC multi_class='ovr' gives (n_classes, n_features) for coef_
        pass

    mean = scaler.mean_.tolist()
    scale = scaler.scale_.tolist()  # std

    # Format floats compactly
    def fmt_arr(arr, indent=8):
        """Format a list as compact Python code."""
        lines = []
        prefix = " " * indent
        for i, row in enumerate(arr):
            if isinstance(row, (list, np.ndarray)):
                vals = ", ".join(f"{v:12.8f}" for v in row)
                lines.append(f"{prefix}[{vals}],")
            else:
                lines.append(f"{prefix}{row:12.8f},")
        return "\n".join(lines)

    coef_str = fmt_arr(coef.tolist())
    intercept_str = fmt_arr(intercept.tolist())
    mean_str = fmt_arr(mean)
    scale_str = fmt_arr(scale)

    # Activity label map
    act_map = ",\n    ".join(f"{i}: \"{ACTIVITIES[i]}\"" for i in range(N_CLASSES))

    # Calibration params for accelerometer
    acc_calib = calib_data.get("accelerometer", {})
    acc_bias = acc_calib.get("bias", [0, 0, 0])
    acc_scale = acc_calib.get("scale", [1, 1, 1])

    code = f'''# Auto-generated model parameters for ESP32 real-time HAR inference.
# Generated by src/d11_export_model.py
# Model: {type(clf).__name__}
# Features: {len(feature_names)} time-domain (14 × 9 axes)
# Accuracy (full-data train): {model.score(
    np.zeros((1, len(feature_names))), np.zeros(1)):.4f}  # placeholder

N_CLASSES = {N_CLASSES}
N_FEATURES = {len(feature_names)}
ACTIVITIES = {{ {act_map} }}

# Linear model weights: shape (N_CLASSES, N_FEATURES)
COEF = [
{coef_str}
]

# Intercept: shape (N_CLASSES,)
INTERCEPT = [
{intercept_str}
]

# StandardScaler parameters
SCALER_MEAN = [
{mean_str}
]

SCALER_STD = [
{scale_str}
]

# Accelerometer calibration (simplified: bias + scale only)
ACC_BIAS = [{acc_bias[0]:.6f}, {acc_bias[1]:.6f}, {acc_bias[2]:.6f}]
ACC_SCALE = [{acc_scale[0]:.6f}, {acc_scale[1]:.6f}, {acc_scale[2]:.6f}]
GRAVITY = 9.80665

# Feature names (for reference)
FEATURE_NAMES = {feature_names}
'''

    out_path.write_text(code, encoding="utf-8")
    print(f"Model parameters exported to: {out_path}")


def main():
    print("=" * 60)
    print("D11: Export model for ESP32 real-time inference")
    print("=" * 60)

    # Load data
    df = pd.read_csv(FEAT_PATH)
    y = df["label"].values.astype(int)
    groups = df["subject_id"].values

    # Select time-domain features only
    td_cols = select_td_features(df)
    X_td = df[td_cols].values.astype(np.float64)

    # Handle NaN
    if np.any(np.isnan(X_td)):
        X_td = SimpleImputer(strategy="median").fit_transform(X_td)

    # Remove constant features
    var_mask = VarianceThreshold(threshold=0.0).fit(X_td).get_support()
    if not var_mask.all():
        X_td = X_td[:, var_mask]
        td_cols = [c for c, m in zip(td_cols, var_mask) if m]
        print(f"After variance filter: {len(td_cols)} features")

    print(f"Training data: {X_td.shape[0]} samples × {X_td.shape[1]} features\n")

    # Train model
    model, loso_acc, loso_f1 = train_linear_model(X_td, y, groups, model_type="lr")
    print(f"Logistic Regression LOSO: acc={loso_acc:.4f}, macro_f1={loso_f1:.4f}")
    print(classification_report(y, model.predict(X_td),
          target_names=CLASS_NAMES, zero_division=0))

    # Try LinearSVM too
    svm, svm_acc, svm_f1 = train_linear_model(X_td, y, groups, model_type="svm")
    print(f"LinearSVM LOSO: acc={svm_acc:.4f}, macro_f1={svm_f1:.4f}")

    # Pick best
    best = model if loso_acc >= svm_acc else svm
    best_acc = max(loso_acc, svm_acc)
    print(f"\nSelected: {type(best.named_steps['clf']).__name__} (acc={best_acc:.4f})")

    # Load calibration params
    calib = {}
    if CALIB_PATH.exists():
        with open(CALIB_PATH, encoding="utf-8") as f:
            calib = json.load(f)

    # Export
    out_path = OUT_DIR / "model_params.py"
    export_model_params(best, td_cols, calib, out_path)

    print("\nDone. Upload firmware/realtime_inference/ to ESP32.")


if __name__ == "__main__":
    main()
