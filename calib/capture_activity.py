# -*- coding: utf-8 -*-
"""
Interactive activity data capture for HAR project.
Requires firmware/har9ch_firmware/main.py flashed to ESP32.

Collects 7 activities × ≥3 trials × N subjects at 50Hz.
Guided workflow with per-trial confirmation.

Usage: python calib/capture_activity.py COM7 S01 [--skip-mag]
  --skip-mag: use when HMC5883L is not connected (6-channel fallback)
"""
import serial
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent

ACTIVITIES = [
    (0, "sit",       60, "Sit quietly on a chair, minimal movement"),
    (1, "stand",     60, "Stand naturally, slight weight shifts OK"),
    (2, "walk",      60, "Walk at normal pace (~1.5 m/s) on flat ground"),
    (3, "run",       60, "Jog at moderate pace (~3 m/s)"),
    (4, "upstairs",  60, "Walk up stairs at normal pace (>=2 floors)"),
    (5, "downstairs",60, "Walk down stairs at normal pace (>=2 floors)"),
    (6, "fall",      15, "Simulate forward/sideways fall onto soft mat, then lie still"),
]

TRIALS_PER_ACTIVITY = 3


def main():
    if len(sys.argv) < 3:
        print("Usage: python calib/capture_activity.py <COM port> <subject_id> [--skip-mag]")
        print(f"Example: python calib/capture_activity.py COM7 S01")
        print(f"         python calib/capture_activity.py COM7 S01 --skip-mag")
        sys.exit(1)

    port = sys.argv[1]
    subject_id = sys.argv[2].upper()
    skip_mag = "--skip-mag" in sys.argv

    if skip_mag:
        print("WARNING: --skip-mag mode (6-channel). Magnetometer columns will be 0.")

    raw_dir = ROOT / "data" / "raw" / subject_id
    raw_dir.mkdir(parents=True, exist_ok=True)

    print(f"Subject: {subject_id}")
    print(f"Activities: {len(ACTIVITIES)}  |  Trials each: {TRIALS_PER_ACTIVITY}")
    print(f"Total trials: {len(ACTIVITIES) * TRIALS_PER_ACTIVITY}")
    print(f"Output dir: {raw_dir}")
    print()

    # Connect
    print(f"Connecting to {port} @ 115200...")
    ser = serial.Serial(port, 115200, timeout=1)
    time.sleep(0.5)
    ser.reset_input_buffer()
    time.sleep(0.5)

    all_files = []

    def read_until_idle(wait=1.0):
        buf = []
        last_read = time.time()
        while True:
            if ser.in_waiting:
                raw = ser.read(ser.in_waiting)
                text = raw.decode("utf-8", errors="replace")
                for line in text.split("\n"):
                    line = line.strip()
                    if line:
                        buf.append(line)
                last_read = time.time()
            elif time.time() - last_read > wait:
                break
            else:
                time.sleep(0.05)
        return buf

    # Reset ESP32
    print("Resetting ESP32 (wait 8s for boot)...")
    ser.dtr = False
    time.sleep(0.5)
    ser.dtr = True
    time.sleep(8)  # ESP32-S3 + MicroPython init needs time

    boot_lines = read_until_idle(wait=4.0)
    boot_text = "\n".join(boot_lines)
    print(f"Boot: {len(boot_lines)} lines")
    # Print last few lines for debugging
    for line in boot_lines[-5:]:
        print(f"  [{line[:80]}]")

    if "MPU6050 OK" not in boot_text and "0x68" not in boot_text:
        print("MPU6050 not detected in boot. Trying manual init...")
        ser.write(b"\r\x03")
        time.sleep(1)
        ser.write(b"\r\x03")
        time.sleep(1)
        ser.write(b"from main import *\r\n")
        time.sleep(3)
        manual = read_until_idle(wait=3.0)
        all_text = boot_text + "\n" + "\n".join(manual)
        if "MPU6050 OK" not in all_text and "0x68" not in all_text:
            print("ERROR: MPU6050 not responding.")
            ser.close()
            sys.exit(1)

    has_hmc = ("HMC5883L OK" in boot_text) or ("0x1e" in boot_text) or ("0x1E" in boot_text)
    if skip_mag:
        has_hmc = False
    print(f"9-channel: {has_hmc} (HMC5883L {'detected' if has_hmc else 'unavailable'})")

    # ─── Collection loop ───
    total_trials = len(ACTIVITIES) * TRIALS_PER_ACTIVITY
    trial_num = 0

    print("\n" + "=" * 60)
    print("DATA COLLECTION PROTOCOL")
    print("=" * 60)
    print("- Hold still between activities (>=30s rest)")
    print("- Cut first/last 2s of each trial in preprocessing")
    print("- Order: static → dynamic (sit → stand → walk → run → up → down → fall)")
    print("- Transitions: start moving 2s BEFORE 'START' to allow trimming")
    print()
    input("Press ENTER to begin data collection...")

    for act_id, act_name, duration, tip in ACTIVITIES:
        for trial in range(1, TRIALS_PER_ACTIVITY + 1):
            trial_num += 1
            print(f"\n{'=' * 60}")
            print(f"[{trial_num}/{total_trials}] {act_name.upper()} — Trial {trial}/{TRIALS_PER_ACTIVITY}")
            print(f"  {tip}")
            print(f"  Duration: {duration}s")
            print(f"{'=' * 60}")

            if trial > 1:
                print(f"  Rest >=30s, then...")
            input(f"\n  Ready for {act_name} trial {trial}? Press ENTER (then start moving)... ")

            # Send collect command
            # For fallback 6-channel mode, wrap with collect_6ch
            cmd = f"collect('{act_name}', {duration})\r\n"
            ser.write(cmd.encode())
            time.sleep(0.3)

            print(f"  *** RECORDING {act_name} trial {trial} ({duration}s) ***")
            lines = read_until_idle(wait=max(3, duration * 0.03))

            # Parse data lines and save to CSV
            data_lines = []
            for line in lines:
                line = line.strip()
                if line.startswith("#") or not line:
                    continue
                data_lines.append(line)

            if len(data_lines) < duration * 25:  # at least 50% of expected
                print(f"  WARNING: Only {len(data_lines)} samples captured "
                      f"(expected ~{duration * 50}). Check connection!")

            # Save to CSV
            filename = f"{subject_id}_{act_name}_{trial:02d}.csv"
            filepath = raw_dir / filename

            with open(filepath, "w", encoding="utf-8") as f:
                if has_hmc:
                    f.write("timestamp,ax,ay,az,gx,gy,gz,mx,my,mz,label,subject_id\n")
                else:
                    f.write("timestamp,ax,ay,az,gx,gy,gz,mx,my,mz,label,subject_id\n")
                timestamp_ms = 0
                for line in data_lines:
                    parts = line.split(",")
                    # Firmware format: sample,ax,ay,az,gx,gy,gz,mx,my,mz,label
                    # or 6ch format: sample,ax,ay,az,gx,gy,gz,label
                    if len(parts) >= 7:
                        try:
                            if len(parts) >= 11:  # 9-channel
                                ax, ay, az = parts[1], parts[2], parts[3]
                                gx, gy, gz = parts[4], parts[5], parts[6]
                                mx, my, mz = parts[7], parts[8], parts[9]
                                label = parts[10].strip()
                            else:  # 6-channel fallback
                                ax, ay, az = parts[1], parts[2], parts[3]
                                gx, gy, gz = parts[4], parts[5], parts[6]
                                mx, my, mz = "0.0", "0.0", "0.0"
                                label = parts[7].strip() if len(parts) > 7 else act_name

                            f.write(f"{timestamp_ms},{ax},{ay},{az},{gx},{gy},{gz},"
                                    f"{mx},{my},{mz},{act_id},{subject_id}\n")
                            timestamp_ms += 20  # 50Hz → 20ms intervals
                        except (ValueError, IndexError):
                            continue

            file_size = filepath.stat().st_size
            all_files.append(filepath)
            print(f"  Saved: {filename} ({file_size:,} bytes, {timestamp_ms/1000:.0f}s)")

    ser.close()

    # Summary
    print(f"\n{'=' * 60}")
    print(f"COLLECTION COMPLETE — Subject {subject_id}")
    print(f"Files saved to: {raw_dir}")
    print(f"Total: {len(all_files)} files")
    for f in all_files:
        print(f"  {f.name}")

    print(f"\nNext steps:")
    print(f"  1. Verify data: python calib/process_mag_calib.py  (if magnetometer calibrated)")
    print(f"  2. Preprocess: python src/preprocess.py")
    print(f"  3. Collect next subject: python calib/capture_activity.py {port} <subject_id>")


if __name__ == "__main__":
    main()
