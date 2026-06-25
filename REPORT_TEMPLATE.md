# 基于惯性/磁传感器的人体活动模式识别系统设计与实现

> **课程论文模板** — 按任务书 §8.2 结构。  
> 正文 5000–8000 字，A4 12–20 页，参考文献 ≥8 篇（英文 ≥2 篇）。  
> 所有图表必须有编号、标题、说明。

---

## 摘要（300 字）

**关键词**：人体活动识别；模式识别；MEMS 惯性传感器；特征工程；集成学习

> 写作要点：1 句背景（HAR 是什么）+ 1 句问题（本文做什么）+ 1 句方法（采集→标定→特征→分类→评估）+ 1 句结果（LOSO 准确率 XX%）+ 1 句结论

---

## 1 引言

### 1.1 研究背景

> 可穿戴计算、健康监护、跌倒检测...

### 1.2 相关工作

> UCI HAR, WISDM, PAMAP2 等公开数据集；传统方法（手工特征+分类器）vs 深度学习方法...

### 1.3 本文贡献

> 三句话：① 完成从硬件到算法的全链路工程实践；② 系统对比多种特征选择与分类方法；③ 用 LOSO 等严谨评估方法给出可靠结论

---

## 2 系统硬件与数据采集

### 2.1 采集协议与被试设计

| 参数 | 设定值 |
|------|--------|
| 传感器 | MPU6050 (加速度+陀螺仪) + HMC5883L (磁力计) |
| 采样率 | 50 Hz |
| 佩戴位置 | 腰部 |
| 被试 | ≥3 人 |
| 活动类别 | 静坐(0), 站立(1), 步行(2), 跑步(3), 上楼(4), 下楼(5), 跌倒(6) |
| 每类每次时长 | ≥60 s（跌倒 ≥10 s） |
| 每类次数 | ≥3 次 |
| 过渡处理 | 前后各裁 2 s |

### 2.2 传感器标定

#### 加速度计六位置标定

> **误差模型**：a_calibrated = M × (a_raw - b)，12 参数最小二乘求解。  
> **约束**：静止时合加速度模长 = 1g。  
> **结果**：RMSE 从 X → Y m/s²。

#### 磁力计椭球拟合

> **模型**：一般二次曲面 DLS 拟合 → SVD 求解硬铁/软铁参数。  
> **结果**：norm_std 从 X → Y uT（改善 Z%）。

#### 陀螺仪零偏与 Allan 方差

> 静态零偏：[X, Y, Z] °/s。Allan 方差：ARW = X, BI = Y。

### 2.3 PCB 扩展板设计（如有）

> 原理图、布局约束（磁力计距天线 ≥15mm）、嘉立创打样、焊接验证。  
> 附：原理图截图 + 实物照片 + I²C 扫描截图。

### 2.4 数据质量与划分策略

> 划分策略：LOSO (Leave-One-Subject-Out)，按 subject_id 划分。  
> 禁止：同一被试跨训练/测试集。

---

## 3 信号预处理与窗口化

### 3.1 预处理流水线

```
raw → 校准(calib_params.json) → 裁剪首尾2s → 去重力(HP 0.3Hz) → 滤波(LP 20Hz) → 标准化 → 窗口化
```

### 3.2 滑动窗口参数

| 参数 | 设定值 | 理由 |
|------|--------|------|
| 窗口长 | 2.56 s (128 点) | 含 1-2 个完整步态周期 |
| 重叠率 | 50% | HAR 文献标准 |
| 标签策略 | 多数表决 (mode) | 窗口内取众数 |

### 3.3 数据集统计

| 指标 | 值 |
|------|-----|
| 被试数 | N |
| 总窗口数 | N |
| 类分布 | ... |

---

## 4 特征工程

### 4.1 时域特征

| 特征 | 公式 | 物理含义 |
|------|------|----------|
| mean | μ = (1/N)Σxᵢ | 信号直流分量 |
| std | σ = √(1/N Σ(xᵢ-μ)²) | 运动强度 |
| rms | √(1/N Σxᵢ²) | 有效值 |
| peak_to_peak | max(x) - min(x) | 最大变化幅度 |
| skew | (1/N)Σ((xᵢ-μ)/σ)³ | 分布不对称性 |
| kurtosis | (1/N)Σ((xᵢ-μ)/σ)⁴-3 | 分布尾重 |
| zero_cross_rate | ... | 信号振荡频繁度 |
| sma | (1/N)Σ|xᵢ| | 信号幅值面积 |
| iqr | Q₃ - Q₁ | 鲁棒离散度 |
| autocorr_lag1 | ... | 一阶自相关（周期性） |

### 4.2 频域特征

| 特征 | 公式 | 物理含义 |
|------|------|----------|
| dominant_freq | argmax |X(f)| | 主频/步频 |
| spectral_centroid | Σ f·|X(f)| / Σ |X(f)| | 频谱能量重心 |
| spectral_entropy | -Σ P(f) log P(f) | 频谱有序度 |
| energy_low/mid/high | 频带能量比 | 不同频段运动成分 |

### 4.3 复合/跨轴特征

> 合加速度/角速度/磁场模长统计、轴间相关系数、垂直/水平能量比、加加速度...

### 4.4 特征选择与降维

#### Filter 方法

> ANOVA F / 互信息 Top-K 排名...

#### Wrapper 与 Embedded

> SFS forward（ANOVA Top-100 预筛）、RF MDI、RFE、L1 LogisticRegression...

