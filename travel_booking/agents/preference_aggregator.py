"""Combines a group's individually-submitted preferences into one set of
search constraints, using a multi-armed bandit -- a real, honestly-scoped
reinforcement learning technique, not a stand-in for deep RL.

Why a bandit, not deep RL: combining N people's budget/amenity trade-offs
into one search is a strategy-SELECTION problem (which of a few well-
defined compromise strategies to use), not a sequential decision process
needing a learned policy over a large state space. A contextual/multi-armed
bandit is the standard RL tool for exactly this shape of problem: a small
set of discrete "arms" (strategies), a reward signal (did the group accept
the resulting trip), and online learning from that feedback -- with none of
deep RL's requirements (a simulator, a training corpus, a neural policy)
that this project genuinely doesn't have. This is the same "explicit,
inspectable, no black box" discipline as the rest of this project's agents
(see verification_agent.py) applied to a genuinely stochastic-selection
problem, where it actually is the appropriate tool.

Group members submit STRUCTURED preferences (budget/dates/amenities via a
form), not freeform text -- this whole module runs with zero Bedrock calls,
deliberately, so trying group trips doesn't compete with the session's
Bedrock budget at all.
"""
from __future__ import annotations

import random
import sys
from datetime import date
from pathlib import Path
from typing import List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from travel_booking.db import get_connection  # noqa: E402

EPSILON = 0.15  # exploration rate: fraction of the time we try a non-greedy arm

ARMS = ("conservative", "balanced", "generous")
ARM_DESCRIPTIONS = {
    "conservative": "tightest budget across the group, only amenities everyone asked for",
    "balanced": "average budget across the group, amenities most of the group asked for",
    "generous": "loosest budget across the group, any amenity anyone asked for",
}


class MemberPreference:
    def __init__(self, date_range_start: str, date_range_end: str, party_size: int,
                 budget_amount: Optional[float], budget_scope: str, required_amenities: List[str]):
        self.date_range_start = date_range_start
        self.date_range_end = date_range_end
        self.party_size = party_size
        self.budget_amount = budget_amount
        self.budget_scope = budget_scope
        self.required_amenities = required_amenities


def _intersect_dates(members: List[MemberPreference]) -> tuple[str, str]:
    """Overlapping date range across every member. Falls back to the widest
    member's range if there's genuinely no overlap (search will then likely
    come back unsatisfiable, honestly, rather than silently picking one
    person's dates over everyone else's)."""
    starts = [date.fromisoformat(m.date_range_start) for m in members]
    ends = [date.fromisoformat(m.date_range_end) for m in members]
    latest_start, earliest_end = max(starts), min(ends)
    if latest_start > earliest_end:
        # no real overlap -- use the union instead of pretending one exists
        return min(starts).isoformat(), max(ends).isoformat()
    return latest_start.isoformat(), earliest_end.isoformat()


def _select_arm() -> str:
    """Epsilon-greedy: explore a random arm EPSILON of the time, otherwise
    exploit the arm with the best observed reward rate so far."""
    conn = get_connection()
    try:
        rows = {r["strategy"]: r for r in conn.execute("SELECT * FROM bandit_arm_stats").fetchall()}
    finally:
        conn.close()

    if random.random() < EPSILON or not rows:
        return random.choice(ARMS)

    def reward_rate(arm: str) -> float:
        row = rows.get(arm)
        if row is None or row["times_chosen"] == 0:
            return 0.5  # unseen arm -- optimistic default, matches standard bandit init
        return row["times_rewarded"] / row["times_chosen"]

    return max(ARMS, key=reward_rate)


def record_chosen(strategy: str) -> None:
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO bandit_arm_stats (strategy, times_chosen, times_rewarded) VALUES (?, 1, 0)
               ON CONFLICT(strategy) DO UPDATE SET times_chosen = times_chosen + 1""",
            (strategy,),
        )
        conn.commit()
    finally:
        conn.close()


def record_reward(strategy: str, accepted: bool) -> None:
    """Real feedback signal: did the group actually keep/accept the trip
    this strategy produced? Called from the group's feedback endpoint."""
    if not accepted:
        return
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO bandit_arm_stats (strategy, times_chosen, times_rewarded) VALUES (?, 0, 1)
               ON CONFLICT(strategy) DO UPDATE SET times_rewarded = times_rewarded + 1""",
            (strategy,),
        )
        conn.commit()
    finally:
        conn.close()


def aggregate(members: List[MemberPreference]) -> dict:
    """Returns {strategy, date_range_start, date_range_end, party_size,
    budget_amount, budget_scope, required_amenities} -- ready to build a
    ResolvedConstraints from, no Bedrock call involved."""
    if not members:
        raise ValueError("aggregate() needs at least 1 member preference")

    strategy = _select_arm()
    record_chosen(strategy)

    date_start, date_end = _intersect_dates(members)
    party_size = sum(m.party_size for m in members)

    budgets = [m.budget_amount for m in members if m.budget_amount is not None]
    if strategy == "conservative":
        budget_amount = min(budgets) if budgets else None
    elif strategy == "generous":
        budget_amount = max(budgets) if budgets else None
    else:
        budget_amount = round(sum(budgets) / len(budgets), 2) if budgets else None
    # Scope: if anyone said total_trip, treat the aggregate as total_trip
    # (a per-night budget from one member can't safely be reinterpreted as a
    # group total without misrepresenting what they actually said).
    budget_scope = "total_trip" if any(m.budget_scope == "total_trip" for m in members) else "per_night_hotel"

    amenity_counts: dict[str, int] = {}
    for m in members:
        for a in m.required_amenities:
            amenity_counts[a] = amenity_counts.get(a, 0) + 1
    n = len(members)
    if strategy == "generous":
        required_amenities = list(amenity_counts.keys())
    elif strategy == "conservative":
        required_amenities = [a for a, c in amenity_counts.items() if c == n]
    else:
        required_amenities = [a for a, c in amenity_counts.items() if c > n / 2]

    return {
        "strategy": strategy,
        "strategy_description": ARM_DESCRIPTIONS[strategy],
        "date_range_start": date_start,
        "date_range_end": date_end,
        "party_size": party_size,
        "budget_amount": budget_amount,
        "budget_scope": budget_scope,
        "required_amenities": required_amenities,
    }
