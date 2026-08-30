"""Visa CE3.0 eligibility rules + dossier PDF generation."""

from __future__ import annotations

from types import SimpleNamespace

from app.evidence import ce3
from app.evidence.ce3 import CE3Result, PriorTxn, evaluate


def _case(reason="unauthorized_transaction"):
    return SimpleNamespace(id="CB-1", reason=reason)


def _customer(prev_orders=20):
    return SimpleNamespace(id="CUST-1", previous_orders=prev_orders)


def _txn(device=True, ip_km=5.0):
    return SimpleNamespace(id="TXN-1", device_seen_before=device,
                           ip_geo_distance_km=ip_km)


def test_not_applicable_for_non_fraud_reason():
    r = evaluate(_case("product_not_received"), _customer(), _txn())
    assert r.status == "not_applicable"


def test_qualifies_with_two_matching_priors_in_window():
    priors = [
        PriorTxn("P1", age_days=200, purchase_ip=True, device_id=True,
                 shipping_address=True, account_id=True),
        PriorTxn("P2", age_days=300, purchase_ip=True, device_id=True,
                 shipping_address=True, account_id=True),
    ]
    r = evaluate(_case(), _customer(), _txn(), priors)
    assert r.status == "qualified"
    assert set(r.matched_main) == {"purchase_ip", "device_id"}
    assert len(r.qualifying_transactions) == 2


def test_requires_action_when_priors_out_of_window():
    priors = [
        PriorTxn("P1", age_days=30, purchase_ip=True, device_id=True,
                 shipping_address=True, account_id=True),
        PriorTxn("P2", age_days=800, purchase_ip=True, device_id=True,
                 shipping_address=True, account_id=True),
    ]
    r = evaluate(_case(), _customer(), _txn(), priors)
    assert r.status == "requires_action"
    assert any("120-365" in m for m in r.missing)


def test_requires_action_when_only_one_main_and_no_secondary():
    # device matches on both, but IP does not, and no secondary shared
    priors = [
        PriorTxn("P1", age_days=200, purchase_ip=False, device_id=True,
                 shipping_address=False, account_id=False),
        PriorTxn("P2", age_days=250, purchase_ip=False, device_id=True,
                 shipping_address=False, account_id=False),
    ]
    r = evaluate(_case(), _customer(), _txn(), priors)
    assert r.status == "requires_action"
    assert r.matched_main == ["device_id"]


def test_one_main_plus_one_secondary_qualifies():
    priors = [
        PriorTxn("P1", age_days=200, purchase_ip=False, device_id=True,
                 shipping_address=True, account_id=False),
        PriorTxn("P2", age_days=250, purchase_ip=False, device_id=True,
                 shipping_address=True, account_id=False),
    ]
    r = evaluate(_case(), _customer(), _txn(), priors)
    assert r.status == "qualified"


def test_reconstructed_priors_are_deterministic():
    a = ce3.reconstruct_prior_transactions(_customer(), _txn(), _case())
    b = ce3.reconstruct_prior_transactions(_customer(), _txn(), _case())
    assert [p.id for p in a] == [p.id for p in b]


def test_result_serializes():
    r = CE3Result(status="qualified", matched_main=["device_id"])
    d = r.dict()
    assert d["status"] == "qualified" and "reason_code" in d


# ---- dossier PDF ---------------------------------------------------------

def test_dossier_pdf_endpoint(client, db):
    from tests.conftest import make_case
    from app.agent.orchestrator import investigate

    case = make_case(db, "CB-DOS-1")
    investigate(db, case)
    r = client.get("/api/cases/CB-DOS-1/dossier.pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:5] == b"%PDF-"
    assert len(r.content) > 1500   # a real multi-section document


def test_dossier_404_for_missing_case(client):
    assert client.get("/api/cases/NOPE/dossier.pdf").status_code == 404
