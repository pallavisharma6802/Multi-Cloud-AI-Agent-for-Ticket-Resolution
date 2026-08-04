"""Shared pytest fixtures.

Mocks the shared Bedrock LLM client (via ``get_llm_client`` singleton), Azure
Text Analytics, and heavy deps (rank_bm25, sentence_transformers) so the suite
runs in CI without AWS/Azure credentials or torch.

Every test gets a MagicMock Bedrock client by default (no boto3 Converse calls).
``tests/test_bedrock_client.py`` constructs a real ``BedrockStructuredClient``
with its own boto3.client patch when it needs to exercise Converse error paths.
"""
import sys
import types
from unittest.mock import MagicMock

if "rank_bm25" not in sys.modules:
    _fake_rank_bm25 = types.ModuleType("rank_bm25")

    class _FakeBM25Okapi:
        """Scores by shared-token count for merge-logic tests."""

        def __init__(self, corpus):
            self.corpus = corpus

        def get_scores(self, query_tokens):
            query_set = set(query_tokens)
            return [float(len(query_set & set(doc))) for doc in self.corpus]

    _fake_rank_bm25.BM25Okapi = _FakeBM25Okapi
    sys.modules["rank_bm25"] = _fake_rank_bm25

# Stub sentence_transformers so EmbeddingGenerator imports without torch.
if "sentence_transformers" not in sys.modules:
    _fake_st = types.ModuleType("sentence_transformers")

    class _FakeArray(list):
        def tolist(self):
            return list(self)

    class _FakeSentenceTransformer:
        def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
            self.model_name = model_name

        def get_sentence_embedding_dimension(self):
            return 384

        def encode(self, text_or_texts, convert_to_numpy=True, show_progress_bar=False):
            if isinstance(text_or_texts, str):
                return _FakeArray([0.0] * 384)
            return _FakeArray([_FakeArray([0.0] * 384) for _ in text_or_texts])

    _fake_st.SentenceTransformer = _FakeSentenceTransformer
    sys.modules["sentence_transformers"] = _fake_st

import pytest

import app.llm.bedrock_client as bedrock_client_module
from app.llm.bedrock_client import LLMCallMetadata


def make_metadata(role: str = "test", model: str = "amazon.nova-lite-v1:0") -> LLMCallMetadata:
    return LLMCallMetadata(
        model=model, role=role, latency_ms=12.5, prompt_tokens=50, completion_tokens=30, attempts=1
    )


@pytest.fixture(autouse=True)
def _default_mock_bedrock_client(monkeypatch):
    """Inject a MagicMock as the process-wide LLM client (zero AWS calls).

    Also stub ``boto3.client`` so accidental ``BedrockStructuredClient()``
    construction cannot reach the network. Tests that need a real client
    (test_bedrock_client) re-patch boto3.client in their own fixtures.
    Pin Nova model IDs so a developer `.env` with legacy Ollama tags cannot
    leak into assertions.
    """
    from app.config import settings

    bedrock_client_module.reset_llm_client()
    for attr in (
        "model_intent_priority",
        "model_grader",
        "model_judge",
        "model_continuation",
        "model_drafting",
        "model_supervisor",
    ):
        monkeypatch.setattr(settings, attr, "amazon.nova-lite-v1:0")
    mock = MagicMock()
    monkeypatch.setattr(bedrock_client_module, "_client", mock)
    monkeypatch.setattr("boto3.client", lambda *args, **kwargs: MagicMock())
    yield mock
    bedrock_client_module.reset_llm_client()


@pytest.fixture
def mock_llm_client(_default_mock_bedrock_client):
    """Alias for the autouse Bedrock MagicMock (agent tests configure return values)."""
    return _default_mock_bedrock_client


@pytest.fixture
def mock_azure_text_analytics(monkeypatch):
    """Prevent AzureNLPAgent from touching the network."""
    mock_client = MagicMock()
    monkeypatch.setattr(
        "app.agents.azure_nlp_agent.TextAnalyticsClient", lambda *a, **kw: mock_client
    )
    return mock_client
