"""Soft-voting ensemble over already-fitted tree models.

Averaging the probability outputs of diverse tree learners reduces
variance without any new dependency. Explainability stays exact: SHAP
values are linear in the model, so the attribution of an average of
models is the average of their attributions - explain.py relies on
this identity rather than an approximate kernel method.
"""

from __future__ import annotations

import numpy as np


class SoftVoteEnsemble:
    """Averages predict_proba over pre-fitted member models."""

    def __init__(self, members: list, member_names: list[str]):
        if not members:
            raise ValueError("ensemble needs at least one member")
        self.members = members
        self.member_names = list(member_names)

    def fit(self, X, y):  # members arrive fitted; kept for API symmetry
        for m in self.members:
            m.fit(X, y)
        return self

    def predict_proba(self, X) -> np.ndarray:
        probs = [m.predict_proba(X) for m in self.members]
        return np.mean(probs, axis=0)
