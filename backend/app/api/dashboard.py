"""Dashboard aggregates."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from riskmodel.costs import WIN_RATE

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

    # estimated recovery from approved contests (expected value, win-rate
    # discounted - labelled as an estimate in the UI)
    approved_contest_amount = (
        db.query(func.coalesce(func.sum(Chargeback.disputed_amount), 0.0))
        .filter(Chargeback.status == "approved",
                Chargeback.recommendation == "contest").scalar())

    return {
        "total_cases": total,
        "open_cases": open_count,
        "high_risk": band_counts.get("high", 0),
        "review_band": band_counts.get("review", 0),
        "low_risk": band_counts.get("low", 0),
        "awaiting_review": awaiting_review,
        "uninvestigated": uninvestigated,
        "open_exposure_inr": round(float(exposure or 0.0), 2),
        "estimated_recovery_inr": round(
            float(approved_contest_amount or 0.0) * WIN_RATE, 2),
        "recovery_note": f"expected value of approved contests at "
                         f"{WIN_RATE:.0%} representment win rate",
    }
