"""Real Google Flights / Google Hotels data via SerpApi.

SerpApi legitimately queries Google's own travel search results and
returns them as structured JSON -- there is no official Google API for
this, SerpApi is the closest real equivalent. Docs verified directly
before writing this (not from memory): https://serpapi.com/google-flights-api
and https://serpapi.com/google-hotels-api.

Requires SERPAPI_API_KEY in .env (free self-serve signup at serpapi.com,
~100-250 free searches/month). Not wired into TravelAgent yet -- this
module is independently callable/testable, but hasn't been given a real
key to verify against live data yet. See travel_booking/BUILD_LOG.md for
the honest list of fields the simulated dataset has that this real API
does NOT provide (front-desk hours, room capacity), and how each of the
4 Verification checks is affected.

IMPORTANT GAPS vs. the simulated dataset (read before wiring this in):
- No front-desk-hours / 24hr-desk field exists in Google Hotels search
  results. arrival_vs_checkin can only compare against check_in_time,
  not "does the desk close before a late arrival" -- that whole trap
  mechanism has no real-data equivalent from this endpoint.
- No room/max-occupancy field in these search results either -- the
  capacity check cannot run against this data as retrieved here.
- Amenities come back as free-text strings ("Air conditioning", "Free
  Wifi"), not a controlled vocabulary -- matched here by substring, not
  exact membership, which is fuzzier than the simulated dataset's exact
  tags.
- A resort-fee-style hidden cost IS naturally observable though:
  comparing rate_per_night vs (total_rate / nights) reveals mandatory
  fees not in the headline nightly rate -- this maps cleanly onto the
  same budget check the simulated dataset's H-AUS-05/H-MIA-03 traps
  exercise, without needing to invent anything.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import requests  # noqa: E402

from app.config import settings  # noqa: E402

BASE_URL = "https://serpapi.com/search"


class SerpApiError(RuntimeError):
    pass


def _get(params: dict) -> dict:
    if not settings.serpapi_api_key:
        raise SerpApiError("SERPAPI_API_KEY is not set in .env -- sign up free at serpapi.com and add it")
    params = {**params, "api_key": settings.serpapi_api_key}
    resp = requests.get(BASE_URL, params=params, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    if data.get("error"):
        raise SerpApiError(data["error"])
    return data


def _to_24h(time_str: Optional[str]) -> Optional[str]:
    """'3:00 PM' -> '15:00'. Returns None if unparseable."""
    if not time_str:
        return None
    m = re.match(r"(\d{1,2}):(\d{2})\s*([AP]M)", time_str.strip(), re.IGNORECASE)
    if not m:
        return None
    hour, minute, ampm = int(m.group(1)), m.group(2), m.group(3).upper()
    if ampm == "PM" and hour != 12:
        hour += 12
    if ampm == "AM" and hour == 12:
        hour = 0
    return f"{hour:02d}:{minute}"


def _split_datetime(dt_str: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """'2026-03-03 10:10' -> ('2026-03-03', '10:10')."""
    if not dt_str:
        return None, None
    parts = dt_str.strip().split(" ")
    if len(parts) != 2:
        return None, None
    return parts[0], parts[1]


def search_flights(
    departure_id: str,
    arrival_id: str,
    outbound_date: str,
    adults: int = 1,
    currency: str = "USD",
) -> List[dict]:
    """Real one-way Google Flights search, normalized toward the same
    shape as data/flights.json (see module docstring for real gaps)."""
    data = _get({
        "engine": "google_flights",
        "departure_id": departure_id,
        "arrival_id": arrival_id,
        "outbound_date": outbound_date,
        "type": 2,  # one-way
        "adults": adults,
        "currency": currency,
        "hl": "en",
        "gl": "us",
    })

    results = []
    for group in ("best_flights", "other_flights"):
        for offer in data.get(group, []):
            legs = offer.get("flights", [])
            if not legs or offer.get("price") is None:
                continue  # can't run the budget check without a price
            first_leg, last_leg = legs[0], legs[-1]
            dep_date, dep_time = _split_datetime(first_leg.get("departure_airport", {}).get("time"))
            arr_date, arr_time = _split_datetime(last_leg.get("arrival_airport", {}).get("time"))
            if not (dep_date and dep_time and arr_date and arr_time):
                continue  # can't run the arrival-time check without parseable times

            results.append({
                "id": offer.get("booking_token") or f"{first_leg.get('flight_number', 'FL')}-{dep_date}",
                "origin": first_leg.get("departure_airport", {}).get("id", departure_id),
                "origin_name": first_leg.get("departure_airport", {}).get("name", ""),
                "destination": last_leg.get("arrival_airport", {}).get("id", arrival_id),
                "destination_name": last_leg.get("arrival_airport", {}).get("name", ""),
                "date": dep_date,
                "airline": first_leg.get("airline", ""),
                "flight_number": first_leg.get("flight_number", ""),
                "departure_time": dep_time,
                "arrival_time": arr_time,
                "arrives_next_day": bool(dep_date and arr_date and arr_date != dep_date),
                "price": offer.get("price"),
                "layovers": max(0, len(legs) - 1),
                "description": f"{first_leg.get('airline', 'Flight')}, {max(0, len(legs) - 1)} stop(s).",
                "image_seed": None,
                "_source": "serpapi_google_flights",
            })
    return results


def search_hotels(
    query: str,
    check_in_date: str,
    check_out_date: str,
    adults: int = 1,
    currency: str = "USD",
) -> List[dict]:
    """Real Google Hotels search, normalized toward the same shape as
    data/hotels.json (see module docstring for real gaps -- notably
    front_desk_24hr/front_desk_closes and max_occupancy are NOT
    available from this endpoint and are returned as None)."""
    from datetime import date as _date

    nights = max(1, (_date.fromisoformat(check_out_date) - _date.fromisoformat(check_in_date)).days)

    data = _get({
        "engine": "google_hotels",
        "q": query,
        "check_in_date": check_in_date,
        "check_out_date": check_out_date,
        "adults": adults,
        "currency": currency,
        "hl": "en",
        "gl": "us",
    })

    results = []
    for h in data.get("properties", []):
        rate = (h.get("rate_per_night") or {}).get("extracted_lowest")
        if rate is None:
            continue  # can't run the budget check without a price -- skip rather than pass a null through
        total = (h.get("total_rate") or {}).get("extracted_lowest")
        resort_fee = None
        if rate is not None and total is not None:
            implied_nightly = total / nights
            diff = round(implied_nightly - rate, 2)
            resort_fee = diff if diff > 0.5 else 0  # ignore rounding noise

        images = h.get("images") or []
        results.append({
            "id": h.get("property_token") or h.get("name", "unknown"),
            "name": h.get("name"),
            "destination_name": query,
            "price_per_night": rate,
            "resort_fee_per_night": resort_fee,
            "resort_fee_inferred": resort_fee is not None,
            "currency": currency,
            "check_in_time": _to_24h(h.get("check_in_time")),
            "front_desk_24hr": None,  # not available from this API -- see module docstring
            "front_desk_closes": None,  # not available from this API -- see module docstring
            "check_out_time": _to_24h(h.get("check_out_time")),
            "max_occupancy": None,  # not available from this API -- see module docstring
            "amenities": h.get("amenities") or [],  # free-text, not the simulated dataset's controlled vocabulary
            "amenity_notes": {},  # not available from this API
            "rating": h.get("overall_rating"),
            "reviews": h.get("reviews"),
            "image_url": images[0].get("thumbnail") if images else None,
            "image_seed": None,
            "_source": "serpapi_google_hotels",
        })
    return results
