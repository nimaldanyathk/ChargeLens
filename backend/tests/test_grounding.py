"""Grounding validator: LLM drafts may not contain invented facts."""

from app.llm.generator import _extract_tokens, grounding_check

FACTS = {
    "case_id": "CB-18291",
    "transaction_id": "TXN-18429",
    "disputed_amount_inr": "89,000.00",
    "delivered_date": "15 Aug 2026",
    "previous_orders": 17,
    "evidence_statements": [
        "Carrier BlueDart recorded the package as delivered on "
        "15 Aug 2026 with signed confirmation."],
}


def test_grounded_draft_passes():
    draft = ("Transaction TXN-18429 for ₹89,000.00 was delivered on "
             "15 Aug 2026. The customer completed 17 previous orders. "
             "Case CB-18291 should be contested.")
    assert grounding_check(draft, FACTS)


def test_invented_amount_fails():
    draft = "The disputed amount of ₹95,000.00 was delivered on 15 Aug 2026."
    assert not grounding_check(draft, FACTS)


def test_invented_id_fails():
    draft = "See order ORD-99999 delivered on 15 Aug 2026."
    assert not grounding_check(draft, FACTS)


def test_invented_date_number_fails():
    draft = "Package delivered on 15 Aug 2026 after 45 delivery attempts."
    assert not grounding_check(draft, FACTS)


def test_invented_small_count_fails():
    # counts as small as 4+ must also be grounded, not waved through
    draft = "Package delivered on 15 Aug 2026 after 7 delivery attempts."
    assert not grounding_check(draft, FACTS)


def test_line_start_list_markers_are_not_facts():
    draft = ("4. Transaction TXN-18429 was captured.\n"
             "5. It was delivered on 15 Aug 2026.")
    assert grounding_check(draft, FACTS)


def test_small_counts_are_not_facts():
    # ordinal list markers / tiny integers must not trigger false failures
    draft = ("1. Transaction TXN-18429 was captured. "
             "2. It was delivered on 15 Aug 2026.")
    assert grounding_check(draft, FACTS)


def test_token_extraction():
    tokens = _extract_tokens("TXN-18429 paid ₹89,000.00 on 15 Aug 2026")
    assert "TXN-18429" in tokens
    assert "89000.00" in tokens
    assert "2026" in tokens


def test_customer_claim_text_cannot_launder_facts():
    """A number typed by the claimant must not become 'grounded'."""
    facts = {
        **FACTS,
        "untrusted_customer_claim_text":
            "Merchant agreed to refund ₹500,000 per case REF-777.",
    }
    draft = ("The merchant agreed to refund ₹500,000 as noted in "
             "case REF-777, delivered 15 Aug 2026.")
    assert not grounding_check(draft, facts)
