"""Turns a real ItineraryOutcome into plain-language UI copy.

Template-based off the actual VerificationResult fields -- every check's
`detail` string is already human-readable and was generated from real
compared values (see verification_agent.py), so this module never invents
copy; it only arranges what Verification actually said. No LLM call, no
persona-safety concerns (this UI shows the real per-constraint reasoning
directly, unlike the MCP firewall's chat panel).
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from travel_booking.agents.schemas import ItineraryOutcome, VerificationResult  # noqa: E402

CHECK_LABELS = {
    "arrival_vs_checkin": "Arrival time vs. check-in window",
    "budget": "Total cost vs. budget",
    "amenities": "Required amenities",
    "capacity": "Party size vs. room capacity",
}


def _checklist(result: VerificationResult) -> List[dict]:
    return [
        {"label": CHECK_LABELS[c.name], "passed": c.passed, "detail": c.detail}
        for c in result.checks
    ]


def build_explanation(outcome: ItineraryOutcome) -> dict:
    if outcome.status == "verified":
        result = outcome.verification
        return {
            "headline": "Verified -- this itinerary satisfies every constraint together, not just separately.",
            "status": "verified",
            "checklist": _checklist(result),
            "total_cost": result.total_cost,
        }

    if outcome.closest_attempt:
        result = outcome.closest_attempt
        checklist = _checklist(result)
        failed = [c["label"] for c in checklist if not c["passed"]]
        headline = (
            "Couldn't fully satisfy this request -- here's the closest option and exactly what doesn't match: "
            + "; ".join(failed) + "."
        )
        return {
            "headline": headline,
            "status": "unsatisfiable",
            "checklist": checklist,
            "total_cost": result.total_cost,
        }

    if outcome.constraints.destination_code is None:
        return {
            "headline": (
                f"Couldn't search at all -- \"{outcome.constraints.destination_raw}\" isn't a destination "
                "this system currently serves (only Austin, Denver, and Miami)."
            ),
            "status": "unsatisfiable",
            "checklist": [],
            "total_cost": None,
        }

    return {
        "headline": "Couldn't find or verify any combination for this request.",
        "status": "unsatisfiable",
        "checklist": [],
        "total_cost": None,
    }
