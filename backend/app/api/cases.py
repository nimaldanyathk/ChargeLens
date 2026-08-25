"""Case endpoints: list, detail, investigate, human decision."""

from __future__ import annotations

from datetime import datetime, timezone

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
        like = f"%{q}%"
        query = query.filter(
            Chargeback.id.like(like) | Chargeback.customer_id.like(like))
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
