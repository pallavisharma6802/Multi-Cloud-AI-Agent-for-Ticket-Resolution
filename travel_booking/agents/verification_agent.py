"""Verification Agent: does a PROPOSED hotel+flight combination actually
satisfy every hard constraint TOGETHER, not each in isolation?

Deterministic, not an LLM call -- see travel_booking/BUILD_LOG.md for why.
Every check is 100% mechanically decidable from the structured data, so an
LLM judgment call would add nothing but latency, cost, and hallucination
risk. Four explicit per-field checks, each returned individually -- never
collapsed into one holistic verdict. This is the direct fix for the exact
bug class the MCP firewall project found and fixed (a single coarse
judgment instead of forced per-field reasoning).
"""
from __future__ import annotations

import sys
from datetime import time as dtime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from travel_booking.agents.schemas import CheckResult, ResolvedConstraints, VerificationResult  # noqa: E402


def _parse_hhmm(s: str) -> dtime:
    h, m = s.split(":")
    return dtime(int(h), int(m))


def check_arrival_vs_checkin(hotel: dict, flight: dict) -> CheckResult:
    if hotel.get("front_desk_24hr") is None and hotel.get("front_desk_closes") is None:
        # Real data source (e.g. SerpApi/Google Hotels) doesn't expose front-desk
        # hours at all -- don't invent a proxy check, be honest that this can't
        # be verified rather than silently passing it off as checked.
        return CheckResult(
            name="arrival_vs_checkin",
            passed=True,
            data_available=False,
            detail=f"{hotel.get('name', 'This hotel')}'s front-desk hours aren't available from this data "
            f"source, so whether the {flight['arrival_time']} arrival on {flight['flight_number']} can "
            f"actually check in couldn't be verified.",
            expected="front-desk hours data",
            actual="not available from this data source",
        )
    if hotel["front_desk_24hr"]:
        return CheckResult(
            name="arrival_vs_checkin",
            passed=True,
            detail=f"{hotel['name']} has a 24-hour front desk, so the {flight['arrival_time']} arrival "
            f"on {flight['flight_number']} can check in at any time.",
            expected="front desk staffed at arrival time (24hr desk)",
            actual="front_desk_24hr=true",
        )

    desk_closes = hotel["front_desk_closes"]
    if flight["arrives_next_day"]:
        return CheckResult(
            name="arrival_vs_checkin",
            passed=False,
            detail=f"{flight['flight_number']} arrives at {flight['arrival_time']} the NEXT day (after "
            f"midnight); {hotel['name']}'s front desk closes at {desk_closes} and is not staffed "
            f"overnight, so no one can check the guest in.",
            expected=f"arrival at or before {desk_closes}, same day",
            actual=f"arrival {flight['arrival_time']} (next day)",
        )

    arrival = _parse_hhmm(flight["arrival_time"])
    closes = _parse_hhmm(desk_closes)
    passed = arrival <= closes
    return CheckResult(
        name="arrival_vs_checkin",
        passed=passed,
        detail=(
            f"{flight['flight_number']} arrives at {flight['arrival_time']}, {hotel['name']}'s front "
            f"desk closes at {desk_closes} -- "
            + ("arrival is before the desk closes." if passed else "arrival is AFTER the desk closes.")
        ),
        expected=f"arrival at or before {desk_closes}",
        actual=f"arrival {flight['arrival_time']}",
    )


def compute_total_cost(hotel: dict, flight: dict, constraints: ResolvedConstraints) -> float:
    flight_total = flight["price"] * constraints.party_size
    hotel_nightly = hotel["price_per_night"] + (hotel.get("resort_fee_per_night") or 0)
    hotel_total = hotel_nightly * constraints.nights
    return round(flight_total + hotel_total, 2)


