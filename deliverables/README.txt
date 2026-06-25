HAR 可穿戴人体活动识别系统 — 最终交付物

============================================

交付日期: 2026-06-25
团队: 孔子瑜（算法与工程）、李宝平（数据采集与固件）
导师: 郑积仕
GitHub: https://github.com/kkawo/har-project.git

============================================

文件清单:

[1] 最终报告
    reports/final_report.md          课程论文正文 (5000+字)
    PDF版本请用 Pandoc 转换:
    pandoc reports/final_report.md -o reports/final_report.pdf --pdf-engine=xelatex

[2] 答辩PPT
    reports/defense_ppt.pptx         17页, 16:9宽屏
    生成脚本: src/d10_generate_ppt.py

[3] Demo视频脚本
    reports/demo_script.md           ≤2分钟分镜表

[4] 项目文档
    项目深度说明.md                    完整项目手册
    HANDOVER.md                      交接文档
    PROJECT_STATUS.md                 项目状态
    TODO.md                          待办清单
    AI_USAGE.md                      AI协作记录
    答辩问答库.md                     25+问答准备

[5] 源码 (src/)
    utils.py (38行)                  常量与路径
    preprocess.py (503行)            预处理流水线
    features.py (448行)              特征提取
    feature_selection.py (619行)     特征选择与降维
    classifiers_baseline.py (403行)  基线分类器
    models_advanced.py (347行)       高级模型
    evaluation.py (509行)            评估体系
    d9_advanced_exploration.py (814行) 进阶探索
    d10_generate_ppt.py (280+行)    PPT生成

[6] 关键数据
    calib/calib_params.json          三传感器标定参数
    data/raw/real/S01-S02/           真实数据 (14 CSV)
    data/windowed/windowed_dataset.npz  (566,128,9)
    data/features/feature_matrix.npz  (566,292)

[7] 报告图表 (reports/)
    共 19+ PNG，涵盖标定、预处理、特征选择、分类对比、
    混淆矩阵、ROC曲线、时序平滑、CNN对比、聚类可视化

============================================

一键复现:

    Windows: 双击 deliverables\一键复现.bat
    或手动: 见 README.md §一键复现

============================================

答辩前检查清单:
  [ ] 读 答辩问答库.md (至少抽问 5 题能讲清)
  [ ] 核心算法原理已理解 (贝叶斯/LOSO/PCA/McNemar)
  [ ] PPT 已审查每页内容
  [ ] Demo 视频已拍摄/编辑
  [ ] GitHub README 已更新
  [ ] 最终报告已转 PDF
