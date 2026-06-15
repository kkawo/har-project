"""
D7: Nonlinear classifiers and ensemble learning.
- Kernel SVM (RBF / polynomial)
- k-Nearest Neighbors (with kd-tree)
- Decision Tree, Random Forest, AdaBoost, GBDT
- MLP (Multi-Layer Perceptron)
- GridSearchCV / RandomizedSearchCV for hyperparameter tuning
"""

import numpy as np
from sklearn.svm import SVC
from sklearn.neighbors import KNeighborsClassifier
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import (
    RandomForestClassifier,
    AdaBoostClassifier,
    GradientBoostingClassifier,
)
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


def get_advanced_models():
    """Return a dict of nonlinear & ensemble classifier pipelines."""
    return {
        "kNN": Pipeline([
            ("scaler", StandardScaler()),
            ("clf", KNeighborsClassifier(n_neighbors=5, algorithm="kd_tree")),
        ]),
        "RBF_SVM": Pipeline([
            ("scaler", StandardScaler()),
            ("clf", SVC(kernel="rbf", probability=True, random_state=42)),
        ]),
        "DecisionTree": Pipeline([
            ("clf", DecisionTreeClassifier(random_state=42)),
        ]),
        "RandomForest": Pipeline([
            ("clf", RandomForestClassifier(n_estimators=200, random_state=42)),
        ]),
        "AdaBoost": Pipeline([
            ("clf", AdaBoostClassifier(n_estimators=200, random_state=42)),
        ]),
        "GBDT": Pipeline([
            ("clf", GradientBoostingClassifier(n_estimators=200, random_state=42)),
        ]),
        "MLP": Pipeline([
            ("scaler", StandardScaler()),
            ("clf", MLPClassifier(
                hidden_layer_sizes=(128, 64),
                max_iter=500,
                random_state=42,
                early_stopping=True,
            )),
        ]),
    }


# Hyperparameter grids for GridSearchCV
PARAM_GRIDS = {
    "kNN": {
        "clf__n_neighbors": [3, 5, 7, 9, 11],
        "clf__weights": ["uniform", "distance"],
    },
    "RBF_SVM": {
        "clf__C": [0.1, 1, 10, 100],
        "clf__gamma": ["scale", "auto", 0.01, 0.1],
    },
    "RandomForest": {
        "clf__n_estimators": [100, 200, 300],
        "clf__max_depth": [None, 10, 20, 30],
        "clf__min_samples_split": [2, 5, 10],
    },
    "GBDT": {
        "clf__n_estimators": [100, 200],
        "clf__learning_rate": [0.01, 0.1, 0.2],
        "clf__max_depth": [3, 5, 7],
    },
    "MLP": {
        "clf__hidden_layer_sizes": [(64,), (128, 64), (256, 128, 64)],
        "clf__alpha": [0.0001, 0.001, 0.01],
    },
}


if __name__ == "__main__":
    models = get_advanced_models()
    for name, pipe in models.items():
        print(f"  {name}: {pipe.steps[-1][1].__class__.__name__}")
    print(f"\nParameter grids defined for: {list(PARAM_GRIDS.keys())}")