def check_budget(hotel: dict, flight: dict, constraints: ResolvedConstraints) -> CheckResult:
    total_cost = compute_total_cost(hotel, flight, constraints)
    hotel_nightly = hotel["price_per_night"] + (hotel.get("resort_fee_per_night") or 0)

    if constraints.budget_amount is None:
        return CheckResult(
            name="budget",
            passed=True,
            detail=f"No budget was stated; total trip cost would be ${total_cost:.2f} "
            f"(flight ${flight['price']}x{constraints.party_size} + hotel ${hotel_nightly:.2f}/night "
            f"x{constraints.nights} nights).",
            expected="no budget stated",
            actual=f"${total_cost:.2f} total",
        )

    if constraints.budget_scope == "per_night_hotel":
        passed = hotel_nightly <= constraints.budget_amount
        fee_note = ""
        if hotel.get("resort_fee_per_night"):
            fee_note = (
                f" (${hotel['price_per_night']} listed rate + ${hotel['resort_fee_per_night']} "
                f"mandatory resort fee)"
            )
        return CheckResult(
            name="budget",
            passed=passed,
            detail=(
                f"Effective hotel rate is ${hotel_nightly:.2f}/night{fee_note} against a stated budget "
                f"of ${constraints.budget_amount:.2f}/night -- "
                + ("within budget." if passed else "OVER budget.")
            ),
            expected=f"<= ${constraints.budget_amount:.2f}/night",
            actual=f"${hotel_nightly:.2f}/night",
        )

    # total_trip (or unspecified scope with a stated amount -- treat as total)
    passed = total_cost <= constraints.budget_amount
    return CheckResult(
        name="budget",
        passed=passed,
        detail=(
            f"Total trip cost is ${total_cost:.2f} (flight ${flight['price']} x "
            f"{constraints.party_size} travelers + hotel ${hotel_nightly:.2f}/night x "
            f"{constraints.nights} nights) against a stated total budget of "
            f"${constraints.budget_amount:.2f} -- "
            + ("within budget." if passed else "OVER budget.")
        ),
        expected=f"<= ${constraints.budget_amount:.2f} total",
        actual=f"${total_cost:.2f} total",
    )


def check_hotel_only_budget(hotel: dict, constraints: ResolvedConstraints) -> CheckResult:
    """Budget check for browsing hotels with no paired flight -- there's no
    total-trip cost to compute without one, so this only ever checks the
    hotel's own nightly/stay cost, never claiming to check a "total" that
    isn't knowable yet."""
    hotel_nightly = hotel["price_per_night"] + (hotel.get("resort_fee_per_night") or 0)
    fee_note = ""
    if hotel.get("resort_fee_per_night"):
        fee_note = f" (${hotel['price_per_night']} listed rate + ${hotel['resort_fee_per_night']} mandatory resort fee)"

    if constraints.budget_amount is None:
        return CheckResult(
            name="budget", passed=True,
            detail=f"No budget was stated; this hotel is ${hotel_nightly:.2f}/night{fee_note}.",
            expected="no budget stated", actual=f"${hotel_nightly:.2f}/night",
        )

    if constraints.budget_scope == "per_night_hotel":
        passed = hotel_nightly <= constraints.budget_amount
        return CheckResult(
            name="budget", passed=passed,
            detail=f"Effective hotel rate is ${hotel_nightly:.2f}/night{fee_note} against a stated budget "
            f"of ${constraints.budget_amount:.2f}/night -- " + ("within budget." if passed else "OVER budget."),
            expected=f"<= ${constraints.budget_amount:.2f}/night", actual=f"${hotel_nightly:.2f}/night",
        )

    stay_total = hotel_nightly * constraints.nights
    passed = stay_total <= constraints.budget_amount
    return CheckResult(
        name="budget", passed=passed,
        detail=f"{constraints.nights} nights at ${hotel_nightly:.2f}/night{fee_note} = ${stay_total:.2f} "
        f"(hotel only, no flight priced yet) against a stated total budget of ${constraints.budget_amount:.2f} -- "
        + ("within budget." if passed else "OVER budget, before a flight is even added."),
        expected=f"<= ${constraints.budget_amount:.2f} for the stay", actual=f"${stay_total:.2f} for the stay",
    )


