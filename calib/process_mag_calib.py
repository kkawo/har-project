"""
Process HMC5883L magnetometer calibration data → update calib_params.json.
Usage: python calib/process_mag_calib.py

Reads raw_hmc5883l_calib.txt from serial capture,
performs ellipsoid fitting, generates comparison chart,
and updates calib/calib_params.json with real magnetometer parameters.
"""
import sys, json, re
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

import numpy as np
from pathlib import Path
from calib.calibrate import (
    ellipsoid_fit, apply_mag_calibration,
    plot_calibration_comparison, allan_variance_analysis,
)

ROOT = Path(__file__).parent.parent
REPORTS_DIR = ROOT / "reports" / "figures"
CALIB_DIR = ROOT / "calib"
CALIB_PARAMS_PATH = CALIB_DIR / "calib_params.json"
INPUT_FILE = CALIB_DIR / "raw_hmc5883l_calib.txt"


def parse_mag_calib_log(filepath):
    """Parse HMC5883L calibration serial log into (mx, my, mz) array."""
    samples = []

    with open(filepath, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Format: sample,mx,my,mz
            parts = line.split(",")
            if len(parts) >= 4:
                try:
                    mx = float(parts[1])
                    my = float(parts[2])
                    mz = float(parts[3])
                    samples.append([mx, my, mz])
                except ValueError:
                    continue

    if not samples:
        print(f"ERROR: No valid samples found in {filepath}")
        print("Expected format: sample,mx,my,mz")
        return None

    samples = np.array(samples)
    print(f"Parsed {len(samples)} magnetometer samples")
    print(f"  mx: [{samples[:, 0].min():.1f}, {samples[:, 0].max():.1f}] uT")
    print(f"  my: [{samples[:, 1].min():.1f}, {samples[:, 1].max():.1f}] uT")
    print(f"  mz: [{samples[:, 2].min():.1f}, {samples[:, 2].max():.1f}] uT")
    return samples


def main():
    if not INPUT_FILE.exists():
        print(f"""
Input file not found: {INPUT_FILE}

Please collect magnetometer calibration data first:
  1. Flash firmware/har9ch_firmware/main.py to ESP32
  2. Run: python calib/capture_mag_calib.py <COM port>
  3. Slowly rotate the sensor in all directions for 60 seconds
  4. Re-run: python calib/process_mag_calib.py
""")
        return

    # Parse
    mag_raw = parse_mag_calib_log(INPUT_FILE)
    if mag_raw is None:
        return

    # Compute raw norm statistics (before calibration)
    raw_norms = np.linalg.norm(mag_raw, axis=1)
    raw_norm_mean = float(np.mean(raw_norms))
    raw_norm_std = float(np.std(raw_norms))
    print(f"\nBefore calibration:")
    print(f"  Field magnitude: {raw_norm_mean:.2f} ± {raw_norm_std:.2f} uT")

    # Ellipsoid fitting
    # Fuzhou geomagnetic field ~45 uT (reference for scaling)
    FUZHOU_FIELD = 45.0
    mag_calib = ellipsoid_fit(mag_raw, reference_field=FUZHOU_FIELD)
    print(f"\nEllipsoid fitting results:")
    print(f"  Hard iron:  [{mag_calib['hard_iron'][0]:.2f}, "
          f"{mag_calib['hard_iron'][1]:.2f}, {mag_calib['hard_iron'][2]:.2f}] uT")
    print(f"  Soft iron:  {np.round(mag_calib['soft_iron'], 4)}")
    print(f"  Field magnitude (calibrated): {mag_calib['field_magnitude']:.1f} uT")

    # Apply calibration
    mag_calibrated = apply_mag_calibration(mag_raw, mag_calib)
    cal_norms = np.linalg.norm(mag_calibrated, axis=1)
    cal_norm_std = float(np.std(cal_norms))
    print(f"\nAfter calibration:")
    print(f"  Field magnitude std: {cal_norm_std:.2f} uT")
    print(f"  Improvement: {(1 - cal_norm_std / max(raw_norm_std, 1e-9)) * 100:.1f}% reduction in norm variance")

    # Diagnostic: check if enough coverage
    # Ratio of min/max radius on each axis → should be close to 1 for good coverage
    coverage_x = (mag_raw[:, 0].max() - mag_raw[:, 0].min()) / max(abs(mag_raw[:, 0]).max(), 1e-9)
    coverage_y = (mag_raw[:, 1].max() - mag_raw[:, 1].min()) / max(abs(mag_raw[:, 1]).max(), 1e-9)
    coverage_z = (mag_raw[:, 2].max() - mag_raw[:, 2].min()) / max(abs(mag_raw[:, 2]).max(), 1e-9)
    coverage_score = min(coverage_x, coverage_y, coverage_z)
    if coverage_score < 0.5:
        print(f"\n  WARNING: Limited coverage (score={coverage_score:.2f}).")
        print(f"  Consider re-collecting with more thorough rotation in all axes.")

    # Plot comparison
    plot_calibration_comparison(
        mag_raw, mag_calibrated,
        "Magnetometer Calibration: Ellipsoid Fit (HMC5883L / GY-273)",
        ["mx (uT)", "my (uT)", "mz (uT)"],
        save_path=REPORTS_DIR / "mag_calib_comparison.png",
    )
    print("  -> reports/figures/mag_calib_comparison.png")

    # Update calib_params.json
    if not CALIB_PARAMS_PATH.exists():
        print(f"\nERROR: {CALIB_PARAMS_PATH} not found. Run D2 calibration first.")
        return

    with open(CALIB_PARAMS_PATH, encoding="utf-8") as f:
        params = json.load(f)

    params["magnetometer"] = {
        "hard_iron": mag_calib["hard_iron"],
        "soft_iron": mag_calib["soft_iron"],
        "field_magnitude": mag_calib["field_magnitude"],
        "method": "ellipsoid_fit_svd",
        "raw_norm_std": raw_norm_std,
        "calibrated_norm_std": cal_norm_std,
    }
    params["notes"] = params.get("notes", "") + (
        f" HMC5883L mag calib: hard_iron={np.round(mag_calib['hard_iron'], 2)}, "
        f"norm_std {raw_norm_std:.1f}→{cal_norm_std:.1f}uT."
    )
    params["calibration_date"] = params.get("calibration_date", "2026-06-17")

    with open(CALIB_PARAMS_PATH, "w", encoding="utf-8") as f:
        json.dump(params, f, indent=2, ensure_ascii=False)
    print(f"  -> {CALIB_PARAMS_PATH} updated with magnetometer params")

    print("\n=== Magnetometer calibration complete ===")


if __name__ == "__main__":
    main()
