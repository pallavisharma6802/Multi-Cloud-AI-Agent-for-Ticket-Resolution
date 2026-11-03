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

    agent = RetrievalAgent(domain_pack_id="vscode_support")
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
    assert kwargs.get("namespace") == "vscode_support"


def test_hybrid_ranking_rewards_agreement_not_score_magnitude(retrieval_agent):
    shared = {"id": "shared", "text": "Windows install", "score": 0.7, "source": "kb"}
    dense_only = {"id": "dense", "text": "Other install", "score": 0.99, "source": "kb"}
    sparse_only = {"id": "sparse", "text": "Repeated install keywords", "score": 1.0, "source": "kb"}
    retrieval_agent._pinecone_mock.query.return_value = [dense_only, shared]
    retrieval_agent._bm25_search = MagicMock(return_value=[sparse_only, shared])
    results = retrieval_agent.retrieve_relevant_documents("Windows install", top_k=3)
    assert results[0].doc_id == "shared"
    assert results[0].metadata["retrieval_method"] == "hybrid"


def test_retrieval_restores_same_article_context_and_links(retrieval_agent, tmp_path, monkeypatch):
    import json

    from app.config import settings
    article_dir = tmp_path / 'vscode_support' / 'kb'
    article_dir.mkdir(parents=True)
    article_dir.joinpath('doc1.json').write_text(json.dumps({
        'source': 'kb', 'content': 'Installer adds PATH. Restart your terminal. [Download](/download)',
    }))
    monkeypatch.setattr(settings, 'domains_root', str(tmp_path))
    result = retrieval_agent.retrieve_relevant_documents('cancel order', top_k=1)[0]
    assert 'Restart your terminal' in result.content
    article_dir.joinpath('doc1.json').write_text(json.dumps({
        'source': 'different-version-source', 'content': 'Wrong evidence',
    }))
    result = retrieval_agent.retrieve_relevant_documents('cancel order', top_k=1)[0]
    assert 'Wrong evidence' not in result.content
