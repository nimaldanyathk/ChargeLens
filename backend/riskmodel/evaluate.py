"""Held-out test evaluation. Reads the TEST split exactly once.

Everything in artifacts/metrics.json is computed here from real model
output on unseen data - nothing is hand-written. The frontend analytics
page renders this file directly, so what the judges see is what the
model actually measured.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
from sklearn.metrics import (
    average_precision_score, brier_score_loss, confusion_matrix,
    precision_recall_curve, roc_auc_score, roc_curve,
)

from .bootstrap import confidence_intervals
from .costs import OPS_COST, cost_breakdown, expected_cost
from .features import FEATURE_COLUMNS, build_features
from .train import ARTIFACT_DIR, MODEL_VERSION, load_split

REVIEW_OPS_COST = 150.0   # INR: cost of one human review (assumption)


def _downsample(xs, ys, n=120):
    xs, ys = np.asarray(xs), np.asarray(ys)
    if len(xs) <= n:
        idx = np.arange(len(xs))
    else:
        idx = np.linspace(0, len(xs) - 1, n).astype(int)
    return [{"x": round(float(xs[i]), 4), "y": round(float(ys[i]), 4)}
            for i in idx]


def _calibration_bins(y_true, p, n_bins=10):
    bins = []
    edges = np.linspace(0, 1, n_bins + 1)
    for lo, hi in zip(edges[:-1], edges[1:]):
        mask = (p >= lo) & (p < hi if hi < 1 else p <= hi)
        if mask.sum() == 0:
            continue
        bins.append({
            "bin": f"{lo:.1f}-{hi:.1f}",
            "mean_predicted": round(float(p[mask].mean()), 4),
            "observed_rate": round(float(y_true[mask].mean()), 4),
            "count": int(mask.sum()),
        })
    return bins


def main():
    test_df = load_split("test")
    X_test = build_features(test_df)[FEATURE_COLUMNS]
    y = test_df["label_abusive"].to_numpy()
    amounts = test_df["disputed_amount"].to_numpy()

    model = joblib.load(ARTIFACT_DIR / "model.joblib")
    thresholds = json.loads((ARTIFACT_DIR / "thresholds.json").read_text())
    t_low, t_high = thresholds["t_low"], thresholds["t_high"]

    p = model.predict_proba(X_test)[:, 1]

    # ---- binary contest decision at t_high ------------------------------
    pred = (p >= t_high).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    f1 = 2 * precision * recall / max(precision + recall, 1e-12)
    fpr_val = fp / max(fp + tn, 1)
    fnr_val = fn / max(fn + tp, 1)

    # ---- threshold-free metrics ------------------------------------------
    roc_auc = roc_auc_score(y, p)
    pr_auc = average_precision_score(y, p)
    brier = brier_score_loss(y, p)
    prec_c, rec_c, _ = precision_recall_curve(y, p)
    fpr_c, tpr_c, _ = roc_curve(y, p)

    # ---- three-band routing ------------------------------------------------
    band = np.where(p >= t_high, "high", np.where(p >= t_low, "review", "low"))
    bands = {}
    for b in ("low", "review", "high"):
        mask = band == b
        bands[b] = {
            "count": int(mask.sum()),
            "share": round(float(mask.mean()), 4),
            "abusive_rate": round(float(y[mask].mean()), 4)
            if mask.sum() else None,
        }

    # ---- bootstrap confidence intervals on the headline metrics ---------
    ci = confidence_intervals(y, p, amounts, t_low, t_high, B=5000)

    # ---- cost analysis --------------------------------------------------
    model_cost = cost_breakdown(y, pred, amounts)
    accept_all = expected_cost(y, np.zeros_like(y), amounts)
    contest_all = expected_cost(y, np.ones_like(y), amounts)
    # three-band policy: auto-decide outside the review band; humans decide
    # review-band cases and are assumed correct (assumption disclosed here)
    auto_mask = band != "review"
    rev_mask = ~auto_mask
    policy_cost = (
        expected_cost(y[auto_mask], pred[auto_mask], amounts[auto_mask])
        + expected_cost(y[rev_mask], y[rev_mask], amounts[rev_mask])
        + float(rev_mask.sum()) * REVIEW_OPS_COST)

    metrics = {
        "disclosure": "Synthetic dataset (see data/manifest.json). All "
                      "metrics computed on the held-out test split, which "
                      "was never used for training, model selection, "
                      "calibration, or threshold tuning.",
        "model_version": MODEL_VERSION,
        "evaluated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "test_set": {
            "n_cases": int(len(y)),
            "n_abusive": int(y.sum()),
            "n_legitimate": int((1 - y).sum()),
            "abusive_rate": round(float(y.mean()), 4),
        },
        "thresholds": {"t_low": t_low, "t_high": t_high},
        "contest_decision_at_t_high": {
            "precision": round(float(precision), 4),
            "recall": round(float(recall), 4),
            "f1": round(float(f1), 4),
            "false_positive_rate": round(float(fpr_val), 4),
            "false_negative_rate": round(float(fnr_val), 4),
            "confusion_matrix": {"tp": int(tp), "fp": int(fp),
                                 "fn": int(fn), "tn": int(tn)},
        },
        "threshold_free": {
            "roc_auc": round(float(roc_auc), 4),
            "pr_auc": round(float(pr_auc), 4),
            "brier_score": round(float(brier), 4),
        },
        "confidence_intervals": ci,
        "bands": bands,
        "cost_analysis": {
            **model_cost,
            "review_ops_cost_inr_per_case": REVIEW_OPS_COST,
            "policy_costs_inr": {
                "accept_all_disputes": round(float(accept_all), 2),
                "contest_all_disputes": round(float(contest_all), 2),
                "model_binary_at_t_high": model_cost["net_cost_inr"],
                "model_three_band_with_human_review": round(
                    float(policy_cost), 2),
            },
            "three_band_assumption": "review-band cases are decided by a "
                                     "human assumed correct; each review "
                                     f"costs INR {REVIEW_OPS_COST:.0f}",
            "estimated_savings_vs_accept_all_inr": round(
                float(accept_all - policy_cost), 2),
        },
        "curves": {
            "precision_recall": _downsample(rec_c, prec_c),
            "roc": _downsample(fpr_c, tpr_c),
            "calibration": _calibration_bins(y, p),
        },
    }
    (ARTIFACT_DIR / "metrics.json").write_text(json.dumps(metrics, indent=2))
    print(json.dumps({k: metrics[k] for k in (
        "test_set", "thresholds", "contest_decision_at_t_high",
        "threshold_free", "bands")}, indent=2))
    print(f"wrote {ARTIFACT_DIR / 'metrics.json'}")


if __name__ == "__main__":
    main()
