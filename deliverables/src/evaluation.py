"""
D8: Model evaluation and statistical rigor.
- LOSO evaluation with per-fold confusion matrices
- Best model deep analysis: CM, P/R/F1 (macro/micro), ROC-AUC (OvR)
- Error analysis: most confused classes + physical reasons
- McNemar test: best vs runner-up significance
- Bootstrap CI: 95% confidence interval
- Calibration gain: pre- vs post-calibration accuracy comparison
"""

from __future__ import annotations

import sys
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.base import clone
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler, label_binarize
from sklearn.decomposition import PCA
from sklearn.svm import LinearSVC, SVC
from sklearn.ensemble import RandomForestClassifier
from sklearn.neighbors import KNeighborsClassifier
from sklearn.model_selection import LeaveOneGroupOut
from sklearn.impute import SimpleImputer
from sklearn.feature_selection import VarianceThreshold
from sklearn.metrics import (
    accuracy_score, confusion_matrix, classification_report,
    roc_auc_score, roc_curve, auc,
    f1_score, precision_score, recall_score,
)
from scipy import stats

ROOT = Path(__file__).parent.parent
REPORTS_DIR = ROOT / "reports"
REPORTS_DIR.mkdir(exist_ok=True)

ACTIVITIES = {
    0: "sit", 1: "stand", 2: "walk", 3: "run",
    4: "upstairs", 5: "downstairs", 6: "fall",
}
CLASS_NAMES = [ACTIVITIES[i] for i in range(7)]

# Pre-computed confusion priors from project plan (§3.5)
CONFUSION_PRIORS = {
    ("sit", "stand"): "准静态活动, 加速度幅值接近 1g, 角速度接近零",
    ("upstairs", "downstairs"): "步态周期性相近, 仅垂直加速度方向相反, 单一特征难区分",
    ("walk", "upstairs"): "步频相近 (1.5-2 Hz), 加速度幅值上楼略大但重叠严重",
    ("walk", "run"): "均为平移周期性运动, 跑步强度更高 (RMS/主频 ~3 Hz vs ~2 Hz)",
    ("fall", "run"): "跌落冲击脉冲与跑步落地峰值时域幅值接近, 但时序结构不同 (单脉冲 vs 周期)",
}


# ---------------------------------------------------------------------------
# 1. LOSO evaluation (detailed)
# ---------------------------------------------------------------------------

def loso_evaluate_detailed(model, X, y, groups, model_name="model"):
    """LOSO with per-fold confusion matrix and pooled predictions.

    Returns
    -------
    results : dict
    """
    logo = LeaveOneGroupOut()
    y_true_all, y_pred_all, y_prob_all = [], [], []
    fold_results = []

    for fold_i, (train_idx, test_idx) in enumerate(logo.split(X, y, groups)):
        X_train, X_test = X[train_idx], X[test_idx]
        y_train, y_test = y[train_idx], y[test_idx]
        subj = np.unique(groups[test_idx])[0]

        m = clone(model)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            m.fit(X_train, y_train)
        y_pred = m.predict(X_test)

        # Get probabilities if available
        try:
            y_prob = m.predict_proba(X_test)
        except (AttributeError, NotImplementedError):
            y_prob = None

        acc = accuracy_score(y_test, y_pred)
        cm = confusion_matrix(y_test, y_pred, labels=range(7))
        fold_results.append({
            "fold": fold_i + 1, "subject": subj,
            "n_train": len(y_train), "n_test": len(y_test),
            "accuracy": acc, "confusion_matrix": cm,
        })

        y_true_all.extend(y_test)
        y_pred_all.extend(y_pred)
        if y_prob is not None:
            y_prob_all.append(y_prob)

    y_true_all = np.array(y_true_all)
    y_pred_all = np.array(y_pred_all)
    y_prob_all = np.vstack(y_prob_all) if y_prob_all else None

    return {
        "model_name": model_name,
        "accuracy": accuracy_score(y_true_all, y_pred_all),
        "macro_f1": f1_score(y_true_all, y_pred_all, average="macro"),
        "macro_precision": precision_score(y_true_all, y_pred_all, average="macro"),
        "macro_recall": recall_score(y_true_all, y_pred_all, average="macro"),
        "per_class_precision": precision_score(y_true_all, y_pred_all, average=None, labels=range(7)),
        "per_class_recall": recall_score(y_true_all, y_pred_all, average=None, labels=range(7)),
        "per_class_f1": f1_score(y_true_all, y_pred_all, average=None, labels=range(7)),
        "confusion_matrix": confusion_matrix(y_true_all, y_pred_all, labels=range(7)),
        "classification_report": classification_report(
            y_true_all, y_pred_all, target_names=CLASS_NAMES, zero_division=0,
        ),
        "y_true": y_true_all, "y_pred": y_pred_all, "y_prob": y_prob_all,
        "fold_results": fold_results,
    }


