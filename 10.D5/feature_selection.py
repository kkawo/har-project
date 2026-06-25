"""
D5: Feature selection and dimensionality reduction.

Covers four families of feature selection, plus dimensionality reduction:
  1. Filter methods — variance threshold, ANOVA F, mutual information
  2. Wrapper methods — SFS (forward), SBS (backward) with CV
  3. Embedded methods — L1 (Lasso), tree importance, RFE
  4. Dimensionality reduction — PCA (K-L transform), LDA, t-SNE

Each method returns selected feature indices and a report dict so downstream
D6/D7 modules can slice the feature matrix consistently.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt
from sklearn.impute import SimpleImputer
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_selection import (
    SelectFromModel,
    SelectKBest,
    SequentialFeatureSelector,
    VarianceThreshold,
    f_classif,
    mutual_info_classif,
    RFE,
)
from sklearn.linear_model import LogisticRegression
from sklearn.decomposition import PCA
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis as LDA
from sklearn.manifold import TSNE
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC

# ---------------------------------------------------------------------------
# shared helpers
# ---------------------------------------------------------------------------

ROOT = Path(__file__).parent.parent
REPORTS_DIR = ROOT / "reports"

FEATURE_NAMES_FILE = ROOT / "docs" / "feature_names.txt"  # optional, one name per line


def _ensure_reports_dir():
    REPORTS_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# 1. Filter methods
# ---------------------------------------------------------------------------

def filter_variance(X, threshold=0.01):
    """Remove near-constant features.

    Returns
    -------
    mask : np.ndarray of bool
    report : dict with keys ``n_original``, ``n_kept``, ``dropped_indices``
    """
    sel = VarianceThreshold(threshold=threshold)
    sel.fit(X)
    return sel.get_support(), {
        "method": "VarianceThreshold",
        "threshold": threshold,
        "n_original": X.shape[1],
        "n_kept": int(sel.get_support().sum()),
        "dropped_indices": np.where(~sel.get_support())[0].tolist(),
    }


def filter_anova(X, y, k=50):
    """ANOVA F-score top-k selection.

    Returns
    -------
    indices : np.ndarray (k,)  — descending F-score order
    scores : np.ndarray (n_features,)  — F-score for every feature
    report : dict
    """
    sel = SelectKBest(f_classif, k=min(k, X.shape[1]))
    sel.fit(X, y)
    order = np.argsort(sel.scores_)[::-1]
    return order[:k], sel.scores_, {
        "method": "ANOVA_F",
        "k": k,
        "top_k_indices": order[:k].tolist(),
        "top_k_scores": sel.scores_[order[:k]].tolist(),
    }


def filter_mutual_info(X, y, k=50, random_state=42):
    """Mutual-information top-k selection.

    Returns
    -------
    indices : np.ndarray (k,)
    scores : np.ndarray (n_features,)
    report : dict
    """
    from functools import partial
    mi = partial(mutual_info_classif, random_state=random_state)
    sel = SelectKBest(mi, k=min(k, X.shape[1]))
    sel.fit(X, y)
    order = np.argsort(sel.scores_)[::-1]
    return order[:k], sel.scores_, {
        "method": "MutualInfo",
        "k": k,
        "top_k_indices": order[:k].tolist(),
        "top_k_scores": sel.scores_[order[:k]].tolist(),
    }


def filter_ensemble(X, y, k=50, n_methods=2):
    """Voting across ANOVA F and mutual information: features ranked by
    average percentile rank across the two filter scores.

    Returns
    -------
    indices : np.ndarray (k,)
    report : dict
    """
    _, f_scores, _ = filter_anova(X, y, k=X.shape[1])
    _, mi_scores, _ = filter_mutual_info(X, y, k=X.shape[1])

    def _percentile_rank(scores):
        from scipy.stats import rankdata
        return rankdata(scores) / len(scores)

    avg_rank = (_percentile_rank(f_scores) + _percentile_rank(mi_scores)) / n_methods
    order = np.argsort(avg_rank)[::-1]
    return order[:k], avg_rank, {
        "method": "FilterEnsemble",
        "k": k,
        "top_k_indices": order[:k].tolist(),
    }


# ---------------------------------------------------------------------------
# 2. Wrapper methods
# ---------------------------------------------------------------------------

def wrapper_sfs(X, y, k=30, direction="forward", cv=3, scoring="accuracy",
                random_state=42):
    """Sequential Feature Selection (forward or backward) with a linear SVM.

    Parameters
    ----------
    direction : "forward" | "backward"

    Returns
    -------
    indices : np.ndarray (k,)
    report : dict
    """
    clf = Pipeline([
        ("scaler", StandardScaler()),
        ("svc", LinearSVC(max_iter=2000, dual="auto", random_state=random_state)),
    ])
    sfs = SequentialFeatureSelector(
        clf, n_features_to_select=min(k, X.shape[1]),
        direction=direction, cv=cv, scoring=scoring, n_jobs=-1,
    )
    sfs.fit(X, y)
    indices = np.where(sfs.get_support())[0]
    return indices, {
        "method": f"SFS_{direction}",
        "k": len(indices),
        "cv": cv,
        "scoring": scoring,
        "selected_indices": indices.tolist(),
    }


def wrapper_sbs(X, y, k=30, cv=3, scoring="accuracy", random_state=42):
    """Backward elimination convenience wrapper."""
    return wrapper_sfs(X, y, k=k, direction="backward", cv=cv,
                       scoring=scoring, random_state=random_state)


# ---------------------------------------------------------------------------
# 3. Embedded methods
# ---------------------------------------------------------------------------

def embedded_l1(X, y, C=0.1, max_iter=2000, random_state=42):
    """L1-penalised logistic regression (sparsity-driven selection).

    Returns
    -------
    indices : np.ndarray  — features with non-zero coefficients
    report : dict
    """
    clf = LogisticRegression(
        penalty="l1", solver="saga", C=C,
        max_iter=max_iter, random_state=random_state,
    )
    clf.fit(StandardScaler().fit_transform(X), y)
    mask = np.any(clf.coef_ != 0, axis=0)
    return np.where(mask)[0], {
        "method": "L1_LogReg",
        "C": C,
        "n_selected": int(mask.sum()),
        "selected_indices": np.where(mask)[0].tolist(),
    }


def embedded_tree_importance(X, y, k=50, n_estimators=200, random_state=42):
    """Random Forest MDI (mean decrease in impurity) top-k.

    Returns
    -------
    indices : np.ndarray (k,)
    importances : np.ndarray (n_features,)
    report : dict
    """
    rf = RandomForestClassifier(
        n_estimators=n_estimators, random_state=random_state, n_jobs=-1,
    )
    rf.fit(X, y)
    order = np.argsort(rf.feature_importances_)[::-1]
    return order[:k], rf.feature_importances_, {
        "method": "RF_MDI",
        "k": k,
        "top_k_indices": order[:k].tolist(),
    }


def embedded_rfe(X, y, k=50, step=5, random_state=42):
    """Recursive Feature Elimination with a linear SVM core.

    Returns
    -------
    indices : np.ndarray (k,)
    report : dict
    """
    clf = LinearSVC(max_iter=2000, dual="auto", random_state=random_state)
    # Standardize once for RFE (RFE doesn't support Pipeline internally for coef_)
    X_s = StandardScaler().fit_transform(X)
    rfe = RFE(clf, n_features_to_select=min(k, X.shape[1]), step=step)
    rfe.fit(X_s, y)
    indices = np.where(rfe.support_)[0]
    return indices, {
        "method": "RFE",
        "k": len(indices),
        "step": step,
        "selected_indices": indices.tolist(),
    }


# ---------------------------------------------------------------------------
# 4. Dimensionality reduction
# ---------------------------------------------------------------------------

def apply_pca(X_train, X_test=None, n_components=None):
    """Fit PCA on training data; return transformer + transformed matrices."""
    pca = PCA(n_components=n_components, random_state=42)
    X_train_pca = pca.fit_transform(X_train)
    X_test_pca = pca.transform(X_test) if X_test is not None else None
    return pca, X_train_pca, X_test_pca


def pca_explained_variance(pca: PCA, top_n=30):
    """Return a report of cumulative explained variance per component."""
    cumvar = np.cumsum(pca.explained_variance_ratio_)
    n_95 = int(np.searchsorted(cumvar, 0.95) + 1)
    n_99 = int(np.searchsorted(cumvar, 0.99) + 1)
    return {
        "n_components_total": len(pca.explained_variance_ratio_),
        "n_for_95pct": n_95,
        "n_for_99pct": n_99,
        "top_n_cumvar": cumvar[:top_n].tolist(),
    }


def apply_lda(X_train, y_train, X_test=None, n_components=None):
    """Fit LDA (supervised) and transform."""
    n_max = min(X_train.shape[1], len(np.unique(y_train)) - 1)
    if n_components is None or n_components > n_max:
        n_components = n_max
    lda = LDA(n_components=n_components)
    X_train_lda = lda.fit_transform(X_train, y_train)
    X_test_lda = lda.transform(X_test) if X_test is not None else None
    return lda, X_train_lda, X_test_lda


def apply_tsne(X, n_components=2, perplexity=30, random_state=42):
    """t-SNE on the full dataset (no train/test split)."""
    tsne = TSNE(
        n_components=n_components, perplexity=perplexity,
        random_state=random_state, init="pca", learning_rate="auto",
    )
    X_tsne = tsne.fit_transform(StandardScaler().fit_transform(X))
    return tsne, X_tsne


# ---------------------------------------------------------------------------
# 5. Selection quality evaluation
# ---------------------------------------------------------------------------

def evaluate_selection(X, y, selected_indices, classifier=None, cv=5,
                       random_state=42):
    """Quick 5-fold CV accuracy using a given (or default) classifier on the
    selected feature subset."""
    if classifier is None:
        classifier = Pipeline([
            ("scaler", StandardScaler()),
            ("svc", LinearSVC(max_iter=2000, dual="auto", random_state=random_state)),
        ])
    from sklearn.model_selection import cross_val_score
    X_sub = X[:, selected_indices]
    scores = cross_val_score(classifier, X_sub, y, cv=cv, n_jobs=-1)
    return float(scores.mean()), float(scores.std())


def compare_methods(X, y, k=30, cv=5, random_state=42):
    """Run every selection method at target dimensionality *k* and return a
    ranked comparison table.

    Returns
    -------
    results : list[dict]  — sorted by mean CV accuracy descending
    """
    results = []

    # ---- filter ----
    for name, fn in [
        ("ANOVA_F", lambda: filter_anova(X, y, k=k)),
        ("MutualInfo", lambda: filter_mutual_info(X, y, k=k)),
        ("FilterEnsemble", lambda: filter_ensemble(X, y, k=k)),
    ]:
        idx, _, _ = fn()
        acc, std = evaluate_selection(X, y, idx, cv=cv, random_state=random_state)
        results.append({"method": name, "n_features": len(idx), "cv_mean_acc": acc,
                        "cv_std_acc": std})

    # ---- wrapper (SFS only on top-100 ANOVA pre-filter; skip SBS — too slow) ----
    top100, _, _ = filter_anova(X, y, k=min(100, X.shape[1]))
    X100 = X[:, top100]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        idx_sfs_sub, _ = wrapper_sfs(X100, y, k=min(k, 100), cv=cv, random_state=random_state)
    idx_sfs_full = top100[idx_sfs_sub]
    acc, std = evaluate_selection(X, y, idx_sfs_full, cv=cv, random_state=random_state)
    results.append({"method": "SFS_forward", "n_features": len(idx_sfs_full),
                    "cv_mean_acc": acc, "cv_std_acc": std})

    # ---- embedded ----
    for name, fn in [
        ("RF_MDI", lambda: embedded_tree_importance(X, y, k=k, random_state=random_state)),
        ("RFE", lambda: embedded_rfe(X, y, k=k, random_state=random_state)),
    ]:
        idx, *_ = fn()
        acc, std = evaluate_selection(X, y, idx, cv=cv, random_state=random_state)
        results.append({"method": name, "n_features": len(idx), "cv_mean_acc": acc,
                        "cv_std_acc": std})

    # L1 is special — k is not controlled, report separately
    idx_l1, _ = embedded_l1(X, y, random_state=random_state)
    acc_l1, std_l1 = evaluate_selection(X, y, idx_l1, cv=cv, random_state=random_state)
    results.append({"method": "L1_LogReg", "n_features": len(idx_l1),
                    "cv_mean_acc": acc_l1, "cv_std_acc": std_l1})

    # ---- PCA baseline ----
    pca, X_pca, _ = apply_pca(X, n_components=k)
    from sklearn.model_selection import cross_val_score
    clf = Pipeline([
        ("scaler", StandardScaler()),
        ("svc", LinearSVC(max_iter=2000, dual="auto", random_state=random_state)),
    ])
    scores = cross_val_score(clf, X_pca, y, cv=cv, n_jobs=-1)
    results.append({"method": "PCA", "n_features": k,
                    "cv_mean_acc": float(scores.mean()),
                    "cv_std_acc": float(scores.std())})

    # ---- all features (upper bound) ----
    scores_all = cross_val_score(clf, X, y, cv=cv, n_jobs=-1)
    results.append({"method": "AllFeatures", "n_features": X.shape[1],
                    "cv_mean_acc": float(scores_all.mean()),
                    "cv_std_acc": float(scores_all.std())})

    results.sort(key=lambda r: r["cv_mean_acc"], reverse=True)
    return results


# ---------------------------------------------------------------------------
# 6. Visualisation
# ---------------------------------------------------------------------------

def plot_feature_importance(scores, top_k=20, title="Feature Importance",
                            feature_names=None, save_path=None):
    """Horizontal bar chart of top-k feature scores."""
    order = np.argsort(scores)[::-1][:top_k]
    labels = (
        [feature_names[i] for i in order]
        if feature_names is not None
        else [f"f{i}" for i in order]
    )
    fig, ax = plt.subplots(figsize=(8, max(6, top_k * 0.25)))
    ax.barh(range(top_k), scores[order][::-1], color="steelblue")
    ax.set_yticks(range(top_k))
    ax.set_yticklabels(labels[::-1], fontsize=8)
    ax.set_xlabel("Score")
    ax.set_title(title)
    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches="tight")
    return fig


def plot_pca_cumvar(pca: PCA, top_n=None, title="PCA Cumulative Explained Variance",
                    save_path=None):
    """Plot cumulative explained variance ratio with 95% / 99% markers."""
    cumvar = np.cumsum(pca.explained_variance_ratio_)
    n = top_n or len(cumvar)
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(range(1, n + 1), cumvar[:n], "b-", linewidth=1.5)
    ax.axhline(0.95, color="gray", linestyle="--", label="95%")
    ax.axhline(0.99, color="gray", linestyle=":", label="99%")
    n95 = int(np.searchsorted(cumvar, 0.95) + 1)
    ax.axvline(n95, color="gray", linestyle="--", alpha=0.5)
    ax.set_xlabel("Number of components")
    ax.set_ylabel("Cumulative explained variance ratio")
    ax.set_title(title)
    ax.legend()
    ax.set_ylim(0, 1.02)
    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches="tight")
    return fig


def plot_comparison(results, title="Feature Selection Method Comparison",
                    save_path=None):
    """Grouped bar chart: CV accuracy ± std for each method."""
    methods = [r["method"] for r in results]
    accs = [r["cv_mean_acc"] for r in results]
    stds = [r["cv_std_acc"] for r in results]
    n_feats = [r["n_features"] for r in results]

    fig, ax = plt.subplots(figsize=(10, 5))
    x = range(len(methods))
    bars = ax.bar(x, accs, yerr=stds, capsize=4, color="steelblue", alpha=0.85)
    ax.set_xticks(x)
    ax.set_xticklabels(methods, rotation=30, ha="right", fontsize=9)
    ax.set_ylabel("CV Accuracy")
    ax.set_title(title)

    # annotate n_features above each bar
    for i, (bar, nf) in enumerate(zip(bars, n_feats)):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.005,
                f"n={nf}", ha="center", fontsize=7, color="dimgray")

    ax.set_ylim(0, 1.05)
    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches="tight")
    return fig


def plot_tsne(X_tsne, y, title="t-SNE Visualization", save_path=None):
    """2-D t-SNE scatter coloured by class label."""
    fig, ax = plt.subplots(figsize=(8, 6))
    scatter = ax.scatter(
        X_tsne[:, 0], X_tsne[:, 1], c=y,
        cmap="tab10", alpha=0.6, s=8,
    )
    plt.colorbar(scatter, ax=ax, label="Activity")
    ax.set_title(title)
    ax.set_xlabel("t-SNE 1")
    ax.set_ylabel("t-SNE 2")
    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches="tight")
    return fig


# ---------------------------------------------------------------------------
# 7. Console report
# ---------------------------------------------------------------------------

def print_selection_report(results):
    """Pretty-print the comparison table produced by ``compare_methods``."""
    header = f"{'Method':<20} {'n_feat':>7} {'CV Acc':>8} {'±Std':>7}"
    print("\n" + "=" * 50)
    print("Feature Selection Method Comparison")
    print("=" * 50)
    print(header)
    print("-" * 50)
    for r in results:
        print(
            f"{r['method']:<20} {r['n_features']:>7} "
            f"{r['cv_mean_acc']:>8.4f} {r['cv_std_acc']:>7.4f}"
        )
    print("=" * 50 + "\n")


# ---------------------------------------------------------------------------
# CLI / demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    import pandas as pd
    from sklearn.model_selection import train_test_split

    # -- load data ---------------------------------------------------------
    feature_matrix_path = ROOT / "data" / "features" / "feature_matrix.csv"
    if not feature_matrix_path.exists():
        print(
            "feature_matrix.csv  not found at "
            f"{feature_matrix_path}.\n"
            "Run D4 feature extraction first, then re-run this script.",
            file=sys.stderr,
        )
        sys.exit(1)

    df = pd.read_csv(feature_matrix_path)
    y = df["label"].values
    drop_cols = [c for c in ["subject_id", "window_id", "label"] if c in df.columns]
    X = df.drop(columns=drop_cols).values.astype(np.float64)
    feature_names = list(df.drop(columns=drop_cols).columns)

    # handle NaN (7/294 features, <0.05% of cells — gyro skew/kurtosis)
    if np.any(np.isnan(X)):
        nan_cols = np.where(np.any(np.isnan(X), axis=0))[0]
        print(f"  Imputing NaN in {len(nan_cols)} features: "
              f"{[feature_names[i] for i in nan_cols]}")
        X = SimpleImputer(strategy="median").fit_transform(X)

    # drop constant features (10/294 — magnetometer spectral_flatness/rolloff)
    var_mask, _ = filter_variance(X, threshold=0.0)
    if not var_mask.all():
        n_dropped = (~var_mask).sum()
        print(f"  Dropping {n_dropped} constant features")
        X = X[:, var_mask]
        feature_names = [feature_names[i] for i in np.where(var_mask)[0]]

    print(f"Loaded {X.shape[0]} samples × {X.shape[1]} features")

    # -- 1. filter ensemble consensus --------------------------------------
    print("\n[1/5] Filter ensemble …")
    idx_filter, _, rep_filter = filter_ensemble(X, y, k=50)
    print(f"  Ensemble top-5 indices: {idx_filter[:5].tolist()}")

    # -- 2. wrapper (pre-filter to top-100 with ANOVA F for speed) ---------
    print("[2/5] SFS (forward, on top-100 ANOVA features) …")
    top100, _, _ = filter_anova(X, y, k=100)
    X_top100 = X[:, top100]
    idx_sfs_sub, rep_sfs = wrapper_sfs(X_top100, y, k=20, cv=3)
    idx_sfs = top100[idx_sfs_sub]  # map back to original indices
    print(f"  SFS selected {len(idx_sfs)} features")

    # -- 3. embedded -------------------------------------------------------
    print("[3/5] Embedded (RF MDI + RFE) …")
    idx_rf, imp_rf, rep_rf = embedded_tree_importance(X, y, k=30)
    idx_rfe, rep_rfe = embedded_rfe(X, y, k=30)
    print(f"  RF MDI top-5: {idx_rf[:5].tolist()}")
    print(f"  RFE selected {len(idx_rfe)} features")

    # -- 4. PCA ------------------------------------------------------------
    print("[4/5] PCA …")
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=42,
    )
    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)

    pca, X_train_pca, X_test_pca = apply_pca(X_train_s, X_test_s, n_components=50)
    pca_report = pca_explained_variance(pca)
    print(f"  PCA: {pca_report['n_for_95pct']} components for 95% variance, "
          f"{pca_report['n_for_99pct']} for 99%")

    # -- 5. compare all methods --------------------------------------------
    print("[5/5] Comparing all methods …")
    results = compare_methods(X, y, k=30, cv=3)
    print_selection_report(results)

    # -- visualisations ---------------------------------------------------
    _ensure_reports_dir()
    print("Generating figures …")

    # feature importance (RF)
    fig1 = plot_feature_importance(
        imp_rf, top_k=20, feature_names=feature_names,
        title="Random Forest Feature Importance (MDI)",
        save_path=REPORTS_DIR / "d5_rf_importance.png",
    )
    plt.close(fig1)

    # PCA cumulative variance
    fig2 = plot_pca_cumvar(
        pca, top_n=50,
        save_path=REPORTS_DIR / "d5_pca_cumvar.png",
    )
    plt.close(fig2)

    # method comparison
    fig3 = plot_comparison(
        results,
        save_path=REPORTS_DIR / "d5_method_comparison.png",
    )
    plt.close(fig3)

    # t-SNE
    print("  t-SNE (may take a moment on 294-d data) …")
    _, X_tsne = apply_tsne(X_train_s, n_components=2, perplexity=30)
    fig4 = plot_tsne(
        X_tsne, y_train,
        save_path=REPORTS_DIR / "d5_tsne.png",
    )
    plt.close(fig4)

    print(f"\nDone. Reports saved to {REPORTS_DIR}")
