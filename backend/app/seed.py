"""Database seeding for the demo.

Every seeded case comes from the HELD-OUT TEST split of the synthetic
dataset - i.e. records the model never saw during training, selection,
calibration, or threshold tuning - plus three scripted walkthrough cases
(CB-DEMO-1/2/3) matching the demo narrative. Ground-truth labels are NOT
loaded into the application database: the app operates blind, as it
would in production.

Run:  python -m app.seed
"""

from __future__ import annotations

import sys
import zlib
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from .config import settings
from .database import SessionLocal, engine, init_db
from .models.entities import (
    AuditLog, Base, Chargeback, Customer, Delivery, EvidenceItem, Order,
    RiskPrediction, Transaction,
)

CARRIERS = ["Delhivery", "BlueDart", "Ekart", "DTDC", "XpressBees"]
# product names per category, split into price tiers so the displayed
# product is plausible for the disputed amount: (budget <10k, mid, premium >40k)
PRODUCTS = {
    "electronics": (["JBL Earbuds", "Mi Power Bank", "Boat Headphones"],
                    ["Sony WH-1000XM5", "iPad Air", "Samsung Galaxy A55"],
                    ["MacBook Air", "iPhone 15", "Samsung 55'' TV", "Dell XPS 13"]),
    "fashion": (["Puma Sneakers", "Levi's T-shirt Pack"],
                ["Nike Air Max", "Levi's Denim Jacket", "Ray-Ban Aviators"],
                ["Titan Automatic Watch", "Coach Handbag"]),
    "home": (["Prestige Cooker Set", "Milton Flask Set"],
             ["Philips Air Fryer", "IKEA Desk"],
             ["Dyson V12 Vacuum", "LG Dishwasher"]),
    "beauty": (["Lakme Gift Set", "Nykaa Luxe Kit"],
               ["Foreo Luna", "Clinique Set"],
               ["Dyson Airwrap"]),
    "sports": (["Nivia Football Kit", "Yonex Racket"],
               ["Adidas Football Kit", "Garmin Band"],
               ["Decathlon E-Cycle"]),
    "books": (["Book Bundle (5)"], ["Collector's Box Set"],
              ["Signed First-Edition Set"]),
    "toys": (["Hot Wheels Track Set"], ["LEGO Creator Set"],
             ["LEGO Star Wars UCS Set"]),
}


def _product_for(rng, category: str, amount: float) -> str:
    budget, mid, premium = PRODUCTS[category]
    tier = budget if amount < 10_000 else (mid if amount < 40_000 else premium)
    return str(rng.choice(tier))

N_BACKGROUND = 160        # sampled from the test split
N_LEAVE_UNINVESTIGATED = 12


def _parse_ts(v) -> datetime | None:
    if v is None or (isinstance(v, float) and np.isnan(v)) or v == "":
        return None
    return datetime.fromisoformat(str(v))