#### PCA

> 累计方差解释率曲线：X 维 → 95%，Y 维 → 99%。  
> 附图：PCA 累计方差曲线。

#### t-SNE 可视化

> 2D 嵌入图：7 类着色，观察可分布局。  
> 附图：t-SNE 可视化。

---

## 5 模式识别建模

### 5.1 贝叶斯决策与线性分类器

| 模型 | 原理 | 关键参数 |
|------|------|----------|
| GaussianNB | 高斯朴素贝叶斯 | 特征独立假设 |
| LDA | Fisher 线性判别 | SVD 求解器 |
| LogisticRegression | 对数几率回归 | L2 正则, max_iter=2000 |
| LinearSVM | 线性支持向量机 | C=1 |

#### 最小风险贝叶斯

> 代价矩阵 (任务书 §3.6)：跌倒漏检代价 ×10。  
> 对比标准决策 vs 代价敏感决策的跌倒召回率。

### 5.2 非线性分类器与集成学习

| 模型 | 类型 | 最佳参数 |
|------|------|----------|
| RBF_SVM | 核方法 | C=1, gamma=scale |
| RandomForest | Bagging | n=200 |
| AdaBoost | Boosting | n=100, lr=0.5 |
| GBDT | Boosting | n=100, lr=0.01, depth=3 |
| MLP | 神经网络 | hidden=(128,64), alpha=0.0001 |

### 5.3 超参数调优

> GridSearchCV 内嵌 LOSO：每 fold 训练折内 3-fold CV 搜索最佳参数。  
> 附：调参记录表。

---

## 6 实验结果与分析

### 表 1：多模型性能对比 (LOSO)

| 模型 | Accuracy | Macro F1 | Macro Precision | Macro Recall | 训练耗时 |
|------|----------|----------|-----------------|-------------|----------|
| ... | | | | | |

### 图 X：最优模型混淆矩阵

> 附图 + 分析。

### 图 X：ROC 曲线 (OvR)

> 附图 + AUC 值。

### 6.1 标定增益

| 数据 | Accuracy | 改善 |
|------|----------|------|
| 未标定 raw | XX% | — |
| 标定后 calibrated | XX% | +X% |

> 分析标定对识别精度的量化增益。

### 6.2 易混类分析

| 排名 | 混淆对 | 次数 | 物理原因 |
|------|--------|------|----------|
| 1 | upstairs ↔ downstairs | X | 步态周期性相近，仅垂直方向相反 |
| 2 | sit ↔ stand | X | 准静态，加速度均接近 1g |
| 3 | walk ↔ upstairs | X | 步频相近，加速度幅值重叠 |

### 6.3 显著性检验

| 对比 | χ² | p | 显著? |
|------|-----|---|-------|
| 最佳 vs 次佳 | X | X | X |

> McNemar 检验。Bootstrap 95% CI: [XX%, XX%]。

---

## 7 进阶探索（如有）

> 无监督聚类 (K-means/GMM) / HMM 时序平滑 / 1D-CNN-LSTM 端到端 / ESP32 边缘部署...
> 每项附量化对比。

---

## 8 总结与展望

### 8.1 工作总结

> 本文完成的工作：采集→标定→预处理→特征→分类→评估的全链路实践。  
> 最佳模型：XX，LOSO 准确率 XX%，跌倒召回率 XX%。

### 8.2 不足与改进

1. 被试数量有限（N 人），泛化能力待验证
2. 标定参数可进一步优化（磁力计覆盖度）
3. 实时推理尚未部署到 ESP32
4. 特征维度过高（285 维），可进一步精简

### 8.3 个人收获

> 每位成员各写一段。

---

## 致谢

> 感谢郑积仕老师的指导...

---

## 参考文献

1. 张学工.《模式识别》. 清华大学出版社.
2. 李航.《统计学习方法》（第二版）. 清华大学出版社.
3. Bulling, A., et al. "A Tutorial on Human Activity Recognition Using Body-worn Inertial Sensors." *ACM Computing Surveys*, 2014.
4. Anguita, D., et al. "A Public Domain Dataset for Human Activity Recognition Using Smartphones." *ESANN*, 2013.
5. Bao, L., Intille, S. "Activity Recognition from User-Annotated Acceleration Data." *Pervasive*, 2004.
6. Fitzgibbon, A., et al. "Direct Least Square Fitting of Ellipses." *IEEE TPAMI*, 1999.
7. scikit-learn: Machine Learning in Python. *JMLR*, 2011.
8. Ordóñez, F.J., Roggen, D. "Deep Convolutional and LSTM Recurrent Neural Networks for Multimodal Wearable Activity Recognition." *Sensors*, 2016.

---

## 附录

### A. 特征清单

> 见 `docs/特征字典.md`（294 特征 × 类型/公式）

### B. 核心代码清单

> 见 `src/` 目录各文件

### C. 采集协议

> 见 `docs/数据采集协议.md`

### D. PCB 原理图与订单截图

> （如有 PCB）附原理图 + Gerber 预览 + 嘉立创订单号

### E. AI 使用记录

> 见 `AI_USAGE.md`

---

> **使用说明**: 本模板用 Markdown 编写，建议用 Pandoc 转 PDF（`pandoc report.md -o report.pdf --pdf-engine=xelatex -V CJKmainfont=SimSun`）或导入 Word 排版。  
> 所有 `>` 开头的提示语和 `XX` 占位符在正式报告中替换为实际内容。
