"""Test configuration.

The environment is set BEFORE any app import so the settings object
picks up the isolated test database and never auto-seeds.
"""

import os
import tempfile
from datetime import datetime, timedelta

_tmpdir = tempfile.mkdtemp(prefix="chargelens-test-")
os.environ.setdefault(
    "CHARGELENS_DATABASE_URL", f"sqlite:///{_tmpdir}/test.db")
os.environ.setdefault("CHARGELENS_AUTO_SEED", "false")

import pytest  # noqa: E402

from app.database import SessionLocal, engine, init_db  # noqa: E402
from app.models.entities import (  # noqa: E402
    AuditLog, Base, Chargeback, Customer, Delivery, Order, Transaction,
)


def make_case(db, case_id="CB-T-1", *, reason="product_not_received",
              delivery_status="delivered", confirmation="signed",
              device_seen=True, prev_chargebacks=0, amount=25_000.0,
              claim_delay=8.0, prev_orders=17, account_age=420.0):
    """Insert one fully-linked case and return it."""
    cust_id = f"CUST-{case_id}"
    if db.get(Customer, cust_id) is None:
        db.add(Customer(id=cust_id, account_age_days=account_age,
                        previous_orders=prev_orders,
                        previous_chargebacks=prev_chargebacks,
                        previous_returns=1, previous_failed_payments=0,
                        avg_order_value=5_000.0))
    now = datetime(2026, 8, 1, 12, 0)
    db.add(Transaction(
        id=f"TXN-{case_id}", customer_id=cust_id, amount=amount,
        currency="INR", payment_method="credit_card",
        payment_status="captured", device_seen_before=device_seen,
        device_shared_accounts=0, ip_geo_distance_km=10.0, txns_last_24h=1,
        ts=now))
    db.add(Order(
        id=f"ORD-{case_id}", transaction_id=f"TXN-{case_id}",
        customer_id=cust_id, product_name="Test Widget",
        product_category="electronics", quantity=1,
        shipping_city="Bangalore", billing_city="Bangalore",
        shipping_billing_match=True, order_ts=now))
    db.add(Delivery(
        order_id=f"ORD-{case_id}", carrier="BlueDart",
        tracking_number="TRK123456789" if delivery_status != "unknown" else None,
        has_tracking=delivery_status != "unknown",
        delivery_status=delivery_status,
        delivery_confirmation=confirmation,
        shipped_ts=now + timedelta(days=1),
        delivered_ts=(now + timedelta(days=3)
                      if delivery_status == "delivered" else None),
        days_to_deliver=2.0 if delivery_status == "delivered" else None))
    case = Chargeback(
        id=case_id, customer_id=cust_id, transaction_id=f"TXN-{case_id}",
        order_id=f"ORD-{case_id}", reason=reason,
        claim_description="I never received this product.",
        disputed_amount=amount,
        claim_ts=now + timedelta(days=3 + claim_delay),
        claim_delay_days=claim_delay, status="received")
    db.add(case)
    db.add(AuditLog(case_id=case_id, actor="system",
                    event_type="chargeback_received", detail={}))
    db.flush()
    return case


@pytest.fixture()
def db():
    Base.metadata.drop_all(engine)
    init_db()
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture()
def client(db):
    from fastapi.testclient import TestClient

    from app.main import app
    with TestClient(app) as c:
        yield c
