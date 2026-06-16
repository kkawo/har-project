# Project Overview

**项目名称**：从传感器数据到模式识别——可穿戴智能感知系统的全链路工程实践  
**课程**：《模式识别与统计学习》专周实训（2周 / 10实训日 / 60学时）  
**团队**：孔子瑜（算法与工程）、李宝平（数据采集与固件）  
**指导老师**：郑积仕  
**GitHub**：`https://github.com/kkawo/har-project.git`

---

# Current Architecture

## 硬件架构

```
ESP32-S3 N16R8
  └── I²C 总线 (SDA=IO17, SCL=IO18, 面包板搭接, 3V3供电)
        ├── GY-521 (MPU6050: 3轴加速度 + 3轴陀螺仪) @ 0x68 [已标定]
        └── GY-273 (HMC5883L: 3轴磁力计) @ 0x1E [待到货]
  └── Shield 扩展板: KiCad 原理图已手动绘制, PCB 布局布线进行中
```

- 采样率 50Hz, 目标 9 通道 (ax, ay, az, gx, gy, gz, mx, my, mz)
- 传感器佩戴于腰部, Y轴指向前进方向

## 软件架构

```
数据采集 → 预处理(去重力/滤波/窗口化) → 特征提取(时域+频域+跨轴 ~90维)
  → 特征选择(Filter/Wrapper/PCA/LDA/t-SNE) → 分类器(5基线+7高级)
  → LOSO评估 → 模型选择
```

## 代码组织

| 文件 | 状态 | 职责 |
|------|------|------|
| `src/utils.py` | D1 | 常量(FS=50, WINDOW_SEC=2.56, ACTIVITIES, 轴列表) |
| `src/preprocess.py` | D1 | 去重力、巴特沃斯滤波、滑动窗口(128点/50%重叠)、Pipeline |
| `src/features.py` | D1 | 时域12维+频域8维/轴 + 合加速度 + 跨轴相关 → ~90维/窗口 |
| `src/feature_selection.py` | D1 | 方差/ANOVA/MI筛选, PCA/LDA降维, t-SNE可视化 |
| `src/classifiers_baseline.py` | D1 | 5种基线分类器 + MinimumRiskBayes(代价矩阵) |
| `src/models_advanced.py` | D1 | 7种高级分类器 + PARAM_GRIDS |
| `src/evaluation.py` | D1 | LOSO, k-fold, Bootstrap CI, McNemar检验, 混淆矩阵 |
| `calib/calibrate.py` | D2 | 六位置加速度计标定, 椭球拟合磁力计, Allan方差, 对比图 |
| `calib/process_mpu6050_calib.py` | D2 | 串口采集数据 → 标定参数 + 对比图 |
| `calib/capture_mpu6050.py` | D2 | 串口自动采集脚本 (pySerial) |
| `calib/generate_demo_data.py` | D2 | 合成demo数据生成 (无硬件时验证Pipeline) |
| `calib/calib_params.json` | **D2 实测** | GY-521 标定参数 (bias/scale/gyro bias/Allan系数) |
| `firmware/mpu6050_calib/main.py` | **D2 实测** | MicroPython 采集固件 (Thonny, REPL交互) |
| `firmware/har_firmware.ino` | D2 | Arduino 固件 (备用, 支持 HMC5883L) |
| `reports/标定报告.md` | **D2 实测** | 含方法、实测参数、Allan噪声、对比图 |
| `reports/figures/` | D2 | 3张对比图 (accel_calib, allan_accel, allan_gyro) |
| `D2/` | **D2 交付包** | 含 calib_params.json + 报告 + 图表 + raw/calibrated 数据集 |
| `pcb/har-shield/` | D1-D2 | KiCad 10 项目 (用户手动绘制), PCB 布局进行中 |

---

# Progress

## Day 1 (2026-06-15)

- 项目计划书 + 数据采集协议 + Git 仓库
- Python 源码骨架 8 文件
- KiCad 项目建立 + DESIGN.md + 原理图手动绘制
- 10次 commit

## Day 2 (2026-06-17 实测)

### 已完成

