#!/usr/bin/env python3
"""Domain-pack-aware knowledge base seeding.

Loads every KB article from `domains/<pack>/kb/*.json` (real data -- see
data/prepare_it_saas.py for provenance) and indexes it into Pinecone under
a namespace matching the pack id, with proper chunking
(app/embeddings/chunking.py) instead of single-blob documents.

Usage:
    python seed_kb.py --pack it_saas
    python seed_kb.py --pack all
"""
from __future__ import annotations

import argparse
import glob
import json
import logging
import os

from app.agents.retrieval_agent import RetrievalAgent
from app.domain.loader import list_available_packs, load_domain_pack

logging.basicConfig(level="INFO")
logger = logging.getLogger(__name__)


def load_kb_documents(pack_id: str) -> list[dict]:
    pack = load_domain_pack(pack_id)
    files = sorted(glob.glob(os.path.join(pack.kb_dir, "*.json")))
    documents = []
    for path in files:
        with open(path) as f:
            doc = json.load(f)
        documents.append({
            "id": doc["id"],
            "text": doc["content"],
            "source": doc.get("source", "unknown"),
            "category": doc.get("category", "general"),
            "intent": doc.get("intent"),
        })
    return documents


def seed_pack(pack_id: str, test_query: str | None = None):
    logger.info(f"=== Seeding domain pack '{pack_id}' ===")
    documents = load_kb_documents(pack_id)
    if not documents:
        logger.warning(f"No KB documents found for pack '{pack_id}'; skipping.")
        return

    agent = RetrievalAgent(domain_pack_id=pack_id)
    agent.index_knowledge_base(documents)
    logger.info(f"Indexed {len(documents)} source documents (pre-chunking) for '{pack_id}'")

    if test_query:
        results = agent.retrieve_relevant_documents(test_query, top_k=3)
        logger.info(f"Test query: '{test_query}' -> {len(results)} candidates")
        for doc in results:
            logger.info(f"  - {doc.doc_id} ({doc.metadata.get('retrieval_method')}): {doc.similarity_score:.3f}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pack", default="all", help="Domain pack id, or 'all'")
    args = parser.parse_args()

    available = list_available_packs()
    if not available:
        raise SystemExit("No domain packs found under domains/. Run data/prepare_*.py first.")

    targets = available if args.pack == "all" else [args.pack]
    test_queries = {
        "it_saas": "I want to cancel my order, how do I do that?",
    }

    for pack_id in targets:
        seed_pack(pack_id, test_query=test_queries.get(pack_id))

    logger.info("Knowledge base seeding completed successfully!")


if __name__ == "__main__":
    main()
