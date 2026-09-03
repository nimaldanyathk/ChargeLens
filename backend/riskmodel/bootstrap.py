"""Stratified bootstrap confidence intervals for the test metrics.

A point estimate like "precision 86.5%" on a ~1,800-case test set carries
sampling uncertainty, and a quant reviewer's first question is the
interval. We resample the saved per-case model outputs (not re-run the
model) B times, resampling WITHIN each class so the class balance is
preserved, and report percentile intervals.

The same resampling loop yields an interval for the rupee-savings number
for free, since savings is just another function of the resampled cases.
"""

from __future__ import annotations

import numpy as np
from sklearn.metrics import average_precision_score, roc_auc_score

from .costs import expected_cost

REVIEW_OPS_COST = 150.0   # keep in step with evaluate.py


def _three_band_savings(y, pred, amounts, band) -> float:
    """Estimated savings vs accept-all under the three-band policy."""
    accept_all = expected_cost(y, np.zeros_like(y), amounts)
    auto = band != "review"
    rev = ~auto
    policy = (expected_cost(y[auto], pred[auto], amounts[auto])
              + expected_cost(y[rev], y[rev], amounts[rev])
              + float(rev.sum()) * REVIEW_OPS_COST)
    return float(accept_all - policy)


def _metrics_on(idx, y, p, amounts, t_low, t_high) -> dict:
    yy, pp, aa = y[idx], p[idx], amounts[idx]
    pred = (pp >= t_high).astype(int)
    tp = int(((pred == 1) & (yy == 1)).sum())
    fp = int(((pred == 1) & (yy == 0)).sum())
    fn = int(((pred == 0) & (yy == 1)).sum())
    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    f1 = 2 * precision * recall / max(precision + recall, 1e-12)
    band = np.where(pp >= t_high, "high",
                    np.where(pp >= t_low, "review", "low"))
    out = {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "savings_inr": _three_band_savings(yy, pred, aa, band),
    }
    # AUCs need both classes present (guaranteed by stratified resampling)
    if yy.min() != yy.max():
        out["roc_auc"] = float(roc_auc_score(yy, pp))
        out["pr_auc"] = float(average_precision_score(yy, pp))
    return out


def confidence_intervals(y, p, amounts, t_low, t_high,
                         B: int = 5000, seed: int = 7,
                         alpha: float = 0.05) -> dict:
    """Return {metric: {point, lo, hi}} at the (1-alpha) level."""
    y = np.asarray(y)
    p = np.asarray(p, dtype=float)
    amounts = np.asarray(amounts, dtype=float)
    rng = np.random.default_rng(seed)
    pos = np.flatnonzero(y == 1)
    neg = np.flatnonzero(y == 0)

    point = _metrics_on(np.arange(len(y)), y, p, amounts, t_low, t_high)
    draws: dict[str, list] = {k: [] for k in point}
    for _ in range(B):
        idx = np.concatenate([
            rng.choice(pos, size=len(pos), replace=True),
            rng.choice(neg, size=len(neg), replace=True),
        ])
        m = _metrics_on(idx, y, p, amounts, t_low, t_high)
        for k, v in m.items():
            draws[k].append(v)

    lo_q, hi_q = 100 * alpha / 2, 100 * (1 - alpha / 2)
    result = {}
    for k, pv in point.items():
        arr = np.asarray(draws[k], dtype=float)
        result[k] = {
            "point": round(float(pv), 4),
            "lo": round(float(np.percentile(arr, lo_q)), 4),
            "hi": round(float(np.percentile(arr, hi_q)), 4),
        }
    result["_meta"] = {"B": B, "alpha": alpha,
                       "method": "stratified percentile bootstrap"}
    return result
