"""Intent Agent: freeform travel request -> structured TravelConstraints,
via a multi-turn clarification conversation rather than one-shot parsing.

Direct Bedrock structured call (see travel_booking/BUILD_LOG.md for why this
isn't routed through Azure NLP). Reuses app.llm.bedrock_client.generate_structured
as-is, same pattern as every other agent in this codebase.

Completeness (are dates/budget/party-size specific enough to run the 4 hard
checks against) is evaluated with deterministic code, not the LLM's own
self-assessment -- same "don't trust a holistic self-judgment" principle
applied to the Verification Agent. Each turn re-parses the ENTIRE transcript
(not just the latest message) so a later correction ("actually make that
$250") naturally overrides an earlier answer without manual field-diffing.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from typing import List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.config import settings  # noqa: E402
from app.llm.bedrock_client import LLMCallMetadata, get_llm_client  # noqa: E402

from travel_booking.agents.schemas import (  # noqa: E402
    KNOWN_AMENITIES,
    ClarificationTurn,
    ConversationState,
    ResolvedConstraints,
    TravelConstraints,
)

DEFAULT_NIGHTS = 3
MAX_CLARIFICATION_EXCHANGES = 5
MAX_NARROW_RANGE_DAYS = 10
DATASET_MIN_DATE = "2026-10-01"
DATASET_MAX_DATE = "2026-10-31"

SYSTEM_CONTEXT = f"""You extract structured travel-booking constraints from a conversation between a user \
and a booking assistant. You will be shown the full transcript so far (the user's messages and any \
clarifying questions the assistant already asked). Extract the CURRENT, up-to-date understanding as of the \
end of the transcript -- if a later user message corrects or changes something an earlier message said \
(e.g. earlier: "$200/night", later: "actually make that $250"), the LATER statement wins. Never keep or \
report a value the user has since corrected.

Valid amenity vocabulary (use ONLY these words, map synonyms onto them): {list(KNOWN_AMENITIES)}. \
For example "kid-friendly" or "good for families" -> "family_friendly"; "swimming pool" -> "pool"; \
"dogs allowed" -> "pet_friendly".

The only destinations this system currently serves are Austin TX (AUS), Denver CO (DEN), and Miami FL \
(MIA). If the request names one of these (or an unambiguous synonym like "Austin" or "ATX"), set \
destination_code to it. If it names somewhere else, or doesn't name a destination at all, leave \
destination_code null -- do not guess the closest match.

Dates: this system only has inventory for October 2026. If the user gives an exact date or a narrow range \
(10 days or fewer), set date_range_start/date_range_end to those ISO dates. If they only give a vague \
month/season reference ("sometime in October", "next month") with no narrowing, leave both null -- do NOT \
invent a narrow range yourself. HOWEVER, if the user was asked whether to narrow the dates or search the \
whole month, and they explicitly chose the whole month (e.g. "whole month", "search the whole month", "any \
time works", "no preference", "doesn't matter"), that is a resolved answer, not a missing one -- set \
dates_whole_month_ok=true (leave date_range_start/end null, the whole-month default will be applied in code).

Budget: distinguish carefully between a per-night hotel rate ("under $200/night", "hotel under 150 a \
night") and a total trip budget ("$1500 total", "budget of 2000 for everything"). If the request gives a \
number but the scope is genuinely ambiguous, prefer per_night_hotel only if the word "night" appears near \
the number, otherwise total_trip. If the user references cost with no number at all ("not too expensive", \
"affordable"), leave budget_amount null but set budget_mentioned_vague=true.

Party size: if nothing in the transcript implies more than one traveler, party_size=1 is a safe default \
(not ambiguous). If the text implies a group but never gives a count ("my family", "a few of us", "we"), \
give your best single-integer guess but set party_size_ambiguous=true."""


def _render_transcript(turns: List[ClarificationTurn]) -> str:
    lines = []
    for t in turns:
        speaker = "User" if t.role == "user" else "Assistant"
        lines.append(f"{speaker}: {t.text}")
    return "\n".join(lines)


def _evaluate_completeness(c: TravelConstraints) -> List[str]:
    missing = []
    if c.date_range_start is None or c.date_range_end is None:
        if not c.dates_whole_month_ok:
            missing.append("dates")
    else:
        try:
            span = (date.fromisoformat(c.date_range_end) - date.fromisoformat(c.date_range_start)).days
            if span < 0 or span > MAX_NARROW_RANGE_DAYS:
                missing.append("dates")
        except ValueError:
            missing.append("dates")
    if c.budget_amount is None and c.budget_mentioned_vague:
        missing.append("budget")
    if c.party_size_ambiguous:
        missing.append("party_size")
    return missing


def _next_question(missing: List[str], c: TravelConstraints) -> Optional[str]:
    if "dates" in missing:
        if c.date_range_start:
            return (
                f"You mentioned a window starting around {c.date_range_start} -- can you narrow that to a "
                f"specific range of {MAX_NARROW_RANGE_DAYS} days or fewer, or give an exact date?"
            )
        return "Do you have specific dates in mind (e.g. Oct 10-15), or should I search across the whole month?"
    if "budget" in missing:
        return "What's your budget? A per-night hotel rate (e.g. '$200/night') or a total trip amount both work."
    if "party_size" in missing:
        return "How many people are traveling?"
    return None


def _confirmation_message(r: ResolvedConstraints) -> str:
    parts = [f"a {r.party_size}-person trip", f"{r.date_range_start} to {r.date_range_end}"]
    if r.budget_amount is not None:
        suffix = "/night" if r.budget_scope == "per_night_hotel" else " total"
        parts.append(f"under ${r.budget_amount:.0f}{suffix}")
    if r.required_amenities:
        parts.append(f"need {', '.join(r.required_amenities)}")
    msg = "Got it -- searching for " + ", ".join(parts) + "."
    if r.assumptions:
        msg += " (Assumed: " + "; ".join(r.assumptions) + ".)"
    return msg


class IntentAgent:
    def __init__(self, model: Optional[str] = None):
        self.client = get_llm_client()
        self.model = model or settings.model_travel_intent

    def _parse_transcript(self, transcript: str) -> Tuple[TravelConstraints, LLMCallMetadata]:
        prompt = SYSTEM_CONTEXT + "\n\n--- Conversation so far ---\n" + transcript
        constraints, meta = self.client.generate_structured(
            prompt=prompt,
            schema=TravelConstraints,
            model=self.model,
            role="travel_intent",
            temperature=0.1,
            num_predict=400,
        )
        return constraints, meta

    def _advance(self, state: ConversationState) -> ConversationState:
        transcript = _render_transcript(state.turns)
        constraints, _meta = self._parse_transcript(transcript)
        state.constraints = constraints
        missing = _evaluate_completeness(constraints)

        if not missing:
            state.status = "ready"
            state.pending_question = None
            state.missing = []
            resolved = self.resolve_from_conversation(state)
            state.turns.append(ClarificationTurn(role="agent", text=_confirmation_message(resolved)))
        elif state.exchange_count >= MAX_CLARIFICATION_EXCHANGES:
            state.status = "best_effort"
            state.missing = missing
            state.pending_question = None
            resolved = self.resolve_from_conversation(state)
            state.turns.append(ClarificationTurn(role="agent", text=_confirmation_message(resolved)))
        else:
            state.status = "needs_clarification"
            state.missing = missing
            question = _next_question(missing, constraints)
            state.pending_question = question
            state.turns.append(ClarificationTurn(role="agent", text=question))
        return state

    def start(self, raw_request: str) -> ConversationState:
        state = ConversationState(turns=[ClarificationTurn(role="user", text=raw_request)])
        return self._advance(state)

    def continue_conversation(self, state: ConversationState, user_reply: str) -> ConversationState:
        state.turns.append(ClarificationTurn(role="user", text=user_reply))
        state.exchange_count += 1
        return self._advance(state)

    # -- backward-compatible one-shot entry point (used by battery/tests that
    # don't need the clarification loop, e.g. requests that are already complete) --
    def parse(self, raw_request: str) -> Tuple[TravelConstraints, LLMCallMetadata]:
        return self._parse_transcript(f"User: {raw_request}")

    def resolve_from_conversation(self, state: ConversationState) -> ResolvedConstraints:
        c = state.constraints
        assumptions: List[str] = []

        nights = c.nights
        nights_defaulted = nights is None
        if nights is None:
            nights = DEFAULT_NIGHTS
            assumptions.append(f"no trip length given, assumed {DEFAULT_NIGHTS} nights")

        date_start, date_end = c.date_range_start, c.date_range_end
        dates_defaulted = date_start is None or date_end is None
        if dates_defaulted and c.dates_whole_month_ok:
            date_start, date_end = DATASET_MIN_DATE, DATASET_MAX_DATE
            assumptions.append("searching the whole available month, as you asked")
        elif dates_defaulted:
            date_start, date_end = DATASET_MIN_DATE, DATASET_MAX_DATE
            assumptions.append("no specific dates given, searching the whole available month")
        elif "dates" in state.missing:
            # best_effort cutoff hit with a stated-but-too-wide range -- keep it, just note it
            assumptions.append(f"date range {date_start}..{date_end} was wider than ideal but used as given")

        party_size = c.party_size
        if c.party_size_ambiguous and "party_size" in state.missing:
            assumptions.append(f"party size was ambiguous, assumed {party_size} based on best guess")

        budget_amount = c.budget_amount
        budget_scope = c.budget_scope
        if budget_amount is None and c.budget_mentioned_vague:
            assumptions.append("budget was mentioned vaguely with no number, proceeding without a hard budget check")

        amenities = [a for a in c.required_amenities if a in KNOWN_AMENITIES]

        raw_request = " | ".join(t.text for t in state.turns if t.role == "user")

        return ResolvedConstraints(
            destination_code=c.destination_code,
            destination_raw=c.destination_raw,
            party_size=party_size,
            nights=nights,
            nights_defaulted=nights_defaulted,
            date_range_start=date_start,
            date_range_end=date_end,
            dates_defaulted=dates_defaulted,
            budget_amount=budget_amount,
            budget_scope=budget_scope,
            required_amenities=amenities,
            raw_request=raw_request,
            assumptions=assumptions,
        )

    # -- one-shot helper, e.g. for the battery: fully resolve a single message
    # with no clarification (used only when the request is already known-complete) --
    def resolve(self, raw_request: str, constraints: TravelConstraints) -> ResolvedConstraints:
        state = ConversationState(
            turns=[ClarificationTurn(role="user", text=raw_request)],
            constraints=constraints,
            missing=_evaluate_completeness(constraints),
        )
        return self.resolve_from_conversation(state)
