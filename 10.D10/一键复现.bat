@echo off
chcp 65001 >nul
echo ==========================================
echo HAR 项目一键复现
echo ==========================================
echo.

cd /d "%~dp0.."

echo [1/7] 检查 Python 环境...
python --version >nul 2>&1
if errorlevel 1 (
    echo 错误: 未找到 Python，请先安装 Python 3.10+
    pause
    exit /b 1
)
echo   Python OK

echo [2/7] 安装依赖...
pip install -r requirements.txt -q
echo   依赖安装完成

echo [3/7] 确认真实数据...
if not exist "data\raw\real\S01" (
    echo 错误: data\raw\real\S01 不存在!
    pause
    exit /b 1
)
if not exist "data\raw\real\S02" (
    echo 错误: data\raw\real\S02 不存在!
    pause
    exit /b 1
)
echo   数据就绪 (S01 + S02)

echo [4/7] 预处理...
python src/preprocess.py
if errorlevel 1 (echo 预处理失败! && pause && exit /b 1)
echo   预处理完成

echo [5/7] 特征提取...
python src/features.py
if errorlevel 1 (echo 特征提取失败! && pause && exit /b 1)
echo   特征提取完成

echo [6/7] 特征选择 + 分类器 + 评估...
python src/feature_selection.py
python src/classifiers_baseline.py
python src/models_advanced.py
python src/evaluation.py
echo   分类器与评估完成

echo [7/7] 进阶探索 (D9)...
python src/d9_advanced_exploration.py
echo   进阶探索完成

echo.
echo ==========================================
echo 全链路运行完成!
echo ==========================================
echo.
echo 结果文件位置:
echo   reports\d8_confusion_matrix.png   — 混淆矩阵
echo   reports\d8_model_ranking.png      — 模型排名
echo   reports\d9_temporal_smoothing_recall.png — 时序平滑
echo   reports\d9_cnn_comparison.png     — CNN对比
echo   reports\d9_clustering_tsne.png    — 聚类可视化
echo   reports\d9_clustering_metrics.png — 聚类指标
echo   reports\defense_ppt.pptx          — 答辩PPT
echo.
echo 详细报告: reports\final_report.md
echo.
pause
