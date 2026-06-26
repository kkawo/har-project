"""
I²C 总线诊断脚本 — 排查 ENODEV 根因
只检查总线电平和短路，不依赖传感器
"""

from machine import Pin, SoftI2C
from time import sleep_ms

SDA_PIN = 17
SCL_PIN = 18

print("=" * 50)
print("I²C 总线诊断")
print("=" * 50)

# ─── Step 1: GPIO 模式检查 SDA/SCL 是否被拉低 ──
print("\n[1] 检查 SDA/SCL 电平 (GPIO 输入模式)...")

sda = Pin(SDA_PIN, Pin.IN, Pin.PULL_UP)
scl = Pin(SCL_PIN, Pin.IN, Pin.PULL_UP)
sleep_ms(50)

sda_val = sda.value()
scl_val = scl.value()

print(f"    SDA (IO{SDA_PIN}): {'HIGH ✅' if sda_val else 'LOW ❌ 可能短路到GND!'}")
print(f"    SCL (IO{SCL_PIN}): {'HIGH ✅' if scl_val else 'LOW ❌ 可能短路到GND!'}")

if not sda_val or not scl_val:
    print("\n    ⚠️ SDA/SCL 被拉低！")
    print("    排查：")
    print("    1. 用万用表电阻档量 SDA-GND、SCL-GND 是否 < 100Ω")
    print("    2. 检查 J1/J2/J4 排母是否有焊锡桥接到 GND")
    print("    3. 断开电源，量 IO17-GND、IO18-GND 电阻")
    print("=" * 50)

# ─── Step 2: I²C 扫描 ──
print("\n[2] I²C 总线扫描...")

i2c = SoftI2C(sda=Pin(SDA_PIN), scl=Pin(SCL_PIN), freq=100000)
devices = i2c.scan()
print(f"    发现 {len(devices)} 个设备: {[hex(d) for d in devices]}")

if 0x68 not in devices:
    print("    ❌ MPU6050 (0x68) 未检测到")
if 0x1E not in devices:
    print("    ❌ HMC5883L (0x1E) 未检测到")

if len(devices) == 0:
    print("\n    总线上零设备，可能原因：")
    print("    - SDA/SCL 短路到 GND（最常见）")
    print("    - 上拉电阻 R1/R2 (4.7kΩ) 未焊接或虚焊")
    print("    - IO17/IO18 到排母的 PCB 走线断路")
    print("    - MPU6050 模块本身未插入/方向错误")
    print()
    print("    排查步骤：")
    print("    A. 肉眼检查 J4 (GY-273) 排母焊点，SDA/SCL 是否连锡")
    print("    B. 拔出所有模块，单独测 I²C 扫描 → 应为空列表 []")
    print("    C. 只插 GY-521 (MPU6050)，再测 → 应出现 [0x68]")
    print("    D. 再插 GY-273，再测 → 应出现 [0x68, 0x1E]")

# ─── Step 3: 尝试单独读取 MPU6050 WHO_AM_I ──
print("\n[3] 尝试读取 MPU6050 WHO_AM_I 寄存器 (0x75)...")
if 0x68 in devices:
    try:
        whoami = i2c.readfrom_mem(0x68, 0x75, 1)[0]
        expected = 0x68
        if whoami == expected:
            print(f"    ✅ WHO_AM_I = 0x{whoami:02X} (正确)")
        else:
            print(f"    ⚠️ WHO_AM_I = 0x{whoami:02X} (预期 0x{expected:02X})")
    except Exception as e:
        print(f"    ❌ 读取失败: {e}")
else:
    print("    ⏭️ 跳过 (设备未在总线上)")

print("\n" + "=" * 50)
print("诊断完成")
print("=" * 50)
