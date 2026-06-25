# -*- coding: utf-8 -*-
"""
HAR offline data logger — continuous auto-sequencing version.
Flash once, runs all 21 trials in one go. Power with battery bank.

Between trials: 8-second countdown (LED blinks) to get into position.
LED signals:
  White blinks = trial number
  Orange blinks = countdown (positioning)
  Green solid = recording
  Blue blink = trial done, moving to next
  Rainbow = all 21 trials complete
"""
from machine import Pin, SoftI2C
from time import sleep_ms, sleep_us, ticks_us, ticks_diff
import neopixel
import struct
import os

SDA = Pin(17)
SCL = Pin(18)
i2c = SoftI2C(sda=SDA, scl=SCL, freq=400000)
np = neopixel.NeoPixel(Pin(48), 1)

MPU_ADDR = 0x68
HMC_ADDR = 0x1E
ACCL_SENS = 4096.0
GYRO_SENS = 16.4
GRAVITY = 9.80665

# ======== CONFIG ========
SUBJECT = "S02"
PAUSE_SEC = 8  # pause between trials for repositioning

SEQUENCE = [
    ("sit", 1, 65),
    ("stand", 1, 65),
    ("walk", 1, 65),
    ("run", 1, 65),
    ("upstairs", 1, 65),
    ("downstairs", 1, 65),
    ("fall", 1, 15),
]
# =========================


def init_mpu():
    i2c.writeto_mem(MPU_ADDR, 0x6B, b'\x00')
    sleep_ms(50)
    i2c.writeto_mem(MPU_ADDR, 0x19, b'\x13')
    i2c.writeto_mem(MPU_ADDR, 0x1A, b'\x06')
    i2c.writeto_mem(MPU_ADDR, 0x1C, b'\x10')
    i2c.writeto_mem(MPU_ADDR, 0x1B, b'\x18')


def init_hmc():
    i2c.writeto_mem(HMC_ADDR, 0x00, b'\x70')
    i2c.writeto_mem(HMC_ADDR, 0x01, b'\x20')
    i2c.writeto_mem(HMC_ADDR, 0x02, b'\x00')


def read_mpu():
    data = i2c.readfrom_mem(MPU_ADDR, 0x3B, 14)
    vals = struct.unpack('>7h', data)
    ax = vals[0] / ACCL_SENS * GRAVITY
    ay = vals[1] / ACCL_SENS * GRAVITY
    az = vals[2] / ACCL_SENS * GRAVITY
    gx = vals[4] / GYRO_SENS
    gy = vals[5] / GYRO_SENS
    gz = vals[6] / GYRO_SENS
    return ax, ay, az, gx, gy, gz


def read_hmc():
    data = i2c.readfrom_mem(HMC_ADDR, 0x03, 6)
    x, z, y = struct.unpack('>3h', data)
    scale = 100.0 / 1090.0
    return x * scale, y * scale, z * scale


def led_off():
    np[0] = (0, 0, 0)
    np.write()

def led_color(r, g, b):
    np[0] = (r, g, b)
    np.write()

def blink(times, color=(255, 165, 0), duration=300):
    for _ in range(times):
        led_color(*color)
        sleep_ms(duration)
        led_off()
        sleep_ms(duration)


def reinit_sensors():
    """Re-init I2C and both sensors after an error."""
    global i2c
    try:
        i2c = SoftI2C(sda=SDA, scl=SCL, freq=100000)  # drop to 100kHz for stability
        sleep_ms(100)
        devices = i2c.scan()
        if MPU_ADDR in devices:
            init_mpu()
            sleep_ms(10)
        else:
            return False
        if HMC_ADDR in devices:
            init_hmc()
            sleep_ms(10)
        print(f"  [reinit] I2C OK: {[hex(d) for d in devices]}")
        return True
    except Exception as e:
        print(f"  [reinit] FAILED: {e}")
        return False


