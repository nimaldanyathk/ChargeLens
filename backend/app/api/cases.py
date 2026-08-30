"""Case endpoints: list, detail, investigate, human decision."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..agent.orchestrator import investigate
from ..database import get_db
from ..models.entities import AuditLog, Chargeback, RiskPrediction
from .serialize import case_detail, case_summary

router = APIRouter(prefix="/api/cases", tags=["cases"])

VALID_DECISIONS = {"approve", "reject", "escalate"}


class DecisionRequest(BaseModel):
    action: str = Field(pattern="^(approve|reject|escalate)$")
    note: str = ""


class CaseIntake(BaseModel):
    """A new chargeback case arriving from the payment provider."""

    customer_id: str = Field(min_length=1, max_length=32)
    chargeback_reason: Literal["product_not_received",
                               "unauthorized_transaction",
                               "product_not_as_described"]
    claim_description: str = Field(min_length=1, max_length=2000)
    disputed_amount: float = Field(gt=0, le=10_000_000)
    payment_method: Literal["credit_card", "debit_card", "upi",
                            "netbanking", "wallet"]
    product_category: Literal["electronics", "fashion", "home", "beauty",
                              "sports", "books", "toys"]
    product_name: str = Field(min_length=1, max_length=120)
    quantity: int = Field(ge=1, le=50)
    shipping_city: str = Field(min_length=1, max_length=60)
    billing_city: str = Field(min_length=1, max_length=60)
    account_age_days: float = Field(ge=0)
    previous_orders: int = Field(ge=0)
    previous_chargebacks: int = Field(ge=0)
    previous_returns: int = Field(ge=0)
    previous_failed_payments: int = Field(ge=0)
    avg_order_value: float = Field(gt=0)
    delivery_status: Literal["delivered", "in_transit", "failed",
                             "returned_to_sender", "unknown"]
    delivery_confirmation: Literal["signed", "otp", "photo", "none"]
    has_tracking: bool
    days_to_deliver: float | None = Field(default=None, ge=0)
    device_seen_before: bool
    device_shared_accounts: int = Field(ge=0)
    ip_geo_distance_km: float = Field(ge=0)
    txns_last_24h: int = Field(ge=0)
    claim_delay_days: float = Field(ge=0)


@router.post("", status_code=201)
def create_case(body: CaseIntake, db: Session = Depends(get_db)):
    """Register a chargeback case (no investigation happens until asked)."""
    from sqlalchemy.exc import IntegrityError

    from ..seed import _mk_entities

    # count() is only a starting guess; concurrent intakes can collide on
    # it, so commit inside a small retry loop instead of trusting the check
    n = db.query(Chargeback).count()
    for attempt in range(5):
        case_id = f"CB-N{20_000 + n}"
        if db.get(Chargeback, case_id) is not None:
            n += 1
            continue
        row = {
            **body.model_dump(),
            "transaction_id": f"TXN-N{20_000 + n}",
            "order_id": f"ORD-N{20_000 + n}",
            "currency": "INR",
            "payment_status": "captured",
            "shipping_billing_match": int(
                body.shipping_city.strip().lower()
                == body.billing_city.strip().lower()),
            "device_seen_before": int(body.device_seen_before),
            "has_tracking": int(body.has_tracking),
            "order_ts": None, "shipped_ts": None, "delivered_ts": None,
            "claim_ts": datetime.now(timezone.utc)
            .isoformat(timespec="seconds"),
        }
        try:
            case = _mk_entities(db, row, case_id)
            db.commit()
            return case_detail(db, case)
        except IntegrityError:
            db.rollback()
            n += 1
    raise HTTPException(503, "could not allocate a case id; retry")


@router.get("")
def list_cases(
    db: Session = Depends(get_db),
    status: str | None = Query(default=None),
    band: str | None = Query(default=None),
    q: str | None = Query(default=None),
    limit: int = Query(default=200, le=500),
):
    query = db.query(Chargeback)
    if status:
        query = query.filter(Chargeback.status == status)
    if q:
        escaped = (q.replace("\\", "\\\\")
                   .replace("%", "\\%").replace("_", "\\_"))
        like = f"%{escaped}%"
        query = query.filter(
            Chargeback.id.like(like, escape="\\")
            | Chargeback.customer_id.like(like, escape="\\"))
    if band:
        query = (query.join(RiskPrediction,
                            RiskPrediction.case_id == Chargeback.id)
                 .filter(RiskPrediction.band == band))
    cases = (query.order_by(Chargeback.created_at.desc())
             .limit(limit).all())
    return {"cases": [case_summary(c) for c in cases]}


@router.get("/{case_id}")
def get_case(case_id: str, db: Session = Depends(get_db)):
    case = db.get(Chargeback, case_id)
    if case is None:
        raise HTTPException(404, f"case {case_id} not found")
    return case_detail(db, case)


@router.post("/{case_id}/investigate")
def investigate_case(case_id: str, db: Session = Depends(get_db)):
    case = db.get(Chargeback, case_id)
    if case is None:
        raise HTTPException(404, f"case {case_id} not found")
    if case.status in ("approved", "rejected"):
        raise HTTPException(409, "case is already decided")
    investigate(db, case)
    return case_detail(db, case)


@router.get("/{case_id}/dossier.pdf")
def dossier_pdf(case_id: str, db: Session = Depends(get_db)):
    """One-click evidence dossier PDF for issuer review."""
    from fastapi.responses import Response

    from ..evidence.dossier import build_dossier

    case = db.get(Chargeback, case_id)
    if case is None:
        raise HTTPException(404, f"case {case_id} not found")
    detail = case_detail(db, case)
    pdf = build_dossier(case, detail)
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition":
                 f'inline; filename="dossier-{case_id}.pdf"'})


@router.get("/{case_id}/contest-payload")
def contest_payload(case_id: str, db: Session = Depends(get_db)):
    """Contest-ready payload matching Razorpay's real
    PATCH /v1/disputes/:id/contest schema (action stays 'draft' - a
    human submit is a separate, explicit step)."""
    from ..integrations.razorpay import build_contest_payload, keys_configured

    case = db.get(Chargeback, case_id)
    if case is None:
        raise HTTPException(404, f"case {case_id} not found")
    if case.recommendation != "contest":
        raise HTTPException(
            409, "contest payload is only built for cases the agent "
                 "recommends contesting")
    payload = build_contest_payload(case, case.evidence)
    return {
        "dispute_id": case.external_ref or f"disp_demo_{case.id}",
        "endpoint": f"PATCH /v1/disputes/"
                    f"{case.external_ref or 'disp_demo_' + case.id}/contest",
        "mode": "connected" if keys_configured() else "dry_run",
        "payload": payload,
    }


@router.post("/{case_id}/decision")
def decide_case(case_id: str, body: DecisionRequest,
                db: Session = Depends(get_db)):
    case = db.get(Chargeback, case_id)
    if case is None:
        raise HTTPException(404, f"case {case_id} not found")
    if case.status != "awaiting_review":
        raise HTTPException(
            409, "case must be investigated and awaiting review before a "
                 "decision can be recorded")

    case.human_decision = body.action
    case.human_decision_note = body.note
    case.human_decision_ts = datetime.now(timezone.utc)
    case.status = {"approve": "approved", "reject": "rejected",
                   "escalate": "escalated"}[body.action]
    db.add(AuditLog(case_id=case.id, actor="merchant",
                    event_type="human_decision",
                    detail={"action": body.action, "note": body.note,
                            "recommendation_was": case.recommendation}))
    final = _final_action(case)
    db.add(AuditLog(case_id=case.id, actor="system",
                    event_type="final_action", detail={"action": final}))
    db.commit()
    return case_detail(db, case)


def _final_action(case: Chargeback) -> str:
    if case.status == "escalated":
        return "escalated to senior review"
    if case.status == "rejected":
        return "recommendation rejected; case returned to manual handling"
    # approved: what was approved depends on the recommendation
    return {
        "contest": "evidence package submitted for representment",
        "accept": "dispute accepted; refund initiated by merchant",
        "review": "manual review outcome recorded",
    }.get(case.recommendation or "review", "recorded")
