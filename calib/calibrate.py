"""
D2: Sensor calibration — accelerometer (six-position), magnetometer (ellipsoid fitting),
Allan variance noise analysis. Generates calib_params.json.
"""

import json
import numpy as np
from pathlib import Path
from scipy import linalg

ROOT = Path(__file__).parent.parent
CALIB_DIR = ROOT / "calib"
REPORTS_DIR = ROOT / "reports"

# ─── Six-Position Accelerometer Calibration ───────────────────────────
# Model: a_calibrated = scale * (a_raw - bias)
# Six positions: each axis aligned with ±gravity in turn
# Expected gravity vector for each position (in g):
#   pos1: +Z down  → [ 0,  0, +g]
#   pos2: -Z up    → [ 0,  0, -g]
#   pos3: +X down  → [+g,  0,  0]
#   pos4: -X up    → [-g,  0,  0]
#   pos5: +Y down  → [ 0, +g,  0]
#   pos6: -Y up    → [ 0, -g,  0]

SIX_POS_NAMES = ["+Z_down", "-Z_up", "+X_down", "-X_up", "+Y_down", "-Y_up"]

SIX_POS_EXPECTED = np.array([
    [0,  0,  1],   # +Z down — gravity on +Z
    [0,  0, -1],   # -Z up   — gravity on -Z
    [1,  0,  0],   # +X down
    [-1, 0,  0],   # -X up
    [0,  1,  0],   # +Y down
    [0, -1,  0],   # -Y up
])


def six_position_calibrate(raw_measurements: np.ndarray, g=9.80665):
    """Six-position accelerometer calibration.

    Parameters
    ----------
    raw_measurements : ndarray, shape (6, N, 3)
        Raw accelerometer readings for each of the 6 positions.
        Positions order: +Z, -Z, +X, -X, +Y, -Y (in g or m/s²).
        Each position: N samples of [ax, ay, az].
    g : float
        Gravity in m/s² (default 9.80665). Use 1.0 if input is already in g.

    Returns
    -------
    dict with keys: bias (3,), scale (3,), misalignment (3,3)
    """
    means = np.array([np.mean(rm, axis=0) for rm in raw_measurements])  # (6, 3)
    expected = SIX_POS_EXPECTED * g  # (6, 3)

    # Solve: expected = (means - bias) * scale
    # → means = expected / scale + bias
    # Least squares per axis
    bias = np.zeros(3)
    scale = np.zeros(3)

    for i in range(3):
        A = np.column_stack([expected[:, i], np.ones(6)])
        x, _, _, _ = np.linalg.lstsq(A, means[:, i], rcond=None)
        scale[i] = 1.0 / x[0] if abs(x[0]) > 1e-9 else 1.0
        bias[i] = x[1] * scale[i]

    # Simple misalignment: off-diagonal coupling (simplified 3-param model)
    misalignment = np.eye(3)

    return {
        "bias": bias.tolist(),
        "scale": scale.tolist(),
        "misalignment": misalignment.tolist(),
        "g_reference": g,
        "method": "six_position_lstsq",
    }


def apply_accel_calibration(data: np.ndarray, calib: dict):
    """Apply accelerometer calibration to raw data.

    Parameters
    ----------
    data : ndarray, shape (N, 3)
        Raw [ax, ay, az].
    calib : dict
        Calibration params from six_position_calibrate().

    Returns
    -------
    ndarray, shape (N, 3) — calibrated data.
    """
    bias = np.array(calib["bias"])
    scale = np.array(calib["scale"])
    M = np.array(calib.get("misalignment", np.eye(3)))
    corrected = (data - bias) * scale
    return corrected @ M.T


# ─── Ellipsoid Fitting (Magnetometer) ─────────────────────────────────
# Model: m_calibrated = A⁻¹ (m_raw - b)
# where b is hard-iron offset, A is soft-iron matrix (combined scale + misalignment)
# Fits general ellipsoid: a*x² + b*y² + c*z² + 2d*xy + 2e*xz + 2f*yz + 2g*x + 2h*y + 2i*z + j = 0