- **GY-521 六位置标定** (16500样本, 7位置): 加速度计 RMSE 11.35→0.42 m/s², 陀螺仪零偏已修正
- **calib_params.json**: 实测参数 (bias=[0.0009, -0.0947, -0.4559], scale=[-0.9976, 1.0079, 0.9813], gyro bias=[-4.29, -1.21, 0.67])
- **标定报告更新**: 含实测方法、参数表、Allan 噪声系数、3张对比图
- **MicroPython 固件**: Thonny REPL 交互式采集 (`firmware/mpu6050_calib/main.py`)
- **串口采集工具**: `capture_mpu6050.py` (pySerial 自动采集) + `process_mpu6050_calib.py` (解析→标定→出图)
- **D2 交付包**: `D2/` 目录 (calib_params.json + 标定报告 + 对比图 + raw/calibrated 七位置数据集)
- **ESP32 面包板接线**: 仅3根线 (3V3/GND → IO17/SDA, IO18/SCL), 固件验证 I²C 通信正常

### 遇到的问题及解决

| 问题 | 解决 |
|------|------|
| KiCad 10 S-expression 手动生成格式复杂 | 放弃代码生成, 用户保留原始手动绘制的原理图 |
| Thonny Shell 缓冲区不够存 10 分钟数据 | 写 `capture_mpu6050.py` 用 pySerial 直接从 COM7 抓取 |
| Windows GBK 终端不支持 Unicode (`²`, `µ`) | 批量替换为 ASCII 字符 (`^2`, `u`) |
| GY-521 X 轴与六位置假设反向 (scale 为负) | 标定算法自动补偿, 不影响精度 |
| 无硬件时需验证标定 Pipeline | `generate_demo_data.py` 生成合成数据跑通全流程 |

### 未完成

- **GY-273 (HMC5883L) 磁力计标定**: 模块已有, 待到货后补 (椭球拟合代码就绪)
- **PCB 布局布线 + Gerber**: 原理图已手动绘制, 待 KiCad GUI 完成

---

# Open Issues

| # | 问题 | 严重度 | 状态 |
|---|------|--------|------|
| 1 | **GY-273 磁力计待标定** | 🟡 | 模块已有, 接线后补标 |
| 2 | **PCB 布局布线未完成** | 🟡 | 原理图已手动绘制, 待 KiCad 操作 |
| 3 | **S03 被试待定** | 🟢 | 可先用 S01/S02 |
| 4 | **活动数据未采集** | 🟡 | 标定已完成, 数据采集是 D3 任务 |

---

# TODO

## D3 (下一步)

- [ ] GY-273 到货后接线 + 椭球拟合磁力计标定 → 更新 calib_params.json (9通道)
- [ ] 更新固件支持 9 通道 (MPU6050 + HMC5883L) → 烧录
- [ ] 7类活动数据采集 (≥3次 × ≥60s × 2-3被试)
- [ ] 预处理 Pipeline 验证 (去重力 + 滤波 + 窗口化)
- [ ] 生成 raw/ 和 calibrated/ 活动数据集
- [ ] commit + push

## D4-D6

- [ ] D4: 特征提取 + 特征矩阵 + 特征字典
- [ ] D5: 特征选择对比 + 降维可视化
- [ ] D6: 5种基线分类器 + 最小风险贝叶斯 + 决策边界

---

# Handover Notes

- **MicroPython 环境**: ESP32-S3 + Thonny, 固件在 `firmware/mpu6050_calib/main.py`
- **固件用法**: 上传后 REPL 输入 `collect('<label>', seconds)`, 输出 CSV
- **串口采集**: `python calib/capture_mpu6050.py COM7` (需先关 Thonny)
- **标定处理**: `python calib/process_mpu6050_calib.py` (读取 raw_mpu6050_calib.txt → calib_params.json + 对比图)
- **标定参数文件**: `calib/calib_params.json` (当前仅 GY-521, GY-273 placeholder)
- **I²C 接线**: SDA=IO17, SCL=IO18, 模块自带 4.7kΩ 上拉 (GY-521 含 10kΩ)
- **I²C 地址**: MPU6050=0x68 (AD0→GND), HMC5883L=0x1E
- **六位置标定**: 模块 XYZ 标记可能与假设反向, scale 出现负值属正常 (算法自动补偿)
- **PCB 原理图**: 用户手动绘制, 位于 `pcb/har-shield/har-shield.kicad_sch` (KiCad 10)
- **D2 交付包**: `D2/` 目录可直接提交
- **GitHub**: `git push origin main`