def _mk_entities(db, row: dict, case_id: str) -> Chargeback:
    """Create the relational records for one raw case row."""
    # crc32 (not the salted built-in hash) keeps seeding deterministic
    rng = np.random.default_rng(zlib.crc32(case_id.encode()))
    cust_id = row["customer_id"]
    existing = db.get(Customer, cust_id)
    if existing is None:
        db.add(Customer(
            id=cust_id,
            account_age_days=float(row["account_age_days"]),
            previous_orders=int(row["previous_orders"]),
            previous_chargebacks=int(row["previous_chargebacks"]),
            previous_returns=int(row["previous_returns"]),
            previous_failed_payments=int(row["previous_failed_payments"]),
            avg_order_value=float(row["avg_order_value"])))
    else:
        # a repeat customer arrives with fresher history - keep it current
        existing.account_age_days = float(row["account_age_days"])
        existing.previous_orders = int(row["previous_orders"])
        existing.previous_chargebacks = int(row["previous_chargebacks"])
        existing.previous_returns = int(row["previous_returns"])
        existing.previous_failed_payments = int(
            row["previous_failed_payments"])
        existing.avg_order_value = float(row["avg_order_value"])

    txn = Transaction(
        id=row["transaction_id"], customer_id=cust_id,
        amount=float(row["disputed_amount"]), currency=row["currency"],
        payment_method=row["payment_method"],
        payment_status=row["payment_status"],
        device_seen_before=bool(int(row["device_seen_before"])),
        device_shared_accounts=int(row["device_shared_accounts"]),
        ip_geo_distance_km=float(row["ip_geo_distance_km"]),
        txns_last_24h=int(row["txns_last_24h"]),
        ts=_parse_ts(row.get("order_ts")))
    db.add(txn)

    category = row["product_category"]
    product = row.get("product_name") or _product_for(
        rng, category, float(row["disputed_amount"]))
    order = Order(
        id=row["order_id"], transaction_id=txn.id, customer_id=cust_id,
        product_name=product, product_category=category,
        quantity=int(row["quantity"]),
        shipping_city=row["shipping_city"], billing_city=row["billing_city"],
        shipping_billing_match=bool(int(row["shipping_billing_match"])),
        order_ts=_parse_ts(row.get("order_ts")))
    db.add(order)

    has_tracking = bool(int(row["has_tracking"]))
    days = row.get("days_to_deliver")
    days = None if days is None or (isinstance(days, float) and np.isnan(days)) else float(days)
    db.add(Delivery(
        order_id=order.id, carrier=str(rng.choice(CARRIERS)),
        tracking_number=(f"TRK{rng.integers(10**9, 10**10 - 1)}"
                         if has_tracking else None),
        has_tracking=has_tracking,
        delivery_status=row["delivery_status"],
        delivery_confirmation=row["delivery_confirmation"],
        shipped_ts=_parse_ts(row.get("shipped_ts")),
        delivered_ts=_parse_ts(row.get("delivered_ts")),
        days_to_deliver=days))

    # rail/network derive from the payment method; response deadlines
    # differ per rail (NPCI/UPI ~7 working days, card networks ~10)
    method = row["payment_method"]
    rail = {"upi": "upi", "netbanking": "netbanking",
            "wallet": "wallet"}.get(method, "card")
    if rail == "card":
        network = str(rng.choice(["visa", "mastercard", "rupay"],
                                 p=[0.5, 0.4, 0.1]))
    else:
        network = "npci" if rail == "upi" else rail
    claim_ts = _parse_ts(row.get("claim_ts"))
    respond_by = (claim_ts + timedelta(days=7 if rail == "upi" else 10)
                  if claim_ts else None)

    case = Chargeback(
        id=case_id, customer_id=cust_id, transaction_id=txn.id,
        order_id=order.id, reason=row["chargeback_reason"],
        claim_description=row["claim_description"],
        disputed_amount=float(row["disputed_amount"]),
        claim_ts=claim_ts,
        claim_delay_days=float(row["claim_delay_days"]),
        rail=rail, network=network, respond_by=respond_by,
        status="received")
    db.add(case)
    db.add(AuditLog(case_id=case_id, actor="system",
                    event_type="chargeback_received",
                    detail={"reason": row["chargeback_reason"],
                            "disputed_amount": float(row["disputed_amount"])}))
    db.flush()
    return case