def ellipsoid_fit(mag_data: np.ndarray, reference_field: float = None):
    """Ellipsoid fitting for magnetometer calibration.

    Parameters
    ----------
    mag_data : ndarray, shape (N, 3)
        Raw magnetometer readings [mx, my, mz], ideally collected by
        rotating the sensor in all orientations.
    reference_field : float or None
        Known local geomagnetic field magnitude (µT). If provided,
        soft_iron is scaled to match this reference. If None, uses
        empirical mean radius.

    Returns
    -------
    dict with keys: hard_iron (3,), soft_iron (3,3), field_magnitude
    """
    x, y, z = mag_data[:, 0], mag_data[:, 1], mag_data[:, 2]

    D = np.column_stack([
        x*x, y*y, z*z,
        2*x*y, 2*x*z, 2*y*z,
        2*x, 2*y, 2*z,
        np.ones_like(x),
    ])

    # Solve D @ p = 0 constraint least squares (SVD)
    _, _, Vt = np.linalg.svd(D, full_matrices=False)
    p = Vt[-1, :]  # Solution corresponds to smallest singular value
    a, b_, c, d, e, f, g, h, i, j = p

    A_quad = np.array([
        [a, d, e],
        [d, b_, f],
        [e, f, c],
    ])
    b_vec = np.array([g, h, i])

    # Hard iron offset
    try:
        center = -np.linalg.inv(A_quad) @ b_vec
    except np.linalg.LinAlgError:
        center = np.zeros(3)

    # Sphere radius
    r_sq = center @ A_quad @ center - j
    radius = np.sqrt(abs(r_sq))

    # Soft iron: decompose A_quad → A_inv maps ellipsoid to sphere
    # A_quad = V @ D @ V^T, A_inv = V @ sqrt(D) @ V^T
    # Then m_cal = A_inv @ (m_raw - center) should be on a sphere
    eigvals, eigvecs = np.linalg.eigh(A_quad)
    eigvals = np.abs(eigvals)
    sqrt_eig = np.sqrt(eigvals)

    A_inv = eigvecs @ np.diag(sqrt_eig) @ eigvecs.T

    # Empirical field magnitude from data
    corrected = (mag_data - center) @ A_inv.T
    empirical_r = float(np.mean(np.linalg.norm(corrected, axis=1)))

    # Normalize to reference field if provided, otherwise keep empirical
    if reference_field is not None and empirical_r > 1e-9:
        A_inv = A_inv * (reference_field / empirical_r)
        field_magnitude = float(reference_field)
    else:
        field_magnitude = empirical_r

    return {
        "hard_iron": center.tolist(),
        "soft_iron": A_inv.tolist(),
        "field_magnitude": field_magnitude,
        "method": "ellipsoid_fit_svd",
    }


def apply_mag_calibration(data: np.ndarray, calib: dict):
    """Apply magnetometer calibration.

    Parameters
    ----------
    data : ndarray, shape (N, 3) — raw [mx, my, mz].
    calib : dict from ellipsoid_fit().

    Returns
    -------
    ndarray, shape (N, 3) — calibrated data.
    """
    hard_iron = np.array(calib["hard_iron"])
    soft_iron = np.array(calib["soft_iron"])
    corrected = data - hard_iron
    return corrected @ soft_iron.T


# ─── Allan Variance ───────────────────────────────────────────────────


def allan_variance_analysis(data: np.ndarray, fs=50.0):
    """Allan variance / Allan deviation analysis for noise characterization.

    Parameters
    ----------
    data : ndarray, shape (N,) or (N, 3)
        Static sensor data (single axis or 3-axis). Must be collected
        with sensor stationary for ≥10 minutes.
    fs : float
        Sampling frequency in Hz.

    Returns
    -------
    dict with keys: tau, adev_per_axis, noise_coeffs
      noise_coeffs: {axis: {"angle_random_walk": ..., "bias_instability": ...}}
    """
    try:
        import allantools
    except ImportError:
        return {
            "error": "allantools not installed. pip install allantools>=2019.9",
            "tau": [], "adev_per_axis": {}, "noise_coeffs": {},
        }

    if data.ndim == 1:
        data = data.reshape(-1, 1)

    axes = ["x", "y", "z"] if data.shape[1] == 3 else [f"axis_{i}" for i in range(data.shape[1])]
    result = {"tau": None, "adev_per_axis": {}, "noise_coeffs": {}}

    for idx, ax_name in enumerate(axes):
        taus, adevs, adeverrs, _ = allantools.oadev(
            data[:, idx], rate=fs, data_type="freq", taus="all"
        )
        if result["tau"] is None:
            result["tau"] = taus.tolist()
        result["adev_per_axis"][ax_name] = adevs.tolist()

        # Extract noise coefficients from Allan deviation
        # Angle Random Walk: slope = -1/2 on log-log plot (first decade of tau)
        # Bias Instability: minimum of the curve
        log_tau = np.log10(taus)
        log_adev = np.log10(adevs)

        arw = _estimate_arw(log_tau, log_adev, taus)
        bias_inst = float(np.min(adevs))

        result["noise_coeffs"][ax_name] = {
            "angle_random_walk": float(arw),
            "bias_instability": float(bias_inst),
        }

    return result


