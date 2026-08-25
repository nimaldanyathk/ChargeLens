"""End-to-end API tests: intake -> investigate -> decide, plus audit."""

from tests.conftest import make_case


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_case_not_found(client):
    assert client.get("/api/cases/CB-NOPE").status_code == 404


def test_decision_requires_investigation(client, db):
    make_case(db, "CB-T-0")
    db.commit()
    r = client.post("/api/cases/CB-T-0/decision",
                    json={"action": "approve", "note": ""})
    assert r.status_code == 409


def test_full_investigation_flow(client, db):
    make_case(db, "CB-T-1", delivery_status="delivered",
              confirmation="signed", claim_delay=9.0)
    db.commit()

    r = client.post("/api/cases/CB-T-1/investigate")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "awaiting_review"
    assert body["risk"]["risk_score"] is not None
    assert body["risk"]["band"] in ("low", "review", "high")
    assert body["recommendation"] in ("contest", "accept", "review")
    assert len(body["evidence"]) >= 3
    # every evidence item must cite a source inside our own records
    for item in body["evidence"]:
        assert item["source"].count("/") == 1 and "#" in item["source"]
    assert body["generated_response"]
    assert "model prediction" in body["generated_response"]

    # audit trail must reconstruct the pipeline
    events = [a["event_type"] for a in body["audit"]]
    for expected in ("chargeback_received", "investigation_started",
                     "tool_call", "risk_scored", "evidence_collected",
                     "recommendation", "response_generated",
                     "awaiting_human_review"):
        assert expected in events, f"missing audit event {expected}"

    # human decision closes the loop
    r = client.post("/api/cases/CB-T-1/decision",
                    json={"action": "approve", "note": "looks right"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "approved"
    events = [a["event_type"] for a in body["audit"]]
    assert "human_decision" in events
    assert "final_action" in events

    # decided cases cannot be re-investigated
    assert client.post("/api/cases/CB-T-1/investigate").status_code == 409


def test_strong_evidence_pnr_recommends_contest(client, db):
    make_case(db, "CB-T-2", delivery_status="delivered",
              confirmation="signed", prev_chargebacks=1, claim_delay=12.0)
    db.commit()
    body = client.post("/api/cases/CB-T-2/investigate").json()
    assert body["risk"]["band"] == "high"
    assert body["recommendation"] == "contest"


def test_failed_delivery_is_not_contested(client, db):
    make_case(db, "CB-T-3", delivery_status="failed", confirmation="none",
              claim_delay=1.5, prev_orders=40, account_age=900.0)
    db.commit()
    body = client.post("/api/cases/CB-T-3/investigate").json()
    # merchant has nothing to fight with - must never recommend contest
    assert body["recommendation"] in ("accept", "review")
    supports = {e["supports"] for e in body["evidence"]}
    assert "customer" in supports


def test_dashboard_and_list(client, db):
    make_case(db, "CB-T-4")
    db.commit()
    client.post("/api/cases/CB-T-4/investigate")
    dash = client.get("/api/dashboard").json()
    assert dash["total_cases"] >= 1
    assert dash["awaiting_review"] >= 1
    listed = client.get("/api/cases", params={"status": "awaiting_review"})
    assert any(c["case_id"] == "CB-T-4" for c in listed.json()["cases"])


def test_analytics_serves_real_artifacts(client):
    body = client.get("/api/analytics").json()
    m = body["metrics"]
    assert "held-out test split" in m["disclosure"]
    cd = m["contest_decision_at_t_high"]
    assert 0 < cd["precision"] <= 1 and 0 < cd["recall"] <= 1
    cm = cd["confusion_matrix"]
    assert m["test_set"]["n_cases"] == (cm["tp"] + cm["fp"] +
                                        cm["fn"] + cm["tn"])
    assert body["dataset_manifest"]["synthetic"] is True