# ---------------------------------------------------------------------------
# 2. ROC curves (OvR)
# ---------------------------------------------------------------------------

def plot_roc_curves(y_true, y_prob, class_names=None, save_path=None):
    """One-vs-Rest ROC curves for multi-class."""
    if class_names is None:
        class_names = CLASS_NAMES
    n_classes = y_prob.shape[1]
    y_true_bin = label_binarize(y_true, classes=range(n_classes))

    fig, ax = plt.subplots(figsize=(7, 6))
    colors = plt.cm.tab10(np.linspace(0, 1, n_classes))

    for i in range(n_classes):
        fpr, tpr, _ = roc_curve(y_true_bin[:, i], y_prob[:, i])
        roc_auc = auc(fpr, tpr)
        ax.plot(fpr, tpr, color=colors[i], lw=1.5,
                label=f"{class_names[i]} (AUC={roc_auc:.3f})")

    ax.plot([0, 1], [0, 1], "k--", lw=0.8, alpha=0.5)
    ax.set_xlabel("False Positive Rate")
    ax.set_ylabel("True Positive Rate")
    ax.set_title("ROC Curves (One-vs-Rest)")
    ax.legend(fontsize=7, loc="lower right")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1.02)
    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches="tight")
    return fig


# ---------------------------------------------------------------------------
# 3. Confusion matrix plot
# ---------------------------------------------------------------------------

def plot_confusion_matrix(cm, class_names=None, title="Confusion Matrix", save_path=None):
    """Normalized confusion matrix heatmap."""
    if class_names is None:
        class_names = CLASS_NAMES
    cm_norm = cm.astype("float") / cm.sum(axis=1, keepdims=True)

    fig, ax = plt.subplots(figsize=(8, 6))
    im = ax.imshow(cm_norm, cmap="Blues", vmin=0, vmax=1)
    n = cm.shape[0]
    ax.set_xticks(range(n))
    ax.set_yticks(range(n))
    ax.set_xticklabels(class_names, rotation=45, ha="right")
    ax.set_yticklabels(class_names)

    for i in range(n):
        for j in range(n):
            ax.text(j, i, f"{cm[i, j]}\n({cm_norm[i, j]:.1%})",
                    ha="center", va="center", fontsize=8)

    plt.colorbar(im, ax=ax)
    ax.set_xlabel("Predicted")
    ax.set_ylabel("True")
    ax.set_title(title)
    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches="tight")
    return fig


# ---------------------------------------------------------------------------
# 4. Error analysis
# ---------------------------------------------------------------------------

def analyze_errors(cm, class_names=None):
    """Identify top confused class pairs and map to physical reasons.

    Returns
    -------
    list[dict] : sorted by off-diagonal count descending
    """
    if class_names is None:
        class_names = CLASS_NAMES
    n = cm.shape[0]
    errors = []
    for i in range(n):
        for j in range(n):
            if i != j and cm[i, j] > 0:
                pair = (class_names[i], class_names[j])
                reason = CONFUSION_PRIORS.get(pair) or CONFUSION_PRIORS.get(
                    (pair[1], pair[0])) or "需进一步分析"
                errors.append({
                    "true": class_names[i], "predicted": class_names[j],
                    "count": int(cm[i, j]), "reason": reason,
                })
    errors.sort(key=lambda e: e["count"], reverse=True)
    return errors


