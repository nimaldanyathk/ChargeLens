"""Business cost model for threshold selection and evaluation.

All figures are in INR and are stated assumptions for the synthetic
merchant, not measurements. They are deliberately conservative and are
surfaced in the UI so a judge can audit them.

Decision the threshold controls: CONTEST the dispute (predict abusive)
vs ACCEPT it (predict legitimate).

False positive  = contesting a LEGITIMATE dispute.
    The merchant almost always loses the representment, so the disputed
    amount is lost anyway, and on top of that the merchant pays staff
    time to assemble the case and burns customer goodwill (a wrongly
    accused honest customer churns). We charge:
        FP cost = OPS_COST + GOODWILL_COST
    (the disputed amount itself is lost under either action, so it is
    excluded from the *marginal* FP cost).

False negative  = accepting an ABUSIVE dispute.
    The merchant refunds a claim it could have won: the disputed amount
    walks away, plus the scheme's chargeback fee.
        FN cost = disputed_amount * WIN_RATE + CHARGEBACK_FEE
    WIN_RATE discounts for the fact that even a contested abusive
    dispute is not always won.

True positive   = contesting an abusive dispute: costs OPS_COST but
    recovers disputed_amount * WIN_RATE, i.e. a net saving relative to
    accepting it.
True negative   = accepting a legitimate dispute: the correct action,
    zero marginal cost.
"""

from __future__ import annotations

import numpy as np

OPS_COST = 350.0          # staff time to assemble + submit one representment
GOODWILL_COST = 900.0     # expected lifetime-value loss from fighting an honest customer
CHARGEBACK_FEE = 500.0    # scheme/acquirer fee on a lost dispute
WIN_RATE = 0.65           # probability a contested abusive dispute is won


def expected_cost(y_true: np.ndarray, y_pred: np.ndarray,
                  amounts: np.ndarray) -> float:
    """Total marginal cost (INR) of a decision vector vs ground truth."""
    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)
    amounts = np.asarray(amounts, dtype=float)

    fp = (y_pred == 1) & (y_true == 0)
    fn = (y_pred == 0) & (y_true == 1)
    tp = (y_pred == 1) & (y_true == 1)

    cost = 0.0
    cost += fp.sum() * (OPS_COST + GOODWILL_COST)
    cost += float((amounts[fn] * WIN_RATE).sum()) + fn.sum() * CHARGEBACK_FEE
    # contesting a truly abusive case: pay ops, recover expected value
    cost += tp.sum() * OPS_COST - float((amounts[tp] * WIN_RATE).sum())
    return float(cost)


def cost_breakdown(y_true: np.ndarray, y_pred: np.ndarray,
                   amounts: np.ndarray) -> dict:
    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)
    amounts = np.asarray(amounts, dtype=float)
    fp = (y_pred == 1) & (y_true == 0)
    fn = (y_pred == 0) & (y_true == 1)
    tp = (y_pred == 1) & (y_true == 1)
    return {
        "assumptions": {
            "ops_cost_inr": OPS_COST,
            "goodwill_cost_inr": GOODWILL_COST,
            "chargeback_fee_inr": CHARGEBACK_FEE,
            "contest_win_rate": WIN_RATE,
        },
        "false_positive_count": int(fp.sum()),
        "false_positive_cost_inr": round(
            float(fp.sum() * (OPS_COST + GOODWILL_COST)), 2),
        "false_negative_count": int(fn.sum()),
        "false_negative_cost_inr": round(
            float((amounts[fn] * WIN_RATE).sum() + fn.sum() * CHARGEBACK_FEE), 2),
        "recovered_from_true_positives_inr": round(
            float((amounts[tp] * WIN_RATE).sum() - tp.sum() * OPS_COST), 2),
        "net_cost_inr": round(expected_cost(y_true, y_pred, amounts), 2),
    }
