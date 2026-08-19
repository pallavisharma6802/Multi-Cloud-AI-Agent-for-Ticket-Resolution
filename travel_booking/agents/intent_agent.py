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
from datetime import date, timedelta
from pathlib import Path
from typing import List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.config import settings  # noqa: E402
from app.llm.bedrock_client import LLMCallMetadata, get_llm_client  # noqa: E402

from travel_booking.agents.schemas import (  # noqa: E402
    DEFAULT_ORIGIN_CODE,
    DEFAULT_ORIGIN_NAME,
    DESTINATIONS,
    KNOWN_AMENITIES,
    ClarificationTurn,
    ConversationState,
    ResolvedConstraints,
    TravelConstraints,
)

MAX_CLARIFICATION_EXCHANGES = 5
MAX_NARROW_RANGE_DAYS = 10
# Only meaningful in simulated-dataset mode, where data/flights.json and
# data/hotels.json literally only have rows for this month. In live (serpapi)
# mode there's no such inventory window -- see _default_date_range below,
# which is what actually runs when settings.travel_data_source == "serpapi".
DATASET_MIN_DATE = "2026-10-01"
DATASET_MAX_DATE = "2026-10-31"
LIVE_MODE = settings.travel_data_source == "serpapi"
# Bounds for the "search flexibly for the best day" window in live mode --
# a real scan across this range picks the cheapest workable day (see
# orchestrator._build_candidate_queue_serpapi), not one arbitrary date.
FLEXIBLE_WINDOW_START_DAYS = 10
FLEXIBLE_WINDOW_END_DAYS = 270
# Single-date fallback used ONLY when clarification exchanges ran out without
# the user ever confirming dates or "search flexibly" -- deliberately NOT the
# same as the flexible scan above, since burning several extra live searches
# on a request nobody actually confirmed isn't reasonable.
BEST_EFFORT_DAYS_OUT = 21


def _default_date_range() -> tuple[str, str]:
    """Best-effort single-date fallback (max clarification exchanges hit with
    dates still unresolved). NOT used for the "search flexibly" path -- see
    _flexible_date_range."""
    if LIVE_MODE:
        d = (date.today() + timedelta(days=BEST_EFFORT_DAYS_OUT)).isoformat()
        return d, d
    return DATASET_MIN_DATE, DATASET_MAX_DATE


def _flexible_date_range() -> tuple[str, str]:
    """User explicitly asked us to pick -- a real wide window the orchestrator
    scans for the cheapest workable day, not a single guessed date."""
    if LIVE_MODE:
        start = (date.today() + timedelta(days=FLEXIBLE_WINDOW_START_DAYS)).isoformat()
        end = (date.today() + timedelta(days=FLEXIBLE_WINDOW_END_DAYS)).isoformat()
        return start, end
    return DATASET_MIN_DATE, DATASET_MAX_DATE


