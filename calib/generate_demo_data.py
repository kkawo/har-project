"""Generate demo calibration data and run full D2 pipeline.
Produces: calib_params.json, comparison charts, sample raw/calibrated CSVs.
"""
import sys, json
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

import numpy as np
import pandas as pd
from pathlib import Path
from calib.calibrate import (
    six_position_calibrate, ellipsoid_fit, allan_variance_analysis,
    apply_accel_calibration, apply_mag_calibration,
    plot_calibration_comparison, plot_allan, generate_calib_params,
    SIX_POS_NAMES, SIX_POS_EXPECTED,
)

ROOT = Path(__file__).parent.parent
REPORTS_DIR = ROOT / "reports" / "figures"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

np.random.seed(42)
G = 9.80665  # Fuzhou gravity ~9.79, using standard

print("=== Generating demo calibration data ===\n")

# ═══════════════════════════════════════════════════════════════════════
# 1. Six-position accelerometer data
# ═══════════════════════════════════════════════════════════════════════

true_bias = np.array([0.12, -0.08, 0.25])   # m/s^2 (typical MEMS offset)
true_scale = np.array([0.993, 1.007, 0.989]) # scale factor errors ~1%

raw_sixpos = {}
for i, name in enumerate(SIX_POS_NAMES):
    expected = SIX_POS_EXPECTED[i] * G
    noise = np.random.normal(0, 0.015, (200, 3))
    raw = (expected / true_scale) + true_bias + noise
    raw_sixpos[name] = raw

raw_all = np.concatenate(list(raw_sixpos.values()), axis=0)

accel_calib = six_position_calibrate(np.array(
    [raw_sixpos[n] for n in SIX_POS_NAMES]
), g=G)

calibrated_all = apply_accel_calibration(raw_all, accel_calib)
ideal_all = np.concatenate([np.tile(e * G, (200, 1)) for e in SIX_POS_EXPECTED], axis=0)

print(f"Accel bias:    true={true_bias}  ->  calibrated={np.round(accel_calib['bias'], 4)}")
print(f"Accel scale:   true={true_scale}  ->  calibrated={np.round(accel_calib['scale'], 4)}")
bias_err = np.abs(np.array(accel_calib['bias']) - true_bias)
scale_err = np.abs(np.array(accel_calib['scale']) - true_scale)
print(f"  bias error: {np.round(bias_err, 5)} m/s^2, scale error: {np.round(scale_err, 5)}")

plot_calibration_comparison(
    raw_all, calibrated_all,
    "Accelerometer Calibration: Six-Position Before/After",
    ["ax (m/s^2)", "ay (m/s^2)", "az (m/s^2)"],
    save_path=REPORTS_DIR / "accel_calib_comparison.png",
)
print("  -> reports/figures/accel_calib_comparison.png")

# Per-axis error before/after
for i, ax in enumerate(["X", "Y", "Z"]):
    raw_rmse = np.sqrt(np.mean((raw_all[:, i] - ideal_all[:, i])**2))
    cal_rmse = np.sqrt(np.mean((calibrated_all[:, i] - ideal_all[:, i])**2))
    print(f"  {ax}-axis RMSE: {raw_rmse:.4f} -> {cal_rmse:.4f} m/s^2")

# ═══════════════════════════════════════════════════════════════════════
# 2. Magnetometer ellipsoid data
# ═══════════════════════════════════════════════════════════════════════

true_hard = np.array([12.0, -8.5, 5.3])  # uT
true_field = 45.0  # uT (Fuzhou ~45uT @ ~26degN)

# Generate points on sphere, apply soft iron + hard iron distortion
S = np.array([[1.08, 0.04, 0.02],
              [0.04, 0.93, -0.03],
              [0.02, -0.03, 1.05]])  # soft iron matrix

n_mag = 800
phi = np.random.uniform(0, 2 * np.pi, n_mag)
theta = np.random.uniform(0, np.pi, n_mag)
sphere = np.column_stack([
    np.sin(theta) * np.cos(phi),
    np.sin(theta) * np.sin(phi),
    np.cos(theta),
]) * true_field