# Real data sources (e.g. SerpApi/Google Hotels) return free-text amenity names
# ("Outdoor pool", "Free Wi-Fi") instead of the simulated dataset's exact controlled
# vocabulary -- match by substring against these known real-world phrasings.
_AMENITY_SYNONYMS = {
    "wifi": ["wifi", "wi-fi"],
    "pool": ["pool"],
    "gym": ["gym", "fitness"],
    "parking": ["parking"],
    "breakfast": ["breakfast"],
    "pet_friendly": ["pet-friendly", "pet friendly", "pets allowed"],
    "family_friendly": ["kid-friendly", "kid friendly", "family-friendly", "family friendly"],
}


def _amenity_present(required: str, hotel_amenities: list[str]) -> bool:
    if required in hotel_amenities:  # exact match -- simulated dataset's controlled vocabulary
        return True
    synonyms = _AMENITY_SYNONYMS.get(required, [required])
    lowered = [a.lower() for a in hotel_amenities]
    return any(syn in a for a in lowered for syn in synonyms)


def check_amenities(hotel: dict, constraints: ResolvedConstraints) -> CheckResult:
    if not constraints.required_amenities:
        return CheckResult(
            name="amenities",
            passed=True,
            detail="No specific amenities were required.",
            expected="(none required)",
            actual=f"hotel offers: {', '.join(hotel['amenities'])}",
        )

    missing = []
    unavailable = []
    for a in constraints.required_amenities:
        if not _amenity_present(a, hotel["amenities"]):
            missing.append(a)
        elif a in hotel.get("amenity_notes", {}):
            unavailable.append((a, hotel["amenity_notes"][a]))

    passed = not missing and not unavailable
    problems = []
    if missing:
        problems.append(f"not offered at all: {', '.join(missing)}")
    if unavailable:
        problems.append("; ".join(f"'{a}' is tagged but unavailable -- {note}" for a, note in unavailable))

    detail = (
        f"All required amenities ({', '.join(constraints.required_amenities)}) are present and available."
        if passed
        else f"Problem with required amenities: {'; '.join(problems)}."
    )
    return CheckResult(
        name="amenities",
        passed=passed,
        detail=detail,
        expected=f"present and available: {', '.join(constraints.required_amenities)}",
        actual=f"hotel tags: {', '.join(hotel['amenities'])}; notes: {hotel.get('amenity_notes') or '(none)'}",
    )


def check_capacity(hotel: dict, constraints: ResolvedConstraints) -> CheckResult:
    if hotel.get("max_occupancy") is None:
        return CheckResult(
            name="capacity",
            passed=True,
            data_available=False,
            detail=f"Room-capacity data isn't available from this data source, so whether a party of "
            f"{constraints.party_size} fits at {hotel.get('name', 'this hotel')} couldn't be verified.",
            expected=f"max_occupancy >= {constraints.party_size}",
            actual="not available from this data source",
        )
    passed = constraints.party_size <= hotel["max_occupancy"]
    return CheckResult(
        name="capacity",
        passed=passed,
        detail=(
            f"Party of {constraints.party_size} against {hotel['name']}'s max occupancy of "
            f"{hotel['max_occupancy']} -- "
            + ("fits." if passed else "does NOT fit.")
        ),
        expected=f"max_occupancy >= {constraints.party_size}",
        actual=f"max_occupancy={hotel['max_occupancy']}",
    )


class VerificationAgent:
    """Runs all four hard checks on one proposed (hotel, flight) combination."""

    def verify(self, hotel: dict, flight: dict, constraints: ResolvedConstraints) -> VerificationResult:
        checks = [
            check_arrival_vs_checkin(hotel, flight),
            check_budget(hotel, flight, constraints),
            check_amenities(hotel, constraints),
            check_capacity(hotel, constraints),
        ]
        return VerificationResult(
            hotel_id=hotel["id"],
            flight_id=flight["id"],
            passed=all(c.passed for c in checks),
            checks=checks,
            total_cost=compute_total_cost(hotel, flight, constraints),
        )
