# HAR Project — 可穿戴人体活动识别系统

基于惯性/磁传感器的人体活动模式识别系统设计与实现。

福建理工大学 智能科学与技术 | 《模式识别与统计学习》专周实训  
孔子瑜（算法与工程）、李宝平（数据采集与固件） | 导师：郑积仕

---

## 项目概述

从 PCB 设计→传感器标定→数据采集→特征工程→分类器对比→严格评估的 **全链路 HAR 工程实践**。

**硬件**: ESP32-S3 + MPU6050 (Acc+Gyro) + HMC5883L (Mag) → 9通道 @50Hz  
**活动**: 7类（静坐/站立/步行/跑步/上楼/下楼/跌倒）  
**数据**: 2被试, 566滑动窗口 (2.56s, 50%重叠)  
**特征**: 292维（时域14+频域10/轴, 模长, 跨轴复合）  
**模型**: 13种分类器 LOSO 系统对比  
**最佳**: kNN (k=3,distance) + 多数表决 L=7 → **Accuracy 59.5%**

---

## 项目结构

```
har-project/
├── src/                    # 算法源码 (3,681行 Python)
│   ├── utils.py            #    常量与路径配置
│   ├── preprocess.py       # D3 信号预处理与窗口化
│   ├── features.py         # D4 294维特征提取
│   ├── feature_selection.py # D5 特征选择与降维
│   ├── classifiers_baseline.py # D6 基线分类器
│   ├── models_advanced.py  # D7 高级模型与调参
│   ├── evaluation.py       # D8 模型评估
│   └── d9_advanced_exploration.py # D9 进阶探索
├── data/                   # 数据资产
│   ├── raw/real/S01-S02/   # 真实数据 (14 CSV, 566窗口)
│   ├── windowed/           # 窗口化数据集
│   └── features/           # 特征矩阵
├── calib/                  # 传感器标定参数
├── firmware/               # ESP32 MicroPython 固件
├── pcb/                    # KiCad PCB 设计文件
├── reports/                # 报告与图表 (19+ PNG)
├── docs/                   # 项目文档
├── 10.D1-10.D9/            # 各阶段交付物
├── 项目深度说明.md          # 完整项目手册
└── HANDOVER.md             # 交接文档
```

---

## 核心结果

### 模型性能排名 (LOSO)

| 排名 | 模型 | Accuracy | Macro F1 |
|------|------|----------|----------|
| 1 | **kNN (k=3,distance) + MV L=7** | **0.595** | **0.569** |
| 2 | kNN (k=3,distance) | 0.564 | 0.527 |
| 3 | HMM Viterbi | 0.583 | 0.550 |
| 4 | LogisticRegression | 0.525 | 0.490 |
| 5 | MLP (128,64) | 0.507 | 0.472 |
| 6 | RBF_SVM | 0.472 | 0.430 |
| 7 | RandomForest | 0.424 | 0.386 |

### 各类别 Recall

| 类别 | Recall | 主要问题 |
|------|--------|----------|
| walk | **1.000** | — |
| upstairs | **0.935** | ↔ downstairs |
| stand | 0.674 | ↔ sit |
| run | 0.565 | ↔ walk, upstairs |
| fall | 0.500 | ↔ run |
| downstairs | 0.446 | ↔ upstairs |
| **sit** | **0.000** | ↔ stand (跨被试特征偏移) |

### 统计检验

- **McNemar**: kNN vs RBF_SVM p < 0.0001 (显著)
- **Bootstrap 95% CI**: [0.512, 0.594]
- **聚类**: KMeans+PCA ARI=0.364, NMI=0.516

---

## 一键复现

```bash
# 1. 环境准备
git clone https://github.com/kkawo/har-project.git
cd har-project
pip install -r requirements.txt

# 2. 确认真实数据就绪
ls data/raw/real/S01/   # 应有 7 个 CSV
ls data/raw/real/S02/   # 应有 7 个 CSV

# 3. 全链路运行 (约5分钟)
python src/preprocess.py && \
python src/features.py && \
python src/feature_selection.py && \
python src/classifiers_baseline.py && \
python src/models_advanced.py && \
python src/evaluation.py && \
python src/d9_advanced_exploration.py

# 4. 生成答辩PPT
python src/d10_generate_ppt.py

# 5. 查看结果
ls reports/d9_*.png                    # D9 进阶探索图表
ls reports/d8_*.png                    # D8 评估图表
cat reports/d9_exploration_summary.json # 数值结果
```

---

## 技术栈

- Python ≥ 3.10 | NumPy, SciPy, Pandas
- scikit-learn ≥ 1.3 | Matplotlib, seaborn
- hmmlearn ≥ 0.3.0 | TensorFlow ≥ 2.13
- KiCad (PCB) | MicroPython (ESP32固件)

---

## 关键文档

| 文档 | 说明 |
|------|------|
| [项目深度说明](项目深度说明.md) | 完整的项目手册，包含架构、数据流、决策、结果 |
| [HANDOVER](HANDOVER.md) | 新会话接手检查清单 |
| [项目状态](PROJECT_STATUS.md) | 当前进度与 Open Issues |
| [答辩问答库](答辩问答库.md) | 25+ 答辩常见问题与答案 |
| [最终报告](reports/final_report.md) | 课程论文 (5000+字) |
| [AI使用记录](AI_USAGE.md) | AI 协作开发记录 |

---

## 团队

| 角色 | 成员 |
|------|------|
| 数据采集与固件 | 李宝平 |
| 算法与工程 | 孔子瑜 |

---

## 参考文献

1. 张学工.《模式识别》（第四版）. 清华大学出版社
2. 李航.《统计学习方法》（第二版）. 清华大学出版社
3. Bulling, A., et al. "A Tutorial on Human Activity Recognition Using Body-worn Inertial Sensors." *ACM Computing Surveys*, 2014.
4. Anguita, D., et al. "A Public Domain Dataset for Human Activity Recognition Using Smartphones." *ESANN*, 2013.
