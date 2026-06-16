"""
Process MPU6050 serial calibration output → calib_params.json + charts.
Usage:
  1. Flash firmware/mpu6050_calib/mpu6050_calib.ino to ESP32
  2. Serial Monitor @ 115200, collect six-position data
  3. Save serial output as calib/raw_mpu6050_calib.txt
  4. Run: python calib/process_mpu6050_calib.py

Six-position protocol:
  Place sensor on each face, hold still, send:
    MARK +Z_down  → START → (wait 5s) → STOP
    MARK -Z_up    → START → (wait 5s) → STOP
    MARK +X_down  → START → (wait 5s) → STOP
    MARK -X_up    → START → (wait 5s) → STOP
    MARK +Y_down  → START → (wait 5s) → STOP
    MARK -Y_up    → START → (wait 5s) → STOP

Gyro static bias:
    MARK static → START → (wait 10 min) → STOP
"""
import sys, json, re
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

import numpy as np
from pathlib import Path
from calib.calibrate import (
    calibrate_accel_from_static, allan_variance_analysis,
    plot_calibration_comparison, plot_allan, generate_calib_params,
    SIX_POS_NAMES, SIX_POS_EXPECTED,
)

ROOT = Path(__file__).parent.parent
REPORTS_DIR = ROOT / "reports" / "figures"
CALIB_DIR = ROOT / "calib"
INPUT_FILE = CALIB_DIR / "raw_mpu6050_calib.txt"

# ═══════════════════════════════════════════════════════════════════════
# 1. Parse serial output
# ═══════════════════════════════════════════════════════════════════════

