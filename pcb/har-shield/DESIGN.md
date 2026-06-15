# HAR Sensor Shield — 原理图设计文档

## KiCad 8.0 · ESP32 可插拔多传感器扩展板

---

## 一、设计规格

| 项目 | 规格 |
|------|------|
| 板型 | ESP32-DevKitC v4 插拔扩展板 (Shield) |
| 尺寸 | ≤ 60mm × 30mm |
| 层数 | 2 层 |
| 板厚 | 1.6mm（嘉立创默认） |
| 最小线宽/线距 | 0.2mm / 0.2mm |
| 铜厚 | 1oz |

---

## 二、物料清单 (BOM)

| 编号 | 器件 | 规格 | 封装 | 数量 |
|------|------|------|------|------|
| C1, C2 | 去耦电容 | 100nF | C_0805_2012Metric | 2 |
| R1, R2 | I²C 上拉电阻 | 4.7kΩ | R_0805_2012Metric | 2 |
| R3 | LED 限流电阻 | 220Ω | R_0805_2012Metric | 1 |
| D1 | 电源指示灯 | 红色/绿色 | LED_0805_2012Metric | 1 |
| J1 | ESP32 左侧排母 | 1×19P, 2.54mm 间距 | PinHeader_1x19_P2.54mm_Vertical | 1 |
| J2 | ESP32 右侧排母 | 1×19P, 2.54mm 间距 | PinHeader_1x19_P2.54mm_Vertical | 1 |
| J3 | GY-521 (MPU6050) 排母 | 1×8P, 2.54mm 间距 | PinHeader_1x08_P2.54mm_Vertical | 1 |
| J4 | GY-273 (HMC5883L) 排母 | 1×5P, 2.54mm 间距 | PinHeader_1x05_P2.54mm_Vertical | 1 |

> GY-521 和 GY-273 直接插到排母上，不需焊接裸片——降低失败率。

---

## 三、引脚映射表

### 3.1 ESP32 DevKitC v4 → Shield

| 信号 | ESP32 来源 | 排针位置 |
|------|-----------|----------|
| +3V3 | 3V3 输出 | J1 第 1 脚（左上角，靠 USB 口） |
| GND | GND | J1 第 15 脚（左排中间） |
| SDA | GPIO21 | J2 第 5 脚（右排第 5） |
| SCL | GPIO22 | J2 第 2 脚（右排第 2） |

### 3.2 GY-521 (MPU6050) 模块 — J3

| J3 脚号 | 信号 | 连接到 |
|---------|------|--------|
| 1 | VCC | +3V3 |
| 2 | GND | GND |
| 3 | SCL | SCL (J2-2, 经 R2 上拉) |
| 4 | SDA | SDA (J2-5, 经 R1 上拉) |
| 5 | XDA | 悬空（不用辅助 I²C） |
| 6 | XCL | 悬空 |
| 7 | AD0 | GND（固定地址 0x68） |
| 8 | INT | 悬空（不用中断） |

### 3.3 GY-273 (HMC5883L) 模块 — J4

| J4 脚号 | 信号 | 连接到 |
|---------|------|--------|
| 1 | VCC | +3V3 |
| 2 | GND | GND |
| 3 | SCL | SCL (J2-2, 经 R2 上拉) |
| 4 | SDA | SDA (J2-5, 经 R1 上拉) |
| 5 | DRDY | 悬空（不用数据就绪） |

---

## 四、连线清单（逐条对着连）

```
=== 电源网络 (+3V3) ===
  J1-1    (ESP32 3V3)    →  J3-1   (GY-521 VCC)
  J1-1    (ESP32 3V3)    →  J4-1   (GY-273 VCC)
  J1-1    (ESP32 3V3)    →  R1-1   (SCL 上拉电阻)
  J1-1    (ESP32 3V3)    →  R2-1   (SDA 上拉电阻)
  J1-1    (ESP32 3V3)    →  C1-1   (GY-521 去耦)
  J1-1    (ESP32 3V3)    →  C2-1   (GY-273 去耦)
  J1-1    (ESP32 3V3)    →  R3-1   (LED 限流电阻)
  R3-2                    →  D1-A   (LED 阳极, pin 2)

=== 接地网络 (GND) ===
  J1-15   (ESP32 GND)    →  J3-2   (GY-521 GND)
  J1-15   (ESP32 GND)    →  J4-2   (GY-273 GND)
  J1-15   (ESP32 GND)    →  J3-7   (GY-521 AD0 → GND = 地址 0x68)
  J1-15   (ESP32 GND)    →  C1-2   (去耦电容)
  J1-15   (ESP32 GND)    →  C2-2   (去耦电容)
  J1-15   (ESP32 GND)    →  D1-K   (LED 阴极, pin 1)

=== I²C SCL 网络 ===
  J2-2    (ESP32 GPIO22)  →  R2-2   (SCL 上拉)
  R2-2                     →  J3-3   (GY-521 SCL)
  R2-2                     →  J4-3   (GY-273 SCL)

=== I²C SDA 网络 ===
  J2-5    (ESP32 GPIO21)  →  R1-2   (SDA 上拉)
  R1-2                     →  J3-4   (GY-521 SDA)
  R1-2                     →  J4-4   (GY-273 SDA)
```

---

## 五、原理图布局建议

在 KiCad 中打开后，按以下位置摆放（A4 图纸，单位 mm）：

