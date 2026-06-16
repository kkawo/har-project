"""
Capture MPU6050 six-position calibration data from ESP32 serial.
Close Thonny first (or click Stop to disconnect), then run this.

Usage: python calib/capture_mpu6050.py COM7
"""
import serial
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
OUTFILE = ROOT / "calib" / "raw_mpu6050_calib.txt"

POSITIONS = [
    ("+Z_down", 5, "Place sensor flat, label face UP, Z axis down"),
    ("-Z_up", 5, "Flip sensor over, label face DOWN"),
    ("+X_down", 5, "X arrow points DOWN"),
    ("-X_up", 5, "X arrow points UP"),
    ("+Y_down", 5, "Y arrow points DOWN"),
    ("-Y_up", 5, "Y arrow points UP"),
    ("static", 300, "Place sensor still on desk, DON'T touch for 5 min"),
]


def main():
    if len(sys.argv) < 2:
        print("Usage: python calib/capture_mpu6050.py <COM port>")
        print(f"Example: python calib/capture_mpu6050.py COM7")
        sys.exit(1)

    port = sys.argv[1]

    print(f"Connecting to {port} @ 115200...")
    ser = serial.Serial(port, 115200, timeout=1)
    time.sleep(0.5)

    # Flush startup messages
    ser.reset_input_buffer()
    time.sleep(0.5)

    all_lines = []

    def read_until_idle(wait=1.0):
        """Read all available serial data until idle for `wait` seconds."""
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
                        print(line)
                last_read = time.time()
            elif time.time() - last_read > wait:
                break
            else:
                time.sleep(0.05)
        return buf

    # Trigger reset and wait for MicroPython + main.py to boot
    print("\n--- Resetting ESP32 ---")
    ser.dtr = False
    time.sleep(0.3)
    ser.dtr = True
    time.sleep(5)  # ESP32-S3 boot + PSRAM check + MicroPython init takes time

    # Read boot messages
    boot_lines = read_until_idle(wait=3.0)
    all_lines.extend(boot_lines)
    boot_text = "\n".join(boot_lines)
    print(f"--- Boot complete ({len(boot_lines)} lines) ---")

    if "MPU6050 OK" not in boot_text:
        # Maybe main.py didn't auto-run; try soft reset via Ctrl+C then import
        print("\nMPU6050 not auto-detected. Trying manual init...")
        ser.write(b"\r\x03")  # Ctrl+C to stop any running code
        time.sleep(0.5)
        ser.write(b"\r\x03")  # Ctrl+C again
        time.sleep(0.5)
        # Run init manually
        ser.write(b"from main import *\r\n")
        time.sleep(2)
        manual = read_until_idle(wait=2.0)
        all_lines.extend(manual)
        manual_text = "\n".join(manual)
        if "MPU6050 OK" not in manual_text:
            print("\nERROR: MPU6050 not responding.")
            print("Check: SDA=IO17, SCL=IO18, VCC=3V3, GND=GND, AD0=GND")
            ser.close()
            sys.exit(1)

    input("\nPress ENTER to start calibration. Make sure sensor is ready.")

    for i, (label, duration, tip) in enumerate(POSITIONS):
        print(f"\n{'='*60}")
        print(f"[{i+1}/7] {label} — {tip}")
        print(f"  Duration: {duration}s. Keep sensor STILL.")
        print(f"{'='*60}")

        if i > 0:
            input(f"\nReady for '{label}'? Press ENTER...")

        # Send command via REPL
        cmd = f"collect('{label}', {duration})\r\n"
        ser.write(cmd.encode())
        time.sleep(0.3)

        # Read output while collecting
        print(f"\n--- Collecting '{label}' ---")
        lines = read_until_idle(wait=max(2, duration * 0.02))
        all_lines.extend(lines)

        print(f"  Done: {len(lines)} lines captured")

    # Save
    OUTFILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTFILE, "w", encoding="utf-8") as f:
        f.write("\n".join(all_lines))

    print(f"\n{'='*60}")
    print(f"All 7 positions captured!")
    print(f"Saved {len(all_lines)} lines to {OUTFILE}")
    print(f"\nNext: python calib/process_mpu6050_calib.py")
    ser.close()


if __name__ == "__main__":
    main()
