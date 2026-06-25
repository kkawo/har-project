# HANDOVER.md — HAR 项目交接文档

**生成时间**: 2026-06-24  
**移交状态**: D1-D8 全部完成，真实数据已采集，全链路在真实数据上重跑通过  
**当前数据**: 真实数据（14 CSV, 2 被试 7 活动 1 次, 566 窗口）  
**硬件**: ESP32-S3 Shield PCB 焊接完成，I²C 正常，磁力计已重标定  
**下一个会话**: 从 D9 开始（进阶探索）

---

## 一、项目元信息

| 项目 | 内容 |
|------|------|
| 课程 | 《模式识别与统计学习》专周实训，2 周/10 天/60 学时 |
| 学校 | 福建理工大学 智能科学与技术（大三） |
| 团队 | 孔子瑜（算法与工程）、李宝平（数据采集与固件） |
| 导师 | 郑积仕 |
| GitHub | https://github.com/kkawo/har-project.git |
| 工作目录 | `D:\OneDrive\Desktop\2026.6.15专周\har-project` |

---

## 二、当前完成状态

```
D1 [OK]  项目计划书 + 采集协议 + Git 骨架 + KiCad 原理图
D2 [OK]  GY-521 六位置标定 + HMC5883L 椭球拟合 + calib_params.json + 标定报告
D3 [OK]  9 通道固件 + 预处理 Pipeline + windowed_dataset
D4 [OK]  294 维特征提取 + feature_matrix + 特征字典
D5 [OK]  特征选择 Filter/Wrapper/Embedded + PCA/LDA/t-SNE + 对比报告
D6 [OK]  6 基线 + MinimumRiskBayes + LOSO + 决策边界
D7 [OK]  7 高级模型 + GridSearchCV + 学习曲线
D8 [OK]  LOSO + 混淆矩阵 + McNemar + Bootstrap CI + 标定增益
--- 硬件 ---
[HW]    Shield PCB 焊接 + I²C 排错 + 磁力计重标定 + 真实数据采集 (S01+S02)
D9 [  ]  进阶探索（无监督/HMM/DL/边缘部署）
D10 [  ]  最终报告 + 答辩 PPT + demo 视频
```

---

## 三、硬件状态

### Shield PCB
- J1/J2/J3/J4 排母 + R1/R2(4.7kΩ) + C1/C2(100nF) + R3(220Ω) + D1(LED) 全部焊接
- I²C 初始有 SDA/SCL 焊锡桥接, 已修复
- 上电 LED 亮 = 电源正常

### 传感器
- MPU6050 @ 0x68: 正常, +/-8g, +/-2000dps, 50Hz
- HMC5883L @ 0x1E: 正常, 磁力计已重标定 (std 1.22uT, 改善 76.1%)
- 模块建议用胶带固定在 PCB 上, 防止跑步振动松脱

### 固件
- `firmware/offline_logger/main.py`: 连续自动序列, I²C错误恢复, LED信号
- LED信号: 白=编号, 橙=倒计时, 绿=采集中, 蓝=OK, 红=出错, 彩虹=完成
- 修改 SUBJECT 后重新烧录即可采集下一个被试
- `firmware/har9ch_firmware/main.py`: 在线交互式 (REPL), 用于调试
- `firmware/offline_logger/test_run.py`: S01补录用 (run→fall 仅4 trial)

---

## 四、数据文件

### 真实数据 (当前使用)
```
data/raw/real/
  S01/  (7 CSV, 283窗口)
  S02/  (7 CSV, 283窗口)
```
- RAW_DIR 在 `src/utils.py` 第12行已改为 `data/raw/real`
- 每个 CSV 约 250-260KB (65s trial) 或 ~60KB (15s fall)
- 全部无 I²C 错误

### Demo 数据 (保留)
```
data/raw/S01/  (21 CSV demo)
data/raw/S02/  (21 CSV demo)
data/raw/S03/  (空)
```
- 如要切回 demo 数据: 改 `src/utils.py` RAW_DIR 为 `DATA_DIR / "raw"`

### 中间产物 (当前为真实数据)
```
data/windowed/windowed_dataset.npz  (566, 128, 9)
data/features/feature_matrix.npz    (566, 292)
```

---

## 五、全链路运行命令

```bash
cd "D:\OneDrive\Desktop\2026.6.15专周\har-project"

# 全链路 (约 3-5 分钟)
python src/preprocess.py && \
python src/features.py && \
python src/feature_selection.py && \
python src/classifiers_baseline.py && \
python src/models_advanced.py && \
python src/evaluation.py
```

---

## 六、真实数据结果

