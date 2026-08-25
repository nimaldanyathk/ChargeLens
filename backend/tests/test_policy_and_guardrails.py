"""Decision policy and agent permission boundary."""

import pytest

from app.agent.policy import (
    ALLOWED_TOOLS, FORBIDDEN_ACTIONS, GuardrailViolation,
    assert_tool_allowed, recommend,
)
from app.evidence.engine import Evidence


def ev(supports: str, strength: str) -> Evidence:
    return Evidence(key="k", statement="s", value="v", source_table="t",
                    source_id="1", source_field="f", supports=supports,
                    strength=strength)


def test_high_band_strong_evidence_contests():
    rec, reason = recommend("high", 0.93, [ev("merchant", "strong")])
    assert rec == "contest"
    assert "93%" in reason


def test_high_band_weak_evidence_goes_to_review():
    rec, reason = recommend(
        "high", 0.91, [ev("merchant", "weak"), ev("missing", "moderate")])
    assert rec == "review"
    assert "evidence" in reason.lower()


def test_low_band_accepts():
    rec, _ = recommend("low", 0.03, [ev("customer", "strong")])
    assert rec == "accept"


def test_review_band_requires_human():
    rec, _ = recommend("review", 0.2, [ev("merchant", "strong")])
    assert rec == "review"


def test_every_forbidden_action_is_blocked():
    for action in FORBIDDEN_ACTIONS:
        with pytest.raises(GuardrailViolation):
            assert_tool_allowed(action)


def test_arbitrary_tool_names_blocked():
    for name in ("delete_all", "shell", "http_post", "refund_customer"):
        with pytest.raises(GuardrailViolation):
            assert_tool_allowed(name)


def test_allowed_tools_pass():
    for name in ALLOWED_TOOLS:
        assert_tool_allowed(name)  # must not raise


def test_registries_disjoint():
    assert not ALLOWED_TOOLS & FORBIDDEN_ACTIONS