def parse_serial_log(filepath):
    """Parse MPU6050 calibration serial log into per-position arrays."""
    samples = []  # list of (ax, ay, az, gx, gy, gz, label)
    current_label = None

    with open(filepath, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            # Track MARK labels
            if line.startswith("# MARKED"):
                current_label = line.split("MARKED")[-1].strip()
                continue
            if line.startswith("# START"):
                parts = line.split()
                if len(parts) > 2:
                    current_label = parts[-1]
                continue

            # Skip comment lines
            if line.startswith("#"):
                continue

            # Parse CSV: sample,ax,ay,az,gx,gy,gz,label
            parts = line.split(",")
            if len(parts) >= 7:
                try:
                    ax = float(parts[1])
                    ay = float(parts[2])
                    az = float(parts[3])
                    gx = float(parts[4])
                    gy = float(parts[5])
                    gz = float(parts[6])
                    label = parts[7].strip() if len(parts) > 7 else (current_label or "")
                    samples.append((ax, ay, az, gx, gy, gz, label))
                except ValueError:
                    continue

    if not samples:
        print(f"ERROR: No valid samples found in {filepath}")
        print("Expected CSV format: sample,ax,ay,az,gx,gy,gz,label")
        return None

    samples = np.array(samples, dtype=object)
    print(f"Parsed {len(samples)} total samples")
    print(f"Labels found: {set(samples[:, 6])}")
    return samples


def group_by_label(samples):
    """Group samples by position label."""
    groups = {}
    for row in samples:
        label = str(row[6]).strip()
        if not label:
            continue
        if label not in groups:
            groups[label] = []
        groups[label].append([float(row[0]), float(row[1]), float(row[2]),
                              float(row[3]), float(row[4]), float(row[5])])
    for k in groups:
        groups[k] = np.array(groups[k])
        print(f"  {k}: {len(groups[k])} samples")
    return groups


# ═══════════════════════════════════════════════════════════════════════
# 2. Run calibration
# ═══════════════════════════════════════════════════════════════════════

G = 9.80665  # m/s^2 (Fuzhou ~26N: ~9.79, using standard)

# Map user labels to standard six-position names
LABEL_MAP = {
    "+Z_down": "+Z_down", "+z_down": "+Z_down", "Z+": "+Z_down",
    "-Z_up": "-Z_up", "-z_up": "-Z_up", "Z-": "-Z_up",
    "+X_down": "+X_down", "+x_down": "+X_down", "X+": "+X_down",
    "-X_up": "-X_up", "-x_up": "-X_up", "X-": "-X_up",
    "+Y_down": "+Y_down", "+y_down": "+Y_down", "Y+": "+Y_down",
    "-Y_up": "-Y_up", "-y_up": "-Y_up", "Y-": "-Y_up",
}


def main():
    if not INPUT_FILE.exists():
        print(f"""
Input file not found: {INPUT_FILE}

Please collect calibration data first:
  1. Flash firmware/mpu6050_calib/mpu6050_calib.ino to ESP32
  2. Open Serial Monitor @ 115200 baud
  3. For each of six positions:
       MARK +Z_down
       START
       (hold sensor still for 5+ seconds)
       STOP
     Repeat for -Z_up, +X_down, -X_up, +Y_down, -Y_up
  4. For gyro bias:
       MARK static
       START
       (leave sensor still for 10+ minutes)
       STOP
  5. Copy all serial output and save as:
       {INPUT_FILE}
  6. Re-run: python calib/process_mpu6050_calib.py
""")
        return

    # Parse
    samples = parse_serial_log(INPUT_FILE)
    if samples is None:
        return

    groups = group_by_label(samples)

    # Map to standard names
    accel_positions = {}
    static_group = None
    for label, data in groups.items():
        mapped = LABEL_MAP.get(label, None)
        if mapped and mapped in SIX_POS_NAMES:
            accel_positions[mapped] = data[:, :3]  # ax, ay, az only
        elif "static" in label.lower() or "gyro" in label.lower():
            static_group = data
        elif label.lower() in ["s", "st", "static"]:
            static_group = data

    # Check we have all six positions
    missing = [p for p in SIX_POS_NAMES if p not in accel_positions]
    if missing:
        print(f"\nWARNING: Missing positions: {missing}")
        print(f"Available: {list(accel_positions.keys())}")
        print("Will calibrate with available positions only.")
    else:
        print(f"\nAll six positions collected: {list(accel_positions.keys())}")

    if not accel_positions:
        print("ERROR: No accelerometer position data found!")
        print("Try labels like: +Z_down, -Z_up, +X_down, -X_up, +Y_down, -Y_up")
        return

    # Calibrate accelerometer
    available = list(accel_positions.keys())
    measurements = [accel_positions[p] for p in available]
    # Use subset of expected gravity vectors
    expected_subset = np.array([SIX_POS_EXPECTED[SIX_POS_NAMES.index(p)] for p in available])

    accel_calib = calibrate_accel_from_static(
        {p: accel_positions[p] for p in available}, g=G
    )
    print(f"\nAccel bias:  {np.round(accel_calib['bias'], 4)}")
    print(f"Accel scale: {np.round(accel_calib['scale'], 4)}")

    # Apply calibration and plot
    raw_all = np.concatenate([accel_positions[p] for p in available], axis=0)
    from calib.calibrate import apply_accel_calibration
    cal_all = apply_accel_calibration(raw_all, accel_calib)
    ideal_all = np.concatenate([
        np.tile(SIX_POS_EXPECTED[SIX_POS_NAMES.index(p)] * G, (len(accel_positions[p]), 1))
        for p in available
    ], axis=0)

    for i, ax in enumerate(["X", "Y", "Z"]):
        r = np.sqrt(np.mean((raw_all[:, i] - ideal_all[:, i])**2))
        c = np.sqrt(np.mean((cal_all[:, i] - ideal_all[:, i])**2))
        print(f"  {ax} RMSE: {r:.4f} -> {c:.4f} m/s^2")

    plot_calibration_comparison(
        raw_all, cal_all,
        "Accelerometer Calibration: Six-Position (GY-521 / MPU6050)",
        ["ax (m/s^2)", "ay (m/s^2)", "az (m/s^2)"],
        save_path=REPORTS_DIR / "accel_calib_comparison.png",
    )
    print("  -> reports/figures/accel_calib_comparison.png")

    # Gyro bias from static data
    if static_group is not None and len(static_group) > 100:
        gyro_bias = np.mean(static_group[:min(500, len(static_group)), 3:], axis=0)
        print(f"\nGyro bias (static): {np.round(gyro_bias, 5)} deg/s")
    else:
        print("\nWARNING: No static gyro data found. Using zero bias.")
        print("Collect: MARK static → START → wait 10min → STOP")
        gyro_bias = np.zeros(3)

    # Allan variance (if enough static data)
    allan_accel = {"tau": [], "adev_per_axis": {}, "noise_coeffs": {}}
    allan_gyro = {"tau": [], "adev_per_axis": {}, "noise_coeffs": {}}
    if static_group is not None and len(static_group) > 1000:
        print("\nRunning Allan variance analysis...")
        allan_accel = allan_variance_analysis(static_group[:, :3], fs=50)
        allan_gyro = allan_variance_analysis(static_group[:, 3:], fs=50)
        if allan_accel.get("tau") and len(allan_accel["tau"]) > 0:
            plot_allan(allan_accel["tau"], allan_accel["adev_per_axis"],
                       "Accelerometer Allan Deviation (MPU6050)",
                       REPORTS_DIR / "allan_accel.png")
            plot_allan(allan_gyro["tau"], allan_gyro["adev_per_axis"],
                       "Gyroscope Allan Deviation (MPU6050)",
                       REPORTS_DIR / "allan_gyro.png")
            print("  -> reports/figures/allan_accel.png")
            print("  -> reports/figures/allan_gyro.png")
    else:
        print("\nSkipping Allan variance (need >1000 static samples, got "
              + f"{len(static_group) if static_group is not None else 0})")

    # Generate calib_params.json
    # Simulate mag params (placeholder)
    mag_calib = {
        "hard_iron": [0.0, 0.0, 0.0],
        "soft_iron": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
        "field_magnitude": 45.0,
        "method": "placeholder",
    }
    params = generate_calib_params(accel_calib, mag_calib, allan_accel, allan_gyro)
    params["gyroscope"]["bias"] = gyro_bias.tolist()
    params["calibration_date"] = "2026-06-17"
    params["operator"] = "李宝平"
    params["notes"] = (
        "GY-521 (MPU6050) calibration. "
        "Accel: six-position LSTSQ. "
        "Gyro: static bias estimate. "
        f"Positions collected: {available}. "
        "Mag: placeholder (GY-273 not yet available)."
    )

    out_path = ROOT / "calib" / "calib_params.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(params, f, indent=2, ensure_ascii=False)
    print(f"\n  -> calib/calib_params.json")

    print("\n=== Done. Replace raw_mpu6050_calib.txt with real data to update. ===")


if __name__ == "__main__":
    main()