SYSTEM_CONTEXT = f"""You extract structured travel-booking constraints from a conversation between a user \
and a booking assistant. You will be shown the full transcript so far (the user's messages and any \
clarifying questions the assistant already asked). Extract the CURRENT, up-to-date understanding as of the \
end of the transcript -- if a later user message corrects or changes something an earlier message said \
(e.g. earlier: "$200/night", later: "actually make that $250"), the LATER statement wins. Never keep or \
report a value the user has since corrected.

Valid amenity vocabulary (use ONLY these words, map synonyms onto them): {list(KNOWN_AMENITIES)}. \
For example "kid-friendly" or "good for families" -> "family_friendly"; "swimming pool" -> "pool"; \
"dogs allowed" -> "pet_friendly".

Origin: if the user says where they're flying FROM (e.g. "flying from Chicago", "departing NYC", "from \
Boston", "I'm in Seattle"), set origin_code to that city's primary airport's IATA code (3 uppercase \
letters) and origin_raw to the phrase they used. If no origin is mentioned at all, leave origin_code and \
origin_raw null -- do NOT assume a default origin, that will be applied honestly in code with a visible \
assumption, not silently guessed here.

Destinations this system has been specifically tuned for: {", ".join(f"{name} ({code})" for code, name in DESTINATIONS.items())}. \
If the request names one of these (or an unambiguous synonym like "Austin" or "ATX"), set destination_code \
to it and destination_name to the display name shown above. This system searches LIVE real-world flight \
and hotel data though, so it is not actually limited to that list -- if the request clearly names another \
real, major world city (e.g. "Rome", "Toronto", "Singapore"), you may still set destination_code to that \
city's primary international airport's IATA code (3 uppercase letters) and destination_name to a clean \
display name, but only when you are confident of the correct airport code. If the destination is unclear, \
ambiguous, or you are not confident of the airport code, leave destination_code and destination_name null \
rather than guessing.

Dates: {"this system searches LIVE flight/hotel availability, so any real future date works -- there is no fixed inventory month." if LIVE_MODE else "this system only has inventory for October 2026."} If the user gives an exact date or a narrow range \
(10 days or fewer), set date_range_start/date_range_end to those ISO dates. If they only give a vague \
month/season reference ("sometime in October", "next month") with no narrowing, leave both null -- do NOT \
invent a narrow range yourself. HOWEVER, if the user was asked whether to narrow the dates or have this \
system search for the cheapest workable day itself, and they explicitly said so (e.g. "whichever is \
cheapest", "find me the best day", "any time works", "no preference", "you pick"), that is a resolved \
answer, not a missing one -- set dates_whole_month_ok=true (leave date_range_start/end null, a real search \
across a wide date window will be run in code, not a single guessed date).

Nights: how many nights the trip should be. If the user gives an exact number ("3 nights", "a week" -> 7, \
"long weekend" -> 3), set nights to that. If trip length genuinely isn't stated or implied anywhere, leave \
nights null -- do NOT silently assume a default length, that will be asked for explicitly.

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
    if c.origin_code is None:
        missing.append("origin")
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
    if c.nights is None:
        missing.append("nights")
    if c.budget_amount is None and c.budget_mentioned_vague:
        missing.append("budget")
    if c.party_size_ambiguous:
        missing.append("party_size")
    return missing


def _next_question(missing: List[str], c: TravelConstraints) -> Optional[str]:
    if "origin" in missing:
        return "Where are you flying from?"
    if "nights" in missing:
        return "How many nights would you like the trip to be?"
    if "dates" in missing:
        if c.date_range_start:
            return (
                f"You mentioned a window starting around {c.date_range_start} -- can you narrow that to a "
                f"specific range of {MAX_NARROW_RANGE_DAYS} days or fewer, or give an exact date?"
            )
        if LIVE_MODE:
            return "Do you have specific dates in mind, or should I search for the cheapest days that work?"
        return "Do you have specific dates in mind (e.g. Oct 10-15), or should I search across the whole month?"
    if "budget" in missing:
        return "What's your budget? A per-night hotel rate (e.g. '$200/night') or a total trip amount both work."
    if "party_size" in missing:
        return "How many people are traveling?"
    return None


def _confirmation_message(r: ResolvedConstraints) -> str:
    when = "the cheapest days I can find" if r.dates_flexible else f"{r.date_range_start} to {r.date_range_end}"
    parts = [f"a {r.party_size}-person trip from {r.origin_name}", when, f"{r.nights} night(s)"]
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

        origin_code = c.origin_code
        origin_name = c.origin_raw or DEFAULT_ORIGIN_NAME
        origin_defaulted = origin_code is None
        if origin_defaulted:
            origin_code = DEFAULT_ORIGIN_CODE
            origin_name = DEFAULT_ORIGIN_NAME
            assumptions.append(f"no origin given, assumed departing from {DEFAULT_ORIGIN_NAME}")

        nights = c.nights
        nights_defaulted = nights is None
        if nights is None:
            # Only reached if MAX_CLARIFICATION_EXCHANGES ran out without the
            # user ever answering "how many nights" -- an honest best-effort
            # fallback, not a silent assumption during normal flow (that
            # question is asked before this can happen -- see _next_question).
            nights = 3
            assumptions.append("no trip length given after asking, assumed 3 nights")

        date_start, date_end = c.date_range_start, c.date_range_end
        dates_defaulted = date_start is None or date_end is None
        dates_flexible = False
        if dates_defaulted and c.dates_whole_month_ok:
            if LIVE_MODE:
                date_start, date_end = _flexible_date_range()
                dates_flexible = True
                assumptions.append(
                    f"no specific date given -- searching {FLEXIBLE_WINDOW_START_DAYS}-{FLEXIBLE_WINDOW_END_DAYS} "
                    "days out for the cheapest day that actually works, as you asked"
                )
            else:
                date_start, date_end = _default_date_range()
                assumptions.append("searching the whole available month, as you asked")
        elif dates_defaulted:
            # best_effort cutoff hit with dates still unresolved and no "search
            # flexibly" confirmation either -- fall back to one reasonable date
            # rather than run the (much more expensive) flexible scan on a
            # request the user never actually confirmed.
            date_start, date_end = _default_date_range()
            assumptions.append(
                f"no specific dates given, defaulted to {date_start} (~{BEST_EFFORT_DAYS_OUT} days out)"
                if LIVE_MODE else "no specific dates given, searching the whole available month"
            )
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
            origin_code=origin_code,
            origin_name=origin_name,
            origin_defaulted=origin_defaulted,
            destination_code=c.destination_code,
            destination_name=c.destination_name,
            destination_raw=c.destination_raw,
            party_size=party_size,
            nights=nights,
            nights_defaulted=nights_defaulted,
            date_range_start=date_start,
            date_range_end=date_end,
            dates_defaulted=dates_defaulted,
            dates_flexible=dates_flexible,
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
