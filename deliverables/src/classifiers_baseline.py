"""
D6: Basic statistical classifiers.
- Gaussian Bayes (Minimum Error Rate)
- Naive Bayes, LDA, Logistic Regression, Perceptron, Linear SVM, kNN
- Minimum Risk Bayes (cost-sensitive for fall detection)
- LOSO evaluation with decision boundary visualisation
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.naive_bayes import GaussianNB
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.linear_model import LogisticRegression, Perceptron
from sklearn.svm import LinearSVC
from sklearn.neighbors import KNeighborsClassifier
from sklearn.base import clone
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.model_selection import LeaveOneGroupOut, cross_val_score
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    accuracy_score, confusion_matrix, classification_report,
    recall_score, f1_score,
)

ROOT = Path(__file__).parent.parent
REPORTS_DIR = ROOT / "reports"
REPORTS_DIR.mkdir(exist_ok=True)

# Activity labels from utils
ACTIVITIES = {
    0: "sit", 1: "stand", 2: "walk", 3: "run",
    4: "upstairs", 5: "downstairs", 6: "fall",
}


# ---------------------------------------------------------------------------
# Minimum Risk Bayes classifier
# ---------------------------------------------------------------------------

class MinimumRiskBayes:
    """Gaussian Bayes with a user-defined cost matrix for minimum risk decision.

    cost_matrix[i, j] = cost of deciding class i when true class is j.
    (i = predicted, j = true)
    """

    def __init__(self, cost_matrix=None):
        self.cost_matrix = cost_matrix
        self.gnb = GaussianNB()

    def fit(self, X, y):
        self.classes_ = np.unique(y)
        n_classes = len(self.classes_)
        if self.cost_matrix is None:
            self.cost_matrix = np.ones((n_classes, n_classes)) - np.eye(n_classes)
        self.gnb.fit(X, y)
        return self

    def predict(self, X):
        probs = self.gnb.predict_proba(X)
        expected_costs = probs @ self.cost_matrix.T
        idx = np.argmin(expected_costs, axis=1)
        return self.classes_[idx]

    def predict_proba(self, X):
        return self.gnb.predict_proba(X)


def make_fall_cost_matrix(n_classes=7, fall_idx=6, miss_cost=10):
    """Cost matrix where missing a fall is expensive.

    - Non-fall misclassification: cost = 1
    - Non-fall -> predicted fall (false alarm): cost = 2
    - Fall -> predicted non-fall (miss): cost = 10
    """
    cost = np.ones((n_classes, n_classes)) - np.eye(n_classes)  # zero-one loss base
    # Non-fall predicted as fall: slight cost
    cost[fall_idx, :] = 2
    cost[fall_idx, fall_idx] = 0
    # Fall predicted as non-fall: high cost
    cost[:, fall_idx] = miss_cost
    cost[fall_idx, fall_idx] = 0
    return cost


# ---------------------------------------------------------------------------
# Model factory
# ---------------------------------------------------------------------------

def get_baseline_models(random_state=42):
    """Return a dict of baseline classifier pipelines."""
    return {
        "GaussianNB": Pipeline([
            ("scaler", StandardScaler()),
            ("clf", GaussianNB()),
        ]),
        "LDA": Pipeline([
            ("scaler", StandardScaler()),
            ("clf", LinearDiscriminantAnalysis()),
        ]),
        "LogisticRegression": Pipeline([
            ("scaler", StandardScaler()),
            ("clf", LogisticRegression(max_iter=2000, random_state=random_state)),
        ]),
        "Perceptron": Pipeline([
            ("scaler", StandardScaler()),
            ("clf", Perceptron(max_iter=2000, random_state=random_state)),
        ]),
        "LinearSVM": Pipeline([
            ("scaler", StandardScaler()),
            ("clf", LinearSVC(max_iter=2000, dual="auto", random_state=random_state)),
        ]),
        "kNN_k5": Pipeline([
            ("scaler", StandardScaler()),
            ("clf", KNeighborsClassifier(n_neighbors=5, algorithm="kd_tree")),
        ]),
    }


# ---------------------------------------------------------------------------
# LOSO evaluation
# ---------------------------------------------------------------------------

def loso_evaluate(model, X, y, groups, verbose=True):
    """Leave-One-Subject-Out cross-validation.

    Returns
    -------
    results : dict
        accuracy, macro_f1, per_class_recall, confusion_matrix, y_true, y_pred
    """
    logo = LeaveOneGroupOut()
    y_true_all, y_pred_all = [], []

    for fold_i, (train_idx, test_idx) in enumerate(logo.split(X, y, groups)):
        X_train, X_test = X[train_idx], X[test_idx]
        y_train, y_test = y[train_idx], y[test_idx]

        if isinstance(model, MinimumRiskBayes):
            model_clone = MinimumRiskBayes(cost_matrix=model.cost_matrix.copy())
        else:
            model_clone = clone(model)

        model_clone.fit(X_train, y_train)
        y_pred = model_clone.predict(X_test)

        acc = accuracy_score(y_test, y_pred)
        if verbose:
            subj = np.unique(groups[test_idx])[0]
            print(f"  Fold {fold_i + 1} [{subj}]: acc={acc:.4f}")

        y_true_all.extend(y_test)
        y_pred_all.extend(y_pred)

    y_true_all = np.array(y_true_all)
    y_pred_all = np.array(y_pred_all)
    cm = confusion_matrix(y_true_all, y_pred_all)

    return {
        "accuracy": accuracy_score(y_true_all, y_pred_all),
        "macro_f1": f1_score(y_true_all, y_pred_all, average="macro"),
        "per_class_recall": recall_score(y_true_all, y_pred_all, average=None),
        "confusion_matrix": cm,
        "classification_report": classification_report(
            y_true_all, y_pred_all, zero_division=0,
            target_names=[ACTIVITIES[i] for i in range(len(ACTIVITIES))],
        ),
        "y_true": y_true_all,
        "y_pred": y_pred_all,
    }


# ---------------------------------------------------------------------------
# Evaluation runner
# ---------------------------------------------------------------------------

def evaluate_all_baselines(X, y, groups, verbose=True):
    """Run LOSO evaluation on all baseline models + MinimumRiskBayes.

    Returns
    -------
    results_df : pd.DataFrame
    """
    models = get_baseline_models()

    # Add MinimumRiskBayes variants
    cost_standard = make_fall_cost_matrix(n_classes=7, fall_idx=6, miss_cost=1)
    cost_fall = make_fall_cost_matrix(n_classes=7, fall_idx=6, miss_cost=10)

    rows = []
    for name, pipe in models.items():
        if verbose:
            print(f"\n--- {name} ---")
        res = loso_evaluate(pipe, X, y, groups, verbose=verbose)
        fall_recall = res["per_class_recall"][6] if len(res["per_class_recall"]) > 6 else float("nan")
        rows.append({
            "model": name, "accuracy": res["accuracy"], "macro_f1": res["macro_f1"],
            "fall_recall": fall_recall, "type": "standard",
        })

    # MinimumRiskBayes variants
    for mr_name, cost_mat in [("MinRiskBayes_std", cost_standard), ("MinRiskBayes_fall", cost_fall)]:
        if verbose:
            print(f"\n--- {mr_name} ---")
        mr = MinimumRiskBayes(cost_matrix=cost_mat)
        res = loso_evaluate(mr, X, y, groups, verbose=verbose)
        fall_recall = res["per_class_recall"][6] if len(res["per_class_recall"]) > 6 else float("nan")
        rows.append({
            "model": mr_name, "accuracy": res["accuracy"], "macro_f1": res["macro_f1"],
            "fall_recall": fall_recall, "type": "minrisk",
        })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Visualisation
# ---------------------------------------------------------------------------

def plot_decision_boundaries(X_2d, y, models, class_names=None, save_path=None):
    """Plot decision boundaries for each model in a 2×3 grid (PCA 2D)."""
    if class_names is None:
        class_names = [ACTIVITIES[i] for i in sorted(np.unique(y))]

    n = len(models)
    cols = 3
    rows = int(np.ceil(n / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(14, rows * 4))
    axes = axes.flatten() if n > 1 else [axes]

    # Create mesh grid
    x_min, x_max = X_2d[:, 0].min() - 0.5, X_2d[:, 0].max() + 0.5
    y_min, y_max = X_2d[:, 1].min() - 0.5, X_2d[:, 1].max() + 0.5
    xx, yy = np.meshgrid(np.linspace(x_min, x_max, 200),
                         np.linspace(y_min, y_max, 200))

    for ax, (name, clf) in zip(axes, models.items()):
        if isinstance(clf, MinimumRiskBayes):
            clf_clone = MinimumRiskBayes(cost_matrix=clf.cost_matrix.copy())
        else:
            clf_clone = clone(clf)
        clf_clone.fit(X_2d, y)
        Z = clf_clone.predict(np.c_[xx.ravel(), yy.ravel()])
        Z = Z.reshape(xx.shape)

        ax.contourf(xx, yy, Z, alpha=0.3, cmap="tab10", levels=len(class_names) - 1)
        scatter = ax.scatter(X_2d[:, 0], X_2d[:, 1], c=y, cmap="tab10",
                             alpha=0.6, s=6, edgecolors="none")
        ax.set_title(name, fontsize=10)
        ax.set_xticks([])
        ax.set_yticks([])

    # Hide unused axes
    for ax in axes[n:]:
        ax.set_visible(False)

    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches="tight")
    return fig


def plot_baseline_comparison(results_df, save_path=None):
    """Grouped bar: accuracy + fall_recall for each model."""
    fig, ax = plt.subplots(figsize=(10, 5))
    x = np.arange(len(results_df))
    w = 0.35

    bars1 = ax.bar(x - w / 2, results_df["accuracy"], w, label="Accuracy",
                   color="steelblue", alpha=0.85)
    bars2 = ax.bar(x + w / 2, results_df["fall_recall"], w, label="Fall Recall",
                   color="coral", alpha=0.85)

    ax.set_xticks(x)
    ax.set_xticklabels(results_df["model"], rotation=25, ha="right", fontsize=9)
    ax.set_ylabel("Score")
    ax.set_title("Baseline Classifier LOSO Comparison")
    ax.legend(loc="lower right")
    ax.set_ylim(0, 1.08)

    for bar in bars1:
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width() / 2, h + 0.01, f"{h:.3f}",
                ha="center", fontsize=7)
    for bar in bars2:
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width() / 2, h + 0.01, f"{h:.3f}",
                ha="center", fontsize=7)

    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches="tight")
    return fig


def plot_cost_sensitivity_comparison(results_df, save_path=None):
    """Highlight fall recall difference between standard and cost-sensitive."""
    df_pivot = results_df[results_df["model"].isin(
        ["GaussianNB", "MinRiskBayes_std", "MinRiskBayes_fall"]
    )]

    fig, ax = plt.subplots(figsize=(6, 4))
    x = np.arange(len(df_pivot))
    w = 0.3

    ax.bar(x - w / 2, df_pivot["accuracy"].values, w, label="Accuracy", color="steelblue")
    ax.bar(x + w / 2, df_pivot["fall_recall"].values, w, label="Fall Recall", color="coral")

    ax.set_xticks(x)
    ax.set_xticklabels(df_pivot["model"].values, fontsize=9)
    ax.set_ylabel("Score")
    ax.set_title("Cost Sensitivity: Standard vs MinRisk")
    ax.legend()
    ax.set_ylim(0, 1.1)
    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches="tight")
    return fig


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # -- load data ---------------------------------------------------------
    feature_path = ROOT / "data" / "features" / "feature_matrix.csv"
    if not feature_path.exists():
        print(f"feature_matrix.csv not found at {feature_path}", file=sys.stderr)
        sys.exit(1)

    df = pd.read_csv(feature_path)
    y = df["label"].values
    groups = df["subject_id"].values

    drop_cols = [c for c in ["subject_id", "window_id", "label"] if c in df.columns]
    X = df.drop(columns=drop_cols).values.astype(np.float64)
    feature_names = list(df.drop(columns=drop_cols).columns)

    # Sanitize
    if np.any(np.isnan(X)):
        X = SimpleImputer(strategy="median").fit_transform(X)

    from sklearn.feature_selection import VarianceThreshold
    var_mask = VarianceThreshold(threshold=0.0).fit(X).get_support()
    if not var_mask.all():
        X = X[:, var_mask]
        feature_names = [feature_names[i] for i in np.where(var_mask)[0]]

    print(f"Loaded {X.shape[0]} samples x {X.shape[1]} features, "
          f"{len(np.unique(groups))} subjects")

    # -- evaluate all baselines -------------------------------------------
    print("\n=== BASELINE CLASSIFIER LOSO EVALUATION ===\n")
    results_df = evaluate_all_baselines(X, y, groups, verbose=True)

    print("\n=== SUMMARY TABLE ===\n")
    print(results_df.to_string(index=False))

    # Save CSV
    results_df.to_csv(REPORTS_DIR / "d6_baseline_results.csv", index=False)

    # -- decision boundaries (on PCA 2D) ----------------------------------
    print("\nGenerating decision boundary plots …")
    pca = PCA(n_components=2, random_state=42)
    X_s = StandardScaler().fit_transform(X)
    X_2d = pca.fit_transform(X_s)

    models_for_viz = get_baseline_models()
    # Add MinimumRiskBayes fall variant
    cost_fall = make_fall_cost_matrix(7, 6, 10)
    models_for_viz["MinRiskBayes_fall"] = MinimumRiskBayes(cost_matrix=cost_fall)

    fig1 = plot_decision_boundaries(
        X_2d, y, models_for_viz,
        class_names=[ACTIVITIES[i] for i in range(7)],
        save_path=REPORTS_DIR / "d6_decision_boundaries.png",
    )
    plt.close(fig1)

    # -- comparison bar chart ---------------------------------------------
    fig2 = plot_baseline_comparison(
        results_df,
        save_path=REPORTS_DIR / "d6_baseline_comparison.png",
    )
    plt.close(fig2)

    # -- cost sensitivity ------------------------------------------------
    fig3 = plot_cost_sensitivity_comparison(
        results_df,
        save_path=REPORTS_DIR / "d6_cost_sensitivity.png",
    )
    plt.close(fig3)

    print(f"\nDone. Results saved to {REPORTS_DIR}")
