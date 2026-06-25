"""
HAR 9-channel firmware — MicroPython for ESP32-S3
Wiring: SDA=IO17, SCL=IO18
  - GY-521 (MPU6050): 0x68 (AD0→GND)
  - GY-273 (HMC5883L): 0x1E

Auto-runs on boot. Drops to REPL after init.
Commands:
  test()              — read once, print 9-channel values
  calibrate_mag(sec)  — collect magnetometer data for ellipsoid fitting
  collect(label, sec) — collect 9-channel activity data
"""

from machine import Pin, SoftI2C
from time import sleep_ms, sleep_us, ticks_us, ticks_diff
import struct

SDA = Pin(17)
SCL = Pin(18)
i2c = SoftI2C(sda=SDA, scl=SCL, freq=400000)

MPU_ADDR = 0x68
HMC_ADDR = 0x1E

# MPU6050 sensitivity
ACCL_SENS = 4096.0   # LSB/g  (+/-8g)
GYRO_SENS = 16.4     # LSB/(deg/s)  (+/-2000 deg/s)
GRAVITY = 9.80665


def init_mpu():
    """Initialize MPU6050: +/-8g, +/-2000dps, 50Hz, no sleep."""
    i2c.writeto_mem(MPU_ADDR, 0x6B, b'\x00')  # wake up
    sleep_ms(50)
    i2c.writeto_mem(MPU_ADDR, 0x19, b'\x13')  # SMPRT_DIV = 19 → 50Hz (1kHz/(1+19))
    i2c.writeto_mem(MPU_ADDR, 0x1A, b'\x06')  # DLPF = 6 (5Hz BW for accel, good for HAR)
    i2c.writeto_mem(MPU_ADDR, 0x1C, b'\x10')  # ACCEL_CONFIG: +/-8g
    i2c.writeto_mem(MPU_ADDR, 0x1B, b'\x18')  # GYRO_CONFIG: +/-2000dps


def init_hmc():
    """Initialize HMC5883L: continuous mode, 15Hz, 8-sample avg, +/-1.3Ga."""
    i2c.writeto_mem(HMC_ADDR, 0x00, b'\x70')  # Config A: 8-avg, 15Hz, normal
    i2c.writeto_mem(HMC_ADDR, 0x01, b'\x20')  # Config B: gain=1, +/-1.3Ga (1090 LSB/Gauss)
    i2c.writeto_mem(HMC_ADDR, 0x02, b'\x00')  # Mode: continuous measurement


def init():
    devices = i2c.scan()
    print(f"I2C devices: {[hex(d) for d in devices]}")

    ok = True
    if MPU_ADDR not in devices:
        print("ERROR: MPU6050 (0x68) not found!")
        ok = False
    else:
        init_mpu()
        print("MPU6050 OK @ 0x68  [+/-8g, +/-2000dps, 50Hz]")

    if HMC_ADDR not in devices:
        print("ERROR: HMC5883L (0x1E) not found!")
        ok = False
    else:
        init_hmc()
        print("HMC5883L OK @ 0x1E  [+/-1.3Ga, 15Hz, 8-avg]")

    return ok


def read_mpu():
    """Read MPU6050: returns ax, ay, az (m/s^2), gx, gy, gz (deg/s)."""
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
    """Read HMC5883L: returns mx, my, mz (uT).
    Note: HMC5883L register order is X, Z, Y (not X, Y, Z).
    Gain=1090 LSB/Gauss, 1 Gauss = 100 uT → 1 LSB = 100/1090 ≈ 0.0917 uT."""
    data = i2c.readfrom_mem(HMC_ADDR, 0x03, 6)
    x, z, y = struct.unpack('>3h', data)  # HMC order: X, Z, Y
    scale = 100.0 / 1090.0  # uT per LSB
    mx = x * scale
    my = y * scale
    mz = z * scale
    return mx, my, mz


def read_9ch():
    """Read all 9 channels. Returns (ax, ay, az, gx, gy, gz, mx, my, mz)."""
    ax, ay, az, gx, gy, gz = read_mpu()
    mx, my, mz = read_hmc()
    return ax, ay, az, gx, gy, gz, mx, my, mz


def test():
    """Print a single 9-channel reading."""
    d = read_9ch()
    print(f"ax={d[0]:.3f} ay={d[1]:.3f} az={d[2]:.3f} | "
          f"gx={d[3]:.2f} gy={d[4]:.2f} gz={d[5]:.2f} | "
          f"mx={d[6]:.1f} my={d[7]:.1f} mz={d[8]:.1f}")


def calibrate_mag(seconds=60):
    """Collect raw magnetometer data for ellipsoid fitting.
    Slowly rotate the sensor in all directions during this time."""
    n = int(seconds * 50)
    print(f"# MAG_CALIB {seconds}s {n}samples")
    print("# sample,mx,my,mz")
    t0 = ticks_us()
    for i in range(n):
        target = t0 + (i + 1) * 20000  # 50Hz
        d = ticks_diff(target, ticks_us())
        if d > 0:
            sleep_us(d)
        try:
            mx, my, mz = read_hmc()
            print(f"{i},{mx:.4f},{my:.4f},{mz:.4f}")
        except Exception as e:
            print(f"# ERR {e}")
            break
    elapsed = ticks_diff(ticks_us(), t0) / 1e6
    print(f"# DONE mag_calib {n}samples {elapsed:.1f}s")


def collect(label, seconds):
    """Collect 9-channel activity data at 50Hz.
    Usage: collect('walk', 60)"""
    n = int(seconds * 50)
    print(f"# COLLECT {label} {seconds}s {n}samples")
    print("# sample,ax,ay,az,gx,gy,gz,mx,my,mz,label")
    t0 = ticks_us()
    for i in range(n):
        target = t0 + (i + 1) * 20000
        d = ticks_diff(target, ticks_us())
        if d > 0:
            sleep_us(d)
        try:
            ax, ay, az, gx, gy, gz, mx, my, mz = read_9ch()
            print(f"{i},{ax:.5f},{ay:.5f},{az:.5f},"
                  f"{gx:.4f},{gy:.4f},{gz:.4f},"
                  f"{mx:.2f},{my:.2f},{mz:.2f},{label}")
        except Exception as e:
            print(f"# ERR {e}")
            break
    elapsed = ticks_diff(ticks_us(), t0) / 1e6
    print(f"# DONE {label} {n}samples {elapsed:.1f}s")


# Auto-init on boot
if init():
    print("# Ready. 9-channel HAR firmware.")
    print("#   test()               — single reading")
    print("#   calibrate_mag(sec)   — mag ellipsoid data collection")
    print("#   collect('label', sec)  — activity data collection")
else:
    print("# Init failed. Check wiring: SDA=IO17, SCL=IO18, VCC=3V3, GND=GND")
