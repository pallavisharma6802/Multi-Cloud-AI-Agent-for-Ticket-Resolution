import pytest
from fastapi.testclient import TestClient
from app.api.main import app

client = TestClient(app)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_ping():
    response = client.get("/ping")
    assert response.status_code == 200
    assert response.json()["message"] == "pong"


def test_ticket_submission_schema():
    invalid_ticket = {
        "title": "Hi",
        "description": "Help",
        "user_email": "user@example.com"
    }
    
    response = client.post("/api/v1/tickets", json=invalid_ticket)
    assert response.status_code == 422
