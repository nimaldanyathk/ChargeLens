"""Razorpay dispute webhooks.

Handles the six real dispute events (payment.dispute.created / won /
lost / closed / under_review / action_required) with signature
verification over the raw body. Without CHARGELENS_RZP_WEBHOOK_SECRET
set the endpoint refuses everything - unsigned intake is not a mode.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from ..database import get_db
from ..integrations.razorpay import (
    map_dispute_payload, verify_webhook_signature,
)
from ..models.entities import AuditLog, Chargeback

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])

DISPUTE_EVENTS = {
    "payment.dispute.created", "payment.dispute.won",
    "payment.dispute.lost", "payment.dispute.closed",
    "payment.dispute.under_review", "payment.dispute.action_required",
}


@router.post("/razorpay")
async def razorpay_webhook(
    request: Request,
    db: Session = Depends(get_db),
    x_razorpay_signature: str = Header(default=""),
):
    secret = os.environ.get("CHARGELENS_RZP_WEBHOOK_SECRET", "")
    if not secret:
        raise HTTPException(
            503, "webhook secret not configured "
                 "(set CHARGELENS_RZP_WEBHOOK_SECRET)")

    raw = await request.body()
    if not verify_webhook_signature(raw, x_razorpay_signature, secret):
        raise HTTPException(401, "invalid webhook signature")

    event = await request.json()
    name = event.get("event", "")
    if name not in DISPUTE_EVENTS:
        return {"status": "ignored", "event": name}

    mapped = map_dispute_payload(event)
    ref = mapped["meta"]["external_ref"]
    existing = (db.query(Chargeback)
                .filter(Chargeback.external_ref == ref).first())

    if name in ("payment.dispute.created",
                "payment.dispute.action_required") and existing is None:
        from ..seed import _mk_entities
        case_id = f"CB-RZP-{ref.removeprefix('disp_')}"
        if db.get(Chargeback, case_id) is not None:
            return {"status": "duplicate", "case_id": case_id}
        row = mapped["row"]
        row["claim_ts"] = datetime.now(timezone.utc).isoformat(
            timespec="seconds")
        case = _mk_entities(db, row, case_id)
        case.external_ref = ref
        case.external_status = mapped["meta"]["status"]
        if mapped["meta"]["respond_by_unix"]:
            case.respond_by = datetime.fromtimestamp(
                mapped["meta"]["respond_by_unix"], tz=timezone.utc)
        db.add(AuditLog(
            case_id=case.id, actor="system",
            event_type="razorpay_dispute_received",
            detail={"event": name, "dispute_id": ref,
                    "phase": mapped["meta"]["phase"],
                    "reason_code": mapped["meta"]["reason_code"],
                    "note": "order/delivery/history fields pending OMS "
                            "enrichment"}))
        db.commit()
        return {"status": "created", "case_id": case.id}

    if existing is not None:
        outcome = name.rsplit(".", 1)[-1]
        existing.external_status = outcome
        db.add(AuditLog(
            case_id=existing.id, actor="system",
            event_type="razorpay_dispute_update",
            detail={"event": name, "dispute_id": ref,
                    "external_status": outcome}))
        db.commit()
        return {"status": "updated", "case_id": existing.id,
                "external_status": outcome}

    return {"status": "unmatched", "dispute_id": ref}
