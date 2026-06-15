"""
D8: Model evaluation and statistical rigor.
- LOSO (Leave-One-Subject-Out) cross-validation
- k-fold stratified CV (for comparison)
- Confusion matrix, P/R/F1 (macro/micro), ROC-AUC
- Bootstrap interval estimation (0.632)
- McNemar's test for significance
- Calibration gain (pre- vs post-calibration accuracy)
"""

import numpy as np
import matplotlib.pyplot as plt
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    classification_report,
    roc_auc_score,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.model_selection import (
    LeaveOneGroupOut,
    StratifiedKFold,
    cross_val_score,
)
from scipy import stats


def loso_evaluate(model, X, y, groups):
    """Leave-One-Subject-Out cross-validation.
    groups: array of subject IDs (same length as X).
    """
    logo = LeaveOneGroupOut()
    y_true_all = []
    y_pred_all = []

    for train_idx, test_idx in logo.split(X, y, groups):
        model_clone = model.__class__(**model.get_params())
        model_clone.fit(X[train_idx], y[train_idx])
        y_pred = model_clone.predict(X[test_idx])
        y_true_all.extend(y[test_idx])
        y_pred_all.extend(y_pred)

    y_true_all = np.array(y_true_all)
    y_pred_all = np.array(y_pred_all)
    return {
        "accuracy": accuracy_score(y_true_all, y_pred_all),
        "macro_f1": f1_score(y_true_all, y_pred_all, average="macro"),
        "confusion_matrix": confusion_matrix(y_true_all, y_pred_all),
        "classification_report": classification_report(y_true_all, y_pred_all, zero_division=0),
        "y_true": y_true_all,
        "y_pred": y_pred_all,
    }


def kfold_evaluate(model, X, y, n_splits=5):
    """Stratified k-fold CV pooling all predictions."""
    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
    y_true_all = []
    y_pred_all = []

    for train_idx, test_idx in skf.split(X, y):
        model_clone = model.__class__(**model.get_params())
        model_clone.fit(X[train_idx], y[train_idx])
        y_pred = model_clone.predict(X[test_idx])
        y_true_all.extend(y[test_idx])
        y_pred_all.extend(y_pred)

    y_true_all = np.array(y_true_all)
    y_pred_all = np.array(y_pred_all)
    return {
        "accuracy": accuracy_score(y_true_all, y_pred_all),
        "macro_f1": f1_score(y_true_all, y_pred_all, average="macro"),
        "confusion_matrix": confusion_matrix(y_true_all, y_pred_all),
    }


def bootstrap_ci(y_true, y_pred, metric=accuracy_score, n_boot=1000, alpha=0.05):
    """Bootstrap confidence interval for a given metric."""
    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)
    n = len(y_true)
    scores = np.zeros(n_boot)
    rng = np.random.RandomState(42)

    for i in range(n_boot):
        idx = rng.choice(n, size=n, replace=True)
        scores[i] = metric(y_true[idx], y_pred[idx])

    lower = np.percentile(scores, 100 * alpha / 2)
    upper = np.percentile(scores, 100 * (1 - alpha / 2))
    observed = metric(y_true, y_pred)
    return observed, lower, upper


def mcnemar_test(y_true, y_pred_a, y_pred_b):
    """McNemar's test: is model A significantly different from model B?"""
    y_true = np.asarray(y_true)
    y_pred_a = np.asarray(y_pred_a)
    y_pred_b = np.asarray(y_pred_b)

    # Contingency table
    n_ab = np.sum((y_pred_a == y_true) & (y_pred_b != y_true))  # A correct, B wrong
    n_ba = np.sum((y_pred_a != y_true) & (y_pred_b == y_true))  # A wrong, B correct

    # Yates continuity correction
    chi2 = (abs(n_ab - n_ba) - 1) ** 2 / (n_ab + n_ba) if (n_ab + n_ba) > 0 else 0
    p_value = 1 - stats.chi2.cdf(chi2, df=1)
    return {"chi2": chi2, "p_value": p_value, "n_ab": n_ab, "n_ba": n_ba}


def plot_confusion_matrix(cm, class_names=None, title="Confusion Matrix", save_path=None):
    """Plot a normalized confusion matrix."""
    cm_norm = cm.astype("float") / cm.sum(axis=1, keepdims=True)
    fig, ax = plt.subplots(figsize=(8, 6))
    im = ax.imshow(cm_norm, cmap="Blues", vmin=0, vmax=1)
    ax.set_xticks(range(len(class_names)) if class_names else range(cm.shape[0]))
    ax.set_yticks(range(len(class_names)) if class_names else range(cm.shape[0]))
    if class_names:
        ax.set_xticklabels(class_names, rotation=45, ha="right")
        ax.set_yticklabels(class_names)
    plt.colorbar(im, ax=ax)
    # Annotate
    for i in range(cm.shape[0]):
        for j in range(cm.shape[1]):
            ax.text(j, i, f"{cm[i, j]}\n({cm_norm[i, j]:.1%})",
                    ha="center", va="center", fontsize=8)
    ax.set_xlabel("Predicted")
    ax.set_ylabel("True")
    ax.set_title(title)
    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=150)
    return fig


if __name__ == "__main__":
    print("Evaluation module loaded.")
    print("Key functions: loso_evaluate, kfold_evaluate, bootstrap_ci, mcnemar_test")
