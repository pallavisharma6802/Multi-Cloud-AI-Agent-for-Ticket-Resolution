"""Hybrid retrieval: dense (Pinecone) + sparse (BM25) candidate pool.

Does not judge relevance; DocumentGrader does that. Dense catches paraphrases;
BM25 catches exact terms (order numbers, error codes).
"""
from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional

from rank_bm25 import BM25Okapi

from app.config import settings
from app.embeddings.chunking import chunk_text
from app.embeddings.embed import EmbeddingGenerator
from app.embeddings.pinecone_client import PineconeClient
from app.schemas.response import KBDocument

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> List[str]:
    return _TOKEN_RE.findall(text.lower())


class RetrievalAgent:
    def __init__(self, domain_pack_id: Optional[str] = None):
        self.domain_pack_id = domain_pack_id or settings.domain_pack
        self.embedding_generator = EmbeddingGenerator()
        self.pinecone_client = PineconeClient()
        self.pinecone_client.initialize_index(dimension=self.embedding_generator.get_dimension())
        self._bm25: Optional[BM25Okapi] = None
        self._bm25_docs: List[Dict] = []

    def index_knowledge_base(self, documents: List[dict]):
        """Chunk and upsert documents into this pack's Pinecone namespace."""
        logger.info(
            f"Indexing {len(documents)} KB documents into namespace='{self.domain_pack_id}'"
        )

        chunk_records: List[dict] = []
        for doc in documents:
            content = doc.get("text") or doc.get("content") or ""
            chunks = chunk_text(content, max_words=400, overlap_words=60)
            for i, chunk in enumerate(chunks):
                chunk_id = doc["id"] if len(chunks) == 1 else f"{doc['id']}__chunk{i}"
                chunk_records.append({
                    "id": chunk_id,
                    "text": chunk,
                    "source": doc.get("source", "unknown"),
                    "category": doc.get("category", "general"),
                    "intent": doc.get("intent"),
                })

        texts = [c["text"] for c in chunk_records]
        embeddings = self.embedding_generator.generate_embeddings_batch(texts)

        indexed_docs = []
        for i, chunk in enumerate(chunk_records):
            indexed_docs.append({**chunk, "embedding": embeddings[i]})

        self.pinecone_client.upsert_documents(indexed_docs, namespace=self.domain_pack_id)
        self._bm25 = None  # invalidate cached sparse index
        logger.info(f"Knowledge base indexing complete: {len(indexed_docs)} chunks")

    def _ensure_bm25_index(self):
        """Build BM25 lazily from documents currently in Pinecone."""
        if self._bm25 is not None:
            return
        docs = self.pinecone_client.fetch_all_documents(namespace=self.domain_pack_id)
        if not docs:
            logger.warning(
                f"No documents found in namespace='{self.domain_pack_id}' to build BM25 index"
            )
            self._bm25_docs = []
            self._bm25 = None
            return
        self._bm25_docs = docs
        tokenized = [_tokenize(d["text"]) for d in docs]
        self._bm25 = BM25Okapi(tokenized)

    def _bm25_search(self, query_text: str, top_k: int) -> List[Dict]:
        self._ensure_bm25_index()
        if not self._bm25:
            return []
        scores = self._bm25.get_scores(_tokenize(query_text))
        ranked = sorted(zip(self._bm25_docs, scores), key=lambda x: x[1], reverse=True)[:top_k]
        max_score = max((s for _, s in ranked), default=0) or 1.0
        return [
            {**doc, "score": float(score) / max_score}
            for doc, score in ranked
            if score > 0
        ]

    def retrieve_relevant_documents(
        self,
        query_text: str,
        intent: Optional[str] = None,
        top_k: int = 8,
        min_similarity: Optional[float] = None,
    ) -> List[KBDocument]:
        """Return a candidate pool for DocumentGrader.

        `min_similarity` is optional (eval/pre-filter only); production leaves it None.
        """
        logger.info(f"Retrieving candidates for query: {query_text[:80]}...")

        query_embedding = self.embedding_generator.generate_embedding(query_text)
        # Healthcare KB articles have intent=null — intent $eq filters match nothing.
        # Also skip empty intent strings. IT keeps intent filter when present.
        filter_dict = None
        use_intent_filter = (
            bool(intent and str(intent).strip())
            and self.domain_pack_id != "healthcare"
        )
        if use_intent_filter:
            filter_dict = {"intent": {"$eq": intent}}

        dense_results = self.pinecone_client.query(
            query_embedding=query_embedding,
            top_k=top_k,
            filter=filter_dict,
            namespace=self.domain_pack_id,
        )
        # If the intent filter zeroes dense hits, retry unfiltered (wrong intent).
        if filter_dict and not dense_results:
            logger.warning(
                f"Dense retrieval returned 0 with intent filter intent={intent!r}; retrying unfiltered"
            )
            dense_results = self.pinecone_client.query(
                query_embedding=query_embedding,
                top_k=top_k,
                filter=None,
                namespace=self.domain_pack_id,
            )
        sparse_results = self._bm25_search(query_text, top_k=top_k)

        merged: Dict[str, Dict] = {}
        for r in dense_results:
            merged[r["id"]] = {**r, "retrieval_method": "dense"}
        for r in sparse_results:
            if r["id"] in merged:
                merged[r["id"]]["retrieval_method"] = "hybrid"
                merged[r["id"]]["score"] = max(merged[r["id"]]["score"], r["score"])
            else:
                merged[r["id"]] = {**r, "retrieval_method": "sparse"}

        candidates = sorted(merged.values(), key=lambda x: x["score"], reverse=True)[:top_k]

        kb_documents = [
            KBDocument(
                doc_id=c["id"],
                content=c["text"],
                # Clamp cosine scores to [0, 1] for KBDocument validation.
                similarity_score=max(0.0, min(1.0, c["score"])),
                metadata={
                    "source": c.get("source", "unknown"),
                    "category": c.get("category", "general"),
                    "intent": c.get("intent", ""),
                    "retrieval_method": c.get("retrieval_method", "dense"),
                },
            )
            for c in candidates
            if min_similarity is None or c["score"] >= min_similarity
        ]

        logger.info(f"Retrieved {len(kb_documents)} candidate documents (pre-grading)")
        return kb_documents
