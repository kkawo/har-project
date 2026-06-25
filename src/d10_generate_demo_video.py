"""
D10: Auto-generate demo video from report charts.
Uses matplotlib + opencv to create a narrated slideshow.

Output: reports/demo_video.mp4 (≤2 min, 1080p, 30fps)

Usage: python src/d10_generate_demo_video.py

Requires: opencv-python (pip install opencv-python)
"""

from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
import cv2
import os
import textwrap

ROOT = Path(__file__).parent.parent
REPORTS_DIR = ROOT / "reports"
OUTPUT_VIDEO = REPORTS_DIR / "demo_video.mp4"

# Video specs
FPS = 30
WIDTH, HEIGHT = 1920, 1080
BG_COLOR = "#1E1E2E"
ACCENT = "#1A56DB"
HIGHLIGHT = "#E86A17"
WHITE = "#FFFFFF"

# Font settings
plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def create_frame(width=WIDTH, height=HEIGHT, bg=BG_COLOR):
    """Create a blank frame with background."""
    fig, ax = plt.subplots(figsize=(width / 100, height / 100), dpi=100)
    fig.patch.set_facecolor(bg)
    ax.set_xlim(0, width)
    ax.set_ylim(0, height)
    ax.set_facecolor(bg)
    ax.axis("off")
    return fig, ax


def add_text_box(ax, text, x, y, w, h, fontsize=24, color=WHITE,
                 ha="center", va="center", bold=False, alpha=0.15):
    """Add a styled text box."""
    rect = FancyBboxPatch(
        (x - w / 2, y - h / 2), w, h,
        boxstyle="round,pad=0.1", facecolor=ACCENT, edgecolor="none",
        alpha=alpha, zorder=0,
    )
    ax.add_patch(rect)
    ax.text(x, y, text, fontsize=fontsize, color=color,
            ha=ha, va=va, fontweight="bold" if bold else "normal",
            zorder=1)


def add_title(ax, text, y=950, fontsize=42):
    """Add a main title."""
    ax.text(WIDTH / 2, y, text, fontsize=fontsize, color=WHITE,
            ha="center", va="center", fontweight="bold")


def add_subtitle(ax, text, y=850, fontsize=22):
    """Add a subtitle."""
    lines = textwrap.wrap(text, width=60)
    for i, line in enumerate(lines):
        ax.text(WIDTH / 2, y - i * 35, line, fontsize=fontsize,
                color="#CCCCCC", ha="center", va="center")


def add_chart(ax, img_path, x, y, w, h):
    """Embed a PNG chart."""
    if os.path.exists(img_path):
        img = plt.imread(img_path)
        ax.imshow(img, extent=[x, x + w, y, y + h], zorder=2)
    else:
        ax.text(x + w / 2, y + h / 2, f"[图表缺失]\n{Path(img_path).name}",
                ha="center", va="center", fontsize=16, color="#666666")


def frame_to_array(fig):
    """Convert matplotlib figure to numpy array for OpenCV."""
    fig.canvas.draw()
    data = np.frombuffer(fig.canvas.tostring_argb(), dtype=np.uint8)
    data = data.reshape(fig.canvas.get_width_height()[::-1] + (4,))
    # ARGB -> BGR (drop alpha, reorder): A=0,R=1,G=2,B=3 → B=3,G=2,R=1
    return np.ascontiguousarray(data[:, :, [3, 2, 1]])


def write_frames(out, fig, n_frames=90):
    """Write n_frames copies to video."""
    frame = frame_to_array(fig)
    for _ in range(n_frames):
        out.write(frame)
    plt.close(fig)


def scene_simple_text(title, subtitle_lines, n_frames=90):
    """Plain text slide."""
    fig, ax = create_frame()
    add_title(ax, title, y=650)
    for i, line in enumerate(subtitle_lines):
        add_subtitle(ax, line, y=550 - i * 40, fontsize=20)
    write_frames(out, fig, n_frames)


def scene_with_chart(title, chart_paths, labels, subtitle_lines=None, n_frames=150):
    """Slide with embedded charts."""
    fig, ax = create_frame()
    add_title(ax, title, y=980, fontsize=32)

    n_charts = len(chart_paths)
    chart_w = 750
    chart_h = 520
    total_w = n_charts * chart_w + (n_charts - 1) * 30
    start_x = (WIDTH - total_w) / 2
    chart_y = 420

    for i, (path, label) in enumerate(zip(chart_paths, labels)):
        x = start_x + i * (chart_w + 30)
        add_chart(ax, path, x, chart_y, chart_w, chart_h)
        ax.text(x + chart_w / 2, chart_y - 15, label,
                fontsize=18, color="#CCCCCC", ha="center", va="bottom")

    if subtitle_lines:
        for i, line in enumerate(subtitle_lines):
            ax.text(WIDTH / 2, 350 - i * 35, line,
                    fontsize=20, color=WHITE, ha="center", va="center")

    write_frames(out, fig, n_frames)


