"""Combines a group's individually-submitted preferences into one set of
search constraints, using an epsilon-greedy multi-armed bandit to pick
between conservative/balanced/generous strategies. Members submit
structured preferences via a form, not freeform text, so this runs with
zero Bedrock calls.
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
    "conservative": "tightest budget across the group, shortest trip length, only amenities everyone asked for",
    "balanced": "average budget and trip length across the group, amenities most of the group asked for",
    "generous": "loosest budget across the group, longest trip length, any amenity anyone asked for",
}


class MemberPreference:
    def __init__(self, date_range_start: str, date_range_end: str, party_size: int,
                 budget_amount: Optional[float], budget_scope: str, required_amenities: List[str],
                 nights: int = 3):
        self.date_range_start = date_range_start
        self.date_range_end = date_range_end
        self.party_size = party_size
        self.budget_amount = budget_amount
        self.budget_scope = budget_scope
        self.required_amenities = required_amenities
        # trip length, kept separate from the availability window -- deriving
        # one from the other produced badly wrong stays
        self.nights = nights


def _intersect_dates(members: List[MemberPreference]) -> tuple[str, str, Optional[str]]:
    """Overlapping availability window across every member. Returns (start,
    end, warning) -- falls back to the union of everyone's windows if there's
    no real overlap, with a warning rather than searching silently."""
    starts = [date.fromisoformat(m.date_range_start) for m in members]
    ends = [date.fromisoformat(m.date_range_end) for m in members]
    latest_start, earliest_end = max(starts), min(ends)
    if latest_start > earliest_end:
        return (
            min(starts).isoformat(),
            max(ends).isoformat(),
            "Your group's available dates don't actually overlap, so this searched everyone's "
            "combined window instead. Agree on shared dates for a result everyone can make.",
        )
    return latest_start.isoformat(), earliest_end.isoformat(), None


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
               ON CONFLICT(strategy) DO UPDATE SET times_chosen = bandit_arm_stats.times_chosen + 1""",
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
               ON CONFLICT(strategy) DO UPDATE SET times_rewarded = bandit_arm_stats.times_rewarded + 1""",
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
    warnings: List[str] = []

    date_start, date_end, date_warning = _intersect_dates(members)
    if date_warning:
        warnings.append(date_warning)
    party_size = sum(m.party_size for m in members)

    # Trip length is a real preference trade-off between members, so it's
    # decided by the same strategy arm as budget/amenities rather than by an
    # arbitrary fixed rule.
    nights_requested = [max(1, m.nights) for m in members]
    if strategy == "conservative":
        nights = min(nights_requested)
    elif strategy == "generous":
        nights = max(nights_requested)
    else:
        nights = round(sum(nights_requested) / len(nights_requested))
    nights = max(1, int(nights))
    if len(set(nights_requested)) > 1:
        warnings.append(
            f"Group members asked for different trip lengths ({min(nights_requested)}-"
            f"{max(nights_requested)} nights); the '{strategy}' strategy used {nights}."
        )

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
        "nights": nights,
        "party_size": party_size,
        "budget_amount": budget_amount,
        "budget_scope": budget_scope,
        "required_amenities": required_amenities,
        "warnings": warnings,
    }
