"""Feature engine invariants: leakage, determinism, missingness."""

import numpy as np
import pandas as pd
import pytest

from riskmodel.features import FEATURE_COLUMNS, FORBIDDEN_COLUMNS, build_features
from riskmodel.generate import GenConfig, generate


@pytest.fixture(scope="module")
def sample_df():
    return generate(GenConfig(n_cases=300, seed=7))


def test_no_forbidden_columns(sample_df):
    X = build_features(sample_df)
    assert not FORBIDDEN_COLUMNS.intersection(X.columns)
    # the latent scenario must never leak into the model matrix
    assert "scenario" not in X.columns
    assert "label_abusive" not in X.columns


def test_feature_columns_stable(sample_df):
    X = build_features(sample_df)
    assert list(X.columns) == FEATURE_COLUMNS


def test_no_nans_after_build(sample_df):
    X = build_features(sample_df)
    assert not X.isna().any().any()


def test_missing_indicator_set():
    row = sample_row()
    row["days_to_deliver"] = None
    X = build_features(pd.DataFrame([row]))
    assert X.iloc[0]["days_to_deliver_missing"] == 1
    assert X.iloc[0]["days_to_deliver"] == -1.0


def test_single_row_matches_batch(sample_df):
    X_batch = build_features(sample_df)
    row = sample_df.iloc[[5]].reset_index(drop=True)
    X_one = build_features(row)
    assert np.allclose(X_batch.iloc[5].to_numpy(dtype=float),
                       X_one.iloc[0].to_numpy(dtype=float))


def test_interaction_features():
    row = sample_row()
    row.update({"chargeback_reason": "product_not_received",
                "delivery_status": "delivered",
                "delivery_confirmation": "signed"})
    X = build_features(pd.DataFrame([row]))
    assert X.iloc[0]["pnr_but_confirmed"] == 1
    row["delivery_confirmation"] = "none"
    X = build_features(pd.DataFrame([row]))
    assert X.iloc[0]["pnr_but_confirmed"] == 0
    assert X.iloc[0]["pnr_but_delivered"] == 1


def sample_row() -> dict:
    return {
        "disputed_amount": 12_000.0, "quantity": 1,
        "account_age_days": 300.0, "previous_orders": 10,
        "previous_chargebacks": 0, "previous_returns": 1,
        "previous_failed_payments": 0, "avg_order_value": 4_000.0,
        "claim_delay_days": 5.0, "days_to_deliver": 3.0,
        "device_shared_accounts": 0, "ip_geo_distance_km": 12.0,
        "txns_last_24h": 1, "has_tracking": 1, "device_seen_before": 1,
        "shipping_billing_match": 1,
        "chargeback_reason": "product_not_received",
        "payment_method": "credit_card",
        "delivery_status": "delivered",
        "delivery_confirmation": "signed",
    }
