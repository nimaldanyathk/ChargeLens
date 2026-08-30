"""Dashboard aggregates."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.entities import Chargeback, RiskPrediction

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

OPEN_STATUSES = ("received", "investigating", "awaiting_review", "escalated")


@router.get("")
def dashboard(db: Session = Depends(get_db)):
    total = db.query(func.count(Chargeback.id)).scalar() or 0
    open_q = db.query(Chargeback).filter(Chargeback.status.in_(OPEN_STATUSES))
    open_count = open_q.count()

    band_counts = dict(
        db.query(RiskPrediction.band, func.count(RiskPrediction.id))
        .join(Chargeback, Chargeback.id == RiskPrediction.case_id)
        .filter(Chargeback.status.in_(OPEN_STATUSES))
        .group_by(RiskPrediction.band).all())

    exposure = (db.query(func.coalesce(func.sum(Chargeback.disputed_amount), 0.0))
                .filter(Chargeback.status.in_(OPEN_STATUSES)).scalar())

    awaiting_review = (db.query(func.count(Chargeback.id))
                       .filter(Chargeback.status == "awaiting_review")
                       .scalar() or 0)
    uninvestigated = (db.query(func.count(Chargeback.id))
                      .filter(Chargeback.status == "received").scalar() or 0)

    # Expected recovery from every OPEN case the agent recommends
    # contesting - the live opportunity in the queue, not just cases a
    # human has already actioned. Uses each case's own economics
    # (per-case win probability x amount) rather than a flat rate.
    contest_preds = (
        db.query(RiskPrediction)
        .join(Chargeback, Chargeback.id == RiskPrediction.case_id)
        .filter(Chargeback.status.in_(OPEN_STATUSES),
                Chargeback.recommendation == "contest").all())
    expected_recovery = 0.0
    expected_ev = 0.0
    contestable = 0
    for p in contest_preds:
        econ = p.economics or {}
        expected_recovery += float(econ.get("expected_recovery_inr", 0.0))
        expected_ev += float(econ.get("ev_contest_inr", 0.0))
        contestable += 1

    return {
        "total_cases": total,
        "open_cases": open_count,
        "high_risk": band_counts.get("high", 0),
        "review_band": band_counts.get("review", 0),
        "low_risk": band_counts.get("low", 0),
        "awaiting_review": awaiting_review,
        "uninvestigated": uninvestigated,
        "open_exposure_inr": round(float(exposure or 0.0), 2),
        "estimated_recovery_inr": round(expected_recovery, 2),
        "estimated_net_ev_inr": round(expected_ev, 2),
        "contestable_cases": contestable,
        "recovery_note": f"expected value across {contestable} open "
                         f"case(s) the agent recommends contesting, using "
                         f"each case's own win probability and amount",
    }
