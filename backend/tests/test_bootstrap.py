"""Stratified bootstrap confidence-interval utility."""

from __future__ import annotations

import numpy as np

from riskmodel.bootstrap import confidence_intervals


def _synthetic(n=800, seed=1):
    rng = np.random.default_rng(seed)
    y = (rng.random(n) < 0.3).astype(int)
    # scores correlated with the label so metrics are non-degenerate
    p = np.clip(0.15 + 0.6 * y + rng.normal(0, 0.2, n), 0, 1)
    amounts = rng.uniform(500, 60_000, n)
    return y, p, amounts


def test_intervals_bracket_the_point_estimate():
    y, p, amounts = _synthetic()
    ci = confidence_intervals(y, p, amounts, t_low=0.1, t_high=0.5, B=500)
    for key in ("precision", "recall", "f1", "roc_auc", "pr_auc",
                "savings_inr"):
        assert key in ci
        assert ci[key]["lo"] <= ci[key]["point"] <= ci[key]["hi"], key
        assert ci[key]["lo"] < ci[key]["hi"], key


def test_deterministic_for_a_fixed_seed():
    y, p, amounts = _synthetic()
    a = confidence_intervals(y, p, amounts, 0.1, 0.5, B=300, seed=42)
    b = confidence_intervals(y, p, amounts, 0.1, 0.5, B=300, seed=42)
    assert a["precision"] == b["precision"]
    assert a["roc_auc"] == b["roc_auc"]


def test_probabilities_bounded_in_unit_interval():
    y, p, amounts = _synthetic()
    ci = confidence_intervals(y, p, amounts, 0.1, 0.5, B=300)
    for key in ("precision", "recall", "f1", "roc_auc", "pr_auc"):
        assert 0.0 <= ci[key]["lo"] <= 1.0
        assert 0.0 <= ci[key]["hi"] <= 1.0


def test_meta_records_method():
    y, p, amounts = _synthetic()
    ci = confidence_intervals(y, p, amounts, 0.1, 0.5, B=200)
    assert ci["_meta"]["B"] == 200
    assert "bootstrap" in ci["_meta"]["method"]
