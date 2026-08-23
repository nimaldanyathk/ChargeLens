"""Feature engineering - the single source of truth.

Both the training pipeline (train.py) and the serving path
(app/risk/scorer.py) call `build_features`, so there is no train/serve
skew by construction.

Rules:
  * Only decision-time information is allowed. Columns that would leak
    the outcome (the label, the latent scenario, the split assignment)
    are listed in FORBIDDEN_COLUMNS and asserted absent from the output.
  * Missing values are handled explicitly: a numeric column gets a
    sentinel fill plus a companion `<col>_missing` indicator, never a
    silent imputation.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# columns that must NEVER appear in the model matrix
FORBIDDEN_COLUMNS = frozenset({
    "label_abusive", "scenario", "split", "case_id", "customer_id",
    "transaction_id", "order_id", "claim_description",
})

REASONS = ["product_not_received", "unauthorized_transaction",
           "product_not_as_described"]
PAYMENT_METHODS = ["credit_card", "debit_card", "upi", "netbanking", "wallet"]
DELIVERY_STATUSES = ["delivered", "in_transit", "failed",
                     "returned_to_sender", "unknown"]
CONFIRMATIONS = ["signed", "otp", "photo", "none"]

NUMERIC_RAW = [
    "disputed_amount", "quantity", "account_age_days", "previous_orders",
    "previous_chargebacks", "previous_returns", "previous_failed_payments",
    "avg_order_value", "claim_delay_days", "days_to_deliver",
    "device_shared_accounts", "ip_geo_distance_km", "txns_last_24h",
]
BINARY_RAW = ["has_tracking", "device_seen_before", "shipping_billing_match"]


def _one_hot(df: pd.DataFrame, col: str, categories: list[str]) -> pd.DataFrame:
    out = {}
    values = df[col].astype(str)
    for cat in categories:
        out[f"{col}__{cat}"] = (values == cat).astype(np.int64)
    return pd.DataFrame(out, index=df.index)


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Map raw case records to the model matrix.

    Accepts a DataFrame with the raw case columns (a single case may be
    passed as a one-row frame). Returns a purely numeric DataFrame whose
    column order is stable across calls.
    """
    df = df.copy()
    parts: list[pd.DataFrame] = []

    # ---- numeric columns with explicit missing handling ----------------
    num = {}
    for col in NUMERIC_RAW:
        series = pd.to_numeric(df.get(col), errors="coerce")
        missing = series.isna()
        num[f"{col}_missing"] = missing.astype(np.int64)
        num[col] = series.fillna(-1.0).astype(np.float64)
    parts.append(pd.DataFrame(num, index=df.index))

    # ---- binary flags ---------------------------------------------------
    bin_ = {}
    for col in BINARY_RAW:
        series = pd.to_numeric(df.get(col), errors="coerce")
        bin_[col] = series.fillna(0).astype(np.int64)
    parts.append(pd.DataFrame(bin_, index=df.index))

    # ---- categoricals ---------------------------------------------------
    parts.append(_one_hot(df, "chargeback_reason", REASONS))
    parts.append(_one_hot(df, "payment_method", PAYMENT_METHODS))
    parts.append(_one_hot(df, "delivery_status", DELIVERY_STATUSES))
    parts.append(_one_hot(df, "delivery_confirmation", CONFIRMATIONS))

    # ---- derived signals -------------------------------------------------
    amount = pd.to_numeric(df.get("disputed_amount"), errors="coerce")
    aov = pd.to_numeric(df.get("avg_order_value"), errors="coerce")
    orders = pd.to_numeric(df.get("previous_orders"), errors="coerce").fillna(0)
    age = pd.to_numeric(df.get("account_age_days"), errors="coerce")
    cbs = pd.to_numeric(df.get("previous_chargebacks"), errors="coerce").fillna(0)
    status = df.get("delivery_status").astype(str)
    conf = df.get("delivery_confirmation").astype(str)
    reason = df.get("chargeback_reason").astype(str)
    device_seen = pd.to_numeric(df.get("device_seen_before"),
                                errors="coerce").fillna(0)

    delivered = (status == "delivered").astype(np.int64)
    confirmed = conf.isin(["signed", "otp", "photo"]).astype(np.int64)
    is_pnr = (reason == "product_not_received").astype(np.int64)
    is_unauth = (reason == "unauthorized_transaction").astype(np.int64)

    derived = pd.DataFrame({
        # size of this ticket relative to the customer's normal spend
        "amount_over_aov": (amount / aov.replace(0, np.nan))
        .fillna(-1.0).clip(upper=50.0),
        "log_amount": np.log1p(amount.fillna(0)),
        # order cadence and dispute propensity
        "orders_per_month": (orders / (age / 30.0).replace(0, np.nan))
        .fillna(-1.0).clip(upper=60.0),
        "chargeback_rate": (cbs / (orders + 1.0)),
        # the contradiction signals the verifier lives on
        "delivered_with_confirmation": delivered * confirmed,
        "pnr_but_delivered": is_pnr * delivered,
        "pnr_but_confirmed": is_pnr * delivered * confirmed,
        "unauth_but_known_device": is_unauth * device_seen.astype(np.int64),
        "new_account_high_value": (
            (age.fillna(9999) < 60).astype(np.int64)
            * (amount.fillna(0) > 10_000).astype(np.int64)),
    }, index=df.index)
    parts.append(derived)

    X = pd.concat(parts, axis=1)

    leaked = FORBIDDEN_COLUMNS.intersection(X.columns)
    if leaked:
        raise ValueError(f"leaked columns in feature matrix: {sorted(leaked)}")
    return X


FEATURE_COLUMNS: list[str] = list(
    build_features(pd.DataFrame([{
        "disputed_amount": 100.0, "quantity": 1, "account_age_days": 10,
        "previous_orders": 1, "previous_chargebacks": 0,
        "previous_returns": 0, "previous_failed_payments": 0,
        "avg_order_value": 100.0, "claim_delay_days": 1.0,
        "days_to_deliver": 2.0, "device_shared_accounts": 0,
        "ip_geo_distance_km": 1.0, "txns_last_24h": 1,
        "has_tracking": 1, "device_seen_before": 1,
        "shipping_billing_match": 1,
        "chargeback_reason": REASONS[0], "payment_method": PAYMENT_METHODS[0],
        "delivery_status": DELIVERY_STATUSES[0],
        "delivery_confirmation": CONFIRMATIONS[0],
    }])).columns
)
