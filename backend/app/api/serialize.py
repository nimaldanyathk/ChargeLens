"""Row -> JSON serializers shared by the case routes."""

from __future__ import annotations

from datetime import timezone

from sqlalchemy.orm import Session

from ..models.entities import (
    Chargeback, Customer, Delivery, Order, Transaction,
)


def _ts(dt) -> str | None:
    """Serialize as explicit UTC. SQLite returns naive datetimes; all of
    ours are stored in UTC, so stamp the offset instead of letting the
    client guess (a bare ISO string parses as local time in JS)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat(timespec="seconds")


def case_summary(case: Chargeback) -> dict:
    pred = case.prediction
    return {
        "case_id": case.id,
        "customer_id": case.customer_id,
        "reason": case.reason,
        "disputed_amount": case.disputed_amount,
        "claim_ts": _ts(case.claim_ts),
        "status": case.status,
        "recommendation": case.recommendation,
        "risk_score": pred.risk_score if pred else None,
        "band": pred.band if pred else None,
        "rail": case.rail,
        "network": case.network,
        "respond_by": _ts(case.respond_by),
        "external_ref": case.external_ref,
        "external_status": case.external_status,
    }


def case_detail(db: Session, case: Chargeback) -> dict:
    txn = db.get(Transaction, case.transaction_id)
    order = db.get(Order, case.order_id)
    delivery = (db.query(Delivery)
                .filter(Delivery.order_id == case.order_id).first())
    customer = db.get(Customer, case.customer_id)
    pred = case.prediction
    return {
        **case_summary(case),
        "claim_description": case.claim_description,
        "claim_delay_days": case.claim_delay_days,
        "recommendation_reason": case.recommendation_reason,
        "generated_response": case.generated_response,
        "response_generator": case.response_generator,
        "human_decision": case.human_decision,
        "human_decision_note": case.human_decision_note,
        "human_decision_ts": _ts(case.human_decision_ts),
        "transaction": {
            "id": txn.id, "amount": txn.amount, "currency": txn.currency,
            "payment_method": txn.payment_method,
            "payment_status": txn.payment_status,
            "device_seen_before": txn.device_seen_before,
            "device_shared_accounts": txn.device_shared_accounts,
            "ip_geo_distance_km": txn.ip_geo_distance_km,
            "txns_last_24h": txn.txns_last_24h,
            "ts": _ts(txn.ts),
        } if txn else None,
        "order": {
            "id": order.id, "product_name": order.product_name,
            "product_category": order.product_category,
            "quantity": order.quantity,
            "shipping_city": order.shipping_city,
            "billing_city": order.billing_city,
            "shipping_billing_match": order.shipping_billing_match,
            "order_ts": _ts(order.order_ts),
        } if order else None,
        "delivery": {
            "carrier": delivery.carrier,
            "tracking_number": delivery.tracking_number,
            "has_tracking": delivery.has_tracking,
            "delivery_status": delivery.delivery_status,
            "delivery_confirmation": delivery.delivery_confirmation,
            "shipped_ts": _ts(delivery.shipped_ts),
            "delivered_ts": _ts(delivery.delivered_ts),
        } if delivery else None,
        "customer": {
            "id": customer.id,
            "account_age_days": customer.account_age_days,
            "previous_orders": customer.previous_orders,
            "previous_chargebacks": customer.previous_chargebacks,
            "previous_returns": customer.previous_returns,
            "previous_failed_payments": customer.previous_failed_payments,
            "avg_order_value": customer.avg_order_value,
        } if customer else None,
        "risk": {
            "risk_score": pred.risk_score,
            "band": pred.band,
            "model_version": pred.model_version,
            "top_factors": pred.top_factors,
            "scored_at": _ts(pred.created_at),
            "economics": pred.economics,
        } if pred else None,
        "evidence": [{
            "key": e.key, "statement": e.statement, "value": e.value,
            "source": f"{e.source_table}/{e.source_id}#{e.source_field}",
            "supports": e.supports, "strength": e.strength,
        } for e in case.evidence],
        "audit": [{
            "ts": _ts(a.ts), "actor": a.actor,
            "event_type": a.event_type, "detail": a.detail,
        } for a in case.audit],
    }
