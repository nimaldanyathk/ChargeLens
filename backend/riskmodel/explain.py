"""Explainability artifacts.

Computes SHAP global feature importance for the selected model on a
validation sample and stores a small background sample so the serving
path can compute per-case attributions live. Importances are
associational, not causal, and the UI labels them accordingly.
"""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from .features import FEATURE_COLUMNS, build_features
from .train import ARTIFACT_DIR, load_split

BACKGROUND_N = 200
SAMPLE_N = 1500


class _EnsembleExplainer:
    """SHAP for a soft-vote ensemble: Shapley values are linear in the
    model, so the attribution of the average model is exactly the average
    of the members' attributions - no approximation involved."""

    def __init__(self, members):
        import shap
        self.explainers = [shap.TreeExplainer(m) for m in members]

    def shap_values(self, X):
        mats = [_normalize_shap(e.shap_values(X)) for e in self.explainers]
        return np.mean(mats, axis=0)


def _normalize_shap(values) -> np.ndarray:
    if isinstance(values, list):          # RandomForest: [class0, class1]
        values = values[1]
    values = np.asarray(values)
    if values.ndim == 3:                   # (n, features, classes)
        values = values[:, :, 1]
    return values


def make_explainer(model, background: pd.DataFrame):
    """Build a SHAP explainer for a tree model, the soft-vote ensemble,
    or the LR pipeline."""
    import shap

    base = model.base_model
    if base.__class__.__name__ == "SoftVoteEnsemble":
        return _EnsembleExplainer(base.members)
    if hasattr(base, "get_booster") or base.__class__.__name__ in (
            "RandomForestClassifier", "XGBClassifier"):
        return shap.TreeExplainer(base)
    # sklearn Pipeline(scaler, LogisticRegression)
    def predict(X):
        return base.predict_proba(pd.DataFrame(X, columns=FEATURE_COLUMNS))[:, 1]
    return shap.Explainer(predict, background.to_numpy(),
                          feature_names=FEATURE_COLUMNS)


def shap_values_matrix(explainer, X: pd.DataFrame) -> np.ndarray:
    """Return (n, n_features) SHAP values for the positive class."""
    return _normalize_shap(explainer.shap_values(X))


def main():
    rng = np.random.default_rng(7)
    model = joblib.load(ARTIFACT_DIR / "model.joblib")
    val_df = load_split("val")
    X_val = build_features(val_df)[FEATURE_COLUMNS]

    bg_idx = rng.choice(len(X_val), size=min(BACKGROUND_N, len(X_val)),
                        replace=False)
    background = X_val.iloc[bg_idx]
    background.to_csv(ARTIFACT_DIR / "shap_background.csv", index=False)

    sample_idx = rng.choice(len(X_val), size=min(SAMPLE_N, len(X_val)),
                            replace=False)
    X_sample = X_val.iloc[sample_idx]

    explainer = make_explainer(model, background)
    values = shap_values_matrix(explainer, X_sample)

    mean_abs = np.abs(values).mean(axis=0)
    mean_signed = values.mean(axis=0)
    order = np.argsort(mean_abs)[::-1]
    importance = [{
        "feature": FEATURE_COLUMNS[i],
        "mean_abs_shap": round(float(mean_abs[i]), 5),
        "mean_shap": round(float(mean_signed[i]), 5),
    } for i in order[:25]]

    (ARTIFACT_DIR / "global_importance.json").write_text(json.dumps({
        "method": "SHAP (TreeExplainer for tree models); associational, "
                  "not causal",
        "sample_size": int(len(X_sample)),
        "top_features": importance,
    }, indent=2))
    print(json.dumps(importance[:10], indent=2))


if __name__ == "__main__":
    main()
