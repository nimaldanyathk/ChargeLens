"""Out-of-time robustness check.

The primary model is trained and tested on a customer-grouped split (no
customer straddles splits). That is leak-free for identity, but it is
still a *random* split in time: train and test are drawn from the same
period. Fraud shifts over time, so a random split tends to overstate what
the model will do on future disputes.

This script retrains the identical pipeline on a strict TIME-ORDERED
split of the same data - earliest cases train, the middle validates, the
latest cases test - and reports the test metrics next to the primary
ones. Publishing the honest degradation is the point: it is the
difference between "measured on data like training" and "measured on the
future".

Writes artifacts/robustness.json. Run after train.py / evaluate.py.
"""

from __future__ import annotations

import json

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

from .calibration import IsotonicCalibratedModel
from .features import FEATURE_COLUMNS, build_features
from .train import (
    ARTIFACT_DIR, DATA_DIR, SEED, candidates, tune_thresholds,
)


def _temporal_split(df: pd.DataFrame, train=0.70, val=0.15):
    df = df.sort_values("claim_ts").reset_index(drop=True)
    n = len(df)
    part = np.full(n, "test", dtype=object)
    part[: int(n * train)] = "train"
    part[int(n * train): int(n * (train + val))] = "val"
    df = df.copy()
    df["tsplit"] = part
    return df


def _headline(y, p, t_high) -> dict:
    pred = (p >= t_high).astype(int)
    tp = int(((pred == 1) & (y == 1)).sum())
    fp = int(((pred == 1) & (y == 0)).sum())
    fn = int(((pred == 0) & (y == 1)).sum())
    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    return {
        "roc_auc": round(float(roc_auc_score(y, p)), 4),
        "pr_auc": round(float(average_precision_score(y, p)), 4),
        "precision": round(float(precision), 4),
        "recall": round(float(recall), 4),
        "n_test": int(len(y)),
    }


def main():
    df = _temporal_split(pd.read_csv(DATA_DIR / "cases.csv"))
    tr = df[df["tsplit"] == "train"]
    va = df[df["tsplit"] == "val"]
    te = df[df["tsplit"] == "test"]

    X_tr = build_features(tr)[FEATURE_COLUMNS]
    X_va = build_features(va)[FEATURE_COLUMNS]
    X_te = build_features(te)[FEATURE_COLUMNS]
    y_tr = tr["label_abusive"].to_numpy()
    y_va = va["label_abusive"].to_numpy()
    y_te = te["label_abusive"].to_numpy()

    # same candidate set, selection by validation PR-AUC
    best_name, best_model, best_ap = None, None, -1.0
    for name, model in candidates(y_tr).items():
        model.fit(X_tr, y_tr)
        ap = average_precision_score(y_va, model.predict_proba(X_va)[:, 1])
        if ap > best_ap:
            best_name, best_model, best_ap = name, model, ap

    # calibrate on the earlier half of validation (by time), tune on the
    # later half - keeps calibration and tuning out of sample and in order
    half = len(va) // 2
    cal_idx = np.arange(len(va)) < half
    calibrated = IsotonicCalibratedModel(best_model, FEATURE_COLUMNS)
    calibrated.fit_calibrator(X_va[cal_idx], y_va[cal_idx])
    p_tune = calibrated.predict_proba(X_va[~cal_idx])[:, 1]
    thr = tune_thresholds(y_va[~cal_idx], p_tune,
                          va["disputed_amount"].to_numpy()[~cal_idx])

    p_te = calibrated.predict_proba(X_te)[:, 1]
    temporal = _headline(y_te, p_te, thr["t_high"])

    # primary (customer-grouped) numbers straight from metrics.json
    primary_metrics = json.loads(
        (ARTIFACT_DIR / "metrics.json").read_text())
    cd = primary_metrics["contest_decision_at_t_high"]
    tf = primary_metrics["threshold_free"]
    primary = {
        "roc_auc": tf["roc_auc"], "pr_auc": tf["pr_auc"],
        "precision": cd["precision"], "recall": cd["recall"],
        "n_test": primary_metrics["test_set"]["n_cases"],
    }

    delta = {k: round(temporal[k] - primary[k], 4)
             for k in ("roc_auc", "pr_auc", "precision", "recall")}

    worst = min(delta[k] for k in ("roc_auc", "pr_auc", "precision", "recall"))
    interpretation = (
        "Out-of-time performance holds here (no material drop). This "
        "synthetic generator samples dispute scenarios i.i.d. over time, "
        "so there is no concept drift to degrade on - the honest reading "
        "is that the numbers are stable BECAUSE the data is stationary, "
        "not because drift was handled. On real, non-stationary disputes a "
        "gap would appear; this check is the methodology that surfaces it."
        if worst > -0.03 else
        "Out-of-time metrics are lower than the random-split numbers - the "
        "expected effect of evaluating on the future. The gap is reported "
        "rather than hidden; the random-split figures should be read as an "
        "optimistic bound.")
    out = {
        "note": "Same pipeline, two evaluation protocols. 'customer_grouped'"
                " is the primary split (leak-free by identity, random in "
                "time). 'out_of_time' trains on the earliest disputes and "
                "tests on the latest.",
        "interpretation": interpretation,
        "selected_model_out_of_time": best_name,
        "out_of_time_thresholds": {"t_low": thr["t_low"],
                                   "t_high": thr["t_high"]},
        "customer_grouped": primary,
        "out_of_time": temporal,
        "delta_out_of_time_minus_primary": delta,
    }
    (ARTIFACT_DIR / "robustness.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