def scene_big_number(numbers_with_labels, title, n_frames=120):
    """Key metrics highlight slide."""
    fig, ax = create_frame()
    add_title(ax, title, y=920, fontsize=36)

    n_items = len(numbers_with_labels)
    item_w = WIDTH / n_items
    for i, (num, label, color) in enumerate(numbers_with_labels):
        x = item_w * i + item_w / 2
        ax.text(x, 600, str(num), fontsize=72, color=color,
                ha="center", va="center", fontweight="bold")
        ax.text(x, 480, label, fontsize=22, color="#CCCCCC",
                ha="center", va="center")

    write_frames(out, fig, n_frames)


# =========================================================================
# Video assembly
# =========================================================================

print("Generating demo video...")

fourcc = cv2.VideoWriter_fourcc(*"mp4v")
out = cv2.VideoWriter(str(OUTPUT_VIDEO), fourcc, FPS, (WIDTH, HEIGHT))

# ---- Scene 1: Title (3s) ----
fig, ax = create_frame()
ax.text(WIDTH / 2, 700, "基于惯性/磁传感器的人体活动模式识别", fontsize=44,
        color=WHITE, ha="center", va="center", fontweight="bold")
ax.text(WIDTH / 2, 580, "系统设计与实现", fontsize=36,
        color=ACCENT, ha="center", va="center", fontweight="bold")
ax.text(WIDTH / 2, 430, "福建理工大学  智能科学与技术", fontsize=22,
        color="#CCCCCC", ha="center", va="center")
ax.text(WIDTH / 2, 380, "孔子瑜（算法与工程）  李宝平（数据采集与固件）  郑积仕 导师", fontsize=18,
        color="#888888", ha="center", va="center")
ax.text(WIDTH / 2, 280, "github.com/kkawo/har-project", fontsize=16,
        color="#666666", ha="center", va="center")
write_frames(out, fig, 90)

# ---- Scene 2: Hardware (5s) ----
fig, ax = create_frame()
add_title(ax, "硬件平台", y=950)
add_text_box(ax, "ESP32-S3 Shield PCB + GY-521 (MPU6050) + GY-273 (HMC5883L)",
             WIDTH / 2, 750, 1600, 80, fontsize=24)
add_text_box(ax, "9通道 @50Hz  |  I²C (SDA=IO17, SCL=IO18)  |  NeoPixel LED状态指示",
             WIDTH / 2, 630, 1500, 70, fontsize=20)
add_text_box(ax, "加速度计 ±8g  |  陀螺仪 ±2000dps  |  磁力计 3-axis  |  腰部佩戴",
             WIDTH / 2, 530, 1400, 60, fontsize=18, color="#CCCCCC")
items = [
    ("GY-521", "Acc+Gyro\n@ 0x68", HIGHLIGHT),
    ("GY-273", "Mag\n@ 0x1E", ACCENT),
    ("ESP32-S3", "N16R8\nWiFi/BLE", "#2E8B57"),
    ("Shield PCB", "KiCad\n手工焊", "#DC3545"),
]
for i, (name, desc, color) in enumerate(items):
    x = 300 + i * 450
    ax.text(x, 340, name, fontsize=30, color=color, ha="center", fontweight="bold")
    ax.text(x, 280, desc, fontsize=18, color="#CCCCCC", ha="center")
write_frames(out, fig, 150)

# ---- Scene 3: Calibration (5s) ----
scene_big_number(
    [("11.35→0.42", "加速度计 RMSE\n(m/s²)", HIGHLIGHT),
     ("7.44→1.22", "磁力计 norm_std\n(uT)", ACCENT),
     ("76.1%", "磁力计\n改善幅度", "#2E8B57"),
     ("96.3%", "加速度计\n改善幅度", "#17A2B8")],
    "传感器标定",
    n_frames=150,
)

# ---- Scene 4: Data Collection (5s) ----
fig, ax = create_frame()
add_title(ax, "真实数据采集", y=950)
add_text_box(ax, "S01 + S02  |  7类活动 × 1次  |  14 CSV  |  566窗口",
             WIDTH / 2, 750, 1500, 80, fontsize=24)
