"""Cost model math and threshold-tuning behaviour."""

import numpy as np

from riskmodel.costs import (
    CHARGEBACK_FEE, GOODWILL_COST, OPS_COST, WIN_RATE, cost_breakdown,
    expected_cost,
)
from riskmodel.train import PRECISION_FLOOR, tune_thresholds


def test_expected_cost_hand_computed():
    # one of each outcome, amount 1000 everywhere
    y_true = np.array([1, 0, 1, 0])
    y_pred = np.array([1, 1, 0, 0])   # TP, FP, FN, TN
    amounts = np.array([1000.0] * 4)
    expected = (
        (OPS_COST + GOODWILL_COST)                 # FP
        + (1000.0 * WIN_RATE + CHARGEBACK_FEE)     # FN
        + (OPS_COST - 1000.0 * WIN_RATE)           # TP
        + 0.0                                       # TN
    )
    assert abs(expected_cost(y_true, y_pred, amounts) - expected) < 1e-9


def test_breakdown_components_sum_to_net():
    rng = np.random.default_rng(0)
    y_true = rng.integers(0, 2, 500)
    y_pred = rng.integers(0, 2, 500)
    amounts = rng.uniform(200, 50_000, 500)
    b = cost_breakdown(y_true, y_pred, amounts)
    net = (b["false_positive_cost_inr"] + b["false_negative_cost_inr"]
           - b["recovered_from_true_positives_inr"])
    assert abs(net - b["net_cost_inr"]) < 0.05


def test_perfect_prediction_is_cheapest():
    rng = np.random.default_rng(1)
    y = rng.integers(0, 2, 400)
    amounts = rng.uniform(500, 30_000, 400)
    perfect = expected_cost(y, y, amounts)
    assert perfect <= expected_cost(y, np.zeros_like(y), amounts)
    assert perfect <= expected_cost(y, np.ones_like(y), amounts)
    assert perfect <= expected_cost(y, 1 - y, amounts)


def test_tune_thresholds_ordering_and_floor():
    rng = np.random.default_rng(2)
    n = 4000
    y = rng.integers(0, 2, n)
    # informative but noisy scores
    p = np.clip(y * 0.55 + rng.uniform(0, 0.45, n), 0, 1)
    amounts = rng.uniform(500, 30_000, n)
    result = tune_thresholds(y, p, amounts)
    assert 0 < result["t_low"] < result["t_high"] < 1
    # the chosen t_high must satisfy the precision floor on this data
    pred = (p >= result["t_high"]).astype(int)
    tp = ((pred == 1) & (y == 1)).sum()
    fp = ((pred == 1) & (y == 0)).sum()
    assert tp / (tp + fp) >= PRECISION_FLOOR - 1e-9
