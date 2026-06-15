"""
D6: Basic statistical classifiers.
- Gaussian Bayes (Minimum Error Rate)
- Naive Bayes baseline
- Minimum Risk Bayes (cost-sensitive for fall detection)
- Fisher LDA, Perceptron, Logistic Regression, Linear SVM
"""

import numpy as np
from sklearn.naive_bayes import GaussianNB
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.linear_model import LogisticRegression, Perceptron
from sklearn.svm import LinearSVC
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


def get_baseline_models():
    """Return a dict of baseline classifier pipelines ready for evaluation."""
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
            ("clf", LogisticRegression(max_iter=1000)),
        ]),
        "Perceptron": Pipeline([
            ("scaler", StandardScaler()),
            ("clf", Perceptron(max_iter=1000, random_state=42)),
        ]),
        "LinearSVM": Pipeline([
            ("scaler", StandardScaler()),
            ("clf", LinearSVC(max_iter=2000, random_state=42)),
        ]),
    }


class MinimumRiskBayes:
    """Gaussian Bayes with a user-defined cost matrix for minimum risk decision."""

    def __init__(self, cost_matrix=None):
        """
        cost_matrix[i, j] = cost of deciding class i when true class is j.
        Default: zero-one loss.
        """
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
        # Minimum risk: choose class with minimum expected cost
        expected_costs = probs @ self.cost_matrix.T
        idx = np.argmin(expected_costs, axis=1)
        return self.classes_[idx]


def make_fall_cost_matrix(n_classes=7, fall_idx=6, miss_cost=10):
    """Create a cost matrix where missing a fall is expensive."""
    cost = np.ones((n_classes, n_classes)) - np.eye(n_classes)  # zero-one loss base
    # Predicting 0 (or other) when truth is fall: high cost
    cost[:, fall_idx] = miss_cost
    cost[fall_idx, fall_idx] = 0  # correct fall prediction has zero cost
    return cost


if __name__ == "__main__":
    models = get_baseline_models()
    for name, pipe in models.items():
        print(f"  {name}: {pipe.steps[-1][1].__class__.__name__}")
