import pytest
from app.embeddings.embed import EmbeddingGenerator
from app.embeddings.pinecone_client import PineconeClient


@pytest.fixture
def embedding_generator():
    return EmbeddingGenerator()


@pytest.fixture
def pinecone_client():
    client = PineconeClient()
    client.initialize_index(dimension=384)
    yield client
    client.delete_all()


def test_embedding_generation(embedding_generator):
    text = "How do I reset my password?"
    embedding = embedding_generator.generate_embedding(text)
    
    assert isinstance(embedding, list)
    assert len(embedding) == 384
    assert all(isinstance(x, float) for x in embedding)


def test_embedding_similarity(embedding_generator):
    text1 = "password reset"
    text2 = "forgot password"
    text3 = "weather forecast"
    
    emb1 = embedding_generator.generate_embedding(text1)
    emb2 = embedding_generator.generate_embedding(text2)
    emb3 = embedding_generator.generate_embedding(text3)
    
    import numpy as np
    
    def cosine_similarity(a, b):
        return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))
    
    similarity_related = cosine_similarity(emb1, emb2)
    similarity_unrelated = cosine_similarity(emb1, emb3)
    
    assert similarity_related > similarity_unrelated


def test_pinecone_upsert_and_query(pinecone_client, embedding_generator):
    documents = [
        {
            "id": "doc1",
            "text": "To reset your password, go to the login page and click Forgot Password",
            "embedding": embedding_generator.generate_embedding("password reset instructions"),
            "category": "password_reset"
        }
    ]
    
    pinecone_client.upsert_documents(documents)
    
    query_embedding = embedding_generator.generate_embedding("how to reset password")
    results = pinecone_client.query(query_embedding, top_k=1)
    
    assert len(results) == 1
    assert results[0]["id"] == "doc1"
    assert results[0]["score"] > 0.6
