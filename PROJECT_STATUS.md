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
  └── I²C 总线 (SDA=IO17, SCL=IO18, Shield PCB 焊接)
        ├── GY-521 (MPU6050: 3轴加速度 + 3轴陀螺仪) @ 0x68 [已标定]
        └── GY-273 (HMC5883L: 3轴磁力计) @ 0x1E [已重标定, 覆盖度 1.22uT]
  └── Shield 扩展板: KiCad 原理图 → Gerber → 嘉立创 → 手工焊接完成
  └── NeoPixel RGB LED @ GPIO48 (离线采集状态指示)
  └── 焊有: R1/R2(4.7kΩ I²C上拉) + C1/C2(100nF去耦) + LED电源指示
```

- 采样率 50Hz, 9 通道 (ax, ay, az, gx, gy, gz, mx, my, mz)
- 传感器佩戴于腰部, Y轴指向前进方向

## 软件架构

```
数据采集 → 预处理(去重力/滤波/窗口化) → 特征提取(时域+频域+跨轴 294维)
  → 特征选择(Filter/PCA/LDA/t-SNE) → 分类器(5基线+7高级)
  → LOSO评估 → 模型选择
```

## 代码组织

| 文件 | 状态 | 职责 |
|------|------|------|
| `src/utils.py` | D1 | 常量(FS=50, WINDOW_SEC=2.56), RAW_DIR指向data/raw/real |
| `src/preprocess.py` | **D3 完成** | 完整 Pipeline: 校准→裁剪→去重力→滤波→窗口化 (503行) |
| `src/features.py` | **D4 完成** | 时域14+频域10/轴+模长+跨轴+复合=294维 (448行) |
| `src/feature_selection.py` | **D5 完成** | Filter(ANOVA/MI/Ensemble) + Wrapper(SFS) + Embedded(RF/RFE/L1) + PCA/LDA/t-SNE (371行) |
| `src/classifiers_baseline.py` | **D6 完成** | 6 基线 + MinimumRiskBayes + LOSO + 决策边界 (290行) |
| `src/models_advanced.py` | **D7 完成** | 7 高级模型 + GridSearchCV + 学习曲线 + LOSO (250行) |
| `src/evaluation.py` | **D8 完成** | LOSO + 混淆矩阵 + McNemar + Bootstrap CI + 标定增益分析 (380行) |
| `calib/calib_params.json` | **D2 实测 + 重标定** | 三传感器完整标定参数 (磁力计覆盖度 1.22uT, 改善76.1%) |
| `firmware/offline_logger/main.py` | **D3+** | 离线连续自动序列, I²C错误恢复, LED信号 (230行) |
| `firmware/har9ch_firmware/main.py` | D3 | 在线 9ch MicroPython 固件 (REPL交互) |
| `data/raw/real/S01-S02/` | **真实数据** | 2被试×7活动×1次 = 14 CSV, 566窗口 |
| `data/raw/S01-S02-S03/` | D3 Demo | 原demo数据保留未覆盖 |
| `firmware/offline_logger/test_run.py` | 调试用 | S01补录固件 (run→fall 4 trial) |

---

# Progress

## Day 1 (2026-06-15)
- 项目计划书 + 数据采集协议 + Git 仓库
- Python 源码骨架 8 文件
- KiCad 项目建立 + DESIGN.md + 原理图手动绘制

## Day 2 (2026-06-17 实测)
- **GY-521 六位置标定**: 16500样本, 7位置, RMSE 11.35→0.42 m/s²
- **HMC5883L 椭球拟合标定**: 3026样本旋转采集, norm_std 7.44→4.78 uT
- **calib_params.json**: 完整三传感器标定参数
- **KiCad PCB**: 原理图手动绘制完成, Gerber 已导出, 嘉立创已下单

## Day 3 (2026-06-17 代码推进)
- **9 通道 MicroPython 固件**: MPU6050(0x68) + HMC5883L(0x1E)
- **离线自动序列固件**: NeoPixel LED 信号, trial 自动推进
- **预处理 Pipeline**: 校准→裁剪→去重力→滤波→窗口化 (503行)
- **Demo 数据集**: 42 CSV, 2被试, 真实物理模拟

## Day 5-8 (2026-06-17)
- D5: 特征选择 (Filter/Wrapper/Embedded + PCA/LDA/t-SNE)
- D6: 6 基线分类器 + MinimumRiskBayes + LOSO + 决策边界
- D7: 7 高级模型 + GridSearchCV + 学习曲线
- D8: LOSO + 混淆矩阵 + McNemar + Bootstrap CI + 标定增益
- 全部基于 demo 数据验证 (100% 精度, 合成数据特性)

## PCB 到货 + 硬件验证 (2026-06-24)
- **PCB 焊接**: J1/J2/J3/J4 排母 + R1/R2/C1/C2/R3/D1 全部焊接
- **I²C 排错**: 初始 SDA/SCL 焊锡桥接短路, 修复后空板扫描正常 ([])
- **I²C 验证**: 0x68 (MPU6050) + 0x1E (HMC5883L) 稳定通信
- **磁力计重标定**: 3000样本旋转采集, 标准差 4.78→1.22 uT, 改善 76.1%
- **固件升级**: 连续自动序列(无需反复插拔) + I²C错误恢复(reinit + retry×3) + LED错误信号(红灯)

## 真实数据采集 (2026-06-24)
- **S01**: 7 trial (sit/stand/walk/run/upstairs/downstairs/fall), 283窗口, 无I²C错误
- **S02**: 7 trial, 283窗口, 无I²C错误
- 数据存储: `data/raw/real/S01/` `data/raw/real/S02/`, demo数据保留在 `data/raw/S01-S03/`

## 真实数据全链路重跑 (2026-06-24)
- **预处理**: 566 窗口 (S01=283, S02=283)
- **特征提取**: (566, 292) 特征矩阵 (2 常量特征自动过滤)
- **特征选择**: RFE 最优 (30维, CV 91.7%), SFS 次之 (30维, 90.8%)
- **基线分类器**: kNN 55.5% 最佳, LR 52.5% 次之, LDA 23.3% (高维失效)
- **高级分类器**: kNN(k=3,distance) 56.4%, MLP(128,64) 50.7%, RF 42.4%
- **评估**: McNemar检验kNN vs RBF_SVM显著(p<0.0001), Bootstrap 95%CI [51.2%, 59.4%]
- **主要问题**: sit recall=0% (与stand/walk高度混淆), fall recall=38% (仅14窗口)

---

# Open Issues

| # | 问题 | 严重度 | 状态 |
|---|------|--------|------|
| 1 | **真实精度偏低 (55.5%)** | 🟡 | 566窗口/2被试, 样本量小, 正常现象 |
| 2 | **sit 完全不可分 (recall=0%)** | 🟡 | 与 stand/walk 加速度特征接近, 需更多特征或时序建模 |
| 3 | **跌倒样本极少 (14窗口)** | 🟡 | fall 仅 15s, 类不平衡严重 |
| 4 | **LOSO 仅 2 folds** | 🟢 | 2 被试, 统计意义有限 |
| 5 | **S03 被试未采集** | 🟢 | 可后续补充 |
| 6 | **原有 demo 数据完好** | 🟢 | 在 data/raw/S01-S03/, 可随时切回对比 |

---

# Quick Reference

- **Python 环境**: `pip install -r requirements.txt`
- **真实数据路径**: `data/raw/real/S01/` `data/raw/real/S02/`
- **RAW_DIR**: `src/utils.py` 已改为 `data/raw/real`
- **标定参数**: `calib/calib_params.json` (磁力计覆盖度 1.22uT)
- **I²C 接线**: SDA=IO17, SCL=IO18, Shield PCB 焊接
- **I²C 地址**: MPU6050=0x68, HMC5883L=0x1E
- **HMC5883L 寄存器顺序**: X, Z, Y (非标准)
- **NeoPixel LED**: GPIO48
- **离线固件**: `firmware/offline_logger/main.py` (连续自动序列 + I²C恢复)
- **详细交接**: 见 HANDOVER.md