def record(activity, trial, duration):
    n = int(duration * 50)
    fname = f"{SUBJECT}_{activity}_{trial:02d}.csv"

    lines = ["timestamp,ax,ay,az,gx,gy,gz,mx,my,mz,label,subject_id\n"]

    t0 = ticks_us()
    ok = 0
    errors = 0
    for i in range(n):
        target = t0 + (i + 1) * 20000
        d = ticks_diff(target, ticks_us())
        if d > 0:
            sleep_us(d)
        try:
            ax, ay, az, gx, gy, gz = read_mpu()
            mx, my, mz = read_hmc()
            ts = i * 20
            lines.append(f"{ts},{ax:.5f},{ay:.5f},{az:.5f},"
                        f"{gx:.4f},{gy:.4f},{gz:.4f},"
                        f"{mx:.2f},{my:.2f},{mz:.2f},{_id(activity)},{SUBJECT}\n")
            ok += 1
        except Exception as e:
            errors += 1
            lines.append(f"# ERR row {i}: {e}\n")
            if errors <= 3:
                print(f"  I2C error at row {i}, reinitializing...")
                if reinit_sensors():
                    continue  # retry next row
            break  # too many errors, stop this trial

    elapsed = ticks_diff(ticks_us(), t0) / 1e6
    lines.append(f"# DONE {ok} samples in {elapsed:.1f}s\n")

    with open(fname, "w") as f:
        f.write("".join(lines))

    size = os.stat(fname)[6]
    print(f"SAVED {fname}  {ok}samples  {size}bytes  {elapsed:.1f}s")
    return fname, ok


def _id(label):
    mapping = {"sit": 0, "stand": 1, "walk": 2, "run": 3,
               "upstairs": 4, "downstairs": 5, "fall": 6}
    return mapping.get(label, -1)


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

print("\n=== HAR OFFLINE LOGGER (continuous) ===")

devices = i2c.scan()
print(f"I2C: {[hex(d) for d in devices]}")

if MPU_ADDR not in devices:
    print("ERROR: MPU6050 not found!")
    blink(10, (255, 0, 0), 100)
    raise SystemExit

init_mpu()
print("MPU6050 OK")
if HMC_ADDR in devices:
    init_hmc()
    print("HMC5883L OK")
else:
    print("WARN: HMC5883L not found")

TOTAL = len(SEQUENCE)
print(f"\n{TOTAL} trials total. ~{PAUSE_SEC}s pause between trials.")
print("Watch the LED for guidance.\n")

for idx, (activity, trial, duration) in enumerate(SEQUENCE):
    print(f"\n=== Trial {idx+1}/{TOTAL}: {activity} #{trial:02d} ({duration}s) ===")

    # Health check: reinit if sensors lost
    devices = i2c.scan()
    if MPU_ADDR not in devices:
        print("  MPU6050 lost! Reinitializing...")
        reinit_sensors()

    # Signal trial number (white)
    blink(idx + 1, (255, 255, 255), 200)
    sleep_ms(600)

    # Countdown (orange), longer for first trial
    pause = 3 if idx == 0 else PAUSE_SEC
    for sec in range(pause, 0, -1):
        print(f"  {sec}...")
        blink(1, (255, 165, 0), 300)
        sleep_ms(700)

    # Record (green)
    led_color(0, 255, 0)
    fname, n = record(activity, trial, duration)
    led_off()

    # Trial done
    if n < int(duration * 50 * 0.9):  # less than 90% samples = error
        print(f"  -> WARNING: {fname} only {n}/{int(duration*50)} samples!")
        blink(3, (255, 0, 0), 300)  # red = incomplete
    elif idx + 1 < TOTAL:
        print(f"  -> {fname} saved. Next: {SEQUENCE[idx+1][0]} #{SEQUENCE[idx+1][1]:02d}")
        blink(1, (0, 0, 255), 500)  # blue = normal
    else:
        print(f"  -> {fname} saved.")
        print(f"\n=== ALL {TOTAL} TRIALS COMPLETE! ===")
        for _ in range(3):
            led_color(255, 0, 0); sleep_ms(200)
            led_color(0, 255, 0); sleep_ms(200)
            led_color(0, 0, 255); sleep_ms(200)
        led_off()
        print("Connect to Thonny and download all CSV files.")
