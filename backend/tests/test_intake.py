"""Case intake endpoint: validation and full lifecycle from intake."""

VALID_BODY = {
    "customer_id": "CUST-NEW-1",
    "chargeback_reason": "product_not_received",
    "claim_description": "I never received this order.",
    "disputed_amount": 15_000.0,
    "payment_method": "credit_card",
    "product_category": "electronics",
    "product_name": "iPad Air",
    "quantity": 1,
    "shipping_city": "Mumbai",
    "billing_city": "Mumbai",
    "account_age_days": 300.0,
    "previous_orders": 12,
    "previous_chargebacks": 0,
    "previous_returns": 1,
    "previous_failed_payments": 0,
    "avg_order_value": 5_000.0,
    "delivery_status": "delivered",
    "delivery_confirmation": "signed",
    "has_tracking": True,
    "days_to_deliver": 3.0,
    "device_seen_before": True,
    "device_shared_accounts": 0,
    "ip_geo_distance_km": 10.0,
    "txns_last_24h": 1,
    "claim_delay_days": 9.0,
}


def test_intake_creates_case(client):
    r = client.post("/api/cases", json=VALID_BODY)
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "received"
    assert body["case_id"].startswith("CB-N")
    assert body["transaction"]["amount"] == 15_000.0
    assert body["order"]["shipping_billing_match"] is True
    # audit starts at intake
    assert any(a["event_type"] == "chargeback_received" for a in body["audit"])


def test_intake_then_investigate_and_decide(client):
    case_id = client.post("/api/cases", json=VALID_BODY).json()["case_id"]
    inv = client.post(f"/api/cases/{case_id}/investigate").json()
    assert inv["status"] == "awaiting_review"
    assert inv["risk"]["band"] in ("low", "review", "high")
    dec = client.post(f"/api/cases/{case_id}/decision",
                      json={"action": "escalate", "note": "double-check"})
    assert dec.json()["status"] == "escalated"


def test_intake_rejects_bad_payloads(client):
    for patch in (
        {"disputed_amount": -5},
        {"chargeback_reason": "made_up_reason"},
        {"quantity": 0},
        {"claim_description": ""},
        {"payment_method": "cash"},
    ):
        r = client.post("/api/cases", json={**VALID_BODY, **patch})
        assert r.status_code == 422, patch


def test_intake_address_mismatch_detected(client):
    r = client.post("/api/cases", json={**VALID_BODY,
                                        "billing_city": "Delhi"})
    assert r.json()["order"]["shipping_billing_match"] is False
