"""Probability calibration.

The winning classifier's raw scores are mapped to calibrated
probabilities with isotonic regression fitted on the VALIDATION split
(never on test). Calibrated probabilities matter here because the UI
shows "risk 91%" to a merchant and the threshold search interprets the
score as a probability when trading off business costs.
"""

from __future__ import annotations

import numpy as np
from sklearn.isotonic import IsotonicRegression


class IsotonicCalibratedModel:
    """Wraps a fitted binary classifier with an isotonic calibrator."""

    def __init__(self, base_model, feature_columns: list[str]):
        self.base_model = base_model
        self.feature_columns = list(feature_columns)
        self.calibrator = IsotonicRegression(
            y_min=0.0, y_max=1.0, out_of_bounds="clip")
        self._fitted = False

    def fit_calibrator(self, X_val, y_val) -> "IsotonicCalibratedModel":
        raw = self.base_model.predict_proba(X_val)[:, 1]
        self.calibrator.fit(raw, np.asarray(y_val, dtype=float))
        self._fitted = True
        return self

    def predict_proba(self, X) -> np.ndarray:
        raw = self.base_model.predict_proba(X)[:, 1]
        if self._fitted:
            p1 = self.calibrator.predict(raw)
        else:
            p1 = raw
        p1 = np.clip(p1, 0.0, 1.0)
        return np.column_stack([1.0 - p1, p1])

    def predict_proba_raw(self, X) -> np.ndarray:
        return self.base_model.predict_proba(X)[:, 1]
