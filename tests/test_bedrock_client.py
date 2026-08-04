"""Unit tests for BedrockStructuredClient error handling (no live AWS calls).

Mocks the boto3 bedrock-runtime client object used by BedrockStructuredClient,
so we exercise retry / throttle / fail-fast logic without hitting the network.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError
from pydantic import BaseModel, Field

from app.llm.bedrock_client import BedrockStructuredClient


class SampleOut(BaseModel):
    answer: str = Field(description="short answer")
    score: float = Field(ge=0.0, le=1.0, description="confidence 0-1")


def _converse_ok(text: str, input_tokens: int = 11, output_tokens: int = 7) -> dict:
    return {
        "output": {"message": {"content": [{"text": text}]}},
        "usage": {"inputTokens": input_tokens, "outputTokens": output_tokens},
    }


def _client_error(code: str, message: str = "boom") -> ClientError:
    """Real botocore ClientError shape: error_response['Error']['Code'/'Message']."""
    return ClientError(
        {"Error": {"Code": code, "Message": message}},
        "Converse",
    )


@pytest.fixture
def bedrock(monkeypatch):
    """Construct BedrockStructuredClient with a MagicMock Converse client (no AWS)."""
    mock_runtime = MagicMock()
    monkeypatch.setattr(
        "boto3.client",
        lambda *args, **kwargs: mock_runtime,
    )
    client = BedrockStructuredClient(region_name="us-east-1")
    assert client._client is mock_runtime
    return client, mock_runtime


def test_generate_structured_happy_path(bedrock):
    client, mock_runtime = bedrock
    payload = SampleOut(answer="yes", score=0.9)
    mock_runtime.converse.return_value = _converse_ok(payload.model_dump_json())

    parsed, meta = client.generate_structured(
        prompt="Classify this",
        schema=SampleOut,
        model=None,
        role="judge",
        max_retries=2,
    )

    assert parsed.answer == "yes"
    assert parsed.score == 0.9
    assert meta.attempts == 1
    assert meta.role == "judge"
    assert meta.model == "amazon.nova-lite-v1:0"  # role → settings default
    assert meta.prompt_tokens == 11
    assert meta.completion_tokens == 7
    assert mock_runtime.converse.call_count == 1
    kwargs = mock_runtime.converse.call_args.kwargs
    assert kwargs["modelId"] == "amazon.nova-lite-v1:0"


def test_generate_structured_retries_after_malformed_json(bedrock, monkeypatch):
    client, mock_runtime = bedrock
    good = SampleOut(answer="fixed", score=0.5).model_dump_json()
    mock_runtime.converse.side_effect = [
        _converse_ok("NOT JSON {{{"),
        _converse_ok(good),
    ]

    parsed, meta = client.generate_structured(
        prompt="Give JSON",
        schema=SampleOut,
        model="amazon.nova-lite-v1:0",
        role="intent_priority",
        max_retries=2,
    )

    assert parsed.answer == "fixed"
    assert meta.attempts == 2
    assert mock_runtime.converse.call_count == 2

    first_prompt = mock_runtime.converse.call_args_list[0].kwargs["messages"][0]["content"][0]["text"]
    second_prompt = mock_runtime.converse.call_args_list[1].kwargs["messages"][0]["content"][0]["text"]
    assert "Give JSON" in first_prompt
    assert "Your previous response did not match the required format" in second_prompt
    assert "Error:" in second_prompt
    # Same model on retry — not a model switch.
    assert mock_runtime.converse.call_args_list[0].kwargs["modelId"] == "amazon.nova-lite-v1:0"
    assert mock_runtime.converse.call_args_list[1].kwargs["modelId"] == "amazon.nova-lite-v1:0"


def test_generate_structured_exhausts_retries_on_persistent_bad_json(bedrock):
    client, mock_runtime = bedrock
    mock_runtime.converse.return_value = _converse_ok("{bad")

    with pytest.raises(RuntimeError, match=r"LLM call failed after 3 attempt\(s\)"):
        client.generate_structured(
            prompt="Give JSON",
            schema=SampleOut,
            model=None,
            role="judge",
            max_retries=2,  # attempts = max_retries + 1 = 3
        )

    assert mock_runtime.converse.call_count == 3


def test_generate_structured_throttles_then_succeeds_same_model(bedrock, monkeypatch):
    client, mock_runtime = bedrock
    sleeps: list[float] = []
    monkeypatch.setattr("app.llm.bedrock_client.time.sleep", lambda s: sleeps.append(s))

    good = SampleOut(answer="ok", score=1.0).model_dump_json()
    mock_runtime.converse.side_effect = [
        _client_error("ThrottlingException", "Rate exceeded"),
        _converse_ok(good),
    ]

    parsed, meta = client.generate_structured(
        prompt="Go",
        schema=SampleOut,
        model=None,
        role="drafting",
        max_retries=2,
    )

    assert parsed.answer == "ok"
    assert meta.attempts == 2
    assert sleeps == [1]  # min(2**(1-1), 8) == 1 on first throttle
    assert mock_runtime.converse.call_count == 2
    ids = [c.kwargs["modelId"] for c in mock_runtime.converse.call_args_list]
    assert ids[0] == ids[1] == "amazon.nova-lite-v1:0"


def test_generate_structured_access_denied_fails_fast(bedrock, monkeypatch):
    client, mock_runtime = bedrock
    sleep = MagicMock()
    monkeypatch.setattr("app.llm.bedrock_client.time.sleep", sleep)
    mock_runtime.converse.side_effect = _client_error(
        "AccessDeniedException", "User is not authorized"
    )

    with pytest.raises(RuntimeError, match="Enable model access") as exc_info:
        client.generate_structured(
            prompt="Go",
            schema=SampleOut,
            model=None,
            role="judge",
            max_retries=2,
        )

    assert "Access denied" in str(exc_info.value) or "access" in str(exc_info.value).lower()
    assert mock_runtime.converse.call_count == 1  # no retries
    sleep.assert_not_called()


def test_generate_structured_validation_exception_fails_fast(bedrock, monkeypatch):
    client, mock_runtime = bedrock
    sleep = MagicMock()
    monkeypatch.setattr("app.llm.bedrock_client.time.sleep", sleep)
    mock_runtime.converse.side_effect = _client_error(
        "ValidationException", "Malformed input request"
    )

    with pytest.raises(RuntimeError, match="ValidationException") as exc_info:
        client.generate_structured(
            prompt="Go",
            schema=SampleOut,
            model=None,
            role="judge",
            max_retries=2,
        )

    assert "bad request params" in str(exc_info.value)
    assert mock_runtime.converse.call_count == 1
    sleep.assert_not_called()


def test_generate_structured_schema_validation_retry_then_ok(bedrock):
    """Pydantic ge/le failure on first parse, valid object on second."""
    client, mock_runtime = bedrock
    mock_runtime.converse.side_effect = [
        _converse_ok(json.dumps({"answer": "x", "score": 2.0})),  # > 1.0
        _converse_ok(json.dumps({"answer": "x", "score": 0.2})),
    ]

    parsed, meta = client.generate_structured(
        prompt="Score it",
        schema=SampleOut,
        model=None,
        role="judge",
        max_retries=2,
    )

    assert parsed.score == 0.2
    assert meta.attempts == 2
    second_prompt = mock_runtime.converse.call_args_list[1].kwargs["messages"][0]["content"][0]["text"]
    assert "did not match the required format" in second_prompt
