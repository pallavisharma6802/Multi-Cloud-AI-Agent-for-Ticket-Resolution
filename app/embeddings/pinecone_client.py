from pinecone import Pinecone, ServerlessSpec
from app.config import settings
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)


class PineconeClient:
    
    def __init__(self):
        self.pc = Pinecone(api_key=settings.pinecone_api_key)
        self.index_name = settings.pinecone_index_name
        self.index = None
        
    def initialize_index(self, dimension: int, metric: str = "cosine"):
        try:
            existing_indexes = [index.name for index in self.pc.list_indexes()]
            
            if self.index_name not in existing_indexes:
                logger.info(f"Creating Pinecone index: {self.index_name}")
                self.pc.create_index(
                    name=self.index_name,
                    dimension=dimension,
                    metric=metric,
                    spec=ServerlessSpec(
                        cloud="aws",
                        region=settings.pinecone_environment
                    )
                )
                logger.info(f"Index {self.index_name} created successfully")
            else:
                logger.info(f"Index {self.index_name} already exists")
            
            self.index = self.pc.Index(self.index_name)
            
        except Exception as e:
            logger.error(f"Failed to initialize Pinecone index: {e}")
            raise
    
    def upsert_documents(self, documents: List[Dict]):
        if not self.index:
            raise RuntimeError("Index not initialized. Call initialize_index() first")
        
        try:
            vectors = []
            for doc in documents:
                vectors.append({
                    "id": doc["id"],
                    "values": doc["embedding"],
                    "metadata": {
                        "text": doc["text"],
                        "source": doc.get("source", "unknown"),
                        "category": doc.get("category", "general")
                    }
                })
            
            self.index.upsert(vectors=vectors)
            logger.info(f"Upserted {len(vectors)} documents to Pinecone")
            
        except Exception as e:
            logger.error(f"Failed to upsert documents: {e}")
            raise
    
    def query(
        self, 
        query_embedding: List[float], 
        top_k: int = 5,
        filter: Optional[Dict] = None
    ) -> List[Dict]:
        if not self.index:
            raise RuntimeError("Index not initialized. Call initialize_index() first")
        
        try:
            response = self.index.query(
                vector=query_embedding,
                top_k=top_k,
                include_metadata=True,
                filter=filter
            )
            
            results = []
            for match in response.matches:
                results.append({
                    "id": match.id,
                    "score": match.score,
                    "text": match.metadata.get("text", ""),
                    "source": match.metadata.get("source", "unknown"),
                    "category": match.metadata.get("category", "general")
                })
            
            logger.info(f"Retrieved {len(results)} documents from Pinecone")
            return results
            
        except Exception as e:
            logger.error(f"Failed to query Pinecone: {e}")
            raise
    
    def delete_all(self):
        if not self.index:
            raise RuntimeError("Index not initialized. Call initialize_index() first")
        
        try:
            self.index.delete(delete_all=True)
            logger.info("Deleted all vectors from index")
        except Exception as e:
            logger.error(f"Failed to delete vectors: {e}")
            raise
    
    def get_stats(self) -> Dict:
        if not self.index:
            raise RuntimeError("Index not initialized. Call initialize_index() first")
        
        try:
            stats = self.index.describe_index_stats()
            return {
                "total_vector_count": stats.total_vector_count,
                "dimension": stats.dimension,
                "index_fullness": stats.index_fullness
            }
        except Exception as e:
            logger.error(f"Failed to get index stats: {e}")
            raise
