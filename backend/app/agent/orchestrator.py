"""The investigation agent.

A bounded orchestrator: it works through read-only tools registered in
TOOLS, records every step in the audit trail as it happens, and produces
a recommendation that always parks in `awaiting_review` for a human. The
registry is the single dispatch path - `run_tool` refuses any name that
is not in ALLOWED_TOOLS, so the forbidden actions in policy.py are not
just discouraged, they are unreachable.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from ..decision import economics
from ..evidence import ce3 as ce3_mod
from ..evidence.engine import collect_evidence, merchant_strength
from ..llm.generator import generate_response_text
from ..models.entities import (
    AuditLog, Chargeback, Customer, Delivery, EvidenceItem, Order,
    RiskPrediction, Transaction,
)
from ..risk.scorer import case_to_raw_row, get_scorer
from .policy import ALLOWED_TOOLS, assert_tool_allowed, recommend


def _log(db: Session, case_id: str, actor: str, event_type: str,
         detail: dict) -> None:
    db.add(AuditLog(case_id=case_id, actor=actor, event_type=event_type,
                    detail=detail))
    db.flush()


# ---- bounded read-only tools ------------------------------------------

def get_transaction(db: Session, case: Chargeback) -> Transaction:
    return db.get(Transaction, case.transaction_id)


def get_order(db: Session, case: Chargeback) -> Order:
    return db.get(Order, case.order_id)


def get_delivery_status(db: Session, case: Chargeback) -> Delivery | None:
    return (db.query(Delivery)
            .filter(Delivery.order_id == case.order_id).first())


def get_customer_history(db: Session, case: Chargeback) -> Customer:
    return db.get(Customer, case.customer_id)


def get_previous_claims(db: Session, case: Chargeback) -> list[Chargeback]:
    return (db.query(Chargeback)
            .filter(Chargeback.customer_id == case.customer_id,
                    Chargeback.id != case.id).all())


TOOLS = {
    "get_transaction": get_transaction,
    "get_order": get_order,
    "get_delivery_status": get_delivery_status,
    "get_customer_history": get_customer_history,
    "get_previous_claims": get_previous_claims,
}
assert set(TOOLS) <= ALLOWED_TOOLS


def run_tool(db: Session, case: Chargeback, name: str):
    """Sole dispatch path for agent tools - enforces the boundary."""
    assert_tool_allowed(name)
    result = TOOLS[name](db, case)
    _log(db, case.id, "agent", "tool_call", {
        "tool": name,
        "result_summary": _summarize(result),
    })
    return result


def _summarize(result) -> str:
    if result is None:
        return "no record found"
    if isinstance(result, list):
        return f"{len(result)} record(s)"
    return f"{result.__class__.__name__} {getattr(result, 'id', '')}".strip()


# ---- the investigation ---------------------------------------------------

def investigate(db: Session, case: Chargeback) -> Chargeback:
    scorer = get_scorer()
    case.status = "investigating"
    if case.human_decision is not None:
        # a re-investigation (e.g. of an escalated case) supersedes the
        # previous decision - clear it explicitly and say so in the audit
        _log(db, case.id, "system", "previous_decision_cleared",
             {"was": case.human_decision, "note": case.human_decision_note})
        case.human_decision = None
        case.human_decision_note = None
        case.human_decision_ts = None
    _log(db, case.id, "system", "investigation_started",
         {"reason": case.reason, "disputed_amount": case.disputed_amount})

    txn = run_tool(db, case, "get_transaction")
    order = run_tool(db, case, "get_order")
    delivery = run_tool(db, case, "get_delivery_status")
    customer = run_tool(db, case, "get_customer_history")
    prior_claims = run_tool(db, case, "get_previous_claims")

    # calculate_risk
    assert_tool_allowed("calculate_risk")
    raw = case_to_raw_row(case, customer, txn, order, delivery)
    result = scorer.score(raw)
    _log(db, case.id, "agent", "risk_scored", {
        "tool": "calculate_risk",
        "risk_score": result["risk_score"], "band": result["band"],
        "model_version": result["model_version"],
        "model_name": result["model_name"],
    })

    # collect_evidence
    assert_tool_allowed("collect_evidence")
    evidence = collect_evidence(case, customer, txn, order, delivery)
    db.query(EvidenceItem).filter(EvidenceItem.case_id == case.id).delete()
    for item in evidence:
        db.add(EvidenceItem(case_id=case.id, **item.dict()))
    _log(db, case.id, "agent", "evidence_collected", {
        "tool": "collect_evidence",
        "items": len(evidence),
        "merchant_supporting": sum(1 for e in evidence
                                   if e.supports == "merchant"),
        "customer_supporting": sum(1 for e in evidence
                                   if e.supports == "customer"),
        "missing": sum(1 for e in evidence if e.supports == "missing"),
        "prior_claims_checked": len(prior_claims),
    })

    # dispute economics: is this contest worth fighting at this amount?
    econ = economics.evaluate(
        case.disputed_amount, result["risk_score"],
        merchant_strength(evidence), case.reason)

    # Visa CE3.0 eligibility (fraud disputes only) - a rules check that
    # can shift liability to the issuer
    ce3_result = ce3_mod.evaluate(case, customer, txn).dict()

    db.query(RiskPrediction).filter(
        RiskPrediction.case_id == case.id).delete()
    db.add(RiskPrediction(
        case_id=case.id, model_version=result["model_version"],
        risk_score=result["risk_score"], band=result["band"],
        top_factors=result["top_factors"], economics=econ, ce3=ce3_result))
    _log(db, case.id, "agent", "economics_computed", {
        "p_win": econ["p_win"],
        "ev_contest_inr": econ["ev_contest_inr"],
        "break_even_p_win": econ["break_even_p_win"],
        "economic": econ["economic"],
    })
    if ce3_result["status"] != "not_applicable":
        _log(db, case.id, "agent", "ce3_evaluated", {
            "status": ce3_result["status"],
            "matched_main": ce3_result["matched_main"],
            "matched_secondary": ce3_result["matched_secondary"],
        })

    # recommendation (policy layer, evidence- and economics-gated)
    recommendation, reason = recommend(
        result["band"], result["risk_score"], evidence, econ)
    case.recommendation = recommendation
    case.recommendation_reason = reason
    _log(db, case.id, "agent", "recommendation", {
        "recommendation": recommendation, "reason": reason,
    })

    # generate_response
    assert_tool_allowed("generate_response")
    text, generator = generate_response_text(
        case, txn, order, delivery, customer, evidence,
        result, recommendation)
    case.generated_response = text
    case.response_generator = generator
    _log(db, case.id, "agent", "response_generated",
         {"tool": "generate_response", "generator": generator,
          "chars": len(text)})

    case.status = "awaiting_review"
    _log(db, case.id, "system", "awaiting_human_review",
         {"note": "no action is taken until the merchant decides"})
    db.commit()
    return case
