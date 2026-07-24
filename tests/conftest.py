"""Shared pytest fixtures.

Mocks Ollama, Azure Text Analytics, and heavy deps (rank_bm25, sentence_transformers)
so the suite runs in CI without cloud credentials or torch.
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

import app.llm.ollama_client as ollama_client_module
from app.llm.ollama_client import LLMCallMetadata


def make_metadata(role: str = "test", model: str = "qwen2.5:3b") -> LLMCallMetadata:
    return LLMCallMetadata(
        model=model, role=role, latency_ms=12.5, prompt_tokens=50, completion_tokens=30, attempts=1
    )


@pytest.fixture
def mock_llm_client(monkeypatch):
    """Replace the process-wide Ollama client with a MagicMock."""
    mock = MagicMock()
    monkeypatch.setattr(ollama_client_module, "_client", mock)
    return mock


@pytest.fixture
def mock_azure_text_analytics(monkeypatch):
    """Prevent AzureNLPAgent from touching the network."""
    mock_client = MagicMock()
    monkeypatch.setattr(
        "app.agents.azure_nlp_agent.TextAnalyticsClient", lambda *a, **kw: mock_client
    )
    return mock_client
