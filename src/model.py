import numpy as np
import lightgbm as lgb
from sklearn.calibration import CalibratedClassifierCV
from sklearn.frozen import FrozenEstimator
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    average_precision_score, roc_auc_score, brier_score_loss,
    precision_score, recall_score, f1_score,
)

from features import build_matrix, align_categories


LGB_PARAMS = dict(
    objective="binary",
    n_estimators=400,
    learning_rate=0.045,
    num_leaves=31,
    min_child_samples=40,
    subsample=0.85,
    subsample_freq=1,
    colsample_bytree=0.85,
    reg_lambda=1.0,
    verbose=-1,
)


class WinnabilityModel:
    def __init__(self, seed=42):
        self.seed = seed
        self.calibrated = None
        self.raw = None
        self._ref = None

    def fit(self, train_df):
        X = build_matrix(train_df)
        y = train_df["won"].to_numpy()
        self._ref = X

        X_fit, X_cal, y_fit, y_cal = train_test_split(
            X, y, test_size=0.25, random_state=self.seed, stratify=y
        )

        self.raw = lgb.LGBMClassifier(random_state=self.seed, **LGB_PARAMS)
        self.raw.fit(X_fit, y_fit, categorical_feature=[
            c for c in X.columns if str(X[c].dtype) == "category"
        ])

        self.calibrated = CalibratedClassifierCV(
            FrozenEstimator(self.raw), method="isotonic"
        )
        self.calibrated.fit(X_cal, y_cal)
        return self

    def predict_proba(self, df):
        X = align_categories(build_matrix(df), self._ref)
        return self.calibrated.predict_proba(X)[:, 1]

    def feature_importance(self, top=12):
        imp = sorted(
            zip(self._ref.columns, self.raw.feature_importances_),
            key=lambda t: -t[1],
        )
        return imp[:top]


def calibration_table(y, p, bins=5):
    edges = np.quantile(p, np.linspace(0, 1, bins + 1))
    edges[0], edges[-1] = -1e-9, 1 + 1e-9
    rows = []
    for i in range(bins):
        m = (p > edges[i]) & (p <= edges[i + 1])
        if m.sum() == 0:
            continue
        rows.append({
            "bucket": f"{edges[i]:.2f}-{edges[i+1]:.2f}",
            "n": int(m.sum()),
            "predicted": float(p[m].mean()),
            "actual": float(y[m].mean()),
        })
    return rows


def evaluate(y, p, threshold=0.5):
    yhat = (p >= threshold).astype(int)
    return {
        "n": int(len(y)),
        "base_rate": float(np.mean(y)),
        "pr_auc": float(average_precision_score(y, p)),
        "roc_auc": float(roc_auc_score(y, p)),
        "brier": float(brier_score_loss(y, p)),
        "precision": float(precision_score(y, yhat, zero_division=0)),
        "recall": float(recall_score(y, yhat, zero_division=0)),
        "f1": float(f1_score(y, yhat, zero_division=0)),
        "threshold": threshold,
    }