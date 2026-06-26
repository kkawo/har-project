# -*- coding: utf-8 -*-
"""
HAR offline data logger v2 — multi-trial per activity.
Flash once, runs all trials in one go. Power with battery bank.

Sensor orientation: X down (toward ground), Y forward (walking direction).
Strap firmly on waist/belt.

LED signals (ALL WHITE, count the blinks):
  1 blink  = sit       2 blinks = stand    3 blinks = walk
  4 blinks = run       5 blinks = upstairs  6 blinks = downstairs
  7 blinks = fall
  Long white pulse  = recording
  1 long blink = trial done   3 long = ALL DONE
"""
from machine import Pin, SoftI2C
from time import sleep_ms, sleep_us, ticks_us, ticks_diff
import struct

# neopixel imported AFTER early I2C test (order matters, like main_wifi.py)

SDA = Pin(17)
SCL = Pin(18)
MPU_ADDR = 0x68
ACCL_SENS = 4096.0    # ±8g
GYRO_SENS = 16.4      # ±2000°/s
GRAVITY = 9.80665

# Early I2C test — "primes" the bus before anything else (like main_wifi.py)
_test_i2c = SoftI2C(sda=SDA, scl=SCL, freq=100000)
_test_who = _test_i2c.readfrom_mem(MPU_ADDR, 0x75, 1)[0]
print(f"EARLY WHO_AM_I: 0x{_test_who:02X}")
_test_d = _test_i2c.readfrom_mem(MPU_ADDR, 0x3B, 14)
_test_az = struct.unpack(">h", _test_d[4:6])[0]
print(f"EARLY ACCEL_Z: {_test_az}")

import neopixel, os
np = neopixel.NeoPixel(Pin(48), 1)
i2c = None  # Created in init_mpu()

# ======== CONFIG ========
SUBJECT = "S01"        # ← CHANGE to "S02" for second person
PAUSE_SEC = 8           # countdown between trials
TRIALS_PER = 3          # trials per activity (3-5 recommended)

ACTIVITIES = [
    # ("sit", 30), ("stand", 30), ("walk", 30), ("run", 30),  # done
    ("upstairs", 30),
    ("downstairs", 30),
    ("fall", 15),
]

SEQUENCE = []
for act, dur in ACTIVITIES:
    for t in range(1, TRIALS_PER + 1):
        SEQUENCE.append((act, t, dur))
# =========================


def init_mpu():
    """Configure MPU6050: ±8g, ±2000°/s, 50Hz."""
    global i2c
    for attempt in range(3):
        try:
            i2c = SoftI2C(sda=SDA, scl=SCL, freq=100000)
            who = i2c.readfrom_mem(MPU_ADDR, 0x75, 1)[0]
            if who != 0x68:
                raise RuntimeError(f"WHO_AM_I: 0x{who:02X}")
            i2c.writeto_mem(MPU_ADDR, 0x6B, b'\x00'); sleep_ms(100)
            i2c.writeto_mem(MPU_ADDR, 0x19, b'\x13')
            i2c.writeto_mem(MPU_ADDR, 0x1A, b'\x06')
            i2c.writeto_mem(MPU_ADDR, 0x1C, b'\x10')
            i2c.writeto_mem(MPU_ADDR, 0x1B, b'\x18')
            i2c.readfrom_mem(MPU_ADDR, 0x3B, 14)  # Verify
            return
        except Exception as e:
            print(f"  MPU retry {attempt+1}: {e}")
            sleep_ms(500)
    raise RuntimeError("MPU6050 init failed")


def read_mpu():
    for _ in range(3):
        try:
            data = i2c.readfrom_mem(MPU_ADDR, 0x3B, 14)
            vals = struct.unpack('>7h', data)
            ax = vals[0] / ACCL_SENS * GRAVITY
            ay = vals[1] / ACCL_SENS * GRAVITY
            az = vals[2] / ACCL_SENS * GRAVITY
            gx = vals[4] / GYRO_SENS
            gy = vals[5] / GYRO_SENS
            gz = vals[6] / GYRO_SENS
            return ax, ay, az, gx, gy, gz
        except OSError:
            sleep_ms(5)
    raise OSError("MPU read failed")


# Activity colors
ACT_COLOR = {
    1: (0, 0, 255),     # sit → Blue
    2: (0, 255, 255),   # stand → Cyan
    3: (0, 255, 0),     # walk → Green
    4: (255, 255, 0),   # run → Yellow
    5: (255, 165, 0),   # upstairs → Orange
    6: (128, 0, 255),   # downstairs → Purple
    7: (255, 0, 0),     # fall → Red
}
WHITE = (60, 60, 60)
DIM = 0.3


def led_off():
    np[0] = (0, 0, 0); np.write()

def led_raw(r, g, b):
    np[0] = (r, g, b); np.write()

