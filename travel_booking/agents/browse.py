"""Standalone hotel/flight browsing -- no paired leg, no full verification
pipeline. Structured filters only (destination, dates, budget, amenities),
never freeform text, so this costs zero Bedrock calls. Backs the "Hotels
only" / "Flights only" tabs. Each listing still gets the per-field checks
that make sense without a pairing partner (budget/amenities/capacity for
hotels), rather than becoming an unverified plain catalog.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path
from typing import List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from travel_booking.agents import serpapi_client  # noqa: E402
from travel_booking.agents.schemas import DESTINATIONS, ResolvedConstraints  # noqa: E402
from travel_booking.agents.verification_agent import (  # noqa: E402
    check_amenities,
    check_capacity,
    check_hotel_only_budget,
)

ORIGIN_AIRPORT = "ORD"
DESTINATION_HOTEL_QUERY = {code: f"hotels in {name}" for code, name in DESTINATIONS.items()}


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

    checkin = date_range_start
    checkout = (date.fromisoformat(checkin) + timedelta(days=nights)).isoformat()
    query = DESTINATION_HOTEL_QUERY.get(destination_code, destination_code)
    hotels = serpapi_client.search_hotels(query, checkin, checkout, adults=party_size)
    hotels = sorted(hotels, key=lambda h: h["price_per_night"])[:16]

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
    origin_code: Optional[str] = None,
) -> List[dict]:
    origin_code = origin_code or ORIGIN_AIRPORT
    flights = serpapi_client.search_flights(origin_code, destination_code, date_range_start, adults=party_size)
    flights = sorted(flights, key=lambda f: f["price"])[:16]

    results = []
    for f in flights:
        # SerpApi's price is already the total for `party_size` adults
        total_for_party = f["price"]
        within_budget = budget_amount is None or total_for_party <= budget_amount
        results.append({
            "record": f,
            "within_stated_budget": within_budget,
            "total_for_party": round(total_for_party, 2),
        })
    return results