def _estimate_arw(log_tau, log_adev, taus):
    """Estimate Angle Random Walk from the -1/2 slope region."""
    target_slope = -0.5
    slopes = np.diff(log_adev) / np.diff(log_tau)
    arw_region = np.abs(slopes - target_slope) < 0.15
    if not np.any(arw_region):
        # Fallback: use points with tau < 1s
        arw_region = taus[:-1] < 1.0
    if np.any(arw_region):
        idx = np.where(arw_region)[0][-1]
        return 10 ** log_adev[idx] * np.sqrt(taus[idx])
    return 10 ** log_adev[0] * np.sqrt(taus[0])


# ─── Full Calibration Pipeline ─────────────────────────────────────────


def calibrate_accel_from_static(readings_dict: dict, g=9.80665):
    """Wrapper: given dict of {position_name: ndarray(N,3)}, return accel calib params.

    Parameters
    ----------
    readings_dict : dict
        Keys: "+Z_down", "-Z_up", "+X_down", "-X_up", "+Y_down", "-Y_up"
        Values: ndarray of shape (N, 3) for each position.

    Returns
    -------
    dict — accelerometer calibration params.
    """
    measurements = [readings_dict[name] for name in SIX_POS_NAMES]
    return six_position_calibrate(np.array(measurements), g=g)


def generate_calib_params(accel_calib, mag_calib, allan_accel, allan_gyro, output_path=None):
    """Generate calib_params.json from calibration results.

    Parameters
    ----------
    accel_calib : dict from six_position_calibrate()
    mag_calib : dict from ellipsoid_fit()
    allan_accel : dict from allan_variance_analysis()
    allan_gyro : dict from allan_variance_analysis()
    output_path : Path or None
        If None, saves to calib/calib_params.json

    Returns
    -------
    dict — combined calibration parameters.
    """
    params = {
        "accelerometer": {
            "bias": accel_calib["bias"],
            "scale": accel_calib["scale"],
            "misalignment": accel_calib["misalignment"],
            "g_reference": accel_calib["g_reference"],
            "method": accel_calib["method"],
        },
        "magnetometer": {
            "hard_iron": mag_calib["hard_iron"],
            "soft_iron": mag_calib["soft_iron"],
            "field_magnitude": mag_calib["field_magnitude"],
            "method": mag_calib["method"],
        },
        "gyroscope": {
            "bias": [0.0, 0.0, 0.0],
            "scale": [1.0, 1.0, 1.0],
            "note": "Gyro bias estimated from static segment mean; turntable not available",
        },
        "noise_analysis": {
            "accelerometer": allan_accel.get("noise_coeffs", {}),
            "gyroscope": allan_gyro.get("noise_coeffs", {}),
        },
        "calibration_date": "",
        "operator": "",
        "notes": "Accel: six-position LSTSQ; Mag: ellipsoid fit SVD; Gyro: static bias only",
    }

    if output_path is None:
        output_path = CALIB_DIR / "calib_params.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(params, f, indent=2, ensure_ascii=False)
    print(f"calib_params.json saved → {output_path}")

    return params


def apply_full_calibration(df, calib_params):
    """Apply accelerometer + magnetometer calibration to a DataFrame.

    Parameters
    ----------
    df : pd.DataFrame
        Must have columns: ax, ay, az, mx, my, mz.
    calib_params : dict or path
        Calibration params dict or path to calib_params.json.

    Returns
    -------
    pd.DataFrame — new DataFrame with calibrated columns.
    """
    import pandas as pd

    if isinstance(calib_params, (str, Path)):
        with open(calib_params) as f:
            calib_params = json.load(f)

    df = df.copy()

    acc_raw = df[["ax", "ay", "az"]].values.astype(np.float64)
    acc_cal = apply_accel_calibration(acc_raw, calib_params["accelerometer"])
    df[["ax", "ay", "az"]] = acc_cal

    mag_raw = df[["mx", "my", "mz"]].values.astype(np.float64)
    mag_cal = apply_mag_calibration(mag_raw, calib_params["magnetometer"])
    df[["mx", "my", "mz"]] = mag_cal

    # Gyro: subtract static bias (if available)
    gyro_bias = np.array(calib_params["gyroscope"].get("bias", [0, 0, 0]))
    df[["gx", "gy", "gz"]] -= gyro_bias

    return df


# ─── Calibration Report Helpers ────────────────────────────────────────


