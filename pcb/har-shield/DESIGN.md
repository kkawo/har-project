# HAR Sensor Shield — 原理图设计文档

## ESP32-S3 N16R8 · 44 脚 (2×22) · CH340C

---

## 一、板端引脚映射

### 左侧排针 (J1, 22 脚, 从上到下)

| 脚号 | 信号 | 用途 |
|------|------|------|
| **1** | **3V3** | → 扩展板供电 |
| 2 | 3V3 | |
| 3 | RST | |
| 4 | IO4 | |
| 5 | IO5 | |
| 6 | IO6 | |
| 7 | IO7 | |
| 8 | IO15 | |
| 9 | IO16 | |
| **10** | **IO17** | **→ SDA** |
| **11** | **IO18** | **→ SCL** |
| 12 | IO8 | |
| 13 | IO3 | |
| 14 | IO46 | |
| 15 | IO9 | |
| 16 | IO10 | |
| 17 | IO11 | |
| 18 | IO12 | |
| 19 | IO13 | |
| 20 | IO14 | |
| 21 | 5VIN | |
| **22** | **GND** | → 扩展板地 |

### 右侧排针 (J2, 22 脚, 从上到下)

| 脚号 | 信号 |
|------|------|
| 1 | GND |
| 2 | TX |
| 3 | RX |
| 4 | IO1 |
| 5 | IO2 |
| 6 | IO42 |
| 7 | IO41 |
| 8 | IO40 |
| 9 | IO39 |
| 10 | IO38 |
| 11 | IO37 |
| 12 | IO36 |
| 13 | IO35 |
| 14 | IO0 |
| 15 | IO45 |
| 16 | IO48 |
| 17 | IO47 |
| 18 | IO21 |
| 19 | IO20 |
| 20 | IO19 |
| 21 | GND |
| 22 | GND |

---

## 二、设计规格

| 项目 | 规格 |
|------|------|
| 板型 | ESP32-S3 44脚开发板插拔扩展板 (Shield) |
| 尺寸 | ≤ 60mm × 30mm |
| 层数 | 2 |
| 排针 | J1 左侧 1×22 + J2 右侧 1×22, 2.54mm 间距 |
| 传感器 | GY-521 (MPU6050) + GY-273 (HMC5883L), 插模块脚位 |

---

## 三、信号映射

| 信号 | ESP32-S3 来源 | Shield 排针 |
|------|--------------|------------|
| +3V3 | 3V3 | J1 脚 1 |
| GND  | GND | J1 脚 22 |
| SDA  | IO17 | J1 脚 10 |
| SCL  | IO18 | J1 脚 11 |

---

## 四、BOM

| 编号 | 器件 | 规格 | 封装 | 数量 |
|------|------|------|------|------|
| C1, C2 | 去耦电容 | 100nF | C_0805_2012Metric | 2 |
| R1, R2 | I²C 上拉电阻 | 4.7kΩ | R_0805_2012Metric | 2 |
| R3 | LED 限流电阻 | 220Ω | R_0805_2012Metric | 1 |
| D1 | 电源指示灯 | 红色 | LED_0805_2012Metric | 1 |
| J1, J2 | ESP32-S3 排母 | 1×22P, 2.54mm | PinHeader_1x22_P2.54mm_Vertical | 2 |
| J3 | GY-521 排母 | 1×8P, 2.54mm | PinHeader_1x08_P2.54mm_Vertical | 1 |
| J4 | GY-273 排母 | 1×5P, 2.54mm | PinHeader_1x05_P2.54mm_Vertical | 1 |

---

## 五、连线清单

```
=== +3V3 ===
J1-1  (3V3)    → J3-1  (GY-521 VCC)
                → J4-1  (GY-273 VCC)
                → R1-1  (SCL 上拉)
                → R2-1  (SDA 上拉)
                → C1-1  (GY-521 去耦)
                → C2-1  (GY-273 去耦)
                → R3-1  (LED 限流)

=== GND ===
J1-22 (GND)    → J3-2  (GY-521 GND)
                → J4-2  (GY-273 GND)
                → J3-7  (GY-521 AD0 → GND, 地址 0x68)
                → C1-2
                → C2-2
                → D1-K (LED 阴极)

=== SCL ===
J1-11 (IO18)   → R1-2  (上拉)
                → J3-3  (GY-521 SCL)
                → J4-3  (GY-273 SCL)

=== SDA ===
J1-10 (IO17)   → R2-2  (上拉)
                → J3-4  (GY-521 SDA)
                → J4-4  (GY-273 SDA)

=== LED ===
R3-2           → D1-A
```

---

## 六、KiCad 手动步骤

### 1. 原理图
```
打开 har-shield.kicad_pro → Eeschema
按 A → 搜索放置符号:
  Connector_Generic:Conn_01x22_Female  ×2  (J1=ESP32_LEFT, J2=ESP32_RIGHT)
  Connector_Generic:Conn_01x08_Female  ×1  (J3=GY-521_MPU6050)
  Connector_Generic:Conn_01x05_Female  ×1  (J4=GY-273_HMC5883L)
  Device:R                             ×3  (R1/R2=4.7k, R3=220)
  Device:C                             ×2  (C1/C2=100nF)
  Device:LED                           ×1  (D1)

赋封装:
  J1,J2: PinHeader_1x22_P2.54mm_Vertical
  J3:    PinHeader_1x08_P2.54mm_Vertical
  J4:    PinHeader_1x05_P2.54mm_Vertical
  R1,R2,R3: R_0805_2012Metric
  C1,C2:    C_0805_2012Metric
  D1:       LED_0805_2012Metric

按第五章连线清单连接
ERC 检查 → 通过
```

### 2. PCB
```
F8 更新 PCB → 元件导入
布局约束:
  - HMC5883L (J4) 远离板顶 ≥15mm (避开 ESP32-S3 天线)
  - C1 靠近 J3, C2 靠近 J4
  - I²C 走线 0.3mm, 两侧包地
  - 电源走线 ≥0.5mm
DRC → 通过 → 导出 Gerber → 嘉立创下单
```

---

## 七、PCB 布局约束

| 约束 | 值 |
|------|-----|
| 板外形 | 60mm × 30mm (Edge.Cuts, 已画好) |
| HMC5883L 距天线 | ≥ 15mm (J4 靠下方放) |
| 去耦电容 | C1/C2 靠近对应模块 VCC 引脚 |
| I²C 上拉 | R1/R2 靠近 SCL/SDA 走线 |
| 安装 | 通过排母直接插接, 无需安装孔 |

---

> ⏰ **D3 中午 12:00 前必须嘉立创下单**（快递 3-5 工作日, D6-D7 到货）
