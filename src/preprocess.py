"""
D3: Signal preprocessing and windowing.
- Gravity removal (high-pass filter)
- Coordinate alignment
- Low-pass / band-pass filtering
- Sliding window segmentation
- Standardization (fit on train only, via sklearn Pipeline)
"""

import numpy as np
import pandas as pd
from scipy import signal
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from utils import FS, WINDOW_SAMPLES, OVERLAP


def remove_gravity(df, acc_axes=None, cutoff=0.3):
    """Separate gravity (low-pass) from body motion (high-pass)."""
    if acc_axes is None:
        acc_axes = ["ax", "ay", "az"]
    nyq = FS / 2
    b, a = signal.butter(3, cutoff / nyq, btype="high")
    df = df.copy()
    for ax in acc_axes:
        df[ax + "_body"] = signal.filtfilt(b, a, df[ax].values)
        df[ax + "_gravity"] = df[ax] - df[ax + "_body"]
    return df


def butter_lowpass_filter(data, cutoff=20, order=4):
    """Anti-aliasing / denoising low-pass filter."""
    nyq = FS / 2
    b, a = signal.butter(order, cutoff / nyq, btype="low")
    return signal.filtfilt(b, a, data, axis=0)


def sliding_window(df, window_samples=None, overlap=None, label_col="label", subject_col="subject_id"):
    """Segment continuous signal into sliding windows."""
    if window_samples is None:
        window_samples = WINDOW_SAMPLES
    if overlap is None:
        overlap = OVERLAP
    step = int(window_samples * (1 - overlap))
    windows = []
    labels = []
    subjects = []

    for start in range(0, len(df) - window_samples + 1, step):
        end = start + window_samples
        win = df.iloc[start:end]
        windows.append(win)
        # Majority vote for label
        labels.append(win[label_col].mode().iloc[0])
        subjects.append(win[subject_col].iloc[0])

    return windows, np.array(labels), np.array(subjects)


def build_preprocessing_pipeline():
    """Build a sklearn Pipeline to prevent data leakage."""
    return Pipeline([
        ("scaler", StandardScaler()),
    ])


if __name__ == "__main__":
    print("Preprocessing module loaded. Use sliding_window() and build_preprocessing_pipeline().")