mag_raw = sphere @ S.T + true_hard + np.random.normal(0, 0.5, (n_mag, 3))

mag_calib = ellipsoid_fit(mag_raw, reference_field=true_field)
mag_calibrated = apply_mag_calibration(mag_raw, mag_calib)

print(f"\nMag hard iron:  true={true_hard}  ->  fitted={np.round(mag_calib['hard_iron'], 2)}")
print(f"Mag field mag:  true={true_field}  ->  fitted={mag_calib['field_magnitude']:.1f}")

mag_raw_norm = np.linalg.norm(mag_raw - true_hard, axis=1)
mag_cal_norm = np.linalg.norm(mag_calibrated, axis=1)
print(f"  Raw norm std:    {np.std(mag_raw_norm):.3f} uT")
print(f"  Calibrated norm std: {np.std(mag_cal_norm):.3f} uT")

plot_calibration_comparison(
    mag_raw, mag_calibrated,
    "Magnetometer Calibration: Ellipsoid Fit Before/After",
    ["mx (uT)", "my (uT)", "mz (uT)"],
    save_path=REPORTS_DIR / "mag_calib_comparison.png",
)
print("  -> reports/figures/mag_calib_comparison.png")

# ═══════════════════════════════════════════════════════════════════════
# 3. Allan variance
# ═══════════════════════════════════════════════════════════════════════

# Simulate 10 min @ 50Hz: white noise + random walk + bias instability
t = np.arange(0, 600, 0.02)  # 10 minutes
n = len(t)

# Generate realistic noise for each axis
def gen_noise(arw_level, bias_inst):
    white = np.random.normal(0, arw_level, n)
    rw = np.cumsum(np.random.normal(0, bias_inst * 0.02, n))
    return white + rw

accel_static = np.column_stack([
    gen_noise(0.003, 0.00005),  # X
    gen_noise(0.003, 0.00005),  # Y
    gen_noise(0.003, 0.00005),  # Z
])
gyro_static = np.column_stack([
    gen_noise(0.05, 0.0005),   # X (deg/s)
    gen_noise(0.05, 0.0005),   # Y
    gen_noise(0.05, 0.0005),   # Z
])

allan_accel = allan_variance_analysis(accel_static, fs=50)
allan_gyro = allan_variance_analysis(gyro_static, fs=50)

plot_allan(allan_accel["tau"], allan_accel["adev_per_axis"],
           "Accelerometer Allan Deviation", REPORTS_DIR / "allan_accel.png")
plot_allan(allan_gyro["tau"], allan_gyro["adev_per_axis"],
           "Gyroscope Allan Deviation", REPORTS_DIR / "allan_gyro.png")
print("  -> reports/figures/allan_accel.png")
print("  -> reports/figures/allan_gyro.png")

# ═══════════════════════════════════════════════════════════════════════
# 4. Generate calib_params.json
# ═══════════════════════════════════════════════════════════════════════

# Gyro bias from static segment mean
gyro_bias = np.mean(gyro_static[:500], axis=0)  # first 10s

params = generate_calib_params(accel_calib, mag_calib, allan_accel, allan_gyro)
params["gyroscope"]["bias"] = gyro_bias.tolist()
params["calibration_date"] = "2026-06-16"
params["operator"] = "李宝平"
params["notes"] = (
    "Demo calibration using synthetic data. "
    "Real calibration to be performed when hardware arrives (PCB D3-D5 delivery). "
    "Accel: six-position LSTSQ, RMSE improved from ~0.3 to <0.03 m/s^2. "
    "Mag: ellipsoid fit SVD, norm std reduced from ~3 to <1 uT. "
    "Gyro: static bias only, no turntable scale calibration."
)

with open(ROOT / "calib" / "calib_params.json", "w", encoding="utf-8") as f:
    json.dump(params, f, indent=2, ensure_ascii=False)
print("\n  -> calib/calib_params.json updated")

# ═══════════════════════════════════════════════════════════════════════
# 5. Generate sample raw/calibrated CSVs
# ═══════════════════════════════════════════════════════════════════════

