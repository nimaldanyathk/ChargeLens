"""Model training, selection, calibration, and threshold tuning.

Protocol (strictly enforced):
  * TRAIN split      -> model fitting only.
  * VALIDATION split -> model selection on the full split; then the split
    is divided by customer into a CALIBRATION half (isotonic fit) and a
    disjoint TUNING half (threshold search), so thresholds are chosen on
    probabilities the calibrator did not see in-sample.
  * TEST split       -> never touched here; evaluate.py reads it once.

Candidates: a logistic-regression baseline, a random forest, and
XGBoost. Selection is by validation PR-AUC (average precision), the
right headline metric for an imbalanced contest/accept decision.

Thresholds (tuned on calibrated validation probabilities):
  * t_high - the CONTEST threshold. Chosen to minimise expected
    business cost (see costs.py), subject to a precision floor so the
    system does not fight honest customers to chase savings.
  * t_low  - the floor of the human-review band. The largest threshold
    for which the auto-accept band (p < t_low) keeps its abusive rate
    at or below MAX_LOW_BAND_ABUSE, i.e. we only auto-accept when the
    negative predictive value stays >= 96%. This sizes the review band
    by evidence, not by an arbitrary percentage.
Cases with t_low <= p < t_high are routed to HUMAN REVIEW.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, precision_score, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

from .calibration import IsotonicCalibratedModel
from .costs import expected_cost
from .features import FEATURE_COLUMNS, build_features

BACKEND_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BACKEND_DIR / "data"
ARTIFACT_DIR = BACKEND_DIR / "artifacts"

SEED = 42
PRECISION_FLOOR = 0.85       # never auto-contest with worse precision than this
MAX_LOW_BAND_ABUSE = 0.04    # auto-accept band must stay >= 96% legitimate
MODEL_VERSION = "1.0.0"


def load_split(split: str) -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / "cases.csv")
    return df[df["split"] == split].reset_index(drop=True)


def candidates(y_train: np.ndarray) -> dict:
    pos = float(y_train.mean())
    spw = (1.0 - pos) / pos  # scale_pos_weight for XGBoost
    return {
        "logistic_regression_C0.1": Pipeline([
            ("scaler", StandardScaler()),
            ("clf", LogisticRegression(
                C=0.1, max_iter=3000, class_weight="balanced",
                random_state=SEED)),
        ]),
        "logistic_regression_C1.0": Pipeline([
            ("scaler", StandardScaler()),
            ("clf", LogisticRegression(
                C=1.0, max_iter=3000, class_weight="balanced",
                random_state=SEED)),
        ]),
        "random_forest": RandomForestClassifier(
            n_estimators=400, min_samples_leaf=5, class_weight="balanced",
            random_state=SEED, n_jobs=-1),
        "xgboost_depth3": XGBClassifier(
            n_estimators=500, learning_rate=0.05, max_depth=3,
            subsample=0.9, colsample_bytree=0.9, scale_pos_weight=spw,
            eval_metric="aucpr", random_state=SEED, n_jobs=-1),
        "xgboost_depth5": XGBClassifier(
            n_estimators=500, learning_rate=0.05, max_depth=5,
            subsample=0.9, colsample_bytree=0.9, scale_pos_weight=spw,
            eval_metric="aucpr", random_state=SEED, n_jobs=-1),
    }


def tune_thresholds(y_val: np.ndarray, p_val: np.ndarray,
                    amounts: np.ndarray) -> dict:
    grid = np.round(np.arange(0.02, 0.99, 0.01), 2)

    # ---- t_high: minimise expected cost subject to a precision floor ----
    best = None
    curve = []
    for t in grid:
        pred = (p_val >= t).astype(int)
        if pred.sum() == 0:
            continue
        prec = precision_score(y_val, pred, zero_division=0)
        cost = expected_cost(y_val, pred, amounts)
        curve.append({"threshold": float(t), "precision": round(float(prec), 4),
                      "expected_cost_inr": round(float(cost), 2)})
        if prec >= PRECISION_FLOOR and (best is None or cost < best[1]):
            best = (float(t), float(cost))
    if best is None:  # precision floor unreachable: fall back to min cost
        best = min(((c["threshold"], c["expected_cost_inr"]) for c in curve),
                   key=lambda x: x[1])
    t_high = best[0]

    # ---- t_low: widest auto-accept band that stays almost surely clean --
    # the empirical abuse rate is not monotone in t (sampling noise), so
    # scan every candidate and keep the LARGEST threshold whose band both
    # satisfies the abuse ceiling and is big enough to certify it
    t_low = 0.02
    for t in grid:
        if t >= t_high:
            break
        low_mask = p_val < t
        if low_mask.sum() < 30:
            continue
        if float(y_val[low_mask].mean()) <= MAX_LOW_BAND_ABUSE:
            t_low = float(t)
    return {"t_low": t_low, "t_high": t_high,
            "precision_floor": PRECISION_FLOOR,
            "max_low_band_abuse": MAX_LOW_BAND_ABUSE,
            "cost_curve": curve}


def main():
    train_df, val_df = load_split("train"), load_split("val")
    X_train = build_features(train_df)[FEATURE_COLUMNS]
    X_val = build_features(val_df)[FEATURE_COLUMNS]
    y_train = train_df["label_abusive"].to_numpy()
    y_val = val_df["label_abusive"].to_numpy()

    # ---- fit and compare candidates on validation ----------------------
    leaderboard = []
    fitted = {}
    for name, model in candidates(y_train).items():
        model.fit(X_train, y_train)
        p = model.predict_proba(X_val)[:, 1]
        leaderboard.append({
            "model": name,
            "val_pr_auc": round(float(average_precision_score(y_val, p)), 4),
            "val_roc_auc": round(float(roc_auc_score(y_val, p)), 4),
        })
        fitted[name] = model
    leaderboard.sort(key=lambda r: r["val_pr_auc"], reverse=True)
    winner_name = leaderboard[0]["model"]
    winner = fitted[winner_name]

    # ---- calibrate on one half of validation, tune on the other --------
    cal_customers = np.array(sorted(val_df["customer_id"].unique()),
                             dtype=object)
    np.random.default_rng(SEED + 2).shuffle(cal_customers)
    cal_set = set(cal_customers[: len(cal_customers) // 2])
    cal_mask = val_df["customer_id"].isin(cal_set).to_numpy()

    calibrated = IsotonicCalibratedModel(winner, FEATURE_COLUMNS)
    calibrated.fit_calibrator(X_val[cal_mask], y_val[cal_mask])
    p_tune = calibrated.predict_proba(X_val[~cal_mask])[:, 1]

    # ---- thresholds (on the disjoint tuning half) -----------------------
    thresholds = tune_thresholds(
        y_val[~cal_mask], p_tune,
        val_df["disputed_amount"].to_numpy()[~cal_mask])

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(calibrated, ARTIFACT_DIR / "model.joblib")
    selection = {
        "model_version": MODEL_VERSION,
        "selected_model": winner_name,
        "selection_metric": "validation PR-AUC",
        "leaderboard": leaderboard,
        "calibration": "isotonic, fitted on the calibration half of "
                       "validation (split by customer)",
        "threshold_tuning": "tuned on the disjoint tuning half of "
                            "validation",
        "thresholds": {k: v for k, v in thresholds.items()
                       if k != "cost_curve"},
        "n_features": len(FEATURE_COLUMNS),
        "seed": SEED,
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    (ARTIFACT_DIR / "model_selection.json").write_text(
        json.dumps(selection, indent=2))
    (ARTIFACT_DIR / "thresholds.json").write_text(json.dumps({
        "t_low": thresholds["t_low"], "t_high": thresholds["t_high"],
        "precision_floor": PRECISION_FLOOR,
        "max_low_band_abuse": MAX_LOW_BAND_ABUSE,
        "cost_curve": thresholds["cost_curve"],
    }, indent=2))
    (ARTIFACT_DIR / "feature_columns.json").write_text(
        json.dumps(FEATURE_COLUMNS, indent=2))
    print(json.dumps(selection, indent=2))


if __name__ == "__main__":
    main()