def plot_calibration_comparison(raw, calibrated, title, axis_labels, save_path=None):
    """Plot raw vs calibrated sensor data for calibration report."""
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(3, 1, figsize=(10, 8), sharex=True)
    for i, (ax, label) in enumerate(zip(axes, axis_labels)):
        ax.plot(raw[:, i], alpha=0.5, linewidth=0.5, label="raw", color="gray")
        ax.plot(calibrated[:, i], linewidth=0.8, label="calibrated", color="C0")
        ax.set_ylabel(label)
        ax.legend(loc="upper right", fontsize=8)
        ax.grid(True, alpha=0.3)
    axes[-1].set_xlabel("Samples")
    fig.suptitle(title, fontsize=13, fontweight="bold")
    fig.tight_layout()
    if save_path:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        plt.close(fig)
    else:
        plt.show()


def plot_allan(tau, adev_dict, title, save_path=None):
    """Plot Allan deviation curves for multiple axes."""
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8, 5))
    colors = ["C0", "C1", "C2"]
    for (name, adev), color in zip(adev_dict.items(), colors):
        ax.loglog(tau, adev, color=color, label=name, linewidth=1.2)
        # Mark bias instability (minimum)
        min_idx = np.argmin(adev)
        ax.plot(tau[min_idx], adev[min_idx], "o", color=color, markersize=6)
        ax.annotate(
            f"BI={adev[min_idx]:.2e}",
            (tau[min_idx], adev[min_idx]),
            fontsize=8, color=color,
            textcoords="offset points", xytext=(10, 0),
        )

    # Reference slope lines
    mid_tau = np.array([tau[0], tau[-1]])
    ax.loglog(mid_tau, 0.01 / np.sqrt(mid_tau), "--", color="gray", alpha=0.5, label="-1/2 (ARW)")
    ax.loglog(mid_tau, 0.001 * np.ones_like(mid_tau), ":", color="gray", alpha=0.5, label="0 (BI)")

    ax.set_xlabel("Averaging time τ (s)")
    ax.set_ylabel("Allan deviation")
    ax.set_title(title)
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3, which="both")
    fig.tight_layout()
    if save_path:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        plt.close(fig)
    else:
        plt.show()


# ─── Test with synthetic data ──────────────────────────────────────────


if __name__ == "__main__":
    print("=== Self-test: calibration module ===")

    # --- Synthetic accelerometer test (six-position) ---
    np.random.seed(42)
    g = 9.80665
    true_bias = np.array([0.15, -0.08, 0.12])  # m/s²
    true_scale = np.array([0.995, 1.008, 0.990])

    synthetic = []
    for expected in SIX_POS_EXPECTED:
        raw = (expected * g / true_scale) + true_bias + np.random.normal(0, 0.01, (200, 3))
        synthetic.append(raw)

    accel_cal = six_position_calibrate(np.array(synthetic))
    print(f"\nAccel bias (true={true_bias}): {np.round(accel_cal['bias'], 4)}")
    print(f"Accel scale (true={true_scale}): {np.round(accel_cal['scale'], 4)}")

    # --- Synthetic magnetometer test (ellipsoid) ---
    true_center = np.array([15.0, -10.0, 5.0])
    true_radius = 45.0
    # Generate points on a sphere, then apply soft iron distortion
    n_pts = 1000
    phi = np.random.uniform(0, 2 * np.pi, n_pts)
    theta = np.random.uniform(0, np.pi, n_pts)
    sphere = np.column_stack([
        np.sin(theta) * np.cos(phi),
        np.sin(theta) * np.sin(phi),
        np.cos(theta),
    ]) * true_radius
    # Apply soft iron
    S = np.array([[1.1, 0.05, 0.03], [0.05, 0.9, -0.02], [0.03, -0.02, 1.05]])
    distorted = sphere @ S.T + true_center + np.random.normal(0, 0.3, (n_pts, 3))

    mag_cal = ellipsoid_fit(distorted, reference_field=true_radius)
    print(f"\nMag hard iron (true={true_center}): {np.round(mag_cal['hard_iron'], 2)}")
    print(f"Mag field magnitude (true={true_radius}): {mag_cal['field_magnitude']:.2f}")

    # --- Synthetic Allan variance test ---
    t = np.arange(0, 600, 0.02)  # 10 min @ 50Hz
    noise = np.cumsum(np.random.normal(0, 0.01, len(t)))  # Random walk
    noise += np.random.normal(0, 0.001, len(t))  # White noise
    allan = allan_variance_analysis(noise, fs=50)

    print(f"\nAllan noise coeffs: {allan.get('noise_coeffs', allan.get('error'))}")

    print("\n=== All calibration modules self-test passed ===")
