"""Scores verified hotel+flight pairs so results can be ranked by more than
price. Every hard constraint (budget/amenities/capacity/arrival) is already
enforced by verification_agent.py before a pair gets here -- this only
decides ordering among pairs that already passed.

Four components, each normalized to roughly [0, 1] across the candidate
pool being ranked:
- price: cheaper relative to the rest of the pool scores higher
- quality: hotel rating (missing rating gets a neutral default, not a penalty)
- convenience: nonstop flight + buffer time before the hotel's front desk
  closes (a 20-minute buffer is riskier than a 4-hour one, even though both
  technically pass the hard arrival check)
- amenities: bonus for amenities offered beyond what was required

Weight presets let the UI expose a real sort control instead of one hidden
heuristic.
"""
from __future__ import annotations

from datetime import time as dtime
from typing import NamedTuple, Optional

from travel_booking.agents.schemas import KNOWN_AMENITIES, ResolvedConstraints

WEIGHT_PRESETS = {
    "best_value": {"price": 0.35, "quality": 0.30, "convenience": 0.20, "amenities": 0.15},
    "cheapest": {"price": 1.0, "quality": 0.0, "convenience": 0.0, "amenities": 0.0},
    "highest_rated": {"price": 0.10, "quality": 0.70, "convenience": 0.10, "amenities": 0.10},
    "most_convenient": {"price": 0.15, "quality": 0.15, "convenience": 0.60, "amenities": 0.10},
}
DEFAULT_PRESET = "best_value"

MAX_CONVENIENCE_BUFFER_MINUTES = 240  # a 4+ hour cushion before desk-close is "fully convenient"


class ScoredCandidate(NamedTuple):
    score: float
    components: dict  # {"price": .., "quality": .., "convenience": .., "amenities": ..} -- unweighted, for eval/debugging
    hotel: dict
    flight: dict


def _parse_hhmm(s: str) -> Optional[dtime]:
    try:
        h, m = s.split(":")
        return dtime(int(h), int(m))
    except (ValueError, AttributeError):
        return None


def _quality_component(hotel: dict) -> float:
    rating = hotel.get("rating")
    if rating is None:
        return 0.6  # neutral default -- missing data shouldn't read as "bad"
    return max(0.0, min(1.0, rating / 5.0))


def _convenience_component(hotel: dict, flight: dict) -> float:
    nonstop_bonus = 0.3 if flight.get("layovers", 0) == 0 else 0.0

    if hotel.get("front_desk_24hr"):
        buffer_score = 0.7
    else:
        closes = _parse_hhmm(hotel.get("front_desk_closes") or "")
        arrival = _parse_hhmm(flight.get("arrival_time") or "")
        if closes is None or arrival is None or flight.get("arrives_next_day"):
            buffer_score = 0.35  # can't compute a real buffer -- neutral, not a penalty
        else:
            buffer_minutes = (closes.hour * 60 + closes.minute) - (arrival.hour * 60 + arrival.minute)
            buffer_score = 0.7 * max(0.0, min(1.0, buffer_minutes / MAX_CONVENIENCE_BUFFER_MINUTES))

    return min(1.0, nonstop_bonus + buffer_score)


def _amenities_component(hotel: dict, constraints: ResolvedConstraints) -> float:
    offered = {a.lower() for a in hotel.get("amenities", [])}
    required = {a.lower() for a in constraints.required_amenities}
    extras = 0
    for known in KNOWN_AMENITIES:
        if known in required:
            continue
        if any(known.replace("_", " ") in o or known in o for o in offered):
            extras += 1
    return min(1.0, extras / 3.0)


def score_candidates(
    candidates: list[tuple[dict, dict]],
    constraints: ResolvedConstraints,
    preset: str = DEFAULT_PRESET,
) -> list[ScoredCandidate]:
    """Scores a batch of (hotel, flight) pairs together. Price is scored as
    percent-more-expensive-than-the-cheapest-in-the-pool, NOT pool min/max
    normalization -- min/max turns any price gap, even a real-dollar-terms-
    tiny one, into a full 1.0-vs-0.0 swing whenever a pool's absolute spread
    happens to be small, which drowned out every other signal for pools of
    similarly-priced options (caught by eval/battery.py's ranking scenarios)."""
    weights = WEIGHT_PRESETS.get(preset, WEIGHT_PRESETS[DEFAULT_PRESET])

    from travel_booking.agents.verification_agent import compute_total_cost

    totals = [compute_total_cost(h, f, constraints) for h, f in candidates]
    cheapest = min(totals)

    scored = []
    for (hotel, flight), total in zip(candidates, totals):
        if cheapest <= 0:
            price_component = 1.0 if total <= 0 else 0.0
        else:
            pct_above_cheapest = (total - cheapest) / cheapest
            price_component = max(0.0, 1.0 - pct_above_cheapest)
        components = {
            "price": price_component,
            "quality": _quality_component(hotel),
            "convenience": _convenience_component(hotel, flight),
            "amenities": _amenities_component(hotel, constraints),
        }
        score = sum(weights[k] * v for k, v in components.items())
        scored.append(ScoredCandidate(score=score, components=components, hotel=hotel, flight=flight))

    scored.sort(key=lambda c: c.score, reverse=True)
    return scored
