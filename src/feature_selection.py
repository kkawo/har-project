"""
D5: Feature selection and dimensionality reduction.
- Filter methods (variance threshold, mutual information, ANOVA F)
- Wrapper methods (SFS, SBS)
- Embedded methods (L1 regularization, tree feature importance)
- PCA (K-L transform), LDA, t-SNE
"""

import numpy as np
import matplotlib.pyplot as plt
from sklearn.feature_selection import (
    VarianceThreshold,
    SelectKBest,
    f_classif,
    mutual_info_classif,
    SequentialFeatureSelector,
)
from sklearn.decomposition import PCA
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis as LDA
from sklearn.manifold import TSNE
from sklearn.ensemble import RandomForestClassifier


def filter_methods(X, y, k=20):
    """Apply multiple filter methods and return unified top-k feature indices."""
    # Variance threshold
    sel_var = VarianceThreshold(threshold=0.01)
    sel_var.fit(X)

    # ANOVA F
    sel_f = SelectKBest(f_classif, k=min(k, X.shape[1]))
    sel_f.fit(X, y)

    # Mutual information
    sel_mi = SelectKBest(mutual_info_classif, k=min(k, X.shape[1]))
    sel_mi.fit(X, y)

    return {
        "f_scores": sel_f.scores_,
        "mi_scores": sel_mi.scores_,
        "f_top_k": np.argsort(sel_f.scores_)[::-1][:k],
        "mi_top_k": np.argsort(sel_mi.scores_)[::-1][:k],
    }


def apply_pca(X_train, X_test=None, n_components=None):
    """Fit PCA on training data and transform both sets."""
    pca = PCA(n_components=n_components)
    X_train_pca = pca.fit_transform(X_train)
    X_test_pca = pca.transform(X_test) if X_test is not None else None
    return pca, X_train_pca, X_test_pca


def apply_lda(X_train, y_train, X_test=None, n_components=None):
    """Fit LDA on training data."""
    lda = LDA(n_components=n_components)
    X_train_lda = lda.fit_transform(X_train, y_train)
    X_test_lda = lda.transform(X_test) if X_test is not None else None
    return lda, X_train_lda, X_test_lda


def apply_tsne(X, n_components=2, perplexity=30):
    """t-SNE visualization (no train/test split — use on full dataset)."""
    tsne = TSNE(n_components=n_components, perplexity=perplexity, random_state=42)
    X_tsne = tsne.fit_transform(X)
    return tsne, X_tsne


def plot_tsne(X_tsne, y, title="t-SNE Visualization", save_path=None):
    """Plot 2D t-SNE embedding colored by class."""
    plt.figure(figsize=(8, 6))
    scatter = plt.scatter(X_tsne[:, 0], X_tsne[:, 1], c=y, cmap="tab10", alpha=0.7, s=10)
    plt.colorbar(scatter, label="Activity")
    plt.title(title)
    plt.xlabel("t-SNE 1")
    plt.ylabel("t-SNE 2")
    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=150)
    return plt.gcf()


if __name__ == "__main__":
    print("Feature selection module loaded.")