```
                                          ┌─────────────────┐
    J1 (ESP32 LEFT)                       │  C1  100nF      │
    ┌──────────┐                          │  ││             │
    │ 1  3V3   ├──── +3V3 ────────────────┼──┤├─┐           │
    │ 2  EN    │                          │  └──┘ │          │
    │ ...      │                          │       │    +3V3  │
    │ 15 GND   ├──── GND ─────────────────┼───────┘    │     │
    │ ...      │                          │       │     │     │
    └──────────┘                          │       │     │     │
                                          │  ┌────┴─┐  │     │
    J2 (ESP32 RIGHT)                      │  │ R1   │  │     │
    ┌──────────┐                          │  │ 4.7k │  │     │
    │ 1  GPIO23│                          │  └──┬───┘  │     │
    │ 2  GPIO22├──── SCL ─────────────────┼─────┤      │     │
    │ 3  TXD   │                          │  ┌──┴───┐ │     │
    │ 4  RXD   │                          │  │ R2   │ │     │
    │ 5  GPIO21├──── SDA ─────────────────┼──┤ 4.7k │ │     │
    │ ...      │                          │  └──┬───┘ │     │
    └──────────┘                          │     │     │     │
                                          │     │     │     │
    ┌──────────┐                          │     │     │     │
    │ D1 LED   │                          │     │     │     │
    │  R3 220Ω │                          │     │     │     │
    └──────────┘                          │     │     │     │
      +3V3 ── R3 ── D1 ── GND            │     │     │     │
                                          └─────┼─────┼─────┘
                                                │     │
                                   ┌────────────┘     └────────────┐
                                   ▼                               ▼
                              ┌─────────┐                    ┌─────────┐
                              │ J3      │                    │ J4      │
                              │ GY-521  │                    │ GY-273  │
                              │ 1 VCC   │                    │ 1 VCC   │
                              │ 2 GND   │                    │ 2 GND   │
                              │ 3 SCL ◄─┤─ SCL              │ 3 SCL ◄─┤─ SCL
                              │ 4 SDA ◄─┤─ SDA              │ 4 SDA ◄─┤─ SDA
                              │ 5 XDA   │                    │ 5 DRDY  │
                              │ 6 XCL   │                    └─────────┘
                              │ 7 AD0 ──┤─ GND
                              │ 8 INT   │
                              └─────────┘
                              │
                              │  C2  100nF
                              │  ││
                              └──┤├── GND
```

---

## 六、KiCad 操作步骤

### Step 1：打开项目
```
KiCad 8.0 → 打开项目 → 选择 pcb/har-shield/har-shield.kicad_pro
```

### Step 2：添加符号
按 `A` 键（Add Symbol），搜索并放置：

| 符号名（KiCad 默认库） | 放置数量 |
|------------------------|----------|
| `Connector:Conn_01x19_Female` | 2（J1, J2） |
| `Connector:Conn_01x08_Female` | 1（J3） |
| `Connector:Conn_01x05_Female` | 1（J4） |
| `Device:R` | 3（R1, R2, R3） |
| `Device:C` | 2（C1, C2） |
| `Device:LED` | 1（D1） |

### Step 3：修改属性
- R1, R2: Value → `4.7k`, Footprint → `Resistor_SMD:R_0805_2012Metric`
- R3: Value → `220`, Footprint → `Resistor_SMD:R_0805_2012Metric`
- C1, C2: Value → `100nF`, Footprint → `Capacitor_SMD:C_0805_2012Metric`
- D1: Value → `LED`, Footprint → `LED_SMD:LED_0805_2012Metric`
- J3: Value → `GY-521_MPU6050`
- J4: Value → `GY-273_HMC5883L`

### Step 4：连线
按 `W` 键（Wire），按第四章连线清单逐条连接。

### Step 5：加网络标签（推荐）
按 `L` 键（Label），给关键网络加标签：
- `+3V3`
- `GND`
- `SDA`
- `SCL`

### Step 6：电气规则检查
运行 ERC（Electrical Rules Checker），修掉所有错误和警告。

---

## 七、PCB 布局约束

| 约束 | 值 |
|------|-----|
| 板外形 | 60mm × 30mm（在 Edge.Cuts 层画矩形） |
| HMC5883L 距 ESP32 天线 | **≥ 15mm**（J4 尽量远离板顶部，靠下方摆放） |
| 去耦电容 C1 | 靠近 J3 (GY-521) VCC 引脚 |
| 去耦电容 C2 | 靠近 J4 (GY-273) VCC 引脚 |
| I²C 走线 | SDA/SCL 平行走线，线宽 0.3mm，两侧包地 |
| 电源走线 | +3V3 和 GND 用 0.5mm 以上走线 |
| 安装孔 | 无（通过排母固定在 ESP32 上） |

---

## 八、制造输出

完成 PCB 布局后：
1. 运行 DRC（Design Rules Checker）
2. 文件 → 制造输出 → Gerber → 生成钻孔文件
3. 将 Gerber 打包 ZIP → 上传嘉立创下单
4. 参数：2 层板、1.6mm、1oz、绿色阻焊、有铅喷锡
5. 5 片约 ¥5，快递 3-5 工作日

---

> **⏰ 时间红线**：D3 中午 12:00 前必须完成嘉立创下单，否则板子赶不及 D6-D7 到货。
