from machine import Pin, SoftI2C
from time import sleep

i2c = SoftI2C(
    sda=Pin(17),
    scl=Pin(18),
    freq=100000
)

print("Scanning GY-273...")

while True:
    devices = i2c.scan()

    if devices:
        print("Found:", [hex(d) for d in devices])
    else:
        print("No I2C devices found!")

    sleep(2)