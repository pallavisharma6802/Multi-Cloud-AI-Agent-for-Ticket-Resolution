"""Standalone hotel/flight browsing -- no paired leg, no full verification
pipeline. Structured filters only (destination, dates, budget, amenities),
never freeform text, so this costs zero Bedrock calls.

This exists because the original UI only ever offered one path: a full
conversational search that verifies a paired hotel+flight combination
together. There was no way to just look at what hotels or flights exist for
a destination -- every click funneled into that one flow. This module backs
the real "Hotels only" / "Flights only" browse tabs that fixes that.

Each listing still gets real per-field checks where they make sense without
a pairing partner (budget/amenities/capacity for hotels; nothing meaningful
to check for a lone flight beyond it existing), rather than turning into an
unverified plain catalog -- the whole point of this project is not
pretending a listing is fine just because it surfaced in search.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path
from typing import List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.config import settings  # noqa: E402
from travel_booking.agents.schemas import ResolvedConstraints  # noqa: E402
from travel_booking.agents.search_agent import SearchAgent  # noqa: E402
from travel_booking.agents.verification_agent import check_amenities, check_capacity, check_hotel_only_budget  # noqa: E402

ORIGIN_AIRPORT = "ORD"
DESTINATION_HOTEL_QUERY = {
    "AUS": "hotels in Austin, TX",
    "DEN": "hotels in Denver, CO",
    "MIA": "hotels in Miami, FL",
}

_search_agent: Optional[SearchAgent] = None


def _get_search_agent() -> SearchAgent:
    global _search_agent
    if _search_agent is None:
        _search_agent = SearchAgent()
    return _search_agent


def browse_hotels(
    destination_code: str,
    date_range_start: str,
    nights: int,
    party_size: int = 1,
    budget_amount: Optional[float] = None,
    budget_scope: str = "per_night_hotel",
    required_amenities: Optional[List[str]] = None,
) -> List[dict]:
    required_amenities = required_amenities or []
    constraints = ResolvedConstraints(
        destination_code=destination_code, destination_raw=destination_code,
        party_size=party_size, nights=nights, nights_defaulted=False,
        date_range_start=date_range_start, date_range_end=date_range_start,
        dates_defaulted=False, budget_amount=budget_amount, budget_scope=budget_scope,
        required_amenities=required_amenities, raw_request="browse", assumptions=[],
    )

    if settings.travel_data_source == "serpapi":
        from travel_booking.agents import serpapi_client
        checkin = date_range_start
        checkout = (date.fromisoformat(checkin) + timedelta(days=nights)).isoformat()
        query = DESTINATION_HOTEL_QUERY.get(destination_code, destination_code)
        hotels = serpapi_client.search_hotels(query, checkin, checkout, adults=party_size)
        hotels = sorted(hotels, key=lambda h: h["price_per_night"])[:16]
    else:
        agent = _get_search_agent()
        hotels = agent.search_hotels(destination_code, f"Hotels in {destination_code}", top_k=16)

    results = []
    for h in hotels:
        checks = [check_hotel_only_budget(h, constraints), check_amenities(h, constraints), check_capacity(h, constraints)]
        results.append({"record": h, "checks": [c.model_dump() for c in checks], "passed_all": all(c.passed for c in checks)})
    return results


def browse_flights(
    destination_code: str,
    date_range_start: str,
    party_size: int = 1,
    budget_amount: Optional[float] = None,
) -> List[dict]:
    if settings.travel_data_source == "serpapi":
        from travel_booking.agents import serpapi_client
        flights = serpapi_client.search_flights(ORIGIN_AIRPORT, destination_code, date_range_start, adults=party_size)
        flights = sorted(flights, key=lambda f: f["price"])[:16]
    else:
        agent = _get_search_agent()
        flights = agent.search_flights(destination_code, f"Flights to {destination_code}", top_k=16)
        flights = [f for f in flights if f["date"] == date_range_start] or flights[:16]

    results = []
    for f in flights:
        within_budget = budget_amount is None or (f["price"] * party_size) <= budget_amount
        results.append({
            "record": f,
            "within_stated_budget": within_budget,
            "total_for_party": round(f["price"] * party_size, 2),
        })
    return results
