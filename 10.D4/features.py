"""
D4: Feature extraction — time-domain + frequency-domain features.

Extracts >= 14 time-domain + 10 frequency-domain features per axis,
plus magnitude, cross-axis, and composite features.

Input:  data/windowed/windowed_dataset.npz  (windows, labels, subjects)
Output: data/features/feature_matrix.npz + feature_matrix.csv
        docs/特征字典.md

Usage: python src/features.py
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import signal
from scipy.stats import skew, kurtosis, iqr

ROOT = Path(__file__).parent.parent
WINDOWED_DIR = ROOT / "data" / "windowed"
FEATURES_DIR = ROOT / "data" / "features"
DOCS_DIR = ROOT / "docs"
FS = 50
CHANNELS = ["ax", "ay", "az", "gx", "gy", "gz", "mx", "my", "mz"]
ACC_AXES = [0, 1, 2]
GYRO_AXES = [3, 4, 5]
MAG_AXES = [6, 7, 8]


# ═══════════════════════════════════════════════════════════════════════════
# 1. Time-domain features (14 per axis)
# ═══════════════════════════════════════════════════════════════════════════

def extract_time_features(x):
    """Extract 14 time-domain features from a 1D signal."""
    n = len(x)
    x_abs = np.abs(x)
    feats = {}

    with np.errstate(all="ignore"):
        feats["mean"] = float(np.mean(x))
        feats["std"] = float(np.std(x))
        feats["var"] = float(np.var(x))
        feats["rms"] = float(np.sqrt(np.mean(np.square(x))))
        feats["peak_to_peak"] = float(np.max(x) - np.min(x))
        feats["max"] = float(np.max(x))
        feats["min"] = float(np.min(x))
        feats["median"] = float(np.median(x))
        feats["skew"] = float(skew(x))
        feats["kurtosis"] = float(kurtosis(x))
        feats["zero_cross_rate"] = float(np.sum(np.diff(np.signbit(x - np.mean(x)))) / n)
        feats["sma"] = float(np.sum(x_abs) / n)
        feats["iqr"] = float(iqr(x))

        # Autocorrelation at lag 1
        x_centered = x - np.mean(x)
        denom = np.dot(x_centered, x_centered)
        feats["autocorr_lag1"] = float(np.dot(x_centered[:-1], x_centered[1:]) / (denom + 1e-12))

    return feats


# ═══════════════════════════════════════════════════════════════════════════
# 2. Frequency-domain features (10 per axis)
# ═══════════════════════════════════════════════════════════════════════════

def extract_freq_features(x, fs=FS):
    """Extract 10 frequency-domain features from a 1D signal."""
    n = len(x)
    fft_vals = np.abs(np.fft.rfft(x))
    freqs = np.fft.rfftfreq(n, d=1 / fs)
    psd = fft_vals ** 2
    total_energy = np.sum(psd) + 1e-12

    feats = {}

    # Dominant frequency (excluding DC)
    dc_end = max(1, int(0.3 * n / fs))  # skip DC component
    if len(fft_vals) > dc_end:
        feats["dominant_freq"] = float(freqs[dc_end + np.argmax(fft_vals[dc_end:])])
    else:
        feats["dominant_freq"] = 0.0

    # Spectral centroid
    feats["spectral_centroid"] = float(np.sum(freqs * fft_vals) / (np.sum(fft_vals) + 1e-12))

    # Spectral entropy
    psd_norm = psd / total_energy
    feats["spectral_entropy"] = float(-np.sum(psd_norm * np.log(psd_norm + 1e-12)))

    # Band energy ratios
    feats["energy_low"] = float(np.sum(psd[(freqs >= 0.3) & (freqs < 1)]) / total_energy)
    feats["energy_mid"] = float(np.sum(psd[(freqs >= 1) & (freqs < 5)]) / total_energy)
    feats["energy_high"] = float(np.sum(psd[(freqs >= 5) & (freqs <= 20)]) / total_energy)

    # Spectral bandwidth (weighted std dev of frequencies)
    feats["spectral_bandwidth"] = float(
        np.sqrt(np.sum(((freqs - feats["spectral_centroid"]) ** 2) * fft_vals) /
                (np.sum(fft_vals) + 1e-12)))

    # Spectral flatness (geometric mean / arithmetic mean)
    geo_mean = np.exp(np.mean(np.log(psd_norm + 1e-12)))
    ari_mean = np.mean(psd_norm)
    feats["spectral_flatness"] = float(geo_mean / (ari_mean + 1e-12))

    # Spectral roll-off (frequency below which 85% of energy is contained)
    cumsum = np.cumsum(psd)
    rolloff_idx = np.argmax(cumsum >= 0.85 * total_energy)
    feats["spectral_rolloff"] = float(freqs[min(rolloff_idx, len(freqs) - 1)])

    # Number of spectral peaks
    from scipy.signal import find_peaks
    peaks, _ = find_peaks(psd, height=0.05 * np.max(psd), distance=3)
    feats["peak_count"] = len(peaks)

    return feats


# ═══════════════════════════════════════════════════════════════════════════
# 3. Per-window feature extraction
# ═══════════════════════════════════════════════════════════════════════════

def extract_all_features(window, fs=FS):
    """Extract all features from one window: (128, 9) ndarray.

    Returns a flat dict of feature_name → value.
    """
    features = {}

    # --- Per-axis: time + frequency ---
    for ch_idx, ch_name in enumerate(CHANNELS):
        x = window[:, ch_idx]
        time_f = extract_time_features(x)
        freq_f = extract_freq_features(x, fs)
        for k, v in time_f.items():
            features[f"{ch_name}_{k}"] = v
        for k, v in freq_f.items():
            features[f"{ch_name}_{k}"] = v

    # --- Magnitude features ---
    # Acceleration magnitude
    acc_mag = np.sqrt(np.sum(window[:, ACC_AXES] ** 2, axis=1))
    for k, v in extract_time_features(acc_mag).items():
        features[f"acc_mag_{k}"] = v
    for k, v in extract_freq_features(acc_mag, fs).items():
        features[f"acc_mag_{k}"] = v

    # Gyroscope magnitude
    gyro_mag = np.sqrt(np.sum(window[:, GYRO_AXES] ** 2, axis=1))
    for k, v in extract_time_features(gyro_mag).items():
        features[f"gyro_mag_{k}"] = v
    for k, v in extract_freq_features(gyro_mag, fs).items():
        features[f"gyro_mag_{k}"] = v

    # Magnetometer magnitude
    mag_mag = np.sqrt(np.sum(window[:, MAG_AXES] ** 2, axis=1))
    for k, v in extract_time_features(mag_mag).items():
        features[f"mag_mag_{k}"] = v

    # --- Cross-axial correlation (within sensor) ---
    for axes, prefix in [(ACC_AXES, "acc"), (GYRO_AXES, "gyro"), (MAG_AXES, "mag")]:
        for i in range(3):
            for j in range(i + 1, 3):
                corr = np.corrcoef(window[:, axes[i]], window[:, axes[j]])[0, 1]
                features[f"{prefix}_corr_{CHANNELS[axes[i]]}_{CHANNELS[axes[j]]}"] = (
                    float(corr) if not np.isnan(corr) else 0.0)

    # --- Cross-sensor correlation ---
    # Acc-Gyro: acceleration magnitude vs gyroscope magnitude
    features["acc_gyro_corr"] = float(np.corrcoef(acc_mag, gyro_mag)[0, 1])

    # --- Jerk (derivative of acceleration) ---
    jerk = np.diff(window[:, ACC_AXES], axis=0) * fs
    jerk_mag = np.sqrt(np.sum(jerk ** 2, axis=1))
    features["jerk_mag_mean"] = float(np.mean(jerk_mag))
    features["jerk_mag_std"] = float(np.std(jerk_mag))
    features["jerk_mag_max"] = float(np.max(jerk_mag))

    # --- Additional discriminative features ---
    # Acc vertical-to-horizontal ratio (az vs ax+ay, useful for upstairs/downstairs)
    az_energy = np.sum(window[:, 2] ** 2)
    axy_energy = np.sum(window[:, 0] ** 2 + window[:, 1] ** 2)
    features["acc_vertical_ratio"] = float(az_energy / (axy_energy + 1e-12))

    # Gyro pitch-roll ratio (gy vs gx+gz, useful for turning vs walking)
    gy_energy = np.sum(window[:, 4] ** 2)
    gxz_energy = np.sum(window[:, 3] ** 2 + window[:, 5] ** 2)
    features["gyro_pitch_ratio"] = float(gy_energy / (gxz_energy + 1e-12))

    # Magnetometer heading stability (std of atan2(my, mx))
    heading = np.arctan2(window[:, 7], window[:, 6])  # my, mx
    features["mag_heading_std"] = float(np.std(np.unwrap(heading)))

    return features


# ═══════════════════════════════════════════════════════════════════════════
# 4. Batch extraction
# ═══════════════════════════════════════════════════════════════════════════

def build_feature_matrix(windows, labels, subjects, fs=FS):
    """Extract features from all windows → feature matrix.

    Parameters
    ----------
    windows : ndarray (N, 128, 9)
    labels : ndarray (N,)
    subjects : ndarray (N,)
    fs : int

    Returns
    -------
    X : ndarray (N, n_features)
    y : ndarray (N,)
    subject_arr : ndarray (N,)
    feature_names : list[str]
    """
    n_windows = len(windows)
    feature_list = []

    for i in range(n_windows):
        feats = extract_all_features(windows[i], fs)
        feature_list.append(feats)
        if (i + 1) % 500 == 0:
            print(f"  {i + 1}/{n_windows} windows processed...")

    feature_names = list(feature_list[0].keys())
    X = np.array([[f[name] for name in feature_names] for f in feature_list], dtype=np.float32)

    return X, labels, subjects, feature_names


# ═══════════════════════════════════════════════════════════════════════════
# 5. Feature dictionary generation
# ═══════════════════════════════════════════════════════════════════════════

TIME_FEATURE_DESCRIPTIONS = {
    "mean": "均值", "std": "标准差", "var": "方差", "rms": "均方根",
    "peak_to_peak": "峰峰值", "max": "最大值", "min": "最小值", "median": "中位数",
    "skew": "偏度 (分布不对称性)", "kurtosis": "峰度 (分布尾重)",
    "zero_cross_rate": "过零率 (信号振荡频繁度)", "sma": "信号幅值面积 (运动强度)",
    "iqr": "四分位距 (鲁棒离散度)", "autocorr_lag1": "一阶自相关 (信号周期性)",
}

FREQ_FEATURE_DESCRIPTIONS = {
    "dominant_freq": "主频 (Hz, 最强周期成分)",
    "spectral_centroid": "频谱质心 (Hz, 能量分布中心)",
    "spectral_entropy": "谱熵 (频谱有序度, 越低越规律)",
    "energy_low": "低频能量比 (0.3-1 Hz, 准静态/缓慢姿态变化)",
    "energy_mid": "中频能量比 (1-5 Hz, 步态主频带)",
    "energy_high": "高频能量比 (5-20 Hz, 冲击/噪声)",
    "spectral_bandwidth": "频谱带宽 (Hz, 能量扩散宽度)",
    "spectral_flatness": "频谱平坦度 (0-1, 接近1=白噪声)",
    "spectral_rolloff": "频谱滚降点 (Hz, 85%能量所在频率)",
    "peak_count": "频谱峰个数 (周期性成分的复杂度)",
}

COMPOSITE_DESCRIPTIONS = {
    "acc_mag": "合加速度模长", "gyro_mag": "合角速度模长", "mag_mag": "合磁场模长",
    "acc_corr": "加速度轴间相关系数 (运动协调性)",
    "gyro_corr": "陀螺仪轴间相关系数",
    "mag_corr": "磁力计轴间相关系数",
    "acc_gyro_corr": "加速度-角速度相关性",
    "jerk_mag_mean": "加加速度均值 (运动平滑度)",
    "jerk_mag_std": "加加速度标准差",
    "jerk_mag_max": "加加速度最大值 (冲击强度)",
    "acc_vertical_ratio": "垂直/水平能量比 (上楼vs下楼判别)",
    "gyro_pitch_ratio": "俯仰轴能量比",
    "mag_heading_std": "磁航向标准差 (朝向稳定性, 静坐vs步行)",
}


def generate_feature_dictionary(feature_names, output_path=None):
    """Generate feature dictionary markdown document."""
    if output_path is None:
        output_path = DOCS_DIR / "特征字典.md"

    lines = [
        "# 特征字典",
        "",
        f"共 {len(feature_names)} 个特征，按信号轴和类型组织。",
        "",
        "| 序号 | 特征名 | 来源 | 类型 | 物理含义 |",
        "|------|--------|------|------|----------|",
    ]

    for i, name in enumerate(feature_names, 1):
        # Parse feature name: <axis>_<feature_type>
        parts = name.split("_", 1)
        source = parts[0] if len(parts) > 1 else "composite"
        ftype = parts[1] if len(parts) > 1 else name

        # Determine type
        if any(ftype.endswith(suf) for suf in TIME_FEATURE_DESCRIPTIONS):
            category = "时域"
            desc = TIME_FEATURE_DESCRIPTIONS.get(
                [s for s in TIME_FEATURE_DESCRIPTIONS if ftype.endswith(s)][0]
                if any(ftype.endswith(s) for s in TIME_FEATURE_DESCRIPTIONS) else "", "")
        elif any(ftype.endswith(suf) for suf in FREQ_FEATURE_DESCRIPTIONS):
            category = "频域"
            desc = FREQ_FEATURE_DESCRIPTIONS.get(
                [s for s in FREQ_FEATURE_DESCRIPTIONS if ftype.endswith(s)][0]
                if any(ftype.endswith(s) for s in FREQ_FEATURE_DESCRIPTIONS) else "", "")
        else:
            category = "复合"
            # Try composite descriptions
            desc = ""
            for key, val in COMPOSITE_DESCRIPTIONS.items():
                if key in name:
                    desc = val
                    break

        # Fallback: check if component type name is in the feature
        if not desc:
            for suf, d in {**TIME_FEATURE_DESCRIPTIONS, **FREQ_FEATURE_DESCRIPTIONS}.items():
                if suf in name:
                    desc = d
                    break

        lines.append(f"| {i} | `{name}` | {source} | {category} | {desc} |")

    lines += [
        "",
        "## 特征统计",
        "",
        f"- 总特征数: {len(feature_names)}",
        f"- 时域特征/轴: {len(TIME_FEATURE_DESCRIPTIONS)}",
        f"- 频域特征/轴: {len(FREQ_FEATURE_DESCRIPTIONS)}",
        f"- 轴数: 9 (ax/ay/az/gx/gy/gz/mx/my/mz)",
        f"- 模长特征组: 3 (acc_mag, gyro_mag, mag_mag)",
        f"- 跨轴/跨传感器/复合特征: {len(COMPOSITE_DESCRIPTIONS)}",
        "",
        "## 特征计算公式",
        "",
    ]

    # Add formulas for time features
    lines.append("### 时域特征")
    lines.append("| 特征 | 公式 |")
    lines.append("|------|------|")
    formulas_time = {
        "mean": r"$\mu = \frac{1}{N}\sum x_i$",
        "std": r"$\sigma = \sqrt{\frac{1}{N}\sum(x_i - \mu)^2}$",
        "var": r"$\sigma^2$",
        "rms": r"$\sqrt{\frac{1}{N}\sum x_i^2}$",
        "peak_to_peak": r"$\max(x) - \min(x)$",
        "skew": r"$\frac{1}{N}\sum\left(\frac{x_i - \mu}{\sigma}\right)^3$",
        "kurtosis": r"$\frac{1}{N}\sum\left(\frac{x_i - \mu}{\sigma}\right)^4 - 3$",
        "zero_cross_rate": r"$\frac{1}{N}\sum \mathbb{1}[\text{sign}(x_i - \bar{x}) \neq \text{sign}(x_{i-1} - \bar{x})]$",
        "sma": r"$\frac{1}{N}\sum |x_i|$",
        "autocorr_lag1": r"$\frac{\sum(x_i - \mu)(x_{i+1} - \mu)}{\sum(x_i - \mu)^2}$",
    }
    for name, formula in formulas_time.items():
        lines.append(f"| {name} | {formula} |")

    lines.append("")
    lines.append("### 频域特征")
    lines.append("| 特征 | 公式 |")
    lines.append("|------|------|")
    formulas_freq = {
        "dominant_freq": r"$\arg\max_f |X(f)|$",
        "spectral_centroid": r"$\frac{\sum f \cdot |X(f)|}{\sum |X(f)|}$",
        "spectral_entropy": r"$-\sum P(f) \log P(f)$  where $P(f) = |X(f)|^2 / \sum|X(f)|^2$",
        "spectral_bandwidth": r"$\sqrt{\frac{\sum (f - f_c)^2 |X(f)|}{\sum |X(f)|}}$",
        "spectral_flatness": r"$\frac{\sqrt[N]{\prod P(f)}}{\frac{1}{N}\sum P(f)}$",
        "spectral_rolloff": r"$f$ such that $\sum_{0}^{f} |X(k)|^2 = 0.85 \cdot \sum |X(f)|^2$",
    }
    for name, formula in formulas_freq.items():
        lines.append(f"| {name} | {formula} |")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"  Feature dictionary: {output_path}")
    return output_path


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

def main():
    print("=== D4: Feature Extraction ===\n")

    # Load windowed dataset
    npz_path = WINDOWED_DIR / "windowed_dataset.npz"
    if not npz_path.exists():
        print(f"ERROR: {npz_path} not found.")
        print("Run 'python src/preprocess.py' first.")
        sys.exit(1)

    data = np.load(npz_path, allow_pickle=True)
    windows = data["windows"]  # (N, 128, 9)
    labels = data["labels"]     # (N,)
    subjects = data["subjects"]  # (N,)

    print(f"Loaded: {windows.shape} windows from {npz_path}")
    print(f"  Labels: {sorted(np.unique(labels).astype(int))}")
    print(f"  Subjects: {sorted(np.unique(subjects))}")
    print()

    # Extract features
    print("Extracting features...")
    X, y, subject_arr, feature_names = build_feature_matrix(windows, labels, subjects)
    print(f"\nFeature matrix: {X.shape}")
    print(f"  Features: {len(feature_names)}")

    # Save
    FEATURES_DIR.mkdir(parents=True, exist_ok=True)

    # NPZ (compact)
    np.savez_compressed(
        FEATURES_DIR / "feature_matrix.npz",
        X=X, y=y, subjects=subject_arr,
        feature_names=np.array(feature_names, dtype=str),
    )
    print(f"\n  Saved: {FEATURES_DIR / 'feature_matrix.npz'}")

    # CSV (with labels)
    df = pd.DataFrame(X, columns=feature_names)
    df.insert(0, "subject_id", subject_arr)
    df.insert(0, "label", y.astype(int))
    df.to_csv(FEATURES_DIR / "feature_matrix.csv", index=False)
    print(f"  Saved: {FEATURES_DIR / 'feature_matrix.csv'} "
          f"({(FEATURES_DIR / 'feature_matrix.csv').stat().st_size / 1024:.0f} KB)")

    # Feature dictionary
    generate_feature_dictionary(feature_names)

    # Per-category breakdown
    n_time = sum(1 for n in feature_names if any(n.endswith(s) for s in TIME_FEATURE_DESCRIPTIONS))
    n_freq = sum(1 for n in feature_names if any(n.endswith(s) for s in FREQ_FEATURE_DESCRIPTIONS))
    n_comp = len(feature_names) - n_time - n_freq
    print(f"\nFeature breakdown:")
    print(f"  Time-domain:     {n_time}")
    print(f"  Frequency-domain: {n_freq}")
    print(f"  Composite/cross:  {n_comp}")
    print(f"  Total:            {len(feature_names)}")

    print(f"\n=== D4 feature extraction complete ===")
    print(f"Next: python src/feature_selection.py")


if __name__ == "__main__":
    main()
