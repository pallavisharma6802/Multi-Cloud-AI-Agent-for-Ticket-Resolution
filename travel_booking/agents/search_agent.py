"""Search Agent: hybrid (dense Pinecone + sparse BM25) candidate retrieval
for hotels and flights.

Reuses the existing `ticket-kb` Pinecone index (same index, new namespaces
`travel-hotels` / `travel-flights` -- namespaces are how domain packs
already separate data in this codebase, see app/agents/retrieval_agent.py)
and the same local sentence-transformers embedding model, so this costs
zero Bedrock calls.

IMPORTANT: this agent hard-filters ONLY on destination -- never on
amenities, capacity, or price. Those are exactly what the Verification
Agent has to catch; if Search silently excluded a trap listing before
Verification ever saw it, the whole point of building Verification would
be untested. Date availability (blackout dates) can't be hard-filtered
here either, since no specific date is chosen until a flight candidate is
picked -- that check happens per-combination in the orchestrator.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Literal, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from rank_bm25 import BM25Okapi  # noqa: E402
from pinecone import Pinecone  # noqa: E402

from app.config import settings  # noqa: E402
from app.embeddings.embed import EmbeddingGenerator  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
HOTELS_NAMESPACE = "travel-hotels"
FLIGHTS_NAMESPACE = "travel-flights"

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> List[str]:
    return _TOKEN_RE.findall(text.lower())


def _hotel_text(h: dict) -> str:
    return (
        f"{h['name']} in {h['destination_name']}. {h['description']} "
        f"Amenities: {', '.join(h['amenities'])}."
    )


def _flight_text(f: dict) -> str:
    return (
        f"{f['airline']} flight {f['flight_number']} to {f['destination_name']}. "
        f"{f['description']} Departs {f['departure_time']}, arrives {f['arrival_time']}, "
        f"price ${f['price']}."
    )


def _load_json(name: str) -> List[dict]:
    return json.loads((DATA_DIR / name).read_text())


class SearchAgent:
    def __init__(self):
        self.embedder = EmbeddingGenerator()
        self.pc = Pinecone(api_key=settings.pinecone_api_key)
        self.index = self.pc.Index(settings.pinecone_index_name)

        self.hotels: Dict[str, dict] = {h["id"]: h for h in _load_json("hotels.json")}
        self.flights: Dict[str, dict] = {f["id"]: f for f in _load_json("flights.json")}

        self._bm25_hotels: Optional[BM25Okapi] = None
        self._bm25_hotel_ids: List[str] = []
        self._bm25_flights: Optional[BM25Okapi] = None
        self._bm25_flight_ids: List[str] = []

    # -- one-time indexing --------------------------------------------------
    def index_all(self) -> None:
        hotel_vectors = []
        for h in self.hotels.values():
            emb = self.embedder.generate_embedding(_hotel_text(h))
            hotel_vectors.append({"id": h["id"], "values": emb, "metadata": {"destination": h["destination"]}})
        self.index.upsert(vectors=hotel_vectors, namespace=HOTELS_NAMESPACE)

        flight_vectors = []
        for f in self.flights.values():
            emb = self.embedder.generate_embedding(_flight_text(f))
            flight_vectors.append({"id": f["id"], "values": emb, "metadata": {"destination": f["destination"]}})
        self.index.upsert(vectors=flight_vectors, namespace=FLIGHTS_NAMESPACE)

        self._build_bm25()

    def _build_bm25(self) -> None:
        self._bm25_hotel_ids = list(self.hotels.keys())
        self._bm25_hotels = BM25Okapi([_tokenize(_hotel_text(self.hotels[i])) for i in self._bm25_hotel_ids])
        self._bm25_flight_ids = list(self.flights.keys())
        self._bm25_flights = BM25Okapi([_tokenize(_flight_text(self.flights[i])) for i in self._bm25_flight_ids])

    def _ensure_bm25(self) -> None:
        if self._bm25_hotels is None or self._bm25_flights is None:
            self._build_bm25()

    # -- hybrid search --------------------------------------------------------
    def _hybrid(
        self,
        kind: Literal["hotel", "flight"],
        query_text: str,
        destination_code: str,
        top_k: int,
    ) -> List[dict]:
        self._ensure_bm25()
        namespace = HOTELS_NAMESPACE if kind == "hotel" else FLIGHTS_NAMESPACE
        records = self.hotels if kind == "hotel" else self.flights
        bm25 = self._bm25_hotels if kind == "hotel" else self._bm25_flights
        bm25_ids = self._bm25_hotel_ids if kind == "hotel" else self._bm25_flight_ids

        query_emb = self.embedder.generate_embedding(query_text)
        dense = self.index.query(
            vector=query_emb,
            top_k=top_k * 3,
            filter={"destination": {"$eq": destination_code}},
            namespace=namespace,
            include_metadata=False,
        )
        dense_scores = {m.id: float(m.score) for m in dense.matches}

        bm25_scores_raw = bm25.get_scores(_tokenize(query_text))
        max_bm25 = max(bm25_scores_raw) or 1.0
        sparse_scores = {
            rid: score / max_bm25
            for rid, score in zip(bm25_ids, bm25_scores_raw)
            if records[rid]["destination"] == destination_code
        }

        merged: Dict[str, dict] = {}
        for rid, score in dense_scores.items():
            merged[rid] = {"id": rid, "score": score, "method": "dense"}
        for rid, score in sparse_scores.items():
            if score <= 0:
                continue
            if rid in merged:
                merged[rid]["method"] = "hybrid"
                merged[rid]["score"] = max(merged[rid]["score"], score)
            else:
                merged[rid] = {"id": rid, "score": score, "method": "sparse"}

        ranked = sorted(merged.values(), key=lambda x: x["score"], reverse=True)[:top_k]
        return [
            {**records[r["id"]], "_search_score": r["score"], "_retrieval_method": r["method"]}
            for r in ranked
        ]

    def search_hotels(self, destination_code: str, query_text: str, top_k: int = 6) -> List[dict]:
        return self._hybrid("hotel", query_text, destination_code, top_k)

    def search_flights(self, destination_code: str, query_text: str, top_k: int = 6) -> List[dict]:
        return self._hybrid("flight", query_text, destination_code, top_k)
