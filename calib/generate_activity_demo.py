"""
Generate realistic 9-channel demo activity data for HAR pipeline validation.
Produces 7 activities x 3 trials x 2 subjects with realistic signal patterns.

Usage: python calib/generate_activity_demo.py
Output: data/raw/S01/*.csv, data/raw/S02/*.csv
Then run: python src/preprocess.py
"""
import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

import numpy as np
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).parent.parent
FS = 50  # Hz
G = 9.80665

# Activities: (id, name, duration_sec, trials)
ACTIVITIES = [
    (0, "sit", 65, 3),
    (1, "stand", 65, 3),
    (2, "walk", 65, 3),
    (3, "run", 65, 3),
    (4, "upstairs", 65, 3),
    (5, "downstairs", 65, 3),
    (6, "fall", 15, 3),
]

# Calibration parameters (realistic for GY-521 + HMC5883L)
ACC_BIAS = np.array([0.10, -0.07, 0.22])
ACC_SCALE = np.array([0.994, 1.008, 0.988])
GYRO_BIAS = np.array([-4.2, -1.2, 0.6])
MAG_HARD = np.array([10.0, -7.0, 4.0])
MAG_SOFT = np.array([[1.06, 0.03, 0.01],
                     [0.03, 0.94, -0.02],
                     [0.01, -0.02, 1.04]])


def add_sensor_noise(n, accel_std=0.03, gyro_std=0.5, mag_std=0.8):
    """Generate baseline sensor noise."""
    return {
        "acc": np.random.normal(0, accel_std, (n, 3)),
        "gyro": np.random.normal(0, gyro_std, (n, 3)),
        "mag": np.random.normal(0, mag_std, (n, 3)),
    }


def simulate_sit(n_samples, subject_variant=0):
    """Sitting: very low amplitude, breathing micro-movements."""
    t = np.arange(n_samples) / FS
    noise = add_sensor_noise(n_samples, accel_std=0.005, gyro_std=0.3, mag_std=0.3)

    # Gravity: sensor flat on waist (Z up approximately)
    acc = np.column_stack([
        np.zeros(n_samples),
        np.zeros(n_samples),
        np.ones(n_samples) * G,
    ]) + noise["acc"]

    # Slight breathing rhythm
    breath = 0.02 * np.sin(2 * np.pi * 0.3 * t + subject_variant * 0.5)
    acc[:, 1] += breath

    gyro = noise["gyro"] + np.random.normal(0, 0.05, (n_samples, 3))  # very still

    # Magnetometer: roughly constant heading
    mag = np.column_stack([
        20 + 2 * np.sin(subject_variant),
        -10 + 1 * np.cos(subject_variant),
        35 + 3 * np.sin(subject_variant * 0.7),
    ]) + noise["mag"] + np.random.normal(0, 0.3, (n_samples, 3))

    return acc, gyro, mag


def simulate_stand(n_samples, subject_variant=0):
    """Standing: slightly more sway than sitting, posture adjustments."""
    t = np.arange(n_samples) / FS
    noise = add_sensor_noise(n_samples, accel_std=0.01, gyro_std=0.5, mag_std=0.4)

    acc = np.column_stack([
        np.zeros(n_samples),
        np.zeros(n_samples),
        np.ones(n_samples) * G,
    ]) + noise["acc"]

    # Postural sway (~0.5 Hz)
    sway = 0.08 * np.sin(2 * np.pi * 0.5 * t + subject_variant * 0.8)
    acc[:, 0] += sway
    acc[:, 1] += 0.05 * np.sin(2 * np.pi * 0.7 * t + subject_variant)

    # Occasional weight shift (every ~15s)
    for shift_t in range(15 * FS, n_samples, 15 * FS):
        if shift_t + FS < n_samples:
            acc[shift_t:shift_t + FS, 2] += 0.15
            gyro_shift = np.random.normal(0, 2, FS)
            pass

    gyro = noise["gyro"] + 0.3 * np.sin(2 * np.pi * 0.5 * t + subject_variant)[:, np.newaxis]

    mag = np.column_stack([
        20 + 2 * np.sin(subject_variant),
        -10 + 1 * np.cos(subject_variant),
        35 + 3 * np.sin(subject_variant * 0.7),
    ]) + noise["mag"]

    return acc, gyro, mag


def simulate_walk(n_samples, subject_variant=0):
    """Walking: ~1.8 Hz gait cycle, clear periodic pattern."""
    t = np.arange(n_samples) / FS
    noise = add_sensor_noise(n_samples, accel_std=0.08, gyro_std=3.0, mag_std=1.0)

    f_walk = 1.8 + subject_variant * 0.1  # Hz
    omega = 2 * np.pi * f_walk

    # Gait pattern: heel strike → push off
    gait = np.sin(omega * t)
    gait_2 = np.sin(2 * omega * t)  # harmonic

    acc = np.column_stack([
        0.6 * gait + 0.3 * gait_2,           # X: lateral sway
        1.5 * gait + 0.4 * gait_2,           # Y: forward-back (main)
        G + 0.9 * gait + 0.3 * gait_2,       # Z: vertical bounce
    ]) + noise["acc"]

    gyro = np.column_stack([
        30 * gait + 10 * gait_2,             # roll
        50 * gait + 15 * gait_2,             # pitch (leg swing)
        20 * np.cos(omega * t + 0.5),        # yaw
    ]) + noise["gyro"]

    # Magnetometer: oscillates with heading changes
    mag = np.column_stack([
        20 + 5 * np.sin(omega * t * 0.3 + subject_variant),
        -10 + 8 * np.cos(omega * t * 0.3 + subject_variant),
        35 + 2 * np.sin(omega * t + subject_variant),
    ]) + noise["mag"]

    return acc, gyro, mag


