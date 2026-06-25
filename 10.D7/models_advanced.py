"""
D7: Nonlinear classifiers and ensemble learning.
- Kernel SVM (RBF), kNN (tuned), Decision Tree, Random Forest, AdaBoost, GBDT, MLP
- GridSearchCV hyperparameter tuning (3-fold CV within training fold)
- Learning curves
- Multi-model LOSO comparison
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.base import clone
from sklearn.svm import SVC
from sklearn.neighbors import KNeighborsClassifier
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import (
    RandomForestClassifier, AdaBoostClassifier, GradientBoostingClassifier,
)
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import (
    LeaveOneGroupOut, GridSearchCV, learning_curve,
)
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score, f1_score
from sklearn.feature_selection import VarianceThreshold

ROOT = Path(__file__).parent.parent
REPORTS_DIR = ROOT / "reports"
REPORTS_DIR.mkdir(exist_ok=True)

ACTIVITIES = {
    0: "sit", 1: "stand", 2: "walk", 3: "run",
    4: "upstairs", 5: "downstairs", 6: "fall",
}


# ---------------------------------------------------------------------------
# Model factory
# ---------------------------------------------------------------------------

def get_advanced_models(random_state=42):
    """Return dict of advanced classifier pipelines with sensible defaults."""
    return {
        "RBF_SVM": Pipeline([
            ("scaler", StandardScaler()),
            ("clf", SVC(kernel="rbf", probability=True, random_state=random_state)),
        ]),
        "kNN": Pipeline([
            ("scaler", StandardScaler()),
            ("clf", KNeighborsClassifier(n_neighbors=5, algorithm="kd_tree")),
        ]),
        "DecisionTree": Pipeline([
            ("clf", DecisionTreeClassifier(random_state=random_state)),
        ]),
        "RandomForest": Pipeline([
            ("clf", RandomForestClassifier(n_estimators=200, random_state=random_state, n_jobs=-1)),
        ]),
        "AdaBoost": Pipeline([
            ("clf", AdaBoostClassifier(n_estimators=200, random_state=random_state)),
        ]),
        "GBDT": Pipeline([
            ("clf", GradientBoostingClassifier(n_estimators=200, random_state=random_state)),
        ]),
        "MLP": Pipeline([
            ("scaler", StandardScaler()),
            ("clf", MLPClassifier(
                hidden_layer_sizes=(128, 64), max_iter=500,
                random_state=random_state, early_stopping=True,
            )),
        ]),
    }


# Parameter grids for GridSearchCV (subset for speed)
PARAM_GRIDS = {
    "RBF_SVM": {
        "clf__C": [0.1, 1, 10, 100],
        "clf__gamma": ["scale", "auto", 0.01],
    },
    "kNN": {
        "clf__n_neighbors": [3, 5, 7, 9],
        "clf__weights": ["uniform", "distance"],
    },
    "DecisionTree": {
        "clf__max_depth": [None, 5, 10, 20],
        "clf__min_samples_split": [2, 5, 10],
    },
    "RandomForest": {
        "clf__n_estimators": [100, 200],
        "clf__max_depth": [None, 10, 20],
        "clf__min_samples_split": [2, 5],
    },
    "AdaBoost": {
        "clf__n_estimators": [100, 200],
        "clf__learning_rate": [0.1, 0.5, 1.0],
    },
    "GBDT": {
        "clf__n_estimators": [100, 200],
        "clf__learning_rate": [0.01, 0.1],
        "clf__max_depth": [3, 5],
    },
    "MLP": {
        "clf__hidden_layer_sizes": [(64,), (128, 64)],
        "clf__alpha": [0.0001, 0.001],
    },
}


# ---------------------------------------------------------------------------
# LOSO + GridSearch
# ---------------------------------------------------------------------------

def loso_grid_search(model, param_grid, X, y, groups, cv_inner=3, verbose=True):
    """LOSO evaluation with GridSearchCV inside each training fold.

    For each LOSO fold:
      1. Split into train / test by subject
      2. GridSearchCV on train set (cv_inner-fold CV)
      3. Evaluate best model on held-out test subject

    Returns
    -------
    results : dict
        accuracy, macro_f1, best_params_per_fold, y_true, y_pred
    """
    logo = LeaveOneGroupOut()
    y_true_all, y_pred_all = [], []
    best_params_per_fold = []

    for fold_i, (train_idx, test_idx) in enumerate(logo.split(X, y, groups)):
        X_train, X_test = X[train_idx], X[test_idx]
        y_train, y_test = y[train_idx], y[test_idx]
        subj = np.unique(groups[test_idx])[0]

        gs = GridSearchCV(
            clone(model), param_grid, cv=cv_inner,
            scoring="accuracy", n_jobs=-1, refit=True,
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            gs.fit(X_train, y_train)

        y_pred = gs.predict(X_test)
        acc = accuracy_score(y_test, y_pred)
        f1 = f1_score(y_test, y_pred, average="macro")

        if verbose:
            print(f"  Fold {fold_i + 1} [{subj}]: acc={acc:.4f}, f1={f1:.4f}, "
                  f"best={gs.best_params_}")

        y_true_all.extend(y_test)
        y_pred_all.extend(y_pred)
        best_params_per_fold.append(gs.best_params_)

    y_true_all = np.array(y_true_all)
    y_pred_all = np.array(y_pred_all)

    return {
        "accuracy": accuracy_score(y_true_all, y_pred_all),
        "macro_f1": f1_score(y_true_all, y_pred_all, average="macro"),
        "best_params": best_params_per_fold,
        "y_true": y_true_all,
        "y_pred": y_pred_all,
    }


# ---------------------------------------------------------------------------
# Evaluation runner
# ---------------------------------------------------------------------------

def evaluate_all_advanced(X, y, groups, cv_inner=3, verbose=True):
    """Run LOSO + GridSearch for all advanced models.

    Returns
    -------
    df : pd.DataFrame
    """
    models = get_advanced_models()
    rows = []

    for name, pipe in models.items():
        if name not in PARAM_GRIDS:
            if verbose:
                print(f"\n--- {name} (default, no grid) ---")
            # Simple LOSO without grid search
            logo = LeaveOneGroupOut()
            yt, yp = [], []
            for train_idx, test_idx in logo.split(X, y, groups):
                m = clone(pipe)
                m.fit(X[train_idx], y[train_idx])
                yp.extend(m.predict(X[test_idx]))
                yt.extend(y[test_idx])
            acc = accuracy_score(yt, yp)
            f1 = f1_score(yt, yp, average="macro")
            rows.append({"model": name, "accuracy": acc, "macro_f1": f1,
                         "best_params": "default"})
            if verbose:
                print(f"  acc={acc:.4f}, f1={f1:.4f}")
            continue

        if verbose:
            print(f"\n--- {name} (GridSearchCV, inner cv={cv_inner}) ---")
        res = loso_grid_search(pipe, PARAM_GRIDS[name], X, y, groups,
                               cv_inner=cv_inner, verbose=verbose)
        rows.append({
            "model": name, "accuracy": res["accuracy"], "macro_f1": res["macro_f1"],
            "best_params": str(res["best_params"]),
        })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Learning curves
# ---------------------------------------------------------------------------

def plot_learning_curves(models, X, y, save_path=None):
    """Plot learning curves for key models (1 row per model, 3 cols)."""
    n = len(models)
    cols = 3
    rows = int(np.ceil(n / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(14, rows * 4))
    axes = axes.flatten() if n > 1 else [axes]

    train_sizes = np.linspace(0.15, 1.0, 8)
    for ax, (name, pipe) in zip(axes, models.items()):
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                N, train_scores, test_scores = learning_curve(
                    pipe, X, y, train_sizes=train_sizes, cv=3,
                    scoring="accuracy", n_jobs=-1, random_state=42,
                )
            train_mean = np.mean(train_scores, axis=1)
            test_mean = np.mean(test_scores, axis=1)
            train_std = np.std(train_scores, axis=1)
            test_std = np.std(test_scores, axis=1)

            ax.fill_between(N, train_mean - train_std, train_mean + train_std,
                            alpha=0.15, color="steelblue")
            ax.fill_between(N, test_mean - test_std, test_mean + test_std,
                            alpha=0.15, color="coral")
            ax.plot(N, train_mean, "o-", color="steelblue", markersize=4, label="Train")
            ax.plot(N, test_mean, "o-", color="coral", markersize=4, label="CV Test")
            ax.set_title(name, fontsize=10)
            ax.set_xlabel("Training samples")
            ax.set_ylabel("Accuracy")
            ax.legend(fontsize=7)
            ax.set_ylim(0, 1.05)
        except Exception as e:
            ax.text(0.5, 0.5, f"Error: {e}", ha="center", va="center", fontsize=8)
            ax.set_title(f"{name} (skipped)")

    for ax in axes[n:]:
        ax.set_visible(False)

    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches="tight")
    return fig


def plot_advanced_comparison(results_df, save_path=None):
    """Bar chart comparing all advanced models."""
    df = results_df.sort_values("accuracy", ascending=True)
    fig, ax = plt.subplots(figsize=(10, 5))
    x = np.arange(len(df))
    w = 0.35

    ax.barh(x - w / 2, df["accuracy"], w, label="Accuracy", color="steelblue")
    ax.barh(x + w / 2, df["macro_f1"], w, label="Macro F1", color="coral")

    ax.set_yticks(x)
    ax.set_yticklabels(df["model"])
    ax.set_xlabel("Score")
    ax.set_title("Advanced Model LOSO Comparison (with GridSearchCV)")
    ax.legend(loc="lower right")
    ax.set_xlim(0, 1.08)

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

    if np.any(np.isnan(X)):
        X = SimpleImputer(strategy="median").fit_transform(X)
    var_mask = VarianceThreshold(threshold=0.0).fit(X).get_support()
    if not var_mask.all():
        X = X[:, var_mask]

    print(f"Loaded {X.shape[0]} samples x {X.shape[1]} features, "
          f"{len(np.unique(groups))} subjects")

    # -- evaluate ---------------------------------------------------------
    print("\n=== ADVANCED MODEL LOSO + GRID SEARCH ===\n")
    results_df = evaluate_all_advanced(X, y, groups, cv_inner=3, verbose=True)

    print("\n=== SUMMARY TABLE ===\n")
    print(results_df[["model", "accuracy", "macro_f1"]].to_string(index=False))

    results_df.to_csv(REPORTS_DIR / "d7_advanced_results.csv", index=False)

    # -- learning curves --------------------------------------------------
    print("\nGenerating learning curves …")
    models_lc = get_advanced_models()
    fig1 = plot_learning_curves(
        models_lc, X, y,
        save_path=REPORTS_DIR / "d7_learning_curves.png",
    )
    plt.close(fig1)

    # -- comparison chart ------------------------------------------------
    fig2 = plot_advanced_comparison(
        results_df,
        save_path=REPORTS_DIR / "d7_model_comparison.png",
    )
    plt.close(fig2)

    print(f"\nDone. Results saved to {REPORTS_DIR}")
