"""API integration tests with in-memory SQLite and a mocked Supervisor."""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import Base


@pytest.fixture
def client(monkeypatch):
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    from app.api.main import app
    from app.db.session import get_db
    from app.schemas.response import DraftedResponse

    def override_get_db():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    # Startup must never create tables in the developer's configured cloud database.
    monkeypatch.setattr("app.db.init_db.init_db", lambda: None)

    mock_result = DraftedResponse(
        ticket_id="TKT-TEST",
        draft_text="Here's how to resolve your issue...",
        confidence=0.9,
        kb_documents=[],
        agent_decisions=[],
        requires_human_review=False,
        trace={
            "domain_pack": "vscode_support",
            "intent": "cancel_order",
            "category": "ORDER",
            "priority": "medium",
            "intent_rationale": "wants to cancel",
            "intent_confidence": 0.9,
            "iteration_count": 0,
            "judge_score_history": [],
            "continuation_rationale": [],
            "escalation_rationale": None,
            "final_action": "auto_resolve",
            "anomaly_flags": [],
            "cost_estimate": {"llm_call_count": 5},
            "sentiment": "neutral",
        },
    )

    import app.api.routes.tickets as tickets_module

    monkeypatch.setattr(tickets_module.supervisor, "process_ticket", MagicMock(return_value=mock_result))

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_ticket_submission_and_trace(client):
    bad = client.post(
        "/api/v1/tickets",
        json={"title": "Hi", "description": "Help", "user_email": "user@example.com"},
    )
    assert bad.status_code == 422

    unknown = client.post(
        "/api/v1/tickets",
        json={
            "title": "Need to cancel my order",
            "description": "I would like to cancel order #12345 please",
            "user_email": "user@example.com",
            "domain_pack": "not_a_real_pack",
        },
    )
    assert unknown.status_code == 400

    ok = client.post(
        "/api/v1/tickets",
        json={
            "title": "Need to cancel my order",
            "description": "I would like to cancel order #12345 please",
            "user_email": "user@example.com",
            "domain_pack": "vscode_support",
        },
    )
    assert ok.status_code == 201
    ticket_id = ok.json()["ticket_id"]
    assert ok.json()["trace"]["intent"] == "cancel_order"

    get_resp = client.get(f"/api/v1/tickets/{ticket_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["ticket_id"] == ticket_id

    trace = client.get(f"/api/v1/tickets/{ticket_id}/trace")
    assert trace.status_code == 200
    assert trace.json()["drafted_response"]["final_action"] == "auto_resolve"


def test_list_domain_packs(client):
    response = client.get("/api/v1/domain-packs")
    assert response.status_code == 200
    ids = [p["id"] for p in response.json()["packs"]]
    assert "vscode_support" in ids


def test_resolved_ticket_is_counted_in_workspace_overview(client):
    response = client.post(
        "/api/v1/tickets",
        json={
            "title": "Help recover my password",
            "description": "I forgot my password and need the reset instructions.",
            "user_email": "demo@example.com",
            "domain_pack": "vscode_support",
        },
    )
    assert response.status_code == 201
    assert response.json()["status"] == "resolved"
    overview = client.get("/api/v1/overview?days=7").json()
    assert overview["total"] == 1
    assert overview["resolved"] == 1
    assert overview["needs_review"] == 0
    assert sum(day["total"] for day in overview["daily"]) == 1
    assert overview["recent"][0]["ticket_id"] == response.json()["ticket_id"]
    assert client.get("/api/v1/overview?days=0").status_code == 422


def test_failed_open_ticket_can_be_retried_without_duplicate(client):
    import app.api.routes.tickets as tickets_module

    processor = tickets_module.supervisor.process_ticket
    processor.side_effect = RuntimeError("Transient model failure")
    payload = {
        "title": "Recover my account",
        "description": "I forgot my password and need help signing in.",
        "user_email": "demo@example.com",
        "domain_pack": "vscode_support",
    }
    failed = client.post("/api/v1/tickets", json=payload)
    assert failed.status_code == 500
    tickets = client.get("/api/v1/tickets").json()
    assert len(tickets) == 1
    assert tickets[0]["status"] == "open"
    ticket_id = tickets[0]["ticket_id"]
    processor.side_effect = None
    retried = client.post(f"/api/v1/tickets/{ticket_id}/retry")
    assert retried.status_code == 200
    assert retried.json()["ticket_id"] == ticket_id
    assert retried.json()["status"] == "resolved"
    assert len(client.get("/api/v1/tickets").json()) == 1
    assert client.post(f"/api/v1/tickets/{ticket_id}/retry").status_code == 409


def test_retry_rejects_ticket_that_is_already_processing(client):
    import app.api.routes.tickets as tickets_module

    processor = tickets_module.supervisor.process_ticket
    processor.side_effect = RuntimeError("Transient failure")
    client.post(
        "/api/v1/tickets",
        json={
            "title": "Recover my account",
            "description": "I need help resetting my password.",
            "user_email": "demo@example.com",
        },
    )
    ticket_id = client.get("/api/v1/tickets").json()[0]["ticket_id"]
    tickets_module._claim_ticket(ticket_id)
    try:
        assert client.post(f"/api/v1/tickets/{ticket_id}/retry").status_code == 409
    finally:
        tickets_module._release_ticket(ticket_id)


def test_human_resolution_preserves_original_ai_assessment(client):
    import app.api.routes.tickets as tickets_module

    result = tickets_module.supervisor.process_ticket.return_value
    result.requires_human_review = True
    result.trace["final_action"] = "escalate"
    created = client.post(
        "/api/v1/tickets",
        json={
            "title": "Investigate duplicate charge",
            "description": "Please have a human investigate two identical subscription charges.",
            "user_email": "demo@example.com",
        },
    )
    assert created.status_code == 201
    assert created.json()["status"] == "in_progress"
    ticket_id = created.json()["ticket_id"]
    before = client.get("/api/v1/overview").json()
    assert before["needs_review"] == 1
    resolved = client.post(f"/api/v1/tickets/{ticket_id}/resolve")
    assert resolved.status_code == 200
    assert resolved.json()["resolution_source"] == "human"
    trace = client.get(f"/api/v1/tickets/{ticket_id}/trace").json()
    assert trace["ticket"]["status"] == "resolved"
    assert trace["drafted_response"]["final_action"] == "escalate"
    assert trace["drafted_response"]["requires_human_review"] is True
    assert any(
        d["agent_name"] == "human_reviewer" and d["action"] == "mark_resolved"
        for d in trace["agent_decisions"]
    )
    after = client.get("/api/v1/overview").json()
    assert after["resolved"] == 1
    assert after["human_resolved"] == 1
    assert after["ai_resolved"] == 0
    assert after["needs_review"] == 0
    assert client.post(f"/api/v1/tickets/{ticket_id}/resolve").status_code == 409


def test_review_reassessment_preserves_id_history_and_audit(client):
    import app.api.routes.tickets as tickets_module
    processor = tickets_module.supervisor.process_ticket
    processor.return_value.requires_human_review = True
    created = client.post('/api/v1/tickets', json={
        'title': 'Installation question', 'description': 'How do I install this application?',
        'user_email': 'demo@example.com', 'domain_pack': 'vscode_support',
    }).json()
    assert created['status'] == 'in_progress'
    ticket_id = created['ticket_id']
    processor.return_value.requires_human_review = False
    retried = client.post(f'/api/v1/tickets/{ticket_id}/retry')
    assert retried.status_code == 200
    assert retried.json()['ticket_id'] == ticket_id
    assert len(client.get('/api/v1/tickets').json()) == 1
    trace = client.get(f'/api/v1/tickets/{ticket_id}/trace').json()
    assert any(d['action'] == 'reassess_review' for d in trace['agent_decisions'])
