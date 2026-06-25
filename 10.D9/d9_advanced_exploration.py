"""
D9: Advanced Exploration — temporal smoothing, 1D-CNN, unsupervised clustering.

Usage:
    python src/d9_advanced_exploration.py                # all modules
    python src/d9_advanced_exploration.py --skip-cnn      # skip CNN
    python src/d9_advanced_exploration.py --skip-clustering  # skip clustering
    python src/d9_advanced_exploration.py --smooth-window 5  # custom window size
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.base import clone
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler, label_binarize
from sklearn.neighbors import KNeighborsClassifier
from sklearn.model_selection import LeaveOneGroupOut
from sklearn.impute import SimpleImputer
from sklearn.feature_selection import VarianceThreshold
from sklearn.decomposition import PCA
from sklearn.manifold import TSNE
from sklearn.cluster import KMeans
from sklearn.mixture import GaussianMixture
from sklearn.metrics import (
    accuracy_score, confusion_matrix, classification_report,
    f1_score, precision_score, recall_score,
    adjusted_rand_score, normalized_mutual_info_score,
    adjusted_mutual_info_score,
)
from scipy.special import logsumexp

ROOT = Path(__file__).parent.parent
REPORTS_DIR = ROOT / "reports"
REPORTS_DIR.mkdir(exist_ok=True)

ACTIVITIES = {
    0: "sit", 1: "stand", 2: "walk", 3: "run",
    4: "upstairs", 5: "downstairs", 6: "fall",
}
CLASS_NAMES = [ACTIVITIES[i] for i in range(7)]
N_CLASSES = 7

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_data():
    """Load feature matrix and windowed dataset."""
    feat_path = ROOT / "data" / "features" / "feature_matrix.csv"
    wnd_path = ROOT / "data" / "windowed" / "windowed_dataset.npz"

    df = pd.read_csv(feat_path)
    y = df["label"].values.astype(int)
    groups = df["subject_id"].values

    drop_cols = [c for c in ["subject_id", "label"] if c in df.columns]
    X = df.drop(columns=drop_cols).values.astype(np.float64)
    feature_names = list(df.drop(columns=drop_cols).columns)

    # Impute + filter low variance
    if np.any(np.isnan(X)):
        X = SimpleImputer(strategy="median").fit_transform(X)
    var_mask = VarianceThreshold(threshold=0.0).fit(X).get_support()
    if not var_mask.all():
        X = X[:, var_mask]

    # Windowed data for CNN
    wnd = np.load(wnd_path)
    windows = wnd["windows"]  # (N, 128, 9)

    return X, y, groups, feature_names, windows


# ===========================================================================
# MODULE 1: Temporal Smoothing
# ===========================================================================

def majority_vote_smooth(y_pred, window_size=5):
    """Apply sliding-window majority voting to a 1D label sequence.

    For boundaries, window shrinks (no padding).
    """
    y_smooth = np.copy(y_pred)
    n = len(y_pred)
    half = window_size // 2
    for i in range(n):
        lo = max(0, i - half)
        hi = min(n, i + half + 1)
        segment = y_pred[lo:hi]
        counts = np.bincount(segment, minlength=N_CLASSES)
        y_smooth[i] = np.argmax(counts)
    return y_smooth


def viterbi_decode(log_emission, log_trans, start_log_prob=None):
    """Viterbi algorithm for sequence decoding.

    Parameters
    ----------
    log_emission : (T, K) log emission probabilities
    log_trans : (K, K) log transition matrix
    start_log_prob : (K,) initial state log probabilities

    Returns
    -------
    path : (T,) best state sequence
    """
    T, K = log_emission.shape
    if start_log_prob is None:
        start_log_prob = np.full(K, -np.log(K))

    log_delta = np.zeros((T, K))
    psi = np.zeros((T, K), dtype=int)

    log_delta[0] = start_log_prob + log_emission[0]

    for t in range(1, T):
        for j in range(K):
            scores = log_delta[t - 1] + log_trans[:, j]
            psi[t, j] = np.argmax(scores)
            log_delta[t, j] = scores[psi[t, j]] + log_emission[t, j]

    path = np.zeros(T, dtype=int)
    path[-1] = np.argmax(log_delta[-1])
    for t in range(T - 2, -1, -1):
        path[t] = psi[t + 1, path[t + 1]]
    return path


def estimate_transition_matrix(labels, n_states=7, pseudocount=0.1):
    """Estimate transition probability matrix from label sequences.

    Detects trial boundaries by label changes and resets after each boundary
    to avoid spurious cross-trial transitions.
    """
    trans = np.full((n_states, n_states), pseudocount)
    change_points = np.where(np.diff(labels) != 0)[0]

    # Transitions at change points
    for cp in change_points:
        trans[labels[cp], labels[cp + 1]] += 1

    # Self-transitions: all positions minus change points
    for i in range(n_states):
        trans[i, i] += np.sum(labels == i) - np.sum(labels[change_points] == i)

    trans /= trans.sum(axis=1, keepdims=True)
    return trans


def smooth_subject_sequence(y_pred, y_prob_train, y_train, y_test,
                            group_train, group_test, smooth_window=5):
    """Apply temporal smoothing to a single test subject's predictions.

    Processes each trial segment separately (detected by true label transitions).
    """
    y_smoothed_mv = np.copy(y_pred)
    y_smoothed_hmm = np.copy(y_pred)

    # Find trial segments in test subject's data
    transitions = np.where(np.diff(y_test) != 0)[0]
    segments = []
    start = 0
    for t in transitions:
        segments.append((start, t + 1))
        start = t + 1
    segments.append((start, len(y_test)))

    # Learn transition matrix from training subject(s)
    trans_matrix = estimate_transition_matrix(y_train, N_CLASSES)

    # Process each trial segment
    for lo, hi in segments:
        seg_len = hi - lo
        if seg_len < 3:
            continue

        seg_pred = y_pred[lo:hi]

        # Majority vote smoothing
        y_smoothed_mv[lo:hi] = majority_vote_smooth(seg_pred, smooth_window)

        # HMM smoothing: use kNN probabilities as emission
        seg_prob = y_prob_train[lo:hi] if y_prob_train is not None else None
        if seg_prob is not None:
            log_emission = np.log(np.clip(seg_prob, 1e-10, 1.0))
            log_trans = np.log(np.clip(trans_matrix, 1e-10, 1.0))
            start_log_prob = np.log(np.ones(N_CLASSES) / N_CLASSES)
            hmm_path = viterbi_decode(log_emission, log_trans, start_log_prob)
            y_smoothed_hmm[lo:hi] = hmm_path

    return y_smoothed_mv, y_smoothed_hmm, trans_matrix


def evaluate_temporal_smoothing(X, y, groups, smooth_windows=(3, 5, 7)):
    """Full temporal smoothing evaluation: train kNN, smooth predictions, compare.

    Returns dict with all metrics for reporting.
    """
    logo = LeaveOneGroupOut()
    kNN = Pipeline([
        ("scaler", StandardScaler()),
        ("clf", KNeighborsClassifier(n_neighbors=3, weights="distance")),
    ])

    y_true_all = []
    y_pred_raw_all = []
    y_smooth_mv_all = {w: [] for w in smooth_windows}
    y_smooth_hmm_all = []

    trans_matrices = []

    for fold_i, (train_idx, test_idx) in enumerate(logo.split(X, y, groups)):
        X_train, X_test = X[train_idx], X[test_idx]
        y_train, y_test = y[train_idx], y[test_idx]

        m = clone(kNN)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            m.fit(X_train, y_train)

        y_pred = m.predict(X_test)
        try:
            y_prob = m.predict_proba(X_test)
        except (AttributeError, NotImplementedError):
            y_prob = None

        # Smooth within this fold
        mv_results = {}
        for w in smooth_windows:
            y_mv, _, _ = smooth_subject_sequence(
                y_pred, y_prob, y_train, y_test, groups[train_idx], groups[test_idx],
                smooth_window=w,
            )
            mv_results[w] = y_mv

        _, y_hmm, trans_mat = smooth_subject_sequence(
            y_pred, y_prob, y_train, y_test, groups[train_idx], groups[test_idx],
        )
        trans_matrices.append(trans_mat)

        y_true_all.extend(y_test)
        y_pred_raw_all.extend(y_pred)
        for w in smooth_windows:
            y_smooth_mv_all[w].extend(mv_results[w])
        y_smooth_hmm_all.extend(y_hmm)

    y_true_all = np.array(y_true_all)
    y_pred_raw_all = np.array(y_pred_raw_all)
    y_smooth_hmm_all = np.array(y_smooth_hmm_all)

    # Compile results
    def metrics(y_t, y_p, label):
        return {
            "label": label,
            "accuracy": accuracy_score(y_t, y_p),
            "macro_f1": f1_score(y_t, y_p, average="macro"),
            "macro_precision": precision_score(y_t, y_p, average="macro"),
            "macro_recall": recall_score(y_t, y_p, average="macro"),
            "per_class_recall": recall_score(y_t, y_p, average=None, labels=range(7)),
            "per_class_precision": precision_score(y_t, y_p, average=None, labels=range(7)),
            "per_class_f1": f1_score(y_t, y_p, average=None, labels=range(7)),
            "confusion_matrix": confusion_matrix(y_t, y_p, labels=range(7)),
            "classification_report": classification_report(
                y_t, y_p, target_names=CLASS_NAMES, zero_division=0,
            ),
        }

    results = {"raw": metrics(y_true_all, y_pred_raw_all, "kNN (no smoothing)")}
    for w in smooth_windows:
        y_sm = np.array(y_smooth_mv_all[w])
        results[f"majority_vote_L{w}"] = metrics(
            y_true_all, y_sm, f"Majority Vote (L={w})",
        )
    results["hmm"] = metrics(
        y_true_all, y_smooth_hmm_all, "HMM Viterbi",
    )

    # Average transition matrix
    avg_trans = np.mean(trans_matrices, axis=0)
    results["avg_transition_matrix"] = avg_trans

    return results


def plot_temporal_smoothing_results(results, smooth_windows=(3, 5, 7)):
    """Plot per-class recall comparison before vs after smoothing."""
    methods = ["raw"] + [f"majority_vote_L{w}" for w in smooth_windows] + ["hmm"]
    labels = ["kNN (raw)"] + [f"MV L={w}" for w in smooth_windows] + ["HMM"]

    n_methods = len(methods)
    x = np.arange(N_CLASSES)
    width = 0.8 / n_methods
    colors = plt.cm.Set2(np.linspace(0, 1, n_methods))

    fig, ax = plt.subplots(figsize=(12, 5))
    for i, (method, label) in enumerate(zip(methods, labels)):
        recall = results[method]["per_class_recall"]
        offset = (i - (n_methods - 1) / 2) * width
        ax.bar(x + offset, recall, width, label=label, color=colors[i])

    ax.set_xticks(x)
    ax.set_xticklabels(CLASS_NAMES)
    ax.set_ylabel("Recall")
    ax.set_title("Per-Class Recall: Before vs After Temporal Smoothing")
    ax.legend(fontsize=8, ncol=2)
    ax.set_ylim(0, 1.08)
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    fig.savefig(REPORTS_DIR / "d9_temporal_smoothing_recall.png", dpi=150)
    plt.close(fig)
    print("  -> reports/d9_temporal_smoothing_recall.png")

    # Accuracy + macro F1 summary chart
    fig2, ax2 = plt.subplots(figsize=(9, 4))
    accs = [results[m]["accuracy"] for m in methods]
    f1s = [results[m]["macro_f1"] for m in methods]
    x2 = np.arange(len(methods))
    w2 = 0.35
    ax2.bar(x2 - w2 / 2, accs, w2, label="Accuracy", color="steelblue")
    ax2.bar(x2 + w2 / 2, f1s, w2, label="Macro F1", color="coral")
    for i, (a, f) in enumerate(zip(accs, f1s)):
        ax2.text(i - w2 / 2, a + 0.01, f"{a:.3f}", ha="center", va="bottom", fontsize=8)
        ax2.text(i + w2 / 2, f + 0.01, f"{f:.3f}", ha="center", va="bottom", fontsize=8)
    ax2.set_xticks(x2)
    ax2.set_xticklabels(labels)
    ax2.set_ylabel("Score")
    ax2.set_title("Accuracy & Macro F1: Temporal Smoothing Comparison")
    ax2.legend(loc="lower right")
    ax2.set_ylim(0, 1.1)
    plt.tight_layout()
    fig2.savefig(REPORTS_DIR / "d9_smoothing_summary.png", dpi=150)
    plt.close(fig2)
    print("  -> reports/d9_smoothing_summary.png")


def plot_hmm_transition_matrix(trans_mat):
    """Plot HMM transition matrix heatmap."""
    fig, ax = plt.subplots(figsize=(7, 6))
    im = ax.imshow(trans_mat, cmap="YlOrRd", vmin=0, vmax=1)
    for i in range(N_CLASSES):
        for j in range(N_CLASSES):
            ax.text(j, i, f"{trans_mat[i, j]:.3f}", ha="center", va="center", fontsize=8)
    ax.set_xticks(range(N_CLASSES))
    ax.set_yticks(range(N_CLASSES))
    ax.set_xticklabels(CLASS_NAMES, rotation=45, ha="right")
    ax.set_yticklabels(CLASS_NAMES)
    ax.set_title("Estimated HMM Transition Matrix\n(from training labels)")
    plt.colorbar(im, ax=ax)
    plt.tight_layout()
    fig.savefig(REPORTS_DIR / "d9_hmm_transition_matrix.png", dpi=150)
    plt.close(fig)
    print("  -> reports/d9_hmm_transition_matrix.png")


# ===========================================================================
# MODULE 2: 1D-CNN End-to-End
# ===========================================================================

def build_cnn(input_shape=(128, 9), n_classes=7):
    """Build a compact 1D-CNN for HAR on raw windows."""
    import os
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
    import tensorflow as tf
    from tensorflow.keras import layers, Model

    inp = layers.Input(shape=input_shape, name="sensor_window")

    x = layers.Conv1D(64, kernel_size=5, padding="same", name="conv1")(inp)
    x = layers.BatchNormalization()(x)
    x = layers.ReLU()(x)
    x = layers.MaxPooling1D(2, name="pool1")(x)

    x = layers.Conv1D(128, kernel_size=5, padding="same", name="conv2")(x)
    x = layers.BatchNormalization()(x)
    x = layers.ReLU()(x)
    x = layers.MaxPooling1D(2, name="pool2")(x)

    x = layers.Conv1D(256, kernel_size=3, padding="same", name="conv3")(x)
    x = layers.BatchNormalization()(x)
    x = layers.ReLU()(x)
    x = layers.GlobalAveragePooling1D(name="gap")(x)

    x = layers.Dense(64, name="fc1")(x)
    x = layers.ReLU()(x)
    x = layers.Dropout(0.3, name="dropout")(x)
    out = layers.Dense(n_classes, activation="softmax", name="output")(x)

    model = Model(inp, out, name="har_1dcnn")
    model.compile(
        optimizer="adam",
        loss="sparse_categorical_crossentropy",
        metrics=["accuracy"],
    )
    return model


def run_cnn_loso(windows, y, groups, epochs=80, batch_size=16):
    """LOSO evaluation of 1D-CNN on raw window data."""
    import os
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
    import tensorflow as tf

    unique_subjs = np.unique(groups)
    y_true_all, y_pred_all = [], []
    histories = []

    for subj in unique_subjs:
        test_mask = groups == subj
        train_mask = ~test_mask

        X_train = windows[train_mask].astype(np.float32)
        y_train = y[train_mask].astype(np.int32)
        X_test = windows[test_mask].astype(np.float32)
        y_test = y[test_mask].astype(np.int32)

        # Standardize per fold (fit on train)
        mean = X_train.mean(axis=(0, 1), keepdims=True)
        std = X_train.std(axis=(0, 1), keepdims=True) + 1e-8
        X_train = (X_train - mean) / std
        X_test = (X_test - mean) / std

        tf.random.set_seed(42)
        model = build_cnn(input_shape=(windows.shape[1], windows.shape[2]))

        early_stop = tf.keras.callbacks.EarlyStopping(
            monitor="val_loss", patience=15, restore_best_weights=True,
        )

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            history = model.fit(
                X_train, y_train,
                validation_split=0.2,
                epochs=epochs,
                batch_size=batch_size,
                callbacks=[early_stop],
                verbose=0,
            )

        y_prob = model.predict(X_test, batch_size=batch_size, verbose=0)
        y_pred = np.argmax(y_prob, axis=1)

        y_true_all.extend(y_test)
        y_pred_all.extend(y_pred)
        histories.append(history)

    y_true_all = np.array(y_true_all)
    y_pred_all = np.array(y_pred_all)

    return {
        "accuracy": accuracy_score(y_true_all, y_pred_all),
        "macro_f1": f1_score(y_true_all, y_pred_all, average="macro"),
        "per_class_recall": recall_score(y_true_all, y_pred_all, average=None, labels=range(7)),
        "per_class_precision": precision_score(y_true_all, y_pred_all, average=None, labels=range(7)),
        "per_class_f1": f1_score(y_true_all, y_pred_all, average=None, labels=range(7)),
        "confusion_matrix": confusion_matrix(y_true_all, y_pred_all, labels=range(7)),
        "classification_report": classification_report(
            y_true_all, y_pred_all, target_names=CLASS_NAMES, zero_division=0,
        ),
        "histories": histories,
        "y_true": y_true_all,
        "y_pred": y_pred_all,
    }


def plot_cnn_results(cnn_result, knn_acc=0.555):
    """Plot CNN training curves and comparison with kNN."""
    histories = cnn_result["histories"]
    folds = len(histories)

    fig, axes = plt.subplots(1, 3, figsize=(15, 4))

    # Training curves
    for i, h in enumerate(histories):
        subj = f"S0{i + 1}"
        axes[0].plot(h.history["accuracy"], alpha=0.6, label=f"{subj} train")
        axes[0].plot(h.history["val_accuracy"], alpha=0.6, ls="--", label=f"{subj} val")
    axes[0].set_xlabel("Epoch")
    axes[0].set_ylabel("Accuracy")
    axes[0].set_title("1D-CNN Training Curves (LOSO)")
    axes[0].legend(fontsize=7)
    axes[0].set_ylim(0, 1.05)

    # Per-class recall comparison
    x = np.arange(N_CLASSES)
    w = 0.35
    knn_recall = [0.0, 0.65, 0.96, 0.62, 0.83, 0.55, 0.38]  # from D8 best kNN
    cnn_recall = cnn_result["per_class_recall"]
    axes[1].bar(x - w / 2, knn_recall, w, label="kNN (hand-crafted)", color="steelblue")
    axes[1].bar(x + w / 2, cnn_recall, w, label="1D-CNN (raw data)", color="coral")
    axes[1].set_xticks(x)
    axes[1].set_xticklabels(CLASS_NAMES)
    axes[1].set_ylabel("Recall")
    axes[1].set_title("Per-Class Recall: kNN vs 1D-CNN")
    axes[1].legend(fontsize=8)
    axes[1].set_ylim(0, 1.08)

    # Overall comparison bars
    cnn_acc = cnn_result["accuracy"]
    cnn_f1 = cnn_result["macro_f1"]
    methods = ["kNN", "1D-CNN"]
    accs = [knn_acc, cnn_acc]
    f1s = [0.506, cnn_f1]
    x2 = np.arange(2)
    axes[2].bar(x2 - w / 2, accs, w, label="Accuracy", color="steelblue")
    axes[2].bar(x2 + w / 2, f1s, w, label="Macro F1", color="coral")
    for i, (a, f) in enumerate(zip(accs, f1s)):
        axes[2].text(i - w / 2, a + 0.01, f"{a:.3f}", ha="center", fontsize=10)
        axes[2].text(i + w / 2, f + 0.01, f"{f:.3f}", ha="center", fontsize=10)
    axes[2].set_xticks(x2)
    axes[2].set_xticklabels(methods)
    axes[2].set_ylabel("Score")
    axes[2].set_title("kNN vs CNN Overall")
    axes[2].legend(loc="lower right")
    axes[2].set_ylim(0, 1.1)

    plt.tight_layout()
    fig.savefig(REPORTS_DIR / "d9_cnn_comparison.png", dpi=150)
    plt.close(fig)
    print("  -> reports/d9_cnn_comparison.png")


# ===========================================================================
# MODULE 3: Unsupervised Clustering
# ===========================================================================

def evaluate_clustering(X, y):
    """K-means and GMM clustering with ARI/NMI/AMI evaluation.

    Tests both RFE-selected features and PCA-reduced space.
    """
    results = {}

    # --- K-means ---
    km = KMeans(n_clusters=7, n_init=20, random_state=42)
    y_km = km.fit_predict(X)
    results["KMeans"] = {
        "y_pred": y_km,
        "ARI": adjusted_rand_score(y, y_km),
        "NMI": normalized_mutual_info_score(y, y_km),
        "AMI": adjusted_mutual_info_score(y, y_km),
        "inertia": km.inertia_,
    }

    # --- GMM ---
    gmm = GaussianMixture(
        n_components=7, covariance_type="full",
        random_state=42, n_init=10,
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        y_gmm = gmm.fit_predict(X)
    results["GMM"] = {
        "y_pred": y_gmm,
        "ARI": adjusted_rand_score(y, y_gmm),
        "NMI": normalized_mutual_info_score(y, y_gmm),
        "AMI": adjusted_mutual_info_score(y, y_gmm),
        "bic": gmm.bic(X),
    }

    # --- Clustering in PCA space ---
    pca = PCA(n_components=30, random_state=42)
    X_pca = pca.fit_transform(StandardScaler().fit_transform(X))

    km_pca = KMeans(n_clusters=7, n_init=20, random_state=42)
    y_km_pca = km_pca.fit_predict(X_pca)
    results["KMeans+PCA"] = {
        "y_pred": y_km_pca,
        "ARI": adjusted_rand_score(y, y_km_pca),
        "NMI": normalized_mutual_info_score(y, y_km_pca),
        "AMI": adjusted_mutual_info_score(y, y_km_pca),
        "inertia": km_pca.inertia_,
    }

    gmm_pca = GaussianMixture(
        n_components=7, covariance_type="full",
        random_state=42, n_init=10,
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        y_gmm_pca = gmm_pca.fit_predict(X_pca)
    results["GMM+PCA"] = {
        "y_pred": y_gmm_pca,
        "ARI": adjusted_rand_score(y, y_gmm_pca),
        "NMI": normalized_mutual_info_score(y, y_gmm_pca),
        "AMI": adjusted_mutual_info_score(y, y_gmm_pca),
        "bic": gmm_pca.bic(X_pca),
    }

    return results


def plot_clustering_tsne(X, y, clustering_results):
    """t-SNE visualization: true labels vs clustering results."""
    # Use PCA 30D as intermediate step for t-SNE (faster, less noisy)
    X_scaled = StandardScaler().fit_transform(X)
    X_pca = PCA(n_components=30, random_state=42).fit_transform(X_scaled)

    tsne = TSNE(n_components=2, random_state=42, perplexity=30, max_iter=500)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        X_tsne = tsne.fit_transform(X_pca)

    fig, axes = plt.subplots(2, 2, figsize=(12, 11))
    colors = plt.cm.tab10(np.linspace(0, 1, 7))

    def plot_embedding(ax, X_2d, labels, title):
        for i in range(7):
            mask = labels == i
            ax.scatter(X_2d[mask, 0], X_2d[mask, 1], c=[colors[i]],
                       label=CLASS_NAMES[i], s=15, alpha=0.7, edgecolors="none")
        ax.set_title(title, fontsize=11)
        ax.legend(fontsize=7, loc="lower left", ncol=2)
        ax.set_xticks([])
        ax.set_yticks([])

    plot_embedding(axes[0, 0], X_tsne, y, "Ground Truth Labels")
    plot_embedding(axes[0, 1], X_tsne, clustering_results["KMeans"]["y_pred"],
                   f"K-Means (ARI={clustering_results['KMeans']['ARI']:.3f})")
    plot_embedding(axes[1, 0], X_tsne, clustering_results["GMM"]["y_pred"],
                   f"GMM (ARI={clustering_results['GMM']['ARI']:.3f})")
    plot_embedding(axes[1, 1], X_tsne, clustering_results["GMM+PCA"]["y_pred"],
                   f"GMM+PCA (ARI={clustering_results['GMM+PCA']['ARI']:.3f})")

    plt.tight_layout()
    fig.savefig(REPORTS_DIR / "d9_clustering_tsne.png", dpi=150)
    plt.close(fig)
    print("  -> reports/d9_clustering_tsne.png")


def plot_clustering_metrics(clustering_results):
    """Bar chart comparing ARI/NMI/AMI across clustering methods."""
    methods = list(clustering_results.keys())
    fig, ax = plt.subplots(figsize=(9, 4))
    x = np.arange(len(methods))
    w = 0.25
    for i, metric in enumerate(["ARI", "NMI", "AMI"]):
        vals = [clustering_results[m][metric] for m in methods]
        ax.bar(x + (i - 1) * w, vals, w, label=metric)
        for j, v in enumerate(vals):
            ax.text(x[j] + (i - 1) * w, v + 0.005, f"{v:.3f}",
                    ha="center", fontsize=7, rotation=90)
    ax.set_xticks(x)
    ax.set_xticklabels(methods)
    ax.set_ylabel("Score")
    ax.set_title("Clustering Quality: ARI / NMI / AMI")
    ax.legend()
    ax.set_ylim(0, 1.1)
    plt.tight_layout()
    fig.savefig(REPORTS_DIR / "d9_clustering_metrics.png", dpi=150)
    plt.close(fig)
    print("  -> reports/d9_clustering_metrics.png")


# ===========================================================================
# Main runner
# ===========================================================================

def main(skip_cnn=False, skip_clustering=False, smooth_window=5):
    print("=" * 60)
    print("D9: ADVANCED EXPLORATION")
    print("=" * 60)

    # Load data
    print("\n[0] Loading data...")
    X, y, groups, feature_names, windows = load_data()
    print(f"  Features: {X.shape}, Windows: {windows.shape}, "
          f"Subjects: {np.unique(groups)}")

    # ═════════════════════════════════════════════════════════════════════
    # Module 1: Temporal Smoothing
    # ═════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 60)
    print("MODULE 1: TEMPORAL SMOOTHING")
    print("=" * 60)

    smooth_results = evaluate_temporal_smoothing(X, y, groups, smooth_windows=(3, 5, 7))

    print("\n--- Smoothing Results ---")
    for key in ["raw", "majority_vote_L3", "majority_vote_L5", "majority_vote_L7", "hmm"]:
        r = smooth_results[key]
        print(f"\n  [{r['label']}]")
        print(f"    Accuracy:    {r['accuracy']:.4f}")
        print(f"    Macro F1:    {r['macro_f1']:.4f}")
        print(f"    Macro Recall:{r['macro_recall']:.4f}")
        per_class = r["per_class_recall"]
        for i, name in enumerate(CLASS_NAMES):
            marker = " ***" if per_class[i] < 0.1 else ""
            print(f"      {name:12s} recall={per_class[i]:.3f}{marker}")

    # Highlight sit recall improvement
    raw_sit = smooth_results["raw"]["per_class_recall"][0]
    best_sit = raw_sit
    best_method = "raw"
    for key in ["majority_vote_L3", "majority_vote_L5", "majority_vote_L7", "hmm"]:
        sit_rec = smooth_results[key]["per_class_recall"][0]
        if sit_rec > best_sit:
            best_sit = sit_rec
            best_method = key

    print(f"\n  *** sit recall: {raw_sit:.4f} (raw) -> {best_sit:.4f} ({best_method}) ***")

    plot_temporal_smoothing_results(smooth_results)
    plot_hmm_transition_matrix(smooth_results["avg_transition_matrix"])

    # ═════════════════════════════════════════════════════════════════════
    # Module 2: 1D-CNN
    # ═════════════════════════════════════════════════════════════════════
    if not skip_cnn:
        print("\n" + "=" * 60)
        print("MODULE 2: 1D-CNN END-TO-END")
        print("=" * 60)

        try:
            cnn_result = run_cnn_loso(windows, y, groups)
            print(f"\n  CNN Accuracy: {cnn_result['accuracy']:.4f}")
            print(f"  CNN Macro F1: {cnn_result['macro_f1']:.4f}")
            print(f"  Per-class recall: {dict(zip(CLASS_NAMES, cnn_result['per_class_recall'].round(3)))}")
            plot_cnn_results(cnn_result)
        except Exception as e:
            print(f"\n  CNN failed: {e}")
            cnn_result = None
            print("  (Skipping CNN — install tensorflow if needed)")

    # ═════════════════════════════════════════════════════════════════════
    # Module 3: Unsupervised Clustering
    # ═════════════════════════════════════════════════════════════════════
    if not skip_clustering:
        print("\n" + "=" * 60)
        print("MODULE 3: UNSUPERVISED CLUSTERING")
        print("=" * 60)

        cluster_results = evaluate_clustering(X, y)

        print("\n--- Clustering Results ---")
        header = f"  {'Method':<15s} {'ARI':>7s} {'NMI':>7s} {'AMI':>7s}"
        print(header)
        print("  " + "-" * len(header))
        for name, r in cluster_results.items():
            print(f"  {name:<15s} {r['ARI']:7.4f} {r['NMI']:7.4f} {r['AMI']:7.4f}")

        plot_clustering_tsne(X, y, cluster_results)
        plot_clustering_metrics(cluster_results)

    # ═════════════════════════════════════════════════════════════════════
    # Summary JSON
    # ═════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 60)
    print("SAVING SUMMARY")
    print("=" * 60)

    import json

    summary = {
        "temporal_smoothing": {
            method: {
                "accuracy": smooth_results[method]["accuracy"],
                "macro_f1": smooth_results[method]["macro_f1"],
                "per_class_recall": dict(zip(
                    CLASS_NAMES,
                    smooth_results[method]["per_class_recall"].tolist(),
                )),
            }
            for method in ["raw", "majority_vote_L3", "majority_vote_L5", "majority_vote_L7", "hmm"]
        },
    }

    if not skip_cnn and cnn_result is not None:
        summary["cnn"] = {
            "accuracy": cnn_result["accuracy"],
            "macro_f1": cnn_result["macro_f1"],
            "per_class_recall": dict(zip(CLASS_NAMES, cnn_result["per_class_recall"].tolist())),
        }

    if not skip_clustering:
        summary["clustering"] = {
            name: {k: v for k, v in r.items() if k != "y_pred"}
            for name, r in cluster_results.items()
        }

    summary_path = REPORTS_DIR / "d9_exploration_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, default=str)
    print(f"  Summary saved to {summary_path}")

    print("\n" + "=" * 60)
    print("D9 COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="D9 Advanced Exploration")
    parser.add_argument("--skip-cnn", action="store_true", help="Skip 1D-CNN module")
    parser.add_argument("--skip-clustering", action="store_true", help="Skip clustering module")
    parser.add_argument("--smooth-window", type=int, default=5, help="Majority vote window size")
    args = parser.parse_args()

    main(
        skip_cnn=args.skip_cnn,
        skip_clustering=args.skip_clustering,
        smooth_window=args.smooth_window,
    )
