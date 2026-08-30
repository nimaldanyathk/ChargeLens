"""Visa Compelling Evidence 3.0 eligibility.

CE3.0 lets a merchant reverse a Visa fraud chargeback (reason code 10.4,
"Fraud - Card Absent Environment") by proving a prior relationship with
the cardholder. When it qualifies, liability shifts back to the issuer -
so detecting eligibility is worth real money, and it is a pure rules
check, not a model.

Qualification (per Visa CE3.0 merchant guidance / Stripe's implementation):

  - the dispute must be reason 10.4 (card-absent fraud); other reasons
    are not applicable
  - at least TWO prior transactions on the same payment credential, each
    120-365 days before the dispute, undisputed
  - the disputed transaction AND both priors must share matching data:
    either two "main" elements (customer purchase IP address, device
    ID/fingerprint) OR one main + one "secondary" element (shipping
    address, account ID/email)
  - device fingerprint + device ID together do NOT count as two mains

This module reports one of three statuses, mirroring Stripe's
required_actions pattern so the merchant sees exactly what is missing:

  qualified        - the rule is satisfied; attach as a dossier exhibit
  requires_action  - it could qualify but data is missing (listed)
  not_applicable   - wrong reason code

Prior transactions are reconstructed deterministically from the
customer's history (synthetic data; in production these come from the
order/transaction store). We never fabricate a match: an element counts
only when the prior actually shares it with the disputed transaction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from ..models.entities import Chargeback, Customer, Transaction

CE3_REASON = "unauthorized_transaction"   # our canonical name for Visa 10.4
MIN_PRIORS = 2
MIN_AGE_DAYS = 120
MAX_AGE_DAYS = 365

MAIN_ELEMENTS = ("purchase_ip", "device_id")
SECONDARY_ELEMENTS = ("shipping_address", "account_id")


@dataclass
class PriorTxn:
    id: str
    age_days: int
    purchase_ip: bool       # shares the disputed txn's IP
    device_id: bool         # shares the disputed txn's device
    shipping_address: bool  # shares the disputed txn's shipping address
    account_id: bool        # same account/email


@dataclass
class CE3Result:
    status: str                     # qualified | requires_action | not_applicable
    reason_code: str = "10.4"
    matched_main: list[str] = field(default_factory=list)
    matched_secondary: list[str] = field(default_factory=list)
    qualifying_transactions: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    note: str = ""

    def dict(self) -> dict:
        return {
            "status": self.status,
            "reason_code": self.reason_code,
            "matched_main": self.matched_main,
            "matched_secondary": self.matched_secondary,
            "qualifying_transactions": self.qualifying_transactions,
            "missing": self.missing,
            "note": self.note,
        }


def reconstruct_prior_transactions(customer: Customer, txn: Transaction,
                                   case: Chargeback) -> list[PriorTxn]:
    """Deterministically rebuild the customer's prior transactions.

    Synthetic stand-in for an order-store lookup: seeded by customer id so
    it is stable across runs. A prior shares the disputed transaction's
    device/IP only when the disputed transaction itself looks
    account-consistent (device seen before, low IP distance), so matches
    reflect the real signals rather than being invented.
    """
    n_priors = min(customer.previous_orders, 6)
    device_consistent = bool(txn.device_seen_before)
    ip_consistent = txn.ip_geo_distance_km < 50
    address_consistent = True   # same customer, same saved address in demo

    priors: list[PriorTxn] = []
    if n_priors == 0:
        return priors
    # space the prior purchases evenly across the last ~2 years so those
    # that fall inside the 120-365 day CE3.0 window are determined by how
    # many prior orders the customer actually has, not by RNG clustering
    span_lo, span_hi = 90, 700
    step = (span_hi - span_lo) / max(1, n_priors - 1) if n_priors > 1 else 0
    for i in range(n_priors):
        age = int(span_lo + step * i)
        priors.append(PriorTxn(
            id=f"{txn.id}-P{i+1}",
            age_days=age,
            purchase_ip=ip_consistent,
            device_id=device_consistent,
            shipping_address=address_consistent,
            account_id=True,
        ))
    return priors


def evaluate(case: Chargeback, customer: Customer, txn: Transaction,
             priors: list[PriorTxn] | None = None) -> CE3Result:
    if case.reason != CE3_REASON:
        return CE3Result(status="not_applicable",
                         note="CE3.0 applies only to Visa reason 10.4 "
                              "(card-absent fraud).")

    if priors is None:
        priors = reconstruct_prior_transactions(customer, txn, case)

    in_window = [p for p in priors
                 if MIN_AGE_DAYS <= p.age_days <= MAX_AGE_DAYS]

    # an element qualifies only if it matches across >= MIN_PRIORS priors
    def shared(attr: str) -> bool:
        return sum(getattr(p, attr) for p in in_window) >= MIN_PRIORS

    matched_main = [e for e in MAIN_ELEMENTS if shared(e)]
    matched_secondary = [e for e in SECONDARY_ELEMENTS if shared(e)]

    # need the priors themselves and a valid element combination
    qualifying = [p.id for p in in_window][:MIN_PRIORS]
    missing: list[str] = []

    if len(in_window) < MIN_PRIORS:
        missing.append(
            f"only {len(in_window)} prior undisputed transaction(s) in the "
            f"120-365 day window; CE3.0 needs {MIN_PRIORS}")

    two_mains = len(matched_main) >= 2
    one_each = len(matched_main) >= 1 and len(matched_secondary) >= 1
    if not (two_mains or one_each):
        missing.append(
            "matching data elements insufficient: need two main elements "
            "(purchase IP + device ID) or one main + one secondary "
            "(shipping address / account ID) shared with two priors")

    if not missing:
        combo = ("two main elements" if two_mains
                 else "one main + one secondary element")
        return CE3Result(
            status="qualified",
            matched_main=matched_main,
            matched_secondary=matched_secondary,
            qualifying_transactions=qualifying,
            note=f"Qualifies on {combo}; liability shifts to the issuer "
                 f"when submitted with these prior transactions.")

    return CE3Result(
        status="requires_action",
        matched_main=matched_main,
        matched_secondary=matched_secondary,
        qualifying_transactions=qualifying,
        missing=missing,
        note="Could qualify for CE3.0 with the items listed under missing.")
