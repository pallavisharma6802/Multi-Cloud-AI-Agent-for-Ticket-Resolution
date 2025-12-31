from app.embeddings.embed import EmbeddingGenerator
from app.embeddings.pinecone_client import PineconeClient
from app.schemas.response import KBDocument
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)


class RetrievalAgent:
    
    def __init__(self):
        self.embedding_generator = EmbeddingGenerator()
        self.pinecone_client = PineconeClient()
        self.pinecone_client.initialize_index(dimension=self.embedding_generator.get_dimension())
    
    def retrieve_relevant_documents(
        self,
        query_text: str,
        intent: Optional[str] = None,
        top_k: int = 5,
        min_similarity: float = 0.7
    ) -> List[KBDocument]:
        logger.info(f"Retrieving documents for query: {query_text[:50]}...")
        
        query_embedding = self.embedding_generator.generate_embedding(query_text)
        
        filter_dict = None
        if intent:
            filter_dict = {"category": {"$eq": intent}}
        
        results = self.pinecone_client.query(
            query_embedding=query_embedding,
            top_k=top_k,
            filter=filter_dict
        )
        
        kb_documents = []
        for result in results:
            if result["score"] >= min_similarity:
                kb_documents.append(KBDocument(
                    doc_id=result["id"],
                    content=result["text"],
                    similarity_score=result["score"],
                    metadata={
                        "source": result.get("source", "unknown"),
                        "category": result.get("category", "general")
                    }
                ))
        
        logger.info(f"Retrieved {len(kb_documents)} documents above similarity threshold {min_similarity}")
        return kb_documents
    
    def index_knowledge_base(self, documents: List[dict]):
        logger.info(f"Indexing {len(documents)} documents to knowledge base")
        
        texts = [doc["text"] for doc in documents]
        embeddings = self.embedding_generator.generate_embeddings_batch(texts)
        
        indexed_docs = []
        for i, doc in enumerate(documents):
            indexed_docs.append({
                "id": doc.get("id", f"doc-{i}"),
                "text": doc["text"],
                "embedding": embeddings[i],
                "source": doc.get("source", "unknown"),
                "category": doc.get("category", "general")
            })
        
        self.pinecone_client.upsert_documents(indexed_docs)
        logger.info("Knowledge base indexing complete")
