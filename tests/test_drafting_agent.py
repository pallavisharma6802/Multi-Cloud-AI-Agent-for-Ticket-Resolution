"""Tests for DraftingAgent transport via shared generate_text (no live LLM)."""
from __future__ import annotations

from unittest.mock import MagicMock

from botocore.exceptions import ClientError

from app.agents.drafting_agent import DraftingAgent
from app.config import settings
from app.llm.bedrock_client import BedrockStructuredClient
from app.schemas.response import KBDocument
from tests.conftest import make_metadata


def test_draft_response_calls_generate_text_with_expected_args(mock_llm_client, monkeypatch):
    mock_llm_client.generate_text.return_value = (
        "Here's how to cancel your order.",
        make_metadata(role="drafting", model="amazon.nova-lite-v1:0"),
    )
    monkeypatch.setattr(
        "app.llm.model_router.resolve_model_for_role",
        lambda role: "amazon.nova-lite-v1:0",
    )

    agent = DraftingAgent()
    text, meta = agent.draft_response(
        ticket_title="Cancel",
        ticket_description="Please cancel ORD-1",
        intent="cancel_order",
        kb_documents=[
            KBDocument(doc_id="d1", content="To cancel, open Orders.", similarity_score=0.9, metadata={})
        ],
    )

    assert text.startswith("Here's how to cancel")
    assert meta.role == "drafting"
    mock_llm_client.generate_text.assert_called_once()
    kwargs = mock_llm_client.generate_text.call_args.kwargs
    assert kwargs["model"] == "amazon.nova-lite-v1:0"
    assert kwargs["role"] == "drafting"
    assert kwargs["temperature"] == 0.6
    assert kwargs["num_predict"] == 500
    assert kwargs["timeout"] == settings.request_timeout_seconds
    assert "Cancel" in kwargs["prompt"]
    assert "cancel_order" in kwargs["prompt"]
    assert "To cancel, open Orders." in kwargs["prompt"]


def test_draft_response_retries_via_shared_client_on_throttle(monkeypatch):
    """Point of the fix: first throttle retries instead of failing outright."""
    mock_runtime = MagicMock()
    monkeypatch.setattr("boto3.client", lambda *a, **k: mock_runtime)
    monkeypatch.setattr(
        "app.llm.model_router.resolve_model_for_role",
        lambda role: "amazon.nova-lite-v1:0",
    )
    monkeypatch.setattr("app.llm.bedrock_client.time.sleep", lambda *_: None)

    ok = {
        "output": {"message": {"content": [{"text": "Retry succeeded draft."}]}},
        "usage": {"inputTokens": 5, "outputTokens": 9},
    }
    throttle = ClientError(
        {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
        "Converse",
    )
    mock_runtime.converse.side_effect = [throttle, ok]

    client = BedrockStructuredClient(region_name="us-east-1")
    agent = DraftingAgent()
    agent.client = client

    text, meta = agent.draft_response(
        ticket_title="T",
        ticket_description="D",
        intent="track_order",
        kb_documents=[],
    )

    assert text == "Retry succeeded draft."
    assert meta.attempts == 2
    assert mock_runtime.converse.call_count == 2
