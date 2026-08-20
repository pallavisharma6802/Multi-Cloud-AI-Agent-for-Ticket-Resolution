"""Two deterministic evals against hand-crafted fixtures -- no Bedrock,
SerpApi, or Pinecone calls, so this is fast, free, and reproducible in CI.

1. Verification correctness: does the 4-check verifier catch every
   deliberately-planted trap (a resort fee, a tag that's actually
   unavailable, a late arrival, an over-capacity room) without also
   flagging clean combinations? Reports precision/recall/catch-rate over
   named checks, not a single pass/fail count.

2. Ranking quality: score_candidates() sorting a pool by its own score is a
   tautology (of course the top score is the top score) -- so each ranking
   scenario instead hand-designs which candidate SHOULD win under a given
   preset (e.g. "best_value" should pick the well-rounded mid-price option,
   not the cheapest dump or the priciest suite) and checks whether it does.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from travel_booking.agents import ranking  # noqa: E402
from travel_booking.agents.schemas import ResolvedConstraints  # noqa: E402
from travel_booking.agents.verification_agent import VerificationAgent  # noqa: E402

EVAL_DIR = Path(__file__).resolve().parent
RESULTS_PATH = EVAL_DIR / "battery_results.jsonl"
SUMMARY_PATH = EVAL_DIR / "summary.json"


def _constraints(**overrides) -> ResolvedConstraints:
    base = dict(
        destination_code="AUS", destination_raw="Austin", party_size=2, nights=3,
        nights_defaulted=False, date_range_start="2026-10-05", date_range_end="2026-10-08",
        dates_defaulted=False, budget_amount=2000.0, budget_scope="total_trip",
        required_amenities=[], raw_request="eval", assumptions=[],
    )
    base.update(overrides)
    return ResolvedConstraints(**base)


def _hotel(**overrides) -> dict:
    base = dict(
        id="H1", name="Test Hotel", destination="AUS", destination_name="Austin, TX",
        price_per_night=100, resort_fee_per_night=0, check_in_time="15:00",
        front_desk_24hr=True, front_desk_closes=None, check_out_time="11:00",
        max_occupancy=4, amenities=["wifi", "pool"], amenity_notes={}, rating=4.0,
    )
    base.update(overrides)
    return base


def _flight(**overrides) -> dict:
    base = dict(
        id="F1", origin="ORD", destination="AUS", date="2026-10-05", airline="Test Air",
        flight_number="TA1", departure_time="08:00", arrival_time="10:45",
        arrives_next_day=False, price=200, layovers=0,
    )
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# 1. Verification correctness
# ---------------------------------------------------------------------------

@dataclass
class VerificationScenario:
    id: str
    hotel: dict
    flight: dict
    constraints: ResolvedConstraints
    expected_failed: set  # check names that MUST fail
    expected_unverifiable: set = field(default_factory=set)  # check names that must be data_available=False
    note: str = ""


VERIFICATION_SCENARIOS = [
    VerificationScenario(
        "clean_pass", _hotel(), _flight(), _constraints(),
        expected_failed=set(), note="nothing should trip",
    ),
    VerificationScenario(
        "clean_pass_family", _hotel(max_occupancy=6, amenities=["wifi", "pool", "family_friendly"]),
        _flight(), _constraints(party_size=5, required_amenities=["pool", "family_friendly"]),
        expected_failed=set(), note="larger party, more required amenities, still clean",
    ),
    VerificationScenario(
        "amenity_tagged_but_unavailable",
        _hotel(amenity_notes={"pool": "Closed for renovation."}), _flight(),
        _constraints(required_amenities=["pool"]),
        expected_failed={"amenities"}, note="tag present, note says otherwise",
    ),
    VerificationScenario(
        "resort_fee_breaks_per_night_budget",
        _hotel(price_per_night=189, resort_fee_per_night=35), _flight(),
        _constraints(budget_amount=200.0, budget_scope="per_night_hotel"),
        expected_failed={"budget"}, note="headline rate is in budget, effective rate isn't",
    ),
    VerificationScenario(
        "late_arrival_desk_closed",
        _hotel(front_desk_24hr=False, front_desk_closes="22:00"), _flight(arrival_time="23:55"),
        _constraints(), expected_failed={"arrival_vs_checkin"},
    ),
    VerificationScenario(
        "next_day_arrival_looks_early",
        _hotel(front_desk_24hr=False, front_desk_closes="22:00"),
        _flight(arrival_time="00:05", arrives_next_day=True),
        _constraints(), expected_failed={"arrival_vs_checkin"},
        note="00:05 is numerically before 22:00; only +1-day flag makes it wrong",
    ),
    VerificationScenario(
        "capacity_trap",
        _hotel(max_occupancy=2), _flight(), _constraints(party_size=4),
        expected_failed={"capacity"},
    ),
    VerificationScenario(
        "real_data_gaps_are_unverifiable_not_passed",
        _hotel(front_desk_24hr=None, front_desk_closes=None, max_occupancy=None), _flight(),
        _constraints(), expected_failed=set(),
        expected_unverifiable={"arrival_vs_checkin", "capacity"},
        note="missing fields must report data_available=False, never a silent pass",
    ),
    VerificationScenario(
        "fuzzy_real_world_amenity_names",
        _hotel(amenities=["Outdoor pool", "Free Wi-Fi", "Fitness center"]), _flight(),
        _constraints(required_amenities=["pool", "wifi", "gym"]),
        expected_failed=set(), note="SerpApi free text should still match the controlled vocabulary",
    ),
    VerificationScenario(
        "double_trap_amenity_and_capacity",
        _hotel(max_occupancy=2, amenity_notes={"pool": "Seasonal, closed in October."}),
        _flight(), _constraints(party_size=5, required_amenities=["pool"]),
        expected_failed={"amenities", "capacity"}, note="two independent failures at once",
    ),
    VerificationScenario(
        "over_total_budget_with_return_flight",
        _hotel(price_per_night=150), _flight(price=300, **{"return": {"price": 320, "_source": None}}),
        _constraints(budget_amount=1000.0, budget_scope="total_trip", nights=3),
        expected_failed={"budget"}, note="outbound+return+hotel must all count toward total",
    ),
    VerificationScenario(
        "under_total_budget_with_return_flight",
        _hotel(price_per_night=100), _flight(price=150, **{"return": {"price": 150, "_source": None}}),
        _constraints(budget_amount=1000.0, budget_scope="total_trip", nights=3),
        expected_failed=set(), note="same shape as above, priced to actually fit",
    ),
]


def _run_verification_scenario(s: VerificationScenario) -> dict:
    result = VerificationAgent().verify(s.hotel, s.flight, s.constraints)
    by_name = {c.name: c for c in result.checks}
    actually_failed = {name for name, c in by_name.items() if not c.passed}
    actually_unverifiable = {name for name, c in by_name.items() if not c.data_available}

    failed_match = actually_failed == s.expected_failed
    unverifiable_match = actually_unverifiable == s.expected_unverifiable
    return {
        "id": s.id,
        "note": s.note,
        "expected_failed": sorted(s.expected_failed),
        "actual_failed": sorted(actually_failed),
        "expected_unverifiable": sorted(s.expected_unverifiable),
        "actual_unverifiable": sorted(actually_unverifiable),
        "matched": failed_match and unverifiable_match,
    }


def _verification_metrics(rows: list[dict], scenarios: list[VerificationScenario]) -> dict:
    """Precision/recall over individual named checks across all scenarios,
    not just whole-scenario pass/fail -- a scenario expecting 2 failed
    checks that only catches 1 is a real miss, not a match."""
    tp = fp = fn = 0
    for s, row in zip(scenarios, rows):
        expected = s.expected_failed
        actual = set(row["actual_failed"])
        tp += len(expected & actual)
        fp += len(actual - expected)
        fn += len(expected - actual)
    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    return {
        "true_positive_checks": tp, "false_positive_checks": fp, "false_negative_checks": fn,
        "precision": round(precision, 3), "recall_trap_catch_rate": round(recall, 3),
        "scenarios_fully_matched": sum(r["matched"] for r in rows),
        "scenarios_total": len(rows),
    }


# ---------------------------------------------------------------------------
# 2. Ranking quality -- hand-designed "intended winner" per scenario
# ---------------------------------------------------------------------------

@dataclass
class RankingScenario:
    id: str
    candidates: list  # list of (hotel, flight)
    constraints: ResolvedConstraints
    intended_winner_id: str  # hotel id that SHOULD be #1 under `preset`
    preset: str
    note: str = ""


RANKING_SCENARIOS = [
    RankingScenario(
        "best_value_avoids_the_cheap_dump",
        candidates=[
            (_hotel(id="cheap", price_per_night=60, rating=2.5, amenities=["wifi"]), _flight(layovers=1)),
            (_hotel(id="balanced", price_per_night=110, rating=4.3, amenities=["wifi", "pool", "gym"]), _flight(layovers=0)),
            (_hotel(id="luxury", price_per_night=340, rating=4.8, amenities=["wifi", "pool", "gym", "breakfast"]), _flight(layovers=0)),
        ],
        constraints=_constraints(budget_amount=None),
        intended_winner_id="balanced", preset="best_value",
        note="cheapest is low-rated, priciest is a big premium for marginal gain -- the well-rounded middle option should win",
    ),
    RankingScenario(
        "cheapest_preset_ignores_quality",
        candidates=[
            (_hotel(id="cheap", price_per_night=60, rating=2.5), _flight(layovers=1)),
            (_hotel(id="balanced", price_per_night=110, rating=4.3), _flight(layovers=0)),
        ],
        constraints=_constraints(),
        intended_winner_id="cheap", preset="cheapest",
        note="preset name is a promise -- cheapest must mean cheapest",
    ),
    RankingScenario(
        "highest_rated_preset_ignores_price",
        candidates=[
            (_hotel(id="cheap", price_per_night=60, rating=3.0), _flight()),
            (_hotel(id="best_rated", price_per_night=280, rating=4.9), _flight()),
        ],
        constraints=_constraints(),
        intended_winner_id="best_rated", preset="highest_rated",
    ),
    RankingScenario(
        "most_convenient_prefers_nonstop_and_buffer",
        candidates=[
            (_hotel(id="tight", front_desk_24hr=False, front_desk_closes="21:00", price_per_night=100),
             _flight(layovers=1, arrival_time="20:30")),
            (_hotel(id="easy", front_desk_24hr=False, front_desk_closes="23:00", price_per_night=100),
             _flight(layovers=0, arrival_time="14:00")),
        ],
        constraints=_constraints(),
        intended_winner_id="easy", preset="most_convenient",
        note="nonstop landing 9 hours before the desk closes vs. a layover landing 30 min before",
    ),
    RankingScenario(
        "amenity_match_breaks_a_near_tie",
        candidates=[
            (_hotel(id="bare", price_per_night=120, rating=4.0, amenities=["wifi", "pool"]), _flight()),
            (_hotel(id="loaded", price_per_night=125, rating=4.0, amenities=["wifi", "pool", "gym", "breakfast", "parking"]), _flight()),
        ],
        constraints=_constraints(required_amenities=["pool"]),
        intended_winner_id="loaded", preset="best_value",
        note="same price and rating -- bonus amenities should tip it",
    ),
]


def _run_ranking_scenario(s: RankingScenario) -> dict:
    scored = ranking.score_candidates(s.candidates, s.constraints, preset=s.preset)
    winner = scored[0].hotel["id"]
    return {
        "id": s.id,
        "note": s.note,
        "preset": s.preset,
        "intended_winner": s.intended_winner_id,
        "actual_winner": winner,
        "ranking": [(c.hotel["id"], round(c.score, 3)) for c in scored],
        "matched": winner == s.intended_winner_id,
    }


def _ranking_metrics(rows: list[dict]) -> dict:
    matched = sum(r["matched"] for r in rows)
    return {
        "intended_winner_match_rate": round(matched / len(rows), 3) if rows else None,
        "scenarios_matched": matched,
        "scenarios_total": len(rows),
    }


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_battery() -> dict:
    verification_rows = [_run_verification_scenario(s) for s in VERIFICATION_SCENARIOS]
    ranking_rows = [_run_ranking_scenario(s) for s in RANKING_SCENARIOS]

    summary = {
        "verification": _verification_metrics(verification_rows, VERIFICATION_SCENARIOS),
        "ranking": _ranking_metrics(ranking_rows),
    }

    with RESULTS_PATH.open("w") as f:
        for row in verification_rows:
            f.write(json.dumps({"kind": "verification", **row}) + "\n")
        for row in ranking_rows:
            f.write(json.dumps({"kind": "ranking", **row}) + "\n")
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2) + "\n")

    return summary


if __name__ == "__main__":
    result = run_battery()
    print(json.dumps(result, indent=2))
    v, r = result["verification"], result["ranking"]
    ok = v["scenarios_fully_matched"] == v["scenarios_total"] and r["scenarios_matched"] == r["scenarios_total"]
    if not ok:
        print("\nFAILED -- see", RESULTS_PATH, "for per-scenario detail")
        sys.exit(1)
    print("\nAll scenarios matched.")