# ---------------------------------------------------------------------------
# 5. McNemar test
# ---------------------------------------------------------------------------

def mcnemar_test(y_true, y_pred_a, y_pred_b):
    """McNemar's test for paired nominal data.

    H0: model A and model B have the same error rate.
    """
    y_true = np.asarray(y_true)
    y_pred_a = np.asarray(y_pred_a)
    y_pred_b = np.asarray(y_pred_b)

    n_ab = np.sum((y_pred_a == y_true) & (y_pred_b != y_true))
    n_ba = np.sum((y_pred_a != y_true) & (y_pred_b == y_true))

    if (n_ab + n_ba) == 0:
        return {"chi2": 0, "p_value": 1.0, "n_ab": n_ab, "n_ba": n_ba,
                "significant": False}

    # Yates continuity correction
    chi2 = (abs(n_ab - n_ba) - 1) ** 2 / (n_ab + n_ba)
    p_value = 1 - stats.chi2.cdf(chi2, df=1)
    return {
        "chi2": chi2, "p_value": p_value,
        "n_ab": n_ab, "n_ba": n_ba,
        "significant": p_value < 0.05,
    }


# ---------------------------------------------------------------------------
# 6. Bootstrap CI
# ---------------------------------------------------------------------------

def bootstrap_ci(y_true, y_pred, metric=accuracy_score, n_boot=1000, alpha=0.05):
    """Bootstrap confidence interval for a metric (0.632 not implemented — standard bootstrap)."""
    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)
    n = len(y_true)
    scores = np.zeros(n_boot)
    rng = np.random.RandomState(42)

    for i in range(n_boot):
        idx = rng.choice(n, size=n, replace=True)
        scores[i] = metric(y_true[idx], y_pred[idx])

    observed = metric(y_true, y_pred)
    lower = np.percentile(scores, 100 * alpha / 2)
    upper = np.percentile(scores, 100 * (1 - alpha / 2))
    return {"observed": observed, "lower": lower, "upper": upper, "n_boot": n_boot}


# ---------------------------------------------------------------------------
# 7. Calibration gain analysis
# ---------------------------------------------------------------------------

def calibration_gain_analysis():
    """Compare classifier accuracy with vs without calibration.

    For demo data this is a placeholder — real data will have raw/ and calibrated/
    feature matrices to compare.

    Returns
    -------
    report : dict
    """
    raw_dir = ROOT / "data" / "raw"
    calib_path = ROOT / "calib" / "calib_params.json"

    has_raw = raw_dir.exists() and any(raw_dir.iterdir())
    has_calib = calib_path.exists()

    if not has_calib:
        return {"status": "skipped", "reason": "calib_params.json not found"}

    # Load calib params summary
    with open(calib_path, "r", encoding="utf-8") as f:
        calib_data = json.load(f)

    report = {
        "status": "calibration_params_available",
        "has_raw_data": has_raw,
        "calib_params_summary": {},
        "note": "Real calibration gain requires re-running full pipeline with raw vs calibrated data. "
                "See §G4 of task book for protocol.",
    }

    # Summarise calibration parameters
    if "accelerometer" in calib_data:
        report["calib_params_summary"]["accelerometer"] = {
            k: v for k, v in calib_data["accelerometer"].items()
            if k in ("bias", "scale", "method")
        }
    if "magnetometer" in calib_data:
        report["calib_params_summary"]["magnetometer"] = {
            k: v for k, v in calib_data["magnetometer"].items()
            if k in ("hard_iron", "soft_iron", "method")
        }
    if "gyroscope" in calib_data:
        report["calib_params_summary"]["gyroscope"] = {
            k: v for k, v in calib_data["gyroscope"].items()
            if k in ("bias", "method")
        }

    # Try to extract noise analysis
    if "noise_analysis" in calib_data:
        report["calib_params_summary"]["noise_analysis"] = calib_data["noise_analysis"]

    return report


