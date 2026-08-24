"""Razorpay Disputes integration.

Three concerns, all matching Razorpay's real API contract
(razorpay.com/docs/api/disputes, razorpay.com/docs/webhooks/payloads/disputes):

1. Webhook signature verification - HMAC-SHA256 of the RAW request body
   with the webhook secret, compared against X-Razorpay-Signature.
   Verification must run on the unparsed body.

2. Payload mapping - payment.dispute.created carries the dispute entity
   (id, payment_id, amount in paise, currency, reason_code, respond_by
   unix ts, status, phase) plus the payment entity. We map it into a
   ChargeLens intake row. Razorpay does not know delivery/customer
   history, so those fields arrive as explicit unknowns for the merchant
   (or an OMS integration) to enrich - the audit trail records this.

3. Contest payload - Razorpay's contest call is
   PATCH /v1/disputes/:id/contest with the ten named evidence keys, each
   a list of document ids uploaded via the Documents API
   (purpose=dispute_evidence), a summary (<=1000 chars) and
   action: "draft" | "submit". We emit a payload that validates against
   that schema; with live test keys we send it, otherwise we return it
   as a dry run so the demo shows exactly what would be submitted.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import urllib.request

RZP_API_BASE = "https://api.razorpay.com/v1"

# Razorpay evidence keys accepted by the contest endpoint.
EVIDENCE_KEYS = [
    "shipping_proof", "billing_proof", "cancellation_proof",
    "customer_communication", "proof_of_service", "explanation_letter",
    "refund_confirmation", "access_activity_log",
    "refund_cancellation_policy", "term_and_conditions",
]

# ChargeLens evidence-item keys -> Razorpay evidence categories.
EVIDENCE_KEY_MAP = {
    "delivery_status": "shipping_proof",
    "delivery_confirmation": "shipping_proof",
    "tracking": "shipping_proof",
    "days_to_deliver": "shipping_proof",
    "payment_status": "billing_proof",
    "amount_match": "billing_proof",
    "shipping_billing_match": "billing_proof",
    "device_known": "access_activity_log",
    "device_shared": "access_activity_log",
    "ip_distance": "access_activity_log",
    "velocity": "access_activity_log",
}


def keys_configured() -> bool:
    return bool(os.environ.get("RAZORPAY_KEY_ID")
                and os.environ.get("RAZORPAY_KEY_SECRET"))


def verify_webhook_signature(raw_body: bytes, signature: str,
                             secret: str) -> bool:
    """HMAC-SHA256 over the raw body; constant-time compare."""
    if not signature or not secret:
        return False
    expected = hmac.new(secret.encode(), raw_body,
                        hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def map_dispute_payload(event: dict) -> dict:
    """payment.dispute.* payload -> ChargeLens intake row + metadata.

    Amounts arrive in paise; respond_by is a unix timestamp.
    """
    dispute = event["payload"]["dispute"]["entity"]
    payment = (event.get("payload", {}).get("payment", {})
               .get("entity", {}))

    method = payment.get("method", "card")
    payment_method = {"card": "credit_card", "upi": "upi",
                      "netbanking": "netbanking",
                      "wallet": "wallet"}.get(method, "credit_card")

    reason = _reason_from_code(dispute.get("reason_code", ""))
    row = {
        "customer_id": f"CUST-RZP-{(payment.get('contact') or dispute['payment_id'])[-6:]}",
        "chargeback_reason": reason,
        "claim_description": dispute.get("reason_description")
        or dispute.get("reason_code") or "chargeback raised via issuer",
        "disputed_amount": dispute["amount"] / 100.0,
        "payment_method": payment_method,
        "product_category": "electronics",   # unknown to Razorpay: enrich from OMS
        "product_name": "(pending OMS enrichment)",
        "quantity": 1,
        "shipping_city": "unknown", "billing_city": "unknown",
        "shipping_billing_match": 0,
        "account_age_days": 0.0, "previous_orders": 0,
        "previous_chargebacks": 0, "previous_returns": 0,
        "previous_failed_payments": 0, "avg_order_value":
        dispute["amount"] / 100.0,
        "delivery_status": "unknown", "delivery_confirmation": "none",
        "has_tracking": 0, "days_to_deliver": None,
        "device_seen_before": 0, "device_shared_accounts": 0,
        "ip_geo_distance_km": 0.0, "txns_last_24h": 1,
        "claim_delay_days": 0.0,
        "transaction_id": dispute["payment_id"],
        "order_id": f"ORD-{dispute['id']}",
        "currency": dispute.get("currency", "INR"),
        "payment_status": payment.get("status", "captured"),
        "order_ts": None, "shipped_ts": None, "delivered_ts": None,
        "claim_ts": None,
    }
    meta = {
        "external_ref": dispute["id"],
        "respond_by_unix": dispute.get("respond_by"),
        "phase": dispute.get("phase"),
        "status": dispute.get("status"),
        "reason_code": dispute.get("reason_code"),
    }
    return {"row": row, "meta": meta}


def _reason_from_code(code: str) -> str:
    """Normalize network reason codes into ChargeLens categories.
    Visa 10.x / MC 4837 = fraud; Visa 13.1 / MC 4853-goods-not-received =
    INR; 13.3 / not-as-described = quality."""
    c = (code or "").lower()
    if c.startswith("10") or "4837" in c or "fraud" in c or "unauth" in c:
        return "unauthorized_transaction"
    if "13.3" in c or "described" in c or "quality" in c:
        return "product_not_as_described"
    return "product_not_received"


def build_contest_payload(case, evidence_items: list) -> dict:
    """Contest-ready payload for PATCH /v1/disputes/:id/contest.

    Document ids are placeholders until files are uploaded through the
    Documents API (purpose=dispute_evidence); the structure and keys match
    the live schema, and `action: "draft"` means even a live call cannot
    submit without a later explicit human `submit`.
    """
    grouped: dict[str, list[str]] = {}
    for item in evidence_items:
        if getattr(item, "supports", None) != "merchant":
            continue
        rzp_key = EVIDENCE_KEY_MAP.get(item.key)
        if rzp_key:
            grouped.setdefault(rzp_key, []).append(
                f"doc_placeholder_{item.key}")

    summary = (case.recommendation_reason or "")[:1000]
    payload: dict = {"amount": int(round(case.disputed_amount * 100)),
                     "summary": summary, "action": "draft"}
    payload.update(grouped)
    return payload


def api_call(path: str, method: str = "GET", body: dict | None = None):
    """Minimal authenticated Razorpay API call (test keys, stdlib only)."""
    key_id = os.environ["RAZORPAY_KEY_ID"]
    key_secret = os.environ["RAZORPAY_KEY_SECRET"]
    token = base64.b64encode(f"{key_id}:{key_secret}".encode()).decode()
    req = urllib.request.Request(
        RZP_API_BASE + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Basic {token}",
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())