### 数据集概览
| 指标 | 值 |
|------|-----|
| 被试 | S01, S02 |
| 窗口数 | 566 (S01=283, S02=283) |
| 窗口形状 | (566, 128, 9) |
| 特征数 | 292 (294 - 2常量) |
| 类分布 | 前6类各≈92, 跌倒=14 |
| LOSO folds | 2 |

### 最佳模型: kNN (k=3, distance weighting)
| 指标 | 值 |
|------|-----|
| Accuracy | 55.5% |
| Macro F1 | 50.6% |
| walk recall | 96% |
| upstairs recall | 83% |
| sit recall | **0%** (与stand完全混淆) |
| fall recall | 38% (仅14样本) |
| McNemar vs RBF_SVM | p<0.0001 (显著) |
| Bootstrap 95% CI | [51.2%, 59.4%] |

### 各模型对比
| 模型 | Accuracy | 备注 |
|------|----------|------|
| kNN (k=3,distance) | 56.4% | 最佳 |
| MLP (128,64) | 50.7% | |
| LR | 52.5% | |
| RBF_SVM | 47.2% | |
| RF | 42.4% | |
| GBDT | 28.1% | 小样本过拟合 |
| LDA | 23.3% | 高维失效 |

### 关键问题
1. **sit recall=0%**: 静坐与站立加速度差异小, 566窗口不足以区分。建议 D9 加时序平滑(HMM)或滑窗投票
2. **fall 仅14窗口**: 15s采集, 建议增加采样时长或被试数量
3. **LOSO 仅2 folds**: 统计意义有限, 建议 D9 报告中坦诚说明

---

## 七、关键设计决策

1. Window: 2.56s (128点@50Hz), 50%重叠
2. 裁剪: 每trial首尾各裁2s
3. HP 0.3Hz → 去重力, LP 20Hz → 抗混叠
4. 窗口标签: 多数表决
5. 数据划分: LOSO按subject_id, 标准化在fold内fit→transform
6. 磁力计寄存器: HMC5883L是 X, Z, Y (非标准), 固件已处理
7. 采集序列: 坐→站→走→跑→上楼→下楼→跌倒, 每类1次
8. 数据隔离: RAW_DIR=real, demo数据保留未删

---

## 八、剩余工作 (D9-D10)

### D9: 进阶探索 (至少选1项, 推荐时序平滑)
| 方向 | 内容 | 难度 | 推荐 |
|------|------|------|------|
| **时序平滑** | 滑窗多数表决 / HMM 消除瞬时抖动, 目标提升 sit recall | ★★ | **强烈推荐** |
| 无监督 | K-means / GMM 聚类 + ARI/NMI | ★★ | |
| 深度学习 | 1D-CNN 端到端 vs 手工特征 | ★★★ | |
| 边缘部署 | 轻量模型导出到 ESP32 | ★★★★ | |

### D10: 最终交付
- [ ] 最终报告 PDF (5000-8000字)
- [ ] 答辩 PPT (10min展示+5min提问)
- [ ] demo视频 (≤2min)
- [ ] GitHub README + 一键复现
- [ ] 交付文件夹整理

---

## 九、新会话接手检查清单

- [ ] 读 HANDOVER.md 全篇
- [ ] 读 PROJECT_STATUS.md + TODO.md
- [ ] 确认 Python 环境: `pip install -r requirements.txt`
- [ ] 确认真实数据: `ls data/raw/real/S01/ data/raw/real/S02/` (各7 CSV)
- [ ] 确认 utils.py RAW_DIR 指向 `data/raw/real`
- [ ] 跑通全链路验证 (约3-5分钟): 按 §五 命令
- [ ] 从 D9 进阶探索开始

---

## 十、AI 使用记录

| 环节 | AI 作用 | 人工审核 |
|------|---------|----------|
| D1-D8 算法代码 | 全部 src/ 文件生成 | 人工审查方法+运行验证 |
| 标定代码 | 六位置/椭球拟合/Allan方差 | 用户实测验证 |
| MicroPython 固件 | 9ch I²C驱动, 离线采集, 错误恢复 | 用户实测验证 |
| PCB 排错 | I²C短路诊断 | 用户焊接修复 |
| 全链路重跑 | 命令+结果分析 | 人工审查结论 |
| 文档维护 | PROJECT_STATUS/TODO/HANDOVER | 人工核定 |
| **报告/PPT** | 尚未开始 | |

> **核心算法原理、实验设计、结论需人工理解并在答辩中讲清。**

---

> **版本**: v3.0 | 2026-06-24 | 真实数据采集+全链路重跑完成
