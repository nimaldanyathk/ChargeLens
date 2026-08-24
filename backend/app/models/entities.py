"""Relational schema.

Tables mirror the track's suggested design: customers, transactions,
orders, deliveries, chargebacks, risk_predictions, evidence, audit_logs.
The application never stores or sees ground-truth labels - it operates
blind, the way it would in production.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    account_age_days: Mapped[float] = mapped_column(Float)
    previous_orders: Mapped[int] = mapped_column(Integer)
    previous_chargebacks: Mapped[int] = mapped_column(Integer)
    previous_returns: Mapped[int] = mapped_column(Integer)
    previous_failed_payments: Mapped[int] = mapped_column(Integer)
    avg_order_value: Mapped[float] = mapped_column(Float)

    chargebacks: Mapped[list["Chargeback"]] = relationship(
        back_populates="customer")


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"),
                                             index=True)
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8), default="INR")
    payment_method: Mapped[str] = mapped_column(String(24))
    payment_status: Mapped[str] = mapped_column(String(24))
    device_seen_before: Mapped[bool] = mapped_column(Boolean)
    device_shared_accounts: Mapped[int] = mapped_column(Integer)
    ip_geo_distance_km: Mapped[float] = mapped_column(Float)
    txns_last_24h: Mapped[int] = mapped_column(Integer)
    ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    transaction_id: Mapped[str] = mapped_column(ForeignKey("transactions.id"))
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"))
    product_name: Mapped[str] = mapped_column(String(120))
    product_category: Mapped[str] = mapped_column(String(40))
    quantity: Mapped[int] = mapped_column(Integer)
    shipping_city: Mapped[str] = mapped_column(String(60))
    billing_city: Mapped[str] = mapped_column(String(60))
    shipping_billing_match: Mapped[bool] = mapped_column(Boolean)
    order_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Delivery(Base):
    __tablename__ = "deliveries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True,
                                    autoincrement=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), index=True)
    carrier: Mapped[str] = mapped_column(String(40))
    tracking_number: Mapped[str | None] = mapped_column(String(40),
                                                        nullable=True)
    has_tracking: Mapped[bool] = mapped_column(Boolean)
    delivery_status: Mapped[str] = mapped_column(String(24))
    delivery_confirmation: Mapped[str] = mapped_column(String(16))
    shipped_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    delivered_ts: Mapped[datetime | None] = mapped_column(DateTime,
                                                          nullable=True)
    days_to_deliver: Mapped[float | None] = mapped_column(Float, nullable=True)


class Chargeback(Base):
    __tablename__ = "chargebacks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"),
                                             index=True)
    transaction_id: Mapped[str] = mapped_column(ForeignKey("transactions.id"))
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"))
    reason: Mapped[str] = mapped_column(String(40))
    claim_description: Mapped[str] = mapped_column(Text)
    disputed_amount: Mapped[float] = mapped_column(Float)
    claim_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    claim_delay_days: Mapped[float | None] = mapped_column(Float,
                                                           nullable=True)
    # payment rail context: UPI disputes follow NPCI URCS semantics
    # (7-working-day merchant response), card disputes follow the
    # network representment track - deadlines and language differ
    rail: Mapped[str] = mapped_column(String(12), default="card")
    network: Mapped[str | None] = mapped_column(String(12), nullable=True)
    respond_by: Mapped[datetime | None] = mapped_column(DateTime,
                                                        nullable=True)
    # set when the case came in through the Razorpay Disputes webhook
    external_ref: Mapped[str | None] = mapped_column(String(40),
                                                     nullable=True,
                                                     index=True)
    external_status: Mapped[str | None] = mapped_column(String(24),
                                                        nullable=True)

    # workflow state
    status: Mapped[str] = mapped_column(String(24), default="received",
                                        index=True)
    recommendation: Mapped[str | None] = mapped_column(String(24),
                                                       nullable=True)
    recommendation_reason: Mapped[str | None] = mapped_column(Text,
                                                              nullable=True)
    generated_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_generator: Mapped[str | None] = mapped_column(String(24),
                                                           nullable=True)
    human_decision: Mapped[str | None] = mapped_column(String(24),
                                                       nullable=True)
    human_decision_note: Mapped[str | None] = mapped_column(Text,
                                                            nullable=True)
    human_decision_ts: Mapped[datetime | None] = mapped_column(DateTime,
                                                               nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    customer: Mapped[Customer] = relationship(back_populates="chargebacks")
    prediction: Mapped["RiskPrediction | None"] = relationship(
        back_populates="case", uselist=False)
    evidence: Mapped[list["EvidenceItem"]] = relationship(
        back_populates="case", order_by="EvidenceItem.id")
    audit: Mapped[list["AuditLog"]] = relationship(
        back_populates="case", order_by="AuditLog.id")


class RiskPrediction(Base):
    __tablename__ = "risk_predictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True,
                                    autoincrement=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("chargebacks.id"),
                                         index=True)
    model_version: Mapped[str] = mapped_column(String(16))
    risk_score: Mapped[float] = mapped_column(Float)
    band: Mapped[str] = mapped_column(String(12))
    top_factors: Mapped[list] = mapped_column(JSON)
    economics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    case: Mapped[Chargeback] = relationship(back_populates="prediction")


class EvidenceItem(Base):
    __tablename__ = "evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True,
                                    autoincrement=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("chargebacks.id"),
                                         index=True)
    key: Mapped[str] = mapped_column(String(48))
    statement: Mapped[str] = mapped_column(Text)
    value: Mapped[str] = mapped_column(String(200))
    source_table: Mapped[str] = mapped_column(String(32))
    source_id: Mapped[str] = mapped_column(String(40))
    source_field: Mapped[str] = mapped_column(String(48))
    supports: Mapped[str] = mapped_column(String(12))   # merchant|customer|neutral|missing
    strength: Mapped[str] = mapped_column(String(12))   # strong|moderate|weak
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    case: Mapped[Chargeback] = relationship(back_populates="evidence")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True,
                                    autoincrement=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("chargebacks.id"),
                                         index=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    actor: Mapped[str] = mapped_column(String(24))       # system|agent|merchant
    event_type: Mapped[str] = mapped_column(String(40))
    detail: Mapped[dict] = mapped_column(JSON)

    case: Mapped[Chargeback] = relationship(back_populates="audit")
