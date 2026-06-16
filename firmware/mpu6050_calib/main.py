"""
GY-521 (MPU6050) calibration — MicroPython for ESP32-S3
Wiring: SDA=IO17, SCL=IO18, VCC=3V3, GND=GND, AD0=GND (0x68)

Auto-runs on boot. Drops to REPL after init.
Use collect(label, seconds) to capture data.
"""

from machine import Pin, SoftI2C
from time import sleep_ms, ticks_us, ticks_diff
import struct

SDA = Pin(17)
SCL = Pin(18)
i2c = SoftI2C(sda=SDA, scl=SCL, freq=400000)
MPU_ADDR = 0x68

ACCL_SENS = 4096.0
GYRO_SENS = 16.4
GRAVITY = 9.80665

def init():
    devices = i2c.scan()
    print(f"I2C scan: {[hex(d) for d in devices]}")
    if MPU_ADDR not in devices:
        print("ERROR: MPU6050 not found!")
        return False
    i2c.writeto_mem(MPU_ADDR, 0x6B, b'\x00')
    sleep_ms(50)
    i2c.writeto_mem(MPU_ADDR, 0x19, b'\x13')
    i2c.writeto_mem(MPU_ADDR, 0x1A, b'\x06')
    i2c.writeto_mem(MPU_ADDR, 0x1C, b'\x10')
    i2c.writeto_mem(MPU_ADDR, 0x1B, b'\x18')
    print("MPU6050 OK @ 0x68, +/-8g, +/-2000dps, 50Hz")
    return True

def read():
    data = i2c.readfrom_mem(MPU_ADDR, 0x3B, 14)
    vals = struct.unpack('>7h', data)
    ax = vals[0] / ACCL_SENS * GRAVITY
    ay = vals[1] / ACCL_SENS * GRAVITY
    az = vals[2] / ACCL_SENS * GRAVITY
    gx = vals[4] / GYRO_SENS
    gy = vals[5] / GYRO_SENS
    gz = vals[6] / GYRO_SENS
    return ax, ay, az, gx, gy, gz

def collect(label, seconds):
    n = int(seconds * 50)
    print(f"# COLLECT {label} {seconds}s {n}samples")
    print("# sample,ax,ay,az,gx,gy,gz,label")
    t0 = ticks_us()
    for i in range(n):
        target = t0 + (i + 1) * 20000
        d = ticks_diff(target, ticks_us())
        if d > 0:
            sleep_ms(d // 1000)
        try:
            a = read()
            print(f"{i},{a[0]:.5f},{a[1]:.5f},{a[2]:.5f},{a[3]:.4f},{a[4]:.4f},{a[5]:.4f},{label}")
        except Exception as e:
            print(f"# ERR {e}")
            break
    t = ticks_diff(ticks_us(), t0) / 1e6
    print(f"# DONE {label} {n}samples {t:.1f}s")

def test():
    a = read()
    print(f"ax={a[0]:.3f} ay={a[1]:.3f} az={a[2]:.3f} | gx={a[3]:.2f} gy={a[4]:.2f} gz={a[5]:.2f}")

# Auto-init on boot
if init():
    print("# Ready.")
    print("# Commands: test(), collect('<label>', seconds)")
else:
    print("# Init failed. Check wiring.")
