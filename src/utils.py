"""
HAR Project - Shared utilities.
"""

import numpy as np
import pandas as pd
from pathlib import Path

# Project root
ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw" / "real2"
CALIB_DIR = DATA_DIR / "calibrated"
REPORTS_DIR = ROOT / "reports"
CALIB_PARAMS = ROOT / "calib" / "calib_params.json"

# Sampling config
FS = 50  # Hz
WINDOW_SEC = 2.56  # seconds
WINDOW_SAMPLES = int(FS * WINDOW_SEC)  # 128 samples
OVERLAP = 0.5

# Activity labels
ACTIVITIES = {
    0: "sit",
    1: "stand",
    2: "walk",
    3: "run",
    4: "upstairs",
    5: "downstairs",
    6: "fall",
}

# Sensor axes
ACC_AXES = ["ax", "ay", "az"]
GYRO_AXES = ["gx", "gy", "gz"]
MAG_AXES = ["mx", "my", "mz"]
ALL_AXES = ACC_AXES + GYRO_AXES + MAG_AXES
