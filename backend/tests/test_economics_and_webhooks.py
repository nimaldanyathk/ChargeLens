"""Dispute economics math + Razorpay webhook contract."""

from __future__ import annotations

import hashlib
import hmac
import json

from app.decision import economics
from app.integrations.razorpay import (
    build_contest_payload, map_dispute_payload, verify_webhook_signature,
)


# ---- economics ------------------------------------------------------------

def test_high_amount_strong_evidence_is_economic():
    econ = economics.evaluate(89_000, 0.98, "strong",
                              "product_not_received")
    # p_win capped at 0.50 then scaled by 0.85 evidence factor
    assert econ["p_win"] == round(0.50 * 0.85, 4)
    assert econ["economic"] is True
    assert econ["ev_contest_inr"] > 0


def test_small_amount_is_uneconomic_even_at_high_confidence():
    econ = economics.evaluate(900, 0.99, "strong", "product_not_received")
    # expected recovery ~0.425 * 0.885 * 900 = ~338 < contest cost 1300
    assert econ["economic"] is False
    assert econ["ev_contest_inr"] < 0


def test_break_even_probability_falls_with_amount():
    small = economics.evaluate(2_000, 0.9, "strong",
                               "product_not_received")
    large = economics.evaluate(80_000, 0.9, "strong",
                               "product_not_received")
    assert large["break_even_p_win"] < small["break_even_p_win"]


def test_unauthorized_claims_capped_lower_than_inr():
    inr = economics.evaluate(50_000, 0.95, "strong",
                             "product_not_received")
    fraud = economics.evaluate(50_000, 0.95, "strong",
                               "unauthorized_transaction")
    assert fraud["p_win"] < inr["p_win"]


def test_weak_evidence_slashes_win_probability():
    strong = economics.evaluate(50_000, 0.9, "strong",
                                "product_not_received")
    weak = economics.evaluate(50_000, 0.9, "weak", "product_not_received")
    assert weak["p_win"] < strong["p_win"] * 0.5


# ---- webhook signature ------------------------------------------------------

def _sign(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_signature_roundtrip():
    body = b'{"event":"payment.dispute.created"}'
    assert verify_webhook_signature(body, _sign(body, "s3cret"), "s3cret")
    assert not verify_webhook_signature(body, _sign(body, "wrong"),
                                        "s3cret")
    assert not verify_webhook_signature(body, "", "s3cret")


def test_signature_covers_raw_bytes_not_parsed_json():
    a = b'{"amount": 100}'
    b = b'{"amount":100}'   # same JSON, different bytes
    assert _sign(a, "k") != _sign(b, "k")


# ---- payload mapping ------------------------------------------------------

SAMPLE_EVENT = {
    "entity": "event",
    "event": "payment.dispute.created",
    "payload": {
        "dispute": {"entity": {
            "id": "disp_AHfqOvkldwsbqt",
            "payment_id": "pay_EsyWjHrfzb59eR",
            "amount": 1000000,          # paise -> Rs 10,000
            "currency": "INR",
            "reason_code": "10.4",
            "respond_by": 1735689600,
            "status": "open",
            "phase": "chargeback",
        }},
        "payment": {"entity": {
            "id": "pay_EsyWjHrfzb59eR", "method": "card",
            "status": "captured", "contact": "+919876543210",
        }},
    },
}


def test_dispute_payload_maps_to_intake_row():
    mapped = map_dispute_payload(SAMPLE_EVENT)
    row, meta = mapped["row"], mapped["meta"]
    assert row["disputed_amount"] == 10_000.0          # paise converted
    assert row["chargeback_reason"] == "unauthorized_transaction"  # 10.4
    assert row["payment_method"] == "credit_card"
    assert meta["external_ref"] == "disp_AHfqOvkldwsbqt"
    assert meta["respond_by_unix"] == 1735689600


def test_webhook_endpoint_creates_case(client, monkeypatch):
    monkeypatch.setenv("CHARGELENS_RZP_WEBHOOK_SECRET", "whsec_test")
    body = json.dumps(SAMPLE_EVENT).encode()
    r = client.post("/api/webhooks/razorpay", content=body,
                    headers={"X-Razorpay-Signature":
                             _sign(body, "whsec_test"),
                             "Content-Type": "application/json"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "created"
    case_id = r.json()["case_id"]
    assert case_id == "CB-RZP-AHfqOvkldwsbqt"

    detail = client.get(f"/api/cases/{case_id}").json()
    assert detail["external_ref"] == "disp_AHfqOvkldwsbqt"
    assert detail["disputed_amount"] == 10_000.0
    assert detail["respond_by"] is not None

    # outcome event updates external status via audit, not workflow state
    won = dict(SAMPLE_EVENT, event="payment.dispute.won")
    body2 = json.dumps(won).encode()
    r2 = client.post("/api/webhooks/razorpay", content=body2,
                     headers={"X-Razorpay-Signature":
                              _sign(body2, "whsec_test")})
    assert r2.json()["status"] == "updated"
    assert r2.json()["external_status"] == "won"


def test_webhook_rejects_bad_signature(client, monkeypatch):
    monkeypatch.setenv("CHARGELENS_RZP_WEBHOOK_SECRET", "whsec_test")
    body = json.dumps(SAMPLE_EVENT).encode()
    r = client.post("/api/webhooks/razorpay", content=body,
                    headers={"X-Razorpay-Signature": "forged"})
    assert r.status_code == 401


def test_webhook_refuses_when_unconfigured(client, monkeypatch):
    monkeypatch.delenv("CHARGELENS_RZP_WEBHOOK_SECRET", raising=False)
    r = client.post("/api/webhooks/razorpay", content=b"{}",
                    headers={"X-Razorpay-Signature": "x"})
    assert r.status_code == 503


# ---- contest payload --------------------------------------------------------

def test_contest_payload_uses_razorpay_evidence_keys():
    class Item:
        def __init__(self, key, supports):
            self.key, self.supports = key, supports

    class Case:
        disputed_amount = 12_345.0
        recommendation_reason = "delivered and signed"
        external_ref = None
        id = "CB-X"

    payload = build_contest_payload(Case(), [
        Item("delivery_confirmed", "merchant"),
        Item("known_device", "merchant"),
        Item("high_velocity", "customer"),  # customer-supporting: excluded
    ])
    assert payload["action"] == "draft"    # never auto-submits
    assert payload["amount"] == 1234500    # rupees -> paise
    assert "shipping_proof" in payload
    assert "access_activity_log" in payload
    # customer-supporting evidence must never appear in the contest pack
    assert all("high_velocity" not in str(v) for v in payload.values())
