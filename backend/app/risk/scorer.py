"""Serving-side risk scoring.

Uses the exact same feature builder as training (riskmodel.features), so
there is no train/serve skew. Per-case SHAP attributions are computed
live against the persisted model.
"""

from __future__ import annotations

import json
from functools import lru_cache

import joblib
import pandas as pd

from riskmodel.features import FEATURE_COLUMNS, build_features

from ..config import settings
from ..models.entities import Chargeback, Customer, Delivery, Order, Transaction

# human-readable labels for the strongest features
FEATURE_LABELS = {
    "pnr_but_confirmed": "'Not received' claim vs confirmed delivery",
    "pnr_but_delivered": "'Not received' claim vs delivered status",
    "unauth_but_known_device": "'Unauthorized' claim from a known device",
    "delivered_with_confirmation": "Delivery confirmed by carrier",
    "delivery_confirmation__none": "No delivery confirmation on file",
    "delivery_confirmation__signed": "Signed delivery confirmation",
    "delivery_confirmation__otp": "OTP-verified delivery",
    "delivery_confirmation__photo": "Photo proof of delivery",
    "delivery_status__delivered": "Order marked delivered",
    "delivery_status__failed": "Delivery failed",
    "delivery_status__in_transit": "Package still in transit",
    "delivery_status__unknown": "Delivery status unknown",
    "claim_delay_days": "Time between delivery and claim",
    "account_age_days": "Account age",
    "previous_orders": "Order history depth",
    "previous_chargebacks": "Prior chargebacks",
    "previous_returns": "Prior returns",
    "previous_failed_payments": "Prior failed payments",
    "chargeback_rate": "Chargeback rate vs order count",
    "device_seen_before": "Device familiarity",
    "device_shared_accounts": "Device shared across accounts",
    "ip_geo_distance_km": "IP distance from usual location",
    "txns_last_24h": "Transaction velocity (24h)",
    "shipping_billing_match": "Shipping/billing address match",
    "disputed_amount": "Disputed amount",
    "log_amount": "Disputed amount (log scale)",
    "amount_over_aov": "Amount vs customer's usual spend",
    "orders_per_month": "Order frequency",
    "new_account_high_value": "New account with high-value order",
    "chargeback_reason__product_not_received": "Claim: product not received",
    "chargeback_reason__unauthorized_transaction": "Claim: unauthorized transaction",
    "chargeback_reason__product_not_as_described": "Claim: not as described",
    "has_tracking": "Tracking number on file",
    "days_to_deliver": "Delivery duration",
}


def case_to_raw_row(case: Chargeback, customer: Customer, txn: Transaction,
                    order: Order, delivery: Delivery | None) -> dict:
    """Assemble the raw record shape the feature builder expects."""
    return {
        "chargeback_reason": case.reason,
        "disputed_amount": case.disputed_amount,
        "claim_delay_days": case.claim_delay_days,
        "quantity": order.quantity,
        "payment_method": txn.payment_method,
        "account_age_days": customer.account_age_days,
        "previous_orders": customer.previous_orders,
        "previous_chargebacks": customer.previous_chargebacks,
        "previous_returns": customer.previous_returns,
        "previous_failed_payments": customer.previous_failed_payments,
        "avg_order_value": customer.avg_order_value,
        "delivery_status": delivery.delivery_status if delivery else "unknown",
        "delivery_confirmation": (delivery.delivery_confirmation
                                  if delivery else "none"),
        "has_tracking": int(delivery.has_tracking) if delivery else 0,
        "days_to_deliver": delivery.days_to_deliver if delivery else None,
        "device_seen_before": int(txn.device_seen_before),
        "device_shared_accounts": txn.device_shared_accounts,
        "ip_geo_distance_km": txn.ip_geo_distance_km,
        "txns_last_24h": txn.txns_last_24h,
        "shipping_billing_match": int(order.shipping_billing_match),
    }


class RiskScorer:
    def __init__(self):
        self.model = joblib.load(settings.artifact_dir / "model.joblib")
        thresholds = json.loads(
            (settings.artifact_dir / "thresholds.json").read_text())
        self.t_low: float = thresholds["t_low"]
        self.t_high: float = thresholds["t_high"]
        selection = json.loads(
            (settings.artifact_dir / "model_selection.json").read_text())
        self.model_version: str = selection["model_version"]
        self.model_name: str = selection["selected_model"]
        self._explainer = None

    @property
    def explainer(self):
        if self._explainer is None:
            from riskmodel.explain import make_explainer
            background = pd.read_csv(
                settings.artifact_dir / "shap_background.csv")
            self._explainer = make_explainer(self.model, background)
        return self._explainer

    def band(self, score: float) -> str:
        if score >= self.t_high:
            return "high"
        if score >= self.t_low:
            return "review"
        return "low"

    def score(self, raw_row: dict) -> dict:
        X = build_features(pd.DataFrame([raw_row]))[FEATURE_COLUMNS]
        prob = float(self.model.predict_proba(X)[0, 1])
        factors = self._top_factors(X)
        return {
            "risk_score": round(prob, 4),
            "band": self.band(prob),
            "model_version": self.model_version,
            "model_name": self.model_name,
            "top_factors": factors,
        }

    def _top_factors(self, X: pd.DataFrame, k: int = 8) -> list[dict]:
        from riskmodel.explain import shap_values_matrix
        values = shap_values_matrix(self.explainer, X)[0]
        pairs = sorted(zip(FEATURE_COLUMNS, values),
                       key=lambda p: abs(p[1]), reverse=True)
        out = []
        for name, val in pairs[:k]:
            if abs(val) < 1e-6:
                continue
            out.append({
                "feature": name,
                "label": FEATURE_LABELS.get(name, name.replace("_", " ")),
                "shap": round(float(val), 4),
                "direction": "raises_risk" if val > 0 else "lowers_risk",
                "value": _display_value(X, name),
            })
        return out


def _display_value(X: pd.DataFrame, feature: str) -> str:
    v = X.iloc[0][feature]
    f = float(v)
    return str(int(f)) if f == int(f) else f"{f:.2f}"


@lru_cache(maxsize=1)
def get_scorer() -> RiskScorer:
    return RiskScorer()
