# TODO

## ✅ D1-D8 全部完成

- [x] D1: 项目计划书 + 采集协议 + Git 仓库 + KiCad 原理图
- [x] D2: GY-521 六位置标定 + HMC5883L 椭球拟合 + calib_params.json + 标定报告 + Gerber 导出
- [x] D3: 9ch 固件 + 预处理 Pipeline + windowed_dataset + 对比图
- [x] D4: 294 维特征提取 + feature_matrix + 特征字典
- [x] D5: 特征选择 (Filter/Wrapper/Embedded) + 降维 (PCA/LDA/t-SNE) + 对比报告
- [x] D6: 6 基线分类器 + MinimumRiskBayes + LOSO + 决策边界
- [x] D7: 7 高级模型 + GridSearchCV + 学习曲线
- [x] D8: LOSO + 混淆矩阵 + McNemar + Bootstrap CI + 标定增益

## ✅ 硬件 + 真实数据 已完成 (2026-06-24)

- [x] PCB 焊接 (J1/J2/J3/J4 + R1/R2/C1/C2/R3/D1)
- [x] I²C 排错 (SDA/SCL短路修复) → 扫描验证 (0x68 + 0x1E)
- [x] 磁力计重标定 (3000样本, std 1.22uT, 改善76.1%)
- [x] 固件升级 (连续自动序列 + I²C错误恢复 + LED信号)
- [x] 离线采集 S01 真实数据 (7 trial, 283窗口)
- [x] 离线采集 S02 真实数据 (7 trial, 283窗口)
- [x] 全链路重跑 (真实数据):
  - 预处理: 566窗口 (566,128,9)
  - 特征提取: (566,292) 特征矩阵
  - 特征选择: RFE最优 (30维, 91.7%)
  - 基线: kNN 55.5% 最佳
  - 高级: kNN(k=3) 56.4%, MLP 50.7%
  - 评估: McNemar p<0.0001, Bootstrap 95%CI [51.2%,59.4%]

## 🟢 D9-D10: 收尾

- [ ] 进阶探索 (HMM/1D-CNN/聚类 至少选1项):
  - 推荐: **时序平滑** (HMM/滑窗投票) 解决 sit 0% recall
  - 可选: 1D-CNN 端到端对比手工特征
  - 可选: K-means/GMM 聚类 + ARI/NMI 评估
- [ ] 最终报告 PDF (5000-8000 字)
- [ ] 答辩 PPT
- [ ] demo 视频 (≤2 min)
- [ ] GitHub 仓库完善 (README, 一键复现)
- [ ] 交付文件夹整理归档

## 📊 真实数据结果速查

| 模型 | Accuracy | 备注 |
|------|----------|------|
| kNN (k=3,distance) | 56.4% | 最佳, McNemar显著 |
| MLP (128,64) | 50.7% | |
| RBF_SVM | 47.2% | |
| RF | 42.4% | |
| GBDT | 28.1% | 小样本过拟合 |
| LDA | 23.3% | 高维失效 |

| 类别 | recall | 问题 |
|------|--------|------|
| sit | 0% | 与stand完全混淆 |
| fall | 38% | 仅14窗口 |
| walk | 96% | 最好 |
| upstairs | 83% | |