add_text_box(ax, "坐 → 站 → 走 → 跑 → 上楼 → 下楼 → 跌倒  |  每trial 65s (跌倒15s)",
             WIDTH / 2, 630, 1500, 60, fontsize=18, color="#CCCCCC")
# Activity timeline
activities = ["sit", "stand", "walk", "run", "upstairs", "downstairs", "fall"]
act_cn = ["静坐", "站立", "步行", "跑步", "上楼", "下楼", "跌倒"]
colors_bar = plt.cm.Set3(np.linspace(0, 1, 7))
bar_y = 450
bar_h = 60
bar_w = 200
for i, (act, cn, c) in enumerate(zip(activities, act_cn, colors_bar)):
    x = 100 + i * 250
    rect = FancyBboxPatch((x, bar_y), bar_w, bar_h, boxstyle="round,pad=0.08",
                          facecolor=c, edgecolor="none", alpha=0.85)
    ax.add_patch(rect)
    ax.text(x + bar_w / 2, bar_y + bar_h / 2 + 8, f"{cn}\n({act})",
            fontsize=16, color=WHITE, ha="center", va="center", fontweight="bold")
    if i < 6:
        ax.annotate("", xy=(x + bar_w + 15, bar_y + bar_h / 2),
                    xytext=(x + bar_w - 20, bar_y + bar_h / 2),
                    arrowprops=dict(arrowstyle="->", color=WHITE, lw=1.5))
write_frames(out, fig, 150)

# ---- Scene 5: Preprocess Pipeline (4s) ----
fig, ax = create_frame()
add_title(ax, "预处理流水线", y=950)
pipeline = ["Raw CSV", "校准\ncalib_params", "裁剪\n首尾2s", "去重力\nHP 0.3Hz",
            "低通\nLP 20Hz", "窗口化\n2.56s/128pt", "输出\n(566,128,9)"]
for i, step in enumerate(pipeline):
    x = 120 + i * 250
    y = 650
    rect = FancyBboxPatch((x, y), 200, 100, boxstyle="round,pad=0.08",
                          facecolor=ACCENT if i < len(pipeline) - 1 else HIGHLIGHT,
                          edgecolor="none", alpha=0.3 + 0.1 * i)
    ax.add_patch(rect)
    ax.text(x + 100, y + 50, step, fontsize=18, color=WHITE,
            ha="center", va="center", fontweight="bold")
    if i < len(pipeline) - 1:
        ax.annotate("", xy=(x + 220, y + 50), xytext=(x + 205, y + 50),
                    arrowprops=dict(arrowstyle="->", color=WHITE, lw=2))
add_subtitle(ax, "去重力：0.3Hz 高通 Butterworth 4阶  |  低通：20Hz 抗混叠", y=520, fontsize=18)
write_frames(out, fig, 120)

# ---- Scene 6: Features (5s) ----
scene_with_chart(
    "特征工程：294维 → 292维",
    [REPORTS_DIR / "d5_pca_cumvar.png", REPORTS_DIR / "d5_tsne.png"],
    ["PCA 累计方差曲线", "t-SNE 2D可视化"],
    ["时域14+频域10/轴  ×  9通道  +  模长特征  +  跨轴复合  =  292维有效特征",
     "RFE(RF) 30维最优 (CV 91.7%)  |  PCA 25维保留95%方差  |  t-SNE: walk/run/upstairs成簇"],
    n_frames=150,
)

# ---- Scene 7: Classifiers + Models (6s) ----
scene_with_chart(
    "13种模型 LOSO 系统对比",
    [REPORTS_DIR / "d8_model_ranking.png", REPORTS_DIR / "d7_learning_curves.png"],
    ["模型排名 (LOSO)", "学习曲线"],
    ["最佳模型: kNN (k=3, distance)  Accuracy 56.4%  |  MLP(128,64) 50.7%  |  RBF_SVM 47.2%",
     "小样本场景(每fold仅283窗口)，非参数kNN优于需大量数据估计参数的集成模型"],
    n_frames=180,
)

# ---- Scene 8: Confusion Matrix + Key Results (6s) ----
scene_with_chart(
    "评估：混淆矩阵分析",
    [REPORTS_DIR / "d8_confusion_matrix.png", REPORTS_DIR / "d8_roc_curves.png"],
    ["混淆矩阵", "ROC曲线 (OvR)"],
    ["sit recall = 0% → 与stand完全混淆（跨被试特征偏移）",
     "walk recall = 93.5% (最优)  |  upstairs = 83.7%  |  fall = 42.9% (仅14窗口)",
     "McNemar: kNN vs RBF_SVM p<0.0001  |  Bootstrap 95% CI: [51.2%, 59.4%]"],
    n_frames=180,
)

