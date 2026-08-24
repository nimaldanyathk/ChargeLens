"""Per-case dispute economics: is this contest worth fighting?

A calibrated risk score is NOT a win probability. Winning representment
also requires evidence the issuer accepts, and industry outcomes are far
lower than model-style optimism:

- average representment win rate is ~20%, and merchants that fight win
  ~43.8% of the cases they choose to fight, but net dollar recovery is
  ~10.7% after second-cycle disputes and fees
  (chargebacks911.com/chargeback-stats/,
   chargebackgurus.com/blog/how-often-do-merchants-win-chargeback-disputes)
- true-fraud reason codes win ~17% vs ~44% for suspected friendly fraud
- ~23% of representment wins are challenged again in pre-arbitration

So the win probability used for money decisions is decomposed:

    p_win = min(p_cal, prior_cap[reason]) * evidence_factor

where p_cal is the calibrated probability the dispute is abusive,
prior_cap is a citable ceiling per reason category, and evidence_factor
in [0.30, 0.85] reflects how strong the merchant's evidence file is.

The contest decision is an expected-value comparison against accepting
(EV(accept) = 0 relative baseline; the disputed amount is already gone):

    EV(contest) = p_win * (1 - PRE_ARB_HAIRCUT) * amount - c_ops - c_fee

India-specific: the dispute fee in the Razorpay ecosystem (~Rs 500-2,000)
is charged for handling the chargeback and is NOT refunded on a win
(razorpay.com/blog/chargebacks/), so it is a sunk cost of contesting.

The break-even probability follows from EV = 0:

    p_break_even = (c_ops + c_fee) / ((1 - PRE_ARB_HAIRCUT) * amount)

which is the example-dependent analogue of Elkan's cost-sensitive
threshold t* = c_FP / (c_FP + c_FN) (Elkan 2001, "The Foundations of
Cost-Sensitive Learning"; Bahnsen et al.'s example-dependent
cost-sensitive fraud work): a Rs 50,000 dispute is worth contesting at a
much lower probability than a Rs 800 one.
"""

from __future__ import annotations

import os

# Cost assumptions (INR). Env-overridable so a merchant can put in their
# actual fee schedule; defaults sit inside the documented Rs 500-2,000
# ecosystem range.
C_FEE = float(os.environ.get("CHARGELENS_DISPUTE_FEE_INR", 1000))
C_OPS = float(os.environ.get("CHARGELENS_CONTEST_OPS_COST_INR", 300))

# 23% of representment wins advance to pre-arbitration
# (chargebackgurus.com); we assume roughly half of those are lost, so a
# win is worth (1 - 0.115) of the amount in expectation.
PRE_ARB_HAIRCUT = 0.115

# Ceilings on achievable win probability per reason category, anchored to
# industry outcomes (sources above). These bound the model: however
# confident the scorer is, the modeled win probability never exceeds what
# merchants actually achieve on that dispute type with strong evidence.
PRIOR_CAPS = {
    # item-not-received with delivery proof is the most winnable class
    "product_not_received": 0.50,
    # quality disputes hinge on subjective description evidence
    "product_not_as_described": 0.45,
    # "unauthorized" claims fight the issuer's fraud determination;
    # true-fraud codes win ~17%, CE3.0-qualified friendly fraud more
    "unauthorized_transaction": 0.30,
}
DEFAULT_CAP = 0.35

# Evidence-strength multipliers by the evidence engine's merchant_strength
EVIDENCE_FACTOR = {"strong": 0.85, "moderate": 0.55, "weak": 0.30}


def evaluate(amount: float, p_cal: float, evidence_strength: str,
             reason: str) -> dict:
    """Return the full economics of contesting one dispute."""
    cap = PRIOR_CAPS.get(reason, DEFAULT_CAP)
    e_factor = EVIDENCE_FACTOR.get(evidence_strength, 0.30)
    p_win = round(min(p_cal, cap) * e_factor, 4)

    effective_amount = (1 - PRE_ARB_HAIRCUT) * amount
    contest_cost = C_OPS + C_FEE
    expected_recovery = p_win * effective_amount
    ev_contest = expected_recovery - contest_cost
    break_even_p = (min(1.0, contest_cost / effective_amount)
                    if effective_amount > 0 else 1.0)

    return {
        "p_cal": round(p_cal, 4),
        "evidence_strength": evidence_strength,
        "evidence_factor": e_factor,
        "prior_cap": cap,
        "p_win": p_win,
        "expected_recovery_inr": round(expected_recovery, 2),
        "contest_cost_inr": round(contest_cost, 2),
        "ev_contest_inr": round(ev_contest, 2),
        "break_even_p_win": round(break_even_p, 4),
        "economic": ev_contest > 0,
        "assumptions": {
            "dispute_fee_inr": C_FEE,
            "ops_cost_inr": C_OPS,
            "pre_arb_haircut": PRE_ARB_HAIRCUT,
            "note": "dispute fee is not refunded on a win",
        },
    }
