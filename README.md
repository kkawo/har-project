# HAR Project — 可穿戴人体活动识别系统

基于惯性/磁传感器的人体活动模式识别系统设计与实现。

## 项目结构

```
har-project/
├── data/
│   ├── raw/           # 标定前原始数据
│   └── calibrated/    # 标定后数据
├── src/
│   ├── preprocess.py       # D3: 信号预处理与窗口化
│   ├── features.py         # D4: 特征提取
│   ├── feature_selection.py # D5: 特征选择与降维
│   ├── classifiers_baseline.py # D6: 基础分类器
│   ├── models_advanced.py  # D7: 非线性分类器与集成学习
│   ├── evaluation.py       # D8: 模型评估
│   └── utils.py            # 通用工具函数
├── notebooks/         # Jupyter 探索笔记
├── calib/             # D2: 标定参数与脚本
├── reports/           # 报告与图表输出
├── pcb/               # KiCad PCB 设计文件（进阶）
├── firmware/          # ESP32 采集固件
├── docs/              # 文档
│   ├── 项目计划书.md
│   ├── 数据采集协议.md
│   └── 特征字典.md
├── .gitignore
└── README.md
```

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 运行预处理
python src/preprocess.py

# 提取特征
python src/features.py

# 训练基线模型
python src/classifiers_baseline.py

# 模型评估
python src/evaluation.py
```

## 技术栈

- Python ≥ 3.10
- NumPy, SciPy, Pandas
- scikit-learn ≥ 1.3
- Matplotlib, seaborn
- allantools

## 团队

| 角色 | 成员 |
|------|------|
| 数据与采集 | （待填） |
| 算法与建模 | （待填） |
| 工程与可视化 | （待填） |

## 参考

- 张学工.《模式识别》. 清华大学出版社
- 李航.《统计学习方法》（第二版）. 清华大学出版社
- Bulling, A., et al. "A Tutorial on Human Activity Recognition Using Body-worn Inertial Sensors." ACM Computing Surveys, 2014.