# ---------------------------------------------------------------------------
# 8. Master evaluation runner
# ---------------------------------------------------------------------------

def run_full_evaluation(X, y, groups):
    """Run the complete D8 evaluation pipeline.

    1. LOSO on 3 best models from D6/D7
    2. Best model deep analysis (CM, ROC, per-class metrics)
    3. Error analysis
    4. McNemar test (best vs runner-up)
    5. Bootstrap CI
    6. Calibration gain summary
    """
    # Pick top models from D6/D7
    models = {
        "LinearSVM": Pipeline([
            ("scaler", StandardScaler()),
            ("clf", LinearSVC(max_iter=2000, dual="auto", random_state=42)),
        ]),
        "RBF_SVM": Pipeline([
            ("scaler", StandardScaler()),
            ("clf", SVC(kernel="rbf", C=1, gamma="scale", probability=True, random_state=42)),
        ]),
        "RandomForest": Pipeline([
            ("clf", RandomForestClassifier(n_estimators=200, random_state=42, n_jobs=-1)),
        ]),
        "kNN_k5": Pipeline([
            ("scaler", StandardScaler()),
            ("clf", KNeighborsClassifier(n_neighbors=5, algorithm="kd_tree")),
        ]),
    }

    print("=== D8 FULL EVALUATION ===\n")

    # --- LOSO for all models ---
    all_results = {}
    for name, model in models.items():
        print(f"--- {name} LOSO ---")
        res = loso_evaluate_detailed(model, X, y, groups, model_name=name)
        all_results[name] = res
        for fr in res["fold_results"]:
            print(f"  Fold {fr['fold']} [{fr['subject']}]: acc={fr['accuracy']:.4f} "
                  f"(train={fr['n_train']}, test={fr['n_test']})")
        print(f"  Overall: acc={res['accuracy']:.4f}, macro_f1={res['macro_f1']:.4f}\n")

    # Rank models
    ranked = sorted(all_results.items(), key=lambda kv: kv[1]["accuracy"], reverse=True)
    best_name, best_res = ranked[0]
    runner_up_name, runner_up_res = ranked[1]
    print(f"Best: {best_name} (acc={best_res['accuracy']:.4f})")
    print(f"Runner-up: {runner_up_name} (acc={runner_up_res['accuracy']:.4f})\n")

    # --- Best model deep analysis ---
    print(f"=== BEST MODEL: {best_name} ===\n")
    print(best_res["classification_report"])

    # Confusion matrix
    fig1 = plot_confusion_matrix(
        best_res["confusion_matrix"], CLASS_NAMES,
        title=f"Confusion Matrix — {best_name} (LOSO)",
        save_path=REPORTS_DIR / "d8_confusion_matrix.png",
    )
    plt.close(fig1)

    # ROC curves
    if best_res["y_prob"] is not None:
        fig2 = plot_roc_curves(
            best_res["y_true"], best_res["y_prob"], CLASS_NAMES,
            save_path=REPORTS_DIR / "d8_roc_curves.png",
        )
        plt.close(fig2)

    # --- Error analysis ---
    print("\n=== ERROR ANALYSIS ===\n")
    errors = analyze_errors(best_res["confusion_matrix"], CLASS_NAMES)
    if errors:
        for e in errors[:5]:
            print(f"  {e['true']} → {e['predicted']}: {e['count']} 次 — {e['reason']}")
    else:
        print("  (no misclassifications)")

    # --- McNemar test ---
    print("\n=== McNEMAR TEST ===\n")
    mcn = mcnemar_test(best_res["y_true"], best_res["y_pred"], runner_up_res["y_pred"])
    print(f"  {best_name} vs {runner_up_name}:")
    print(f"    n_ab (best correct, runner-up wrong): {mcn['n_ab']}")
    print(f"    n_ba (best wrong, runner-up correct): {mcn['n_ba']}")
    print(f"    chi2={mcn['chi2']:.4f}, p={mcn['p_value']:.4f}")
    print(f"    Significant at α=0.05: {'Yes' if mcn['significant'] else 'No'}")

    # --- Bootstrap CI ---
    print("\n=== BOOTSTRAP CI ===\n")
    bci = bootstrap_ci(best_res["y_true"], best_res["y_pred"])
    print(f"  {best_name} accuracy: {bci['observed']:.4f} "
          f"[95% CI: {bci['lower']:.4f}, {bci['upper']:.4f}] (n_boot={bci['n_boot']})")

    # --- Calibration gain ---
    print("\n=== CALIBRATION GAIN ===\n")
    calib_report = calibration_gain_analysis()
    print(f"  Status: {calib_report['status']}")
    if calib_report["status"] != "skipped":
        print(f"  Params available: {list(calib_report.get('calib_params_summary', {}).keys())}")
    print(f"  Note: {calib_report.get('note', 'N/A')}")

    # --- Save summary ---
    summary = {
        "best_model": best_name,
        "best_accuracy": best_res["accuracy"],
        "best_macro_f1": best_res["macro_f1"],
        "runner_up": runner_up_name,
        "runner_up_accuracy": runner_up_res["accuracy"],
        "mcnemar_chi2": mcn["chi2"],
        "mcnemar_p": mcn["p_value"],
        "mcnemar_significant": mcn["significant"],
        "bootstrap_observed": bci["observed"],
        "bootstrap_ci_lower": bci["lower"],
        "bootstrap_ci_upper": bci["upper"],
        "per_class_recall": dict(zip(CLASS_NAMES, best_res["per_class_recall"].tolist())),
        "per_class_precision": dict(zip(CLASS_NAMES, best_res["per_class_precision"].tolist())),
        "top_errors": errors[:5],
        "calibration_status": calib_report["status"],
    }

    summary_path = REPORTS_DIR / "d8_evaluation_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, default=str)

    print(f"\nSummary saved to {summary_path}")

    # --- Model ranking plot ---
    fig3, ax = plt.subplots(figsize=(8, 4))
    names = list(all_results.keys())
    accs = [all_results[n]["accuracy"] for n in names]
    f1s = [all_results[n]["macro_f1"] for n in names]
    x = np.arange(len(names))
    w = 0.35
    ax.bar(x - w / 2, accs, w, label="Accuracy", color="steelblue")
    ax.bar(x + w / 2, f1s, w, label="Macro F1", color="coral")
    ax.set_xticks(x)
    ax.set_xticklabels(names)
    ax.set_ylabel("Score")
    ax.set_title("D8 Final Model Ranking (LOSO)")
    ax.legend()
    ax.set_ylim(0, 1.1)
    plt.tight_layout()
    fig3.savefig(REPORTS_DIR / "d8_model_ranking.png", dpi=150)
    plt.close(fig3)

    return all_results, summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    feature_path = ROOT / "data" / "features" / "feature_matrix.csv"
    if not feature_path.exists():
        print(f"feature_matrix.csv not found at {feature_path}", file=sys.stderr)
        sys.exit(1)

    df = pd.read_csv(feature_path)
    y = df["label"].values
    groups = df["subject_id"].values

    drop_cols = [c for c in ["subject_id", "window_id", "label"] if c in df.columns]
    X = df.drop(columns=drop_cols).values.astype(np.float64)

    if np.any(np.isnan(X)):
        X = SimpleImputer(strategy="median").fit_transform(X)
    var_mask = VarianceThreshold(threshold=0.0).fit(X).get_support()
    if not var_mask.all():
        X = X[:, var_mask]

    print(f"Loaded {X.shape[0]} samples x {X.shape[1]} features, "
          f"{len(np.unique(groups))} subjects\n")

    all_results, summary = run_full_evaluation(X, y, groups)
