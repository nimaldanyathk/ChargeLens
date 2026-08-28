"""Business cost model for threshold selection and evaluation.

All figures are in INR and are stated assumptions for the synthetic
merchant, not measurements. They are deliberately conservative and are
surfaced in the UI so a judge can audit them.

Decision the threshold controls: CONTEST the dispute (predict abusive)
vs ACCEPT it (predict legitimate).

The model is an ABSOLUTE expected-cost account of each case, so no
outcome is charged twice (a previous relative formulation charged the
missed recovery on false negatives AND credited it on true positives,
double-counting the contest margin - this version fixes that):

  accept a dispute   -> the disputed amount is refunded/clawed back and
                        the scheme fee applies:      amount + FEE
  contest and win    -> amount and fee are kept:     OPS_COST only
  contest and lose   -> amount + FEE + OPS_COST
  contesting a LEGITIMATE dispute is assumed lost (win rate ~0) and
  additionally burns customer goodwill.

Per-cell expected cost:
  TN (accept legit):    amount + FEE                (unavoidable refund)
  FN (accept abusive):  amount + FEE                (avoidable loss)
  FP (contest legit):   amount + FEE + OPS + GOODWILL
  TP (contest abusive): OPS + (1 - WIN_RATE) * (amount + FEE)

Only differences between actions drive the threshold choice; the
constant terms keep the totals interpretable as "what disputes cost the
merchant under this policy".
"""

from __future__ import annotations

import numpy as np

OPS_COST = 350.0          # staff time to assemble + submit one representment
GOODWILL_COST = 900.0     # expected lifetime-value loss from fighting an honest customer
CHARGEBACK_FEE = 500.0    # scheme/acquirer fee on a lost dispute
WIN_RATE = 0.65           # probability a contested abusive dispute is won


def expected_cost(y_true: np.ndarray, y_pred: np.ndarray,
                  amounts: np.ndarray) -> float:
    """Total expected dispute cost (INR) of a decision vector."""
    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)
    amounts = np.asarray(amounts, dtype=float)

    tn = (y_pred == 0) & (y_true == 0)
    fn = (y_pred == 0) & (y_true == 1)
    fp = (y_pred == 1) & (y_true == 0)
    tp = (y_pred == 1) & (y_true == 1)

    cost = 0.0
    cost += float(amounts[tn].sum()) + tn.sum() * CHARGEBACK_FEE
    cost += float(amounts[fn].sum()) + fn.sum() * CHARGEBACK_FEE
    cost += (float(amounts[fp].sum()) + fp.sum()
             * (CHARGEBACK_FEE + OPS_COST + GOODWILL_COST))
    cost += tp.sum() * OPS_COST + (1.0 - WIN_RATE) * (
        float(amounts[tp].sum()) + tp.sum() * CHARGEBACK_FEE)
    return float(cost)


def cost_breakdown(y_true: np.ndarray, y_pred: np.ndarray,
                   amounts: np.ndarray) -> dict:
    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)
    amounts = np.asarray(amounts, dtype=float)
    fp = (y_pred == 1) & (y_true == 0)
    fn = (y_pred == 0) & (y_true == 1)
    tp = (y_pred == 1) & (y_true == 1)

    # marginal cost of each error class vs the correct action on that case
    fp_marginal = fp.sum() * (OPS_COST + GOODWILL_COST)
    fn_marginal = float(
        (WIN_RATE * (amounts[fn] + CHARGEBACK_FEE) - OPS_COST).clip(0).sum())
    tp_recovered = float(
        (WIN_RATE * (amounts[tp] + CHARGEBACK_FEE) - OPS_COST).sum())
    return {
        "assumptions": {
            "ops_cost_inr": OPS_COST,
            "goodwill_cost_inr": GOODWILL_COST,
            "chargeback_fee_inr": CHARGEBACK_FEE,
            "contest_win_rate": WIN_RATE,
        },
        "false_positive_count": int(fp.sum()),
        # extra cost incurred by wrongly contesting honest customers
        "false_positive_cost_inr": round(float(fp_marginal), 2),
        "false_negative_count": int(fn.sum()),
        # expected value a correct contest would have recovered
        "false_negative_cost_inr": round(fn_marginal, 2),
        "recovered_from_true_positives_inr": round(tp_recovered, 2),
        # absolute expected dispute cost under this decision vector
        "net_cost_inr": round(expected_cost(y_true, y_pred, amounts), 2),
    }
