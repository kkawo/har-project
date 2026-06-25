"""
Capture HMC5883L magnetometer calibration data from ESP32 serial.
Requires firmware/har9ch_firmware/main.py flashed to ESP32.

Usage: python calib/capture_mag_calib.py COM7
"""
import serial
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
OUTFILE = ROOT / "calib" / "raw_hmc5883l_calib.txt"


def main():
    if len(sys.argv) < 2:
        print("Usage: python calib/capture_mag_calib.py <COM port>")
        print(f"Example: python calib/capture_mag_calib.py COM7")
        sys.exit(1)

    port = sys.argv[1]
    print(f"Connecting to {port} @ 115200...")
    ser = serial.Serial(port, 115200, timeout=1)
    time.sleep(0.5)
    ser.reset_input_buffer()
    time.sleep(0.5)

    all_lines = []

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
                        print(line)
                last_read = time.time()
            elif time.time() - last_read > wait:
                break
            else:
                time.sleep(0.05)
        return buf

    # Reset ESP32
    print("\n--- Resetting ESP32 ---")
    ser.dtr = False
    time.sleep(0.3)
    ser.dtr = True
    time.sleep(5)

    boot_lines = read_until_idle(wait=3.0)
    all_lines.extend(boot_lines)
    boot_text = "\n".join(boot_lines)
    print(f"--- Boot complete ({len(boot_lines)} lines) ---")

    if "HMC5883L OK" not in boot_text:
        print("\nHMC5883L not found. Checking devices...")
        # Try manual init
        ser.write(b"\r\x03")
        time.sleep(0.5)
        ser.write(b"\r\x03")
        time.sleep(0.5)
        ser.write(b"from main import *\r\n")
        time.sleep(2)
        manual = read_until_idle(wait=2.0)
        all_lines.extend(manual)
        manual_text = "\n".join(manual)
        if "HMC5883L OK" not in manual_text:
            print("\nERROR: HMC5883L not responding.")
            print("Check: SDA=IO17, SCL=IO18, GY-273 VCC=3V3, GND=GND")
            ser.close()
            sys.exit(1)

    print("\n" + "=" * 60)
    print("MAGNETOMETER CALIBRATION — ELLIPSOID FITTING")
    print("=" * 60)
    print("""
INSTRUCTIONS:
  1. Hold the sensor in your hand
  2. Slowly rotate it in ALL directions (figure-8, pitch, roll, yaw)
  3. Try to cover as much of the 3D sphere as possible
  4. Duration: 60 seconds

Press ENTER when ready to start...
""")
    input()

    # Run calibration collection
    print("\n--- START ROTATING THE SENSOR NOW ---")
    cmd = f"calibrate_mag(60)\r\n"
    ser.write(cmd.encode())
    time.sleep(0.3)

    lines = read_until_idle(wait=2.0)
    all_lines.extend(lines)

    print(f"\n  Captured {len(lines)} lines")

    # Save
    OUTFILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTFILE, "w", encoding="utf-8") as f:
        f.write("\n".join(all_lines))

    print(f"\nSaved to {OUTFILE}")
    print(f"\nNext: python calib/process_mag_calib.py")
    ser.close()


if __name__ == "__main__":
    main()
