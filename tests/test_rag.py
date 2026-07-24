"""Retrieval: chunking and hybrid dense+sparse (mocked embeddings/Pinecone)."""
from unittest.mock import MagicMock

import pytest

from app.embeddings.chunking import chunk_text


def test_chunk_text_splits_long_documents():
    words = [f"word{i}" for i in range(1000)]
    chunks = chunk_text(" ".join(words), max_words=400, overlap_words=60)
    assert len(chunks) > 1
    assert chunks[0].split()[-1] in chunks[1].split()


@pytest.fixture
def retrieval_agent(monkeypatch):
    mock_embedding_gen = MagicMock()
    mock_embedding_gen.get_dimension.return_value = 384
    mock_embedding_gen.generate_embedding.return_value = [0.1] * 384
    mock_embedding_gen.generate_embeddings_batch.return_value = [[0.1] * 384]

    mock_pinecone = MagicMock()
    mock_pinecone.query.return_value = [
        {
            "id": "doc1",
            "score": 0.9,
            "text": "how to cancel an order",
            "source": "kb",
            "category": "ORDER",
            "intent": "cancel_order",
        },
    ]
    mock_pinecone.fetch_all_documents.return_value = [
        {
            "id": "doc1",
            "text": "how to cancel an order",
            "source": "kb",
            "category": "ORDER",
            "intent": "cancel_order",
        },
        {
            "id": "doc2",
            "text": "how to reset your password",
            "source": "kb",
            "category": "ACCOUNT",
            "intent": "password_reset",
        },
    ]

    monkeypatch.setattr("app.agents.retrieval_agent.EmbeddingGenerator", lambda: mock_embedding_gen)
    monkeypatch.setattr("app.agents.retrieval_agent.PineconeClient", lambda: mock_pinecone)

    from app.agents.retrieval_agent import RetrievalAgent

    agent = RetrievalAgent(domain_pack_id="it_saas")
    agent._pinecone_mock = mock_pinecone
    return agent


def test_retrieval_agent_merges_and_indexes(retrieval_agent):
    results = retrieval_agent.retrieve_relevant_documents("I want to cancel my order", top_k=5)
    assert "doc1" in [r.doc_id for r in results]
    for r in results:
        assert 0.0 <= r.similarity_score <= 1.0

    retrieval_agent.index_knowledge_base(
        [{"id": "doc-99", "text": "short doc", "source": "kb", "category": "ORDER", "intent": "cancel_order"}]
    )
    retrieval_agent._pinecone_mock.upsert_documents.assert_called_once()
    _, kwargs = retrieval_agent._pinecone_mock.upsert_documents.call_args
    assert kwargs.get("namespace") == "it_saas"