# ---- Scene 9: D9 Temporal Smoothing (6s) ----
scene_with_chart(
    "D9 进阶探索①：时序平滑",
    [REPORTS_DIR / "d9_temporal_smoothing_recall.png", REPORTS_DIR / "d9_hmm_transition_matrix.png"],
    ["时序平滑 per-class recall", "HMM 转移矩阵"],
    ["多数表决 L=7: Accuracy 56.4% → 59.5% (+3.1pp)",
     "walk 93.5%→100%  |  upstairs 83.7%→93.5%  |  fall 42.9%→50.0%",
     "sit 恒为 0% — 平滑无法修复特征级混淆（kNN永不预测sit）"],
    n_frames=180,
)

# ---- Scene 10: D9 CNN + Clustering (6s) ----
scene_with_chart(
    "D9 进阶探索②：1D-CNN + 无监督聚类",
    [REPORTS_DIR / "d9_cnn_comparison.png", REPORTS_DIR / "d9_clustering_tsne.png"],
    ["CNN vs kNN 对比", "聚类 t-SNE 2×2"],
    ["CNN整体仅25% (566窗口过少)，但 sit recall=50%！— 唯一检测到sit的模型",
     "KMeans+PCA: ARI=0.364, NMI=0.516 — PCA降维使聚类质量翻倍",
     "CNN与kNN互补：CNN找sit(kNN找不到), kNN找stand/walk(CNN找不到)"],
    n_frames=180,
)

# ---- Scene 11: Summary Key Metrics (5s) ----
scene_big_number(
    [("59.5%", "最佳 Accuracy\n(kNN+MV L=7)", HIGHLIGHT),
     ("0.569", "最佳 Macro F1\n(kNN+MV L=7)", ACCENT),
     ("13", "对比\n模型数", "#2E8B57"),
     ("3,950+", "Python\n代码行数", "#17A2B8"),
     ("566", "真实数据\n窗口数", "#DC3545")],
    "核心指标总览",
    n_frames=150,
)

# ---- Scene 12: Improvement Roadmap (4s) ----
fig, ax = create_frame()
add_title(ax, "改进路线图", y=950)
roadmap = [
    ("短期", "数据增强", "被试≥5人，每类≥3次", "#DC3545"),
    ("短期", "特征优化", "姿态角+小波时频+气压计", HIGHLIGHT),
    ("中期", "模型升级", "CNN+手工特征融合+迁移学习", ACCENT),
    ("长期", "边缘部署", "模型量化→TF-Lite→ESP32实时推理", "#2E8B57"),
]
for i, (time, direction, detail, color) in enumerate(roadmap):
    y = 750 - i * 130
    rect = FancyBboxPatch((200, y), 1520, 100, boxstyle="round,pad=0.08",
                          facecolor=color, edgecolor="none", alpha=0.2)
    ax.add_patch(rect)
    ax.text(260, y + 50, f"[{time}]", fontsize=22, color=color,
            ha="left", va="center", fontweight="bold")
    ax.text(480, y + 50, direction, fontsize=26, color=WHITE,
            ha="left", va="center", fontweight="bold")
    ax.text(750, y + 50, detail, fontsize=20, color="#CCCCCC",
            ha="left", va="center")
write_frames(out, fig, 120)

# ---- Scene 13: Ending (4s) ----
fig, ax = create_frame(bg=ACCENT)
ax.text(WIDTH / 2, 650, "感谢观看", fontsize=56, color=WHITE,
        ha="center", va="center", fontweight="bold")
ax.text(WIDTH / 2, 500, "github.com/kkawo/har-project", fontsize=24,
        color="#CCCCFF", ha="center", va="center")
ax.text(WIDTH / 2, 420, "孔子瑜  李宝平  |  郑积仕老师指导\n福建理工大学  智能科学与技术  |  2026年6月",
        fontsize=20, color="#AAAACC", ha="center", va="center")
write_frames(out, fig, 90)

# =========================================================================
# Finalize
# =========================================================================
out.release()
cv2.destroyAllWindows()

# Estimate duration
total_frames = int(cv2.VideoCapture(str(OUTPUT_VIDEO)).get(cv2.CAP_PROP_FRAME_COUNT))
duration = total_frames / FPS
print(f"\nDemo video saved to: {OUTPUT_VIDEO}")
print(f"Duration: {total_frames} frames / {duration:.1f}s")
print(f"File size: {OUTPUT_VIDEO.stat().st_size / 1024 / 1024:.1f} MB")