# Simulate 10s of walking data @ 50Hz
n_samples = 500
t_sample = np.arange(n_samples) * 20  # ms

f_walk = 1.8  # Hz walking frequency
# Simulate gait-like acceleration
ax = 0.5 * np.sin(2 * np.pi * f_walk * t_sample / 1000) + np.random.normal(0, 0.05, n_samples)
ay = 1.2 * np.sin(2 * np.pi * f_walk * t_sample / 1000 + 0.3) + np.random.normal(0, 0.08, n_samples)
az = 0.8 * np.sin(2 * np.pi * f_walk * 2 * t_sample / 1000) + G + np.random.normal(0, 0.06, n_samples)

gx = 15 * np.sin(2 * np.pi * f_walk * t_sample / 1000) + np.random.normal(0, 2, n_samples)
gy = 20 * np.sin(2 * np.pi * f_walk * t_sample / 1000 + 0.6) + np.random.normal(0, 2, n_samples)
gz = 10 * np.cos(2 * np.pi * f_walk * t_sample / 1000) + np.random.normal(0, 1.5, n_samples)

mx = 20 * np.sin(2 * np.pi * 0.5 * t_sample / 1000) + 15 + np.random.normal(0, 1, n_samples)
my = 25 * np.cos(2 * np.pi * 0.5 * t_sample / 1000) - 8 + np.random.normal(0, 1, n_samples)
mz = 10 * np.sin(2 * np.pi * 0.3 * t_sample / 1000) + 5 + np.random.normal(0, 0.8, n_samples)

# Raw data (before calibration)
df_raw = pd.DataFrame({
    "timestamp": t_sample,
    "ax": ax * true_scale[0] + true_bias[0],
    "ay": ay * true_scale[1] + true_bias[1],
    "az": az * true_scale[2] + true_bias[2],
    "gx": gx + gyro_bias[0],
    "gy": gy + gyro_bias[1],
    "gz": gz + gyro_bias[2],
    "mx": mx * S[0, 0] + my * S[0, 1] + mz * S[0, 2] + true_hard[0],
    "my": mx * S[1, 0] + my * S[1, 1] + mz * S[1, 2] + true_hard[1],
    "mz": mx * S[2, 0] + my * S[2, 1] + mz * S[2, 2] + true_hard[2],
    "label": 2,  # walk
    "subject_id": "S01",
})

for subj in ["S01", "S02", "S03"]:
    (ROOT / "data" / "raw" / subj).mkdir(parents=True, exist_ok=True)
    (ROOT / "data" / "calibrated" / subj).mkdir(parents=True, exist_ok=True)

raw_path = ROOT / "data" / "raw" / "S01" / "S01_walk_01_demo.csv"
df_raw.to_csv(raw_path, index=False)
print(f"  -> {raw_path}")

# Calibrated data
df_cal = df_raw.copy()
acc_raw = df_raw[["ax", "ay", "az"]].values
df_cal[["ax", "ay", "az"]] = apply_accel_calibration(acc_raw, params["accelerometer"])
mag_raw_arr = df_raw[["mx", "my", "mz"]].values
df_cal[["mx", "my", "mz"]] = apply_mag_calibration(mag_raw_arr, params["magnetometer"])
df_cal[["gx", "gy", "gz"]] -= gyro_bias

cal_path = ROOT / "data" / "calibrated" / "S01" / "S01_walk_01_demo.csv"
df_cal.to_csv(cal_path, index=False)
print(f"  -> {cal_path}")

# ═══════════════════════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════════════════════
print(f"""
=== D2 Calibration Pipeline Complete ===
  calib/calib_params.json         — calibration parameters (demo)
  reports/figures/accel_calib_comparison.png
  reports/figures/mag_calib_comparison.png
  reports/figures/allan_accel.png
  reports/figures/allan_gyro.png
  data/raw/S01/S01_walk_01_demo.csv     — raw sample
  data/calibrated/S01/S01_walk_01_demo.csv — calibrated sample

  Replace with real data when hardware arrives (D3-D5).
  See reports/标定报告.md for methods and quality criteria.
""")