def simulate_run(n_samples, subject_variant=0):
    """Running: ~3 Hz, higher amplitude than walking, higher impact."""
    t = np.arange(n_samples) / FS
    noise = add_sensor_noise(n_samples, accel_std=0.15, gyro_std=5.0, mag_std=1.5)

    f_run = 2.9 + subject_variant * 0.2
    omega = 2 * np.pi * f_run

    gait = np.sin(omega * t)
    impact = np.abs(np.sin(omega * t * 0.5))  # heel strike envelope

    acc = np.column_stack([
        1.0 * gait + 0.5 * np.sin(2 * omega * t),
        2.5 * gait + 0.8 * np.sin(2 * omega * t),
        G + 2.0 * gait + 1.5 * impact,
    ]) + noise["acc"]

    gyro = np.column_stack([
        60 * gait + 25 * np.sin(2 * omega * t),
        100 * gait + 30 * np.sin(2 * omega * t),
        40 * np.cos(omega * t + 0.7),
    ]) + noise["gyro"]

    mag = np.column_stack([
        20 + 8 * np.sin(omega * t * 0.4 + subject_variant),
        -10 + 12 * np.cos(omega * t * 0.4 + subject_variant),
        35 + 5 * np.sin(omega * t + subject_variant),
    ]) + noise["mag"]

    return acc, gyro, mag


def simulate_upstairs(n_samples, subject_variant=0):
    """Going upstairs: ~1.5 Hz, higher vertical acceleration, forward lean."""
    t = np.arange(n_samples) / FS
    noise = add_sensor_noise(n_samples, accel_std=0.10, gyro_std=3.5, mag_std=1.0)

    f_step = 1.5 + subject_variant * 0.1
    omega = 2 * np.pi * f_step

    step = np.sin(omega * t)
    # Upstairs: stronger vertical push, slight forward lean (Y gravity component)
    vertical = 1.3 * step + 0.4 * np.abs(np.sin(omega * t * 0.5))

    acc = np.column_stack([
        0.5 * step + 0.2 * np.sin(2 * omega * t),
        G * 0.15 + 1.2 * step,               # forward lean + motion
        G * 0.98 + vertical,
    ]) + noise["acc"]

    gyro = np.column_stack([
        25 * step + 10 * np.sin(2 * omega * t),
        45 * step + 15 * np.sin(2 * omega * t),
        15 * np.cos(omega * t + 0.4),
    ]) + noise["gyro"]

    mag = np.column_stack([
        20 + 4 * np.sin(omega * t * 0.3 + subject_variant),
        -10 + 6 * np.cos(omega * t * 0.3 + subject_variant),
        35 + 4 * np.sin(omega * t + subject_variant),
    ]) + noise["mag"]

    return acc, gyro, mag


def simulate_downstairs(n_samples, subject_variant=0):
    """Going downstairs: similar to upstairs but higher impact on landing."""
    t = np.arange(n_samples) / FS
    noise = add_sensor_noise(n_samples, accel_std=0.10, gyro_std=3.5, mag_std=1.0)

    f_step = 1.6 + subject_variant * 0.1
    omega = 2 * np.pi * f_step

    step = np.sin(omega * t)
    # Downstairs: sharper impact on landing, less vertical push
    impact = np.abs(np.sin(omega * t * 0.5)) ** 1.5  # sharper peaks
    vertical = 0.9 * step + 0.7 * impact

    acc = np.column_stack([
        0.6 * step + 0.2 * np.sin(2 * omega * t),
        -G * 0.10 + 1.1 * step,              # slight backward lean
        G * 0.98 + vertical,
    ]) + noise["acc"]

    gyro = np.column_stack([
        28 * step + 12 * np.sin(2 * omega * t),
        48 * step + 18 * np.sin(2 * omega * t),
        18 * np.cos(omega * t + 0.5),
    ]) + noise["gyro"]

    mag = np.column_stack([
        20 + 4 * np.sin(omega * t * 0.3 + subject_variant + 0.3),
        -10 + 6 * np.cos(omega * t * 0.3 + subject_variant + 0.3),
        35 + 4 * np.sin(omega * t + subject_variant + 0.3),
    ]) + noise["mag"]

    return acc, gyro, mag


