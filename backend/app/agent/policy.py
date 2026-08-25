"""Decision policy and agent guardrails.

The recommendation is NOT the raw model output. The model supplies the
calibrated risk score and band; the policy layer gates it on evidence so
the system never recommends fighting a customer without something to
fight with. This is what keeps the verifier honest rather than
merchant-biased:

  band=high  + strong merchant evidence   -> CONTEST
  band=high  + weak merchant evidence     -> REVIEW ("insufficient
                                             merchant evidence")
  band=review                             -> REVIEW
  band=low                                -> ACCEPT (likely legitimate)

Every recommendation is advisory: the case always waits for a human
merchant decision (approve / reject / escalate) before any final action.
"""

from __future__ import annotations

from ..evidence.engine import Evidence, merchant_strength, missing_evidence


class GuardrailViolation(RuntimeError):
    pass


# The complete set of operations the agent may perform. Anything else -
# refunds, bans, record edits, external calls - is structurally
# impossible: the registry is the only dispatch path.
ALLOWED_TOOLS = frozenset({
    "get_transaction",
    "get_order",
    "get_delivery_status",
    "get_customer_history",
    "get_previous_claims",
    "calculate_risk",
    "collect_evidence",
    "generate_response",
})

# Documented for tests and the audit page: these are refused by name.
FORBIDDEN_ACTIONS = frozenset({
    "issue_refund", "move_money", "ban_customer", "delete_customer",
    "modify_transaction", "modify_evidence", "submit_external_request",
})


def assert_tool_allowed(name: str) -> None:
    if name not in ALLOWED_TOOLS:
        raise GuardrailViolation(
            f"tool '{name}' is outside the agent's permission boundary")


def recommend(band: str, risk_score: float,
              evidence: list[Evidence]) -> tuple[str, str]:
    """Return (recommendation, reason)."""
    strength = merchant_strength(evidence)
    missing = missing_evidence(evidence)

    if band == "high":
        if strength == "strong":
            return ("contest",
                    f"Risk score {risk_score:.0%} with strong contradicting "
                    f"evidence on file. The dispute pattern is consistent "
                    f"with an illegitimate claim and the merchant holds the "
                    f"evidence needed to represent the case.")
        reason = (f"The model scores this claim high risk "
                  f"({risk_score:.0%}), but the merchant's evidence is "
                  f"{strength}: contesting without decisive proof is likely "
                  f"to fail and to harm a possibly honest customer.")
        if missing:
            reason += " Missing: " + "; ".join(missing)
        return ("review", reason)

    if band == "low":
        return ("accept",
                f"Risk score {risk_score:.0%}. The evidence is consistent "
                f"with a legitimate dispute; accepting avoids fighting an "
                f"honest customer.")

    reason = (f"Risk score {risk_score:.0%} falls in the uncertainty band - "
              f"the evidence does not clearly favour either side.")
    if missing:
        reason += " Missing: " + "; ".join(missing)
    return ("review", reason)
