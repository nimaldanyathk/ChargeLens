"""Perturbation benchmark for the grounding gate.

The gate's job: pass drafts whose facts all trace to the record, block
drafts that introduce facts that don't. This measures both directions,
because both have a cost:

  catch rate      = fraction of CORRUPTED drafts the gate blocks
                    (a miss ships a fabricated fact to a bank)
  false-block rate = fraction of CLEAN drafts the gate wrongly blocks
                    (a false block wastes the LLM draft and falls back
                     to the deterministic letter - the gate's own
                     false-positive cost)

Method: build clean grounded drafts from known fact sheets, then
generate corrupted variants across a taxonomy of six fact-level
corruptions (RAGTruth-style: conflicting vs baseless information). The
gate is deterministic and owns the ground truth, so this is exact, needs
no model calls, and runs in milliseconds.

Honest scope: this measures the NUMERIC/IDENTIFIER gate. Corruptions the
gate is not designed to catch (a purely qualitative fabrication with no
new number or ID) are reported in their own bucket rather than hidden,
so the catch rate is not inflated by excluding what the gate cannot see.
"""

from __future__ import annotations

import random
import re

from .generator import grounding_check

# corruption families and whether the numeric/identifier gate is
# expected to catch them (a qualitative-only claim introduces no new
# token, so the numeric gate structurally cannot)
IN_SCOPE = {
    "amount_swap": True,
    "date_digit_swap": True,
    "id_swap": True,
    "fabricated_quantity": True,
    "unsupported_number": True,
    "qualitative_only": False,
}


def _clean_draft(facts: dict) -> str:
    return (
        f"Case {facts['case_id']} concerns transaction "
        f"{facts['transaction_id']} on order {facts['order_id']} for "
        f"customer {facts['customer_id']}. The disputed amount is "
        f"Rs {facts['disputed_amount_inr']}. The order for "
        f"{facts['product']} was marked {facts['delivery_status']} with "
        f"tracking {facts['tracking_number']} via {facts['carrier']}. "
        f"The customer has {facts['previous_orders']} previous orders and "
        f"{facts['previous_chargebacks']} previous chargebacks.")


def _corrupt(draft: str, facts: dict, family: str, rng: random.Random) -> str:
    if family == "amount_swap":
        return draft.replace(str(facts["disputed_amount_inr"]),
                             "88,888.00")
    if family == "date_digit_swap":
        return draft + " The order shipped on 31 Feb 2026."
    if family == "id_swap":
        return draft.replace(facts["transaction_id"], "TXN-99999")
    if family == "fabricated_quantity":
        return draft + " A total of 47 units were delivered."
    if family == "unsupported_number":
        return draft + " A partial refund of Rs 12,500 was already issued."
    if family == "qualitative_only":
        # a fabricated, damaging characterization with NO new number/ID
        return draft + (" The customer has a documented history of "
                        "fraudulent behaviour and acted in bad faith.")
    raise ValueError(family)


def _sample_facts(i: int) -> dict:
    """Deterministic synthetic fact sheets spanning value ranges."""
    return {
        "case_id": f"CB-E{1000 + i}",
        "transaction_id": f"TXN-E{2000 + i}",
        "order_id": f"ORD-E{3000 + i}",
        "customer_id": f"CUST-E{4000 + i}",
        "disputed_amount_inr": f"{5000 + i * 137:,}.00",
        "product": "Sony WH-1000XM5",
        "delivery_status": "delivered",
        "tracking_number": f"TRK{60000000 + i}",
        "carrier": "Delhivery",
        "previous_orders": 10 + (i % 30),
        "previous_chargebacks": i % 3,
    }


def run_benchmark(n_cases: int = 100, seed: int = 7) -> dict:
    rng = random.Random(seed)
    families = list(IN_SCOPE)

    clean_blocked = 0
    per_family = {f: {"n": 0, "caught": 0} for f in families}

    for i in range(n_cases):
        facts = _sample_facts(i)
        clean = _clean_draft(facts)
        # clean drafts must pass
        if not grounding_check(clean, facts):
            clean_blocked += 1
        # one corrupted variant per family per case
        for fam in families:
            corrupted = _corrupt(clean, facts, fam, rng)
            per_family[fam]["n"] += 1
            if not grounding_check(corrupted, facts):
                per_family[fam]["caught"] += 1

    in_scope_n = sum(per_family[f]["n"] for f in families if IN_SCOPE[f])
    in_scope_caught = sum(per_family[f]["caught"] for f in families
                          if IN_SCOPE[f])

    return {
        "n_clean": n_cases,
        "clean_blocked": clean_blocked,
        "false_block_rate": clean_blocked / n_cases if n_cases else 0.0,
        "in_scope_catch_rate": (in_scope_caught / in_scope_n
                                if in_scope_n else 0.0),
        "in_scope_corruptions": in_scope_n,
        "per_family": {
            f: {
                "n": per_family[f]["n"],
                "caught": per_family[f]["caught"],
                "catch_rate": (per_family[f]["caught"] / per_family[f]["n"]
                               if per_family[f]["n"] else 0.0),
                "in_scope": IN_SCOPE[f],
            } for f in families
        },
    }