def simulate_fall(n_samples, subject_variant=0):
    """Fall: impact spike then quiet. 15s total: ~3s pre-fall, ~1s impact, ~11s lying still."""
    noise = add_sensor_noise(n_samples, accel_std=0.02, gyro_std=1.0, mag_std=0.5)
    t = np.arange(n_samples) / FS

    acc = np.column_stack([
        np.zeros(n_samples),
        np.zeros(n_samples),
        np.ones(n_samples) * G,
    ])

    gyro = np.zeros((n_samples, 3))
    mag = np.column_stack([
        20 + 2 * np.sin(subject_variant),
        -10 + 1 * np.cos(subject_variant),
        35 + 3 * np.sin(subject_variant * 0.7),
    ]) + noise["mag"]

    # Impact at ~3 seconds
    impact_start = int(3 * FS)
    impact_dur = int(0.8 * FS)
    impact_end = min(impact_start + impact_dur, n_samples)

    # Forward fall: large spike in Y acceleration, X rotation
    acc[impact_start:impact_end, 1] += 4.0 * np.exp(-2 * np.arange(impact_dur) / FS)
    acc[impact_start:impact_end, 2] -= 1.5 * np.exp(-3 * np.arange(impact_dur) / FS)
    acc[impact_start:impact_end, 0] += 2.0 * np.exp(-2.5 * np.arange(impact_dur) / FS)

    gyro[impact_start:impact_end, 0] += 150 * np.exp(-3 * np.arange(impact_dur) / FS)
    gyro[impact_start:impact_end, 1] += 80 * np.exp(-2.5 * np.arange(impact_dur) / FS)

    # After impact: sensor on its side (gravity shifts)
    post_impact = impact_end
    acc[post_impact:, :] = np.array([0, G * 0.7, G * 0.7]) + noise["acc"][post_impact:]

    # Small residual tremor after fall
    acc[post_impact:post_impact + FS, :] += np.random.normal(0, 0.2, (FS, 3))

    return acc, gyro, mag


# Map activity to simulation function
SIMULATORS = {
    0: simulate_sit,
    1: simulate_stand,
    2: simulate_walk,
    3: simulate_run,
    4: simulate_upstairs,
    5: simulate_downstairs,
    6: simulate_fall,
}


def apply_uncalibration(acc, gyro, mag):
    """Apply inverse calibration to produce 'raw' sensor readings."""
    # acc_raw = acc_cal / scale + bias
    acc_raw = acc / ACC_SCALE + ACC_BIAS
    gyro_raw = gyro + GYRO_BIAS
    # mag_raw = mag_cal @ inv(soft_iron) + hard_iron
    mag_soft_inv = np.linalg.inv(MAG_SOFT)
    mag_raw = mag @ mag_soft_inv.T + MAG_HARD
    return acc_raw, gyro_raw, mag_raw


def generate_subject_data(subject_id, seed=42):
    """Generate all activity data for one subject."""
    np.random.seed(seed)
    subject_variant = hash(subject_id) % 100 / 100.0

    raw_dir = ROOT / "data" / "raw" / subject_id
    raw_dir.mkdir(parents=True, exist_ok=True)

    files_created = []

    for act_id, act_name, duration, n_trials in ACTIVITIES:
        n_samples = int(duration * FS)
        simulator = SIMULATORS[act_id]

        for trial in range(1, n_trials + 1):
            # Add trial-to-trial variation
            trial_seed = seed + act_id * 10 + trial * 100
            np.random.seed(trial_seed)

            acc, gyro, mag = simulator(n_samples, subject_variant + trial * 0.05)
            acc_raw, gyro_raw, mag_raw = apply_uncalibration(acc, gyro, mag)

            # Build DataFrame
            df = pd.DataFrame({
                "timestamp": np.arange(n_samples) * 20,  # ms, 50Hz
                "ax": acc_raw[:, 0],
                "ay": acc_raw[:, 1],
                "az": acc_raw[:, 2],
                "gx": gyro_raw[:, 0],
                "gy": gyro_raw[:, 1],
                "gz": gyro_raw[:, 2],
                "mx": mag_raw[:, 0],
                "my": mag_raw[:, 1],
                "mz": mag_raw[:, 2],
                "label": act_id,
                "subject_id": subject_id,
            })

            fname = f"{subject_id}_{act_name}_{trial:02d}.csv"
            fpath = raw_dir / fname
            df.to_csv(fpath, index=False)
            files_created.append(fpath)

    return files_created


def main():
    print("=== Generating Demo Activity Dataset ===\n")

    subjects = ["S01", "S02"]
    seeds = [42, 123]

    total_files = 0
    for subj, seed in zip(subjects, seeds):
        print(f"Generating {subj} data...")
        files = generate_subject_data(subj, seed=seed)
        total_files += len(files)
        for f in sorted(files):
            print(f"  {f.name}")

    print(f"\n{'=' * 60}")
    print(f"Generated {total_files} files for {len(subjects)} subjects")
    print(f"  - 7 activities x 3 trials = 21 files/subject")
    print(f"  - {'2 subjects x 21 = 42 files' if len(subjects) == 2 else ''}")
    print(f"\nNext: python src/preprocess.py")
    print(f"      python calib/generate_demo_data.py  (if calib_params.json needed)")


if __name__ == "__main__":
    main()
