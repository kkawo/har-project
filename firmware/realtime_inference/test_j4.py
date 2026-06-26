"""
GPIO 连通性测试 — 验证 J4 排母是否焊通
原理：将 IO17/IO18 设为输出并翻转电平，
     用另一个 GPIO 设为输入读取 J4 端电平。

但 ESP32-S3 上我们无法直接读 J4 端。
替代方案：逐一测试不同 I²C 频率和地址。
"""

from machine import Pin, SoftI2C
from time import sleep_ms

SDA = Pin(17); SCL = Pin(18)

print("=" * 50)
print("J4 / HMC5883L 连通性深度诊断")
print("=" * 50)

# ─── Test 1: 检查 J4 是否对 I²C 总线有干扰 ──
print("\n[1] 拔出 GY-273，只留 GY-521，I²C 扫描...")
print("    (请先拔出 GY-273 模块!)")
sleep_ms(2000)

i2c = SoftI2C(sda=SDA, scl=SCL, freq=100000)
devs = i2c.scan()
print(f"    扫描结果: {[hex(d) for d in devs]}")
if 0x68 in devs and len(devs) == 1:
    print("    ✅ 只有 MPU6050，总线干净")
elif len(devs) == 0:
    print("    ❌ 零设备 — 总线或 MPU6050 有问题")
    raise SystemExit

# ─── Test 2: 插回 GY-273，全地址扫描 ──
print("\n[2] 插回 GY-273，全地址扫描 (1-127)...")
print("    (请插回 GY-273 模块!)")
sleep_ms(2000)

found = []
for addr in range(1, 128):
    try:
        i2c.writeto(addr, b'')
        found.append(addr)
    except:
        pass
print(f"    发现设备: {[hex(a) for a in found]}")
if 0x1E not in found:
    print("    ❌ 0x1E 不在总线上")

    # Check if there's any address nearby that might be the HMC5883L
    nearby = [hex(a) for a in found if abs(a - 0x1E) <= 5]
    if nearby:
        print(f"    ⚠️ 发现附近地址: {nearby} — 可能是地址冲突或模块异常")
else:
    print("    ✅ 0x1E 已找到!")

# ─── Test 3: 降低频率重试 ──
print("\n[3] 低频 10kHz + 多次重试...")
i2c_low = SoftI2C(sda=SDA, scl=SCL, freq=10000)
for i in range(5):
    devs = i2c_low.scan()
    hmc = "✅ 0x1E" if 0x1E in devs else "❌"
    print(f"    Attempt {i+1}: {[hex(d) for d in devs]} {hmc}")
    sleep_ms(200)

# ─── Test 4: 单独测试 J4 供电 ──
print("\n[4] 供电检查提示:")
print("    万用表直流电压档：")
print("    - J4 VCC ↔ GND = ? (应为 3.3V)")
print("    - GY-273 模块 VCC ↔ GND = ? (应为 3.3V)")
print()
print("    万用表蜂鸣档 (断电后!)：")
print("    - J4-SDA ↔ ESP32 IO17 = ? (应导通)")
print("    - J4-SCL ↔ ESP32 IO18 = ? (应导通)")
print("    - J4-VCC ↔ 3V3 = ? (应导通)")
print("    - J4-GND ↔ GND = ? (应导通)")

print("\n" + "=" * 50)
print("如果全地址扫描仍无 0x1E，就是 J4 的 SDA/SCL 虚焊")
print("=" * 50)
