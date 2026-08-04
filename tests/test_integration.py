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

    mock_result = DraftedResponse(
        ticket_id="TKT-TEST",
        draft_text="Here's how to resolve your issue...",
        confidence=0.9,
        kb_documents=[],
        agent_decisions=[],
        requires_human_review=False,
        trace={
            "domain_pack": "it_saas",
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
            "domain_pack": "it_saas",
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
    assert "it_saas" in ids and "healthcare" in ids