def show_activity(code, dim=False):
    r, g, b = ACT_COLOR[code]
    if dim: r, g, b = int(r*DIM), int(g*DIM), int(b*DIM)
    led_raw(r, g, b)

def blink_white(times=1, on_ms=400, off_ms=300):
    for _ in range(times):
        led_raw(*WHITE); sleep_ms(on_ms)
        led_off(); sleep_ms(off_ms)


def reinit_sensors():
    global i2c
    try:
        i2c = SoftI2C(sda=SDA, scl=SCL, freq=100000)
        sleep_ms(100)
        init_mpu()
        sleep_ms(200)
        print("  [reinit] OK")
        return True
    except Exception as e:
        print("  [reinit] FAILED:", e)
        return False


def record(activity, trial, duration):
    n = int(duration * 50)
    fname = f"{SUBJECT}_{activity}_{trial:02d}.csv"
    label_id = _id(activity)

    with open(fname, "w") as f:
        f.write("timestamp,ax,ay,az,gx,gy,gz,mx,my,mz,label,subject_id\n")

        t0 = ticks_us()
        ok, errors = 0, 0
        for i in range(n):
            target = t0 + (i + 1) * 20000
            d = ticks_diff(target, ticks_us())
            if d > 0:
                sleep_us(d)
            try:
                ax, ay, az, gx, gy, gz = read_mpu()
                ts = i * 20
                f.write(
                    f"{ts},{ax:.5f},{ay:.5f},{az:.5f},"
                    f"{gx:.4f},{gy:.4f},{gz:.4f},"
                    f"0.00,0.00,0.00,{label_id},{SUBJECT}\n"
                )
                ok += 1
            except Exception as e:
                errors += 1
                f.write(f"# ERR row {i}: {e}\n")
                if errors <= 3:
                    print(f"  I2C error at row {i}, reinit...")
                    if reinit_sensors():
                        continue
                break

        elapsed = ticks_diff(ticks_us(), t0) / 1e6
        f.write(f"# DONE {ok} samples in {elapsed:.1f}s\n")

    size = os.stat(fname)[6]
    print(f"  SAVED {fname}  {ok}samples  {size}bytes  {elapsed:.1f}s")
    return fname, ok


def _id(label):
    mapping = {"sit": 0, "stand": 1, "walk": 2, "run": 3,
               "upstairs": 4, "downstairs": 5, "fall": 6}
    return mapping.get(label, -1)


# ═══════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════

print("\n=== HAR OFFLINE LOGGER v2 ===")
print("  X→DOWN  Y→FORWARD  waist strap tight!")
print("")

init_mpu()
print("MPU6050 OK (±8g, ±2000°/s, 50Hz)")

TOTAL = len(SEQUENCE)
total_sec = sum(d for _, _, d in SEQUENCE)
total_min = (total_sec + PAUSE_SEC * TOTAL) / 60
print(f"\n{TOTAL} trials, ~{total_min:.0f} min | S={SUBJECT} | x{TRIALS_PER}\n")

ACT_CODE = {"sit": 1, "stand": 2, "walk": 3, "run": 4,
            "upstairs": 5, "downstairs": 6, "fall": 7}

for idx, (activity, trial, duration) in enumerate(SEQUENCE):
    code = ACT_CODE[activity]
    print(f"\n=== {idx+1}/{TOTAL}: {activity} #{trial:02d} ({duration}s) ===")

    # Health check before each trial
    try:
        i2c.readfrom_mem(MPU_ADDR, 0x75, 1)
    except Exception:
        print("  MPU6050 lost! Reinit...")
        reinit_sensors()

    # Show activity color 3s
    for _ in range(3):
        show_activity(code); sleep_ms(700)
        led_off(); sleep_ms(300)

    # Countdown with dim pulses
    pause = 3 if idx == 0 else PAUSE_SEC
    for sec in range(pause, 0, -1):
        print(f"  {sec}... ({activity})")
        show_activity(code, dim=True); sleep_ms(400)
        led_off(); sleep_ms(600)

    # Record
    show_activity(code)
    fname, n = record(activity, trial, duration)
    led_off()

    threshold = int(duration * 50 * 0.9)
    if n < threshold:
        print(f"  -> WARN: {fname} only {n}/{int(duration*50)} samples!")
        blink_white(3, on_ms=150, off_ms=150)
    elif idx + 1 < TOTAL:
        nxt = SEQUENCE[idx + 1]
        print(f"  -> {fname} saved. Next: {nxt[0]} #{nxt[1]:02d}")
        blink_white(1)
    else:
        print(f"  -> {fname} saved.\n=== ALL {TOTAL} DONE! ===")
        for c in [4, 1, 2, 3, 5, 6, 7]:
            show_activity(c); sleep_ms(300)
        led_off()
        blink_white(3)
        print("Download CSV files from Thonny.")
