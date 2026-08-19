"""Stage 3 test battery: 15 hand-designed scenarios x 2 runs each = 30 real
runs (real Bedrock intent parse, real Pinecone/BM25 search, deterministic
verification). Same format discipline as mcp_firewall's RESULTS.md: real
numbers, saved jsonl + summary, honest about any false positives/negatives.

Every trap scenario is constructed so the trap hotel is the ONLY candidate
that matches the stated amenities within the stated budget/date window --
this forces it into contention deterministically instead of hoping the
semantic ranker surfaces it (Stage 2's smoke tests showed the ranker often
prefers well-rounded clean listings, so relying on chance would under-test
this).
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from travel_booking.agents.orchestrator import TravelAgent  # noqa: E402
from travel_booking.agents.schemas import ItineraryOutcome  # noqa: E402

EVAL_DIR = Path(__file__).resolve().parent
RESULTS_PATH = EVAL_DIR / "battery_results.jsonl"
SUMMARY_PATH = EVAL_DIR / "summary.json"
RUNS_PER_SCENARIO = 2


@dataclass
class Scenario:
    id: str
    category: str  # clean | trap | combo | unsatisfiable
    request: str
    check: Callable[[ItineraryOutcome], dict]
    note: str = ""


def _attempt_for_hotel(outcome: ItineraryOutcome, hotel_id: str):
    for a in outcome.all_attempts:
        if a.hotel_id == hotel_id:
            return a
    if outcome.closest_attempt and outcome.closest_attempt.hotel_id == hotel_id:
        return outcome.closest_attempt
    return None


def _check_result(attempt, name: str) -> Optional[bool]:
    if attempt is None:
        return None
    for c in attempt.checks:
        if c.name == name:
            return c.passed
    return None


# ---------------------------------------------------------------------------
# Scenario checkers -- each returns {"matched": bool, "detail": str}
# ---------------------------------------------------------------------------

def clean_should_verify(outcome: ItineraryOutcome) -> dict:
    matched = outcome.status == "verified"
    return {"matched": matched, "detail": f"status={outcome.status}, attempts={outcome.attempts_tried}"}


def trap_check(hotel_id: str, expected_failed_check: str):
    def _check(outcome: ItineraryOutcome) -> dict:
        attempt = _attempt_for_hotel(outcome, hotel_id)
        if attempt is None:
            return {"matched": False, "detail": f"{hotel_id} never appeared in attempts or closest_attempt -- trap not tried"}
        target = _check_result(attempt, expected_failed_check)
        others_ok = all(
            c.passed for c in attempt.checks if c.name != expected_failed_check
        )
        matched = (target is False) and others_ok
        detail = (
            f"{hotel_id}: {expected_failed_check}={target} (expected False), "
            f"other checks all pass={others_ok}, final status={outcome.status}"
        )
        return {"matched": matched, "detail": detail}
    return _check


def combo_only_failure_check(outcome: ItineraryOutcome) -> dict:
    for a in outcome.all_attempts:
        by_name = {c.name: c.passed for c in a.checks}
        if by_name.get("arrival_vs_checkin") is False and by_name.get("budget") is True and by_name.get("amenities") is True and by_name.get("capacity") is True:
            return {
                "matched": True,
                "detail": f"combination-only failure observed: {a.hotel_id}+{a.flight_id} failed ONLY arrival_vs_checkin, final status={outcome.status}",
            }
    return {
        "matched": False,
        "detail": f"no attempt showed an arrival-only failure (attempts={len(outcome.all_attempts)}), final status={outcome.status}",
    }


def unsatisfiable_no_destination(outcome: ItineraryOutcome) -> dict:
    matched = outcome.status == "unsatisfiable" and outcome.attempts_tried == 0 and outcome.constraints.destination_code is None
    return {"matched": matched, "detail": f"status={outcome.status}, attempts={outcome.attempts_tried}, destination_code={outcome.constraints.destination_code}"}


def unsatisfiable_generic(outcome: ItineraryOutcome) -> dict:
    matched = outcome.status == "unsatisfiable"
    return {"matched": matched, "detail": f"status={outcome.status}, attempts={outcome.attempts_tried}, closest={outcome.closest_attempt.hotel_id if outcome.closest_attempt else None}"}


SCENARIOS = [
    # -- clean (3) --
    Scenario("clean_austin_family", "clean",
             "Family of 4 to Austin, need a pool, 3 nights, Oct 5-8, budget $2000 total",
             clean_should_verify),
    Scenario("clean_denver_solo", "clean",
             "Solo trip to Denver, 3 nights, Oct 10-13, need wifi and gym, budget $250 a night",
             clean_should_verify),
    Scenario("clean_miami_family6", "clean",
             "Family of 6 to Miami, need pool and family_friendly, 4 nights, Oct 8-12, budget $2500 total",
             clean_should_verify),

    # -- trap (7), one per DESIGN.md trap --
    Scenario("trap_aus02_pool_closed", "trap",
             "Party of 2 to Austin, need a pool, budget $150 a night, 3 nights, Oct 5-9",
             trap_check("H-AUS-02", "amenities"),
             "H-AUS-02 is the only Austin pool hotel at or under $150/night"),
    Scenario("trap_aus04_capacity", "trap",
             "Party of 3 to Austin, need family_friendly, budget $130 a night, 3 nights, Oct 5-9",
             trap_check("H-AUS-04", "capacity"),
             "H-AUS-04 is the only Austin family_friendly hotel at or under $130/night"),
    Scenario("trap_aus05_resort_fee", "trap",
             "Party of 4 to Austin, need pool, gym, and pet_friendly, budget $200 a night, 3 nights, Oct 5-9",
             trap_check("H-AUS-05", "budget"),
             "H-AUS-05 is the only Austin hotel with pool+gym+pet_friendly"),
    Scenario("trap_den03_gym_inaccessible", "trap",
             "Party of 2 to Denver, need pool and gym, budget $205 a night, 3 nights, Oct 6-9",
             trap_check("H-DEN-03", "amenities"),
             "H-DEN-06 also has pool+gym but is $220/night, excluded by the $205 budget"),
    Scenario("trap_den05_pet_restricted", "trap",
             "Party of 2 to Denver, need wifi and pet_friendly, budget $200 a night, 3 nights, Oct 6-9, traveling with our dog",
             trap_check("H-DEN-05", "amenities"),
             "H-DEN-05 is the only pet_friendly hotel in Denver"),
    Scenario("trap_mia03_resort_fee", "trap",
             "Party of 2 to Miami, need pool and pet_friendly, budget $240 a night, 3 nights, Oct 8-11",
             trap_check("H-MIA-03", "budget"),
             "H-MIA-03 is the only pool+pet_friendly hotel in Miami"),
    Scenario("trap_mia05_pool_closed", "trap",
             "Party of 2 to Miami, need pool and gym, budget $185 a night, 3 nights, Oct 8-11",
             trap_check("H-MIA-05", "amenities"),
             "H-MIA-06 and H-MIA-03 also have pool+gym but cost more than $185/night"),

    # -- combination-only failures (2) --
    Scenario("combo_aus03_late_arrivals", "combo",
             "Party of 2 to Austin, need family_friendly and gym, no pool needed, budget $220 a night, sometime in October",
             combo_only_failure_check,
             "H-AUS-03 (desk closes 22:00) is the only family_friendly+gym hotel <= $220/night; some AUS flights arrive after 22:00"),
    Scenario("combo_den02_late_arrivals", "combo",
             "Party of 2 to Denver, need family_friendly, budget $180 a night, sometime in October",
             combo_only_failure_check,
             "H-DEN-02 (desk closes 21:00) is the only family_friendly hotel <= $180/night; F-DEN-06 arrives 00:05 next day"),

    # -- unsatisfiable, no valid combination at all (3) --
    Scenario("unsat_blackout_collision", "unsatisfiable",
             "Party of 2 to Austin, need pool, gym, and pet_friendly, budget $300 a night, Oct 19-21",
             unsatisfiable_generic,
             "H-AUS-05 (only pool+gym+pet_friendly match) is blacked out exactly Oct 19-21"),
    Scenario("unsat_no_destination", "unsatisfiable",
             "Family trip to Seattle, need a pool, 3 nights, budget $200 a night",
             unsatisfiable_no_destination,
             "Seattle isn't a served destination (only AUS/DEN/MIA)"),
    Scenario("unsat_impossible_amenity_combo", "unsatisfiable",
             "Party of 2 to Denver, need pool and pet_friendly, budget $300 a night, 3 nights, Oct 6-9",
             unsatisfiable_generic,
             "No Denver hotel has both pool and pet_friendly, regardless of budget"),
]


def run_battery():
    agent = TravelAgent()
    results = []
    bedrock_calls = 0

    for scenario in SCENARIOS:
        for run_idx in range(1, RUNS_PER_SCENARIO + 1):
            outcome = agent.run(scenario.request)
            bedrock_calls += 1
            verdict = scenario.check(outcome)
            record = {
                "scenario_id": scenario.id,
                "category": scenario.category,
                "run_index": run_idx,
                "request": scenario.request,
                "note": scenario.note,
                "status": outcome.status,
                "attempts_tried": outcome.attempts_tried,
                "matched_expectation": verdict["matched"],
                "detail": verdict["detail"],
                "hotel_id": outcome.hotel_record["id"] if outcome.hotel_record else None,
                "flight_id": outcome.flight_record["id"] if outcome.flight_record else None,
                "all_attempts": [a.model_dump() for a in outcome.all_attempts],
                "closest_attempt": outcome.closest_attempt.model_dump() if outcome.closest_attempt else None,
            }
            results.append(record)
            print(f"[{scenario.category:14}] {scenario.id:32} run{run_idx}: matched={verdict['matched']} | {verdict['detail'][:100]}")

    with RESULTS_PATH.open("w") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")

    by_category = {}
    for r in results:
        by_category.setdefault(r["category"], {"total": 0, "matched": 0})
        by_category[r["category"]]["total"] += 1
        if r["matched_expectation"]:
            by_category[r["category"]]["matched"] += 1

    total = len(results)
    matched = sum(1 for r in results if r["matched_expectation"])

    trap_records = [r for r in results if r["category"] == "trap"]
    trap_catch_rate = sum(1 for r in trap_records if r["matched_expectation"]) / len(trap_records) if trap_records else None

    # False positives: a clean scenario that failed to verify, or a trap
    # scenario where a check that should have passed instead failed.
    false_positives = []
    for r in results:
        if r["category"] == "clean" and not r["matched_expectation"]:
            false_positives.append(r)
        if r["category"] == "trap" and not r["matched_expectation"] and "other checks all pass=False" in r["detail"]:
            false_positives.append(r)

    # False negatives (misses): trap scenarios where the expected check did NOT fail.
    false_negatives = [r for r in trap_records if not r["matched_expectation"]]

    summary = {
        "total_runs": total,
        "total_matched_expectation": matched,
        "overall_match_rate": round(matched / total, 3) if total else None,
        "by_category": by_category,
        "trap_catch_rate": round(trap_catch_rate, 3) if trap_catch_rate is not None else None,
        "false_positive_count": len(false_positives),
        "false_positive_scenario_ids": [r["scenario_id"] + f"#{r['run_index']}" for r in false_positives],
        "false_negative_count": len(false_negatives),
        "false_negative_scenario_ids": [r["scenario_id"] + f"#{r['run_index']}" for r in false_negatives],
        "bedrock_calls_used": bedrock_calls,
    }
    with SUMMARY_PATH.open("w") as f:
        json.dump(summary, f, indent=2)

    print("\n=== SUMMARY ===")
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    run_battery()
