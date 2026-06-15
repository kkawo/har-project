"""
D4: Feature extraction (time-domain, frequency-domain, time-frequency).
Target: >= 12 features per axis, forming a complete feature matrix.
"""

import numpy as np
from scipy import signal
from scipy.stats import skew, kurtosis


def extract_time_features(data, axis_name=""):
    """Extract time-domain features from a 1D signal."""
    features = {}
    prefix = f"{axis_name}_" if axis_name else ""

    features[f"{prefix}mean"] = np.mean(data)
    features[f"{prefix}std"] = np.std(data)
    features[f"{prefix}var"] = np.var(data)
    features[f"{prefix}rms"] = np.sqrt(np.mean(np.square(data)))
    features[f"{prefix}peak_to_peak"] = np.max(data) - np.min(data)
    features[f"{prefix}max"] = np.max(data)
    features[f"{prefix}min"] = np.min(data)
    features[f"{prefix}median"] = np.median(data)
    features[f"{prefix}skew"] = skew(data)
    features[f"{prefix}kurtosis"] = kurtosis(data)
    # Zero crossing rate
    zero_crossings = np.sum(np.diff(np.signbit(data)))
    features[f"{prefix}zero_cross_rate"] = zero_crossings / len(data)
    # Signal magnitude area
    features[f"{prefix}sma"] = np.sum(np.abs(data)) / len(data)

    return features


def extract_freq_features(data, fs=50, axis_name=""):
    """Extract frequency-domain features from a 1D signal."""
    features = {}
    prefix = f"{axis_name}_" if axis_name else ""

    n = len(data)
    fft_vals = np.abs(np.fft.rfft(data))
    freqs = np.fft.rfftfreq(n, d=1/fs)

    # Dominant frequency
    features[f"{prefix}dominant_freq"] = freqs[np.argmax(fft_vals)]
    # Spectral centroid
    if np.sum(fft_vals) > 0:
        features[f"{prefix}spectral_centroid"] = np.sum(freqs * fft_vals) / np.sum(fft_vals)
    else:
        features[f"{prefix}spectral_centroid"] = 0
    # Spectral entropy
    psd = fft_vals ** 2
    psd_norm = psd / (np.sum(psd) + 1e-12)
    features[f"{prefix}spectral_entropy"] = -np.sum(psd_norm * np.log(psd_norm + 1e-12))
    # Band energy ratios (low 0-1Hz, mid 1-5Hz, high 5-20Hz)
    total_energy = np.sum(psd) + 1e-12
    features[f"{prefix}energy_low"] = np.sum(psd[(freqs >= 0) & (freqs < 1)]) / total_energy
    features[f"{prefix}energy_mid"] = np.sum(psd[(freqs >= 1) & (freqs < 5)]) / total_energy
    features[f"{prefix}energy_high"] = np.sum(psd[(freqs >= 5) & (freqs <= 20)]) / total_energy

    return features


def extract_window_features(window_df, acc_axes=None, gyro_axes=None, mag_axes=None, fs=50):
    """Extract all features from a single window DataFrame."""
    if acc_axes is None:
        acc_axes = ["ax", "ay", "az"]
    if gyro_axes is None:
        gyro_axes = ["gx", "gy", "gz"]
    if mag_axes is None:
        mag_axes = ["mx", "my", "mz"]

    features = {}

    # Per-axis features
    all_axes = acc_axes + gyro_axes + mag_axes
    for ax in all_axes:
        data = window_df[ax].values
        features.update(extract_time_features(data, axis_name=ax))
        features.update(extract_freq_features(data, fs=fs, axis_name=ax))

    # Magnitude features (acceleration magnitude)
    acc_mag = np.sqrt(
        window_df[acc_axes[0]]**2 + window_df[acc_axes[1]]**2 + window_df[acc_axes[2]]**2
    ).values
    features.update(extract_time_features(acc_mag, axis_name="acc_mag"))
    features.update(extract_freq_features(acc_mag, fs=fs, axis_name="acc_mag"))

    # Cross-axial correlation
    for i, ax1 in enumerate(acc_axes):
        for ax2 in acc_axes[i+1:]:
            corr = np.corrcoef(window_df[ax1], window_df[ax2])[0, 1]
            features[f"acc_corr_{ax1}_{ax2}"] = corr if not np.isnan(corr) else 0

    return features


def build_feature_matrix(windows, labels=None, subjects=None):
    """Build feature matrix from list of window DataFrames."""
    feature_list = [extract_window_features(w) for w in windows]
    X = np.array([list(f.values()) for f in feature_list])
    feature_names = list(feature_list[0].keys())
    return X, labels, subjects, feature_names


if __name__ == "__main__":
    print("Feature extraction module loaded.")