def demo_rows() -> list[dict]:
    """Three scripted walkthrough cases (see the track's demo section)."""
    base_order = datetime(2026, 8, 3, 11, 20)
    common = {"currency": "INR", "payment_status": "captured"}
    return [
        # DEMO 1 - classic friendly fraud: delivered + signed, claims PNR
        {**common,
         "customer_id": "CUST-DEMO-8129", "transaction_id": "TXN-DEMO-18429",
         "order_id": "ORD-DEMO-82371",
         "chargeback_reason": "product_not_received",
         "claim_description": "I never received the product.",
         "disputed_amount": 89_000.0, "payment_method": "credit_card",
         "product_category": "electronics", "product_name": "MacBook Air",
         "quantity": 1, "shipping_city": "Bangalore",
         "billing_city": "Bangalore", "shipping_billing_match": 1,
         "account_age_days": 420.0, "previous_orders": 17,
         "previous_chargebacks": 1, "previous_returns": 2,
         "previous_failed_payments": 1, "avg_order_value": 6_500.0,
         "delivery_status": "delivered", "delivery_confirmation": "signed",
         "has_tracking": 1, "days_to_deliver": 3.0,
         "device_seen_before": 1, "device_shared_accounts": 0,
         "ip_geo_distance_km": 8.0, "txns_last_24h": 1,
         "order_ts": base_order.isoformat(),
         "shipped_ts": (base_order + timedelta(days=1)).isoformat(),
         "delivered_ts": (base_order + timedelta(days=4)).isoformat(),
         "claim_ts": (base_order + timedelta(days=12)).isoformat(),
         "claim_delay_days": 8.0},
        # DEMO 2 - legitimate: delivery failed, prompt claim, clean history
        {**common,
         "customer_id": "CUST-DEMO-2214", "transaction_id": "TXN-DEMO-77103",
         "order_id": "ORD-DEMO-55402",
         "chargeback_reason": "product_not_received",
         "claim_description": "The order shows shipped weeks ago but "
                              "nothing ever arrived.",
         "disputed_amount": 12_400.0, "payment_method": "upi",
         "product_category": "home", "product_name": "Philips Air Fryer",
         "quantity": 1, "shipping_city": "Pune", "billing_city": "Pune",
         "shipping_billing_match": 1,
         "account_age_days": 910.0, "previous_orders": 41,
         "previous_chargebacks": 0, "previous_returns": 1,
         "previous_failed_payments": 0, "avg_order_value": 3_800.0,
         "delivery_status": "failed", "delivery_confirmation": "none",
         "has_tracking": 1, "days_to_deliver": None,
         "device_seen_before": 1, "device_shared_accounts": 0,
         "ip_geo_distance_km": 4.0, "txns_last_24h": 1,
         "order_ts": base_order.isoformat(),
         "shipped_ts": (base_order + timedelta(days=1)).isoformat(),
         "delivered_ts": None,
         "claim_ts": (base_order + timedelta(days=8)).isoformat(),
         "claim_delay_days": 2.0},
        # DEMO 3 - ambiguous: marked delivered but unconfirmed, mixed history
        {**common,
         "customer_id": "CUST-DEMO-4471", "transaction_id": "TXN-DEMO-33988",
         "order_id": "ORD-DEMO-90114",
         "chargeback_reason": "product_not_received",
         "claim_description": "Item was not delivered to me.",
         "disputed_amount": 8_900.0, "payment_method": "debit_card",
         "product_category": "electronics",
         "product_name": "Sony WH-1000XM5", "quantity": 1,
         "shipping_city": "Chennai", "billing_city": "Chennai",
         "shipping_billing_match": 1,
         "account_age_days": 540.0, "previous_orders": 18,
         "previous_chargebacks": 0, "previous_returns": 1,
         "previous_failed_payments": 0, "avg_order_value": 4_900.0,
         "delivery_status": "delivered", "delivery_confirmation": "none",
         "has_tracking": 0, "days_to_deliver": 4.0,
         "device_seen_before": 1, "device_shared_accounts": 1,
         "ip_geo_distance_km": 60.0, "txns_last_24h": 2,
         "order_ts": base_order.isoformat(),
         "shipped_ts": (base_order + timedelta(days=1)).isoformat(),
         "delivered_ts": (base_order + timedelta(days=5)).isoformat(),
         "claim_ts": (base_order + timedelta(days=8)).isoformat(),
         "claim_delay_days": 3.0},
    ]


def seed(investigate_background: bool = True) -> dict:
    Base.metadata.drop_all(engine)
    init_db()
    df = pd.read_csv(settings.data_dir / "cases.csv")
    test_df = df[df["split"] == "test"].reset_index(drop=True)

    rng = np.random.default_rng(11)
    idx = rng.choice(len(test_df), size=min(N_BACKGROUND, len(test_df)),
                     replace=False)
    sample = test_df.iloc[idx]

    db = SessionLocal()
    created: list[str] = []
    try:
        for _, row in sample.iterrows():
            case = _mk_entities(db, row.to_dict(), row["case_id"])
            created.append(case.id)
        for row in demo_rows():
            n = len([c for c in created if c.startswith("CB-DEMO")]) + 1
            case = _mk_entities(db, row, f"CB-DEMO-{n}")
            created.append(case.id)
        db.commit()

        investigated = 0
        if investigate_background:
            from .agent.orchestrator import investigate
            # leave the demo cases and a demo queue uninvestigated
            to_skip = set(c for c in created if c.startswith("CB-DEMO"))
            background = [c for c in created if c not in to_skip]
            to_skip.update(background[:N_LEAVE_UNINVESTIGATED])
            for case_id in created:
                if case_id in to_skip:
                    continue
                case = db.get(Chargeback, case_id)
                investigate(db, case)
                investigated += 1
        db.commit()
        return {"cases": len(created), "investigated": investigated}
    finally:
        db.close()


if __name__ == "__main__":
    result = seed(investigate_background="--no-investigate" not in sys.argv)
    print(f"seeded {result['cases']} cases "
          f"({result['investigated']} auto-investigated)")
