"""LangGraph orchestrator: propose -> availability_gate -> verify -> decide,
looping until a combination passes all 4 hard checks or every ranked
candidate pair is exhausted. Reports the closest attempt if nothing passes,
never a silently-broken itinerary.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Optional, TypedDict

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from langgraph.graph import END, StateGraph  # noqa: E402

from travel_booking.agents import ranking  # noqa: E402
from travel_booking.agents.intent_agent import IntentAgent  # noqa: E402
from travel_booking.agents.schemas import (  # noqa: E402
    DESTINATIONS,
    ConversationState,
    ItineraryOutcome,
    ResolvedConstraints,
    TripOption,
    VerificationResult,
)
from travel_booking.agents.verification_agent import VerificationAgent  # noqa: E402

MAX_ATTEMPTS = 12  # bound on how many ranked pairs we'll actually verify
MAX_OPTIONS = 3  # how many distinct passing itineraries to surface, ranked, once verification is done
FLEX_SCAN_SAMPLES = 6  # how many candidate days to price out when searching flexibly (bounded -- see _scan_for_best_date)

ORIGIN_AIRPORT = "ORD"  # fallback if no origin was resolved
DESTINATION_HOTEL_QUERY = {code: f"hotels in {name}" for code, name in DESTINATIONS.items()}


def _date_range_overlaps_blackout(start: str, nights: int, blackout: list[str]) -> bool:
    start_d = date.fromisoformat(start)
    stay_dates = {(start_d + timedelta(days=i)).isoformat() for i in range(nights)}
    return bool(stay_dates & set(blackout))


def _hotel_available_for(hotel: dict, flight: dict, nights: int) -> tuple[bool, str]:
    if "available_from" not in hotel:
        # live search was already scoped to the requested dates
        return True, "available (date-scoped by the live search itself)"
    flight_date = flight["date"]
    if not (hotel["available_from"] <= flight_date <= hotel["available_to"]):
        return False, f"{hotel['name']} isn't offered on {flight_date} (available {hotel['available_from']}..{hotel['available_to']})."
    if _date_range_overlaps_blackout(flight_date, nights, hotel["blackout_dates"]):
        return False, f"{hotel['name']} is sold out for part of the {nights}-night stay starting {flight_date} (blackout: {hotel['blackout_dates']})."
    return True, "available"


class TravelAgentState(TypedDict, total=False):
    constraints: ResolvedConstraints
    queue: list[tuple[dict, dict]]
    current: Optional[tuple[dict, dict]]
    gate_passed: bool
    gate_reason: str
    last_result: Optional[VerificationResult]
    attempts: int
    unavailable_skipped: int
    best_failed: Optional[VerificationResult]
    best_failed_count: int
    final: Optional[str]  # "accept" | "escalate"
    accepted: Optional[VerificationResult]
    accepted_options: list[VerificationResult]
    attempt_log: list[VerificationResult]


class TravelAgent:
    def __init__(self):
        self.intent_agent = IntentAgent()
        self.verification_agent = VerificationAgent()
        self.graph = self._build_graph()
        self._last_hotels_by_id: dict = {}
        self._last_flights_by_id: dict = {}

    # -- graph nodes --------------------------------------------------------
    def _propose_node(self, state: TravelAgentState) -> TravelAgentState:
        queue = state["queue"]
        if not queue:
            state["current"] = None
        else:
            state["current"] = queue.pop(0)
        return state

    def _gate_node(self, state: TravelAgentState) -> TravelAgentState:
        hotel, flight = state["current"]
        ok, reason = _hotel_available_for(hotel, flight, state["constraints"].nights)
        state["gate_passed"] = ok
        state["gate_reason"] = reason
        if not ok:
            state["unavailable_skipped"] = state.get("unavailable_skipped", 0) + 1
        return state

    def _verify_node(self, state: TravelAgentState) -> TravelAgentState:
        hotel, flight = state["current"]
        result = self.verification_agent.verify(hotel, flight, state["constraints"])
        state["last_result"] = result
        state["attempts"] = state.get("attempts", 0) + 1
        state.setdefault("attempt_log", []).append(result)
        return state

    def _decide_node(self, state: TravelAgentState) -> TravelAgentState:
        result = state["last_result"]
        options = state.setdefault("accepted_options", [])

        if result.passed:
            # Keep options distinct by hotel. Collects every passing option
            # up to MAX_ATTEMPTS (not just the first MAX_OPTIONS found) so
            # ranking afterward has a real pool to pick the best 3 from,
            # instead of just the first 3 in price order.
            already_have_hotel = any(o.hotel_id == result.hotel_id for o in options)
            if not already_have_hotel:
                options.append(result)
            if not state["queue"] or state["attempts"] >= MAX_ATTEMPTS:
                state["final"] = "accept"
                state["accepted"] = options[0]
            else:
                state["final"] = None
            return state

        failed_count = len(result.failed_checks())
        if state.get("best_failed") is None or failed_count < state.get("best_failed_count", 99):
            state["best_failed"] = result
            state["best_failed_count"] = failed_count

        if not state["queue"] or state["attempts"] >= MAX_ATTEMPTS:
            # Exhausted the queue -- if we already found at least 1 passing
            # option along the way, that's still a real "accept", just with
            # fewer than MAX_OPTIONS choices.
            state["final"] = "accept" if options else "escalate"
            if options:
                state["accepted"] = options[0]
        else:
            state["final"] = None
        return state

    # -- routing --------------------------------------------------------------
    def _route_after_propose(self, state: TravelAgentState) -> str:
        if state["current"] is None:
            return "end"
        return "gate"

    def _route_after_gate(self, state: TravelAgentState) -> str:
        return "verify" if state["gate_passed"] else "propose"

    def _route_after_decide(self, state: TravelAgentState) -> str:
        return "end" if state.get("final") else "propose"

    def _build_graph(self):
        workflow = StateGraph(TravelAgentState)
        workflow.add_node("propose", self._propose_node)
        workflow.add_node("gate", self._gate_node)
        workflow.add_node("verify", self._verify_node)
        workflow.add_node("decide", self._decide_node)

        workflow.set_entry_point("propose")
        workflow.add_conditional_edges("propose", self._route_after_propose, {"gate": "gate", "end": END})
        workflow.add_conditional_edges("gate", self._route_after_gate, {"verify": "verify", "propose": "propose"})
        workflow.add_edge("verify", "decide")
        workflow.add_conditional_edges("decide", self._route_after_decide, {"propose": "propose", "end": END})
        return workflow.compile()

    # -- candidate generation --------------------------------------------------
    def _scan_for_best_date(self, constraints: ResolvedConstraints, origin: str) -> str:
        """Prices FLEX_SCAN_SAMPLES candidate days across the window and
        returns the cheapest, instead of guessing one date. Only checks
        outbound flight price (the main date-sensitive cost, and cheaper
        than also scanning hotels per candidate) -- the full hotel+flight
        search still runs once on the winning date."""
        from travel_booking.agents import serpapi_client

        start = date.fromisoformat(constraints.date_range_start)
        end = date.fromisoformat(constraints.date_range_end)
        span_days = (end - start).days
        n_samples = max(1, min(FLEX_SCAN_SAMPLES, span_days + 1))
        step = span_days / max(1, n_samples - 1) if n_samples > 1 else 0
        candidate_dates = sorted({(start + timedelta(days=round(i * step))).isoformat() for i in range(n_samples)})

        best_date, best_price = None, None
        for d in candidate_dates:
            try:
                flights = serpapi_client.search_flights(origin, constraints.destination_code, d, adults=constraints.party_size)
            except Exception:
                continue
            if not flights:
                continue
            cheapest = min(f["price"] for f in flights)
            if best_price is None or cheapest < best_price:
                best_price, best_date = cheapest, d
        return best_date or candidate_dates[0]

    def _build_candidate_queue(self, constraints: ResolvedConstraints) -> tuple[list[tuple[dict, dict]], int, int]:
        """Doesn't search across every day in a wide date range by default --
        real flight search is per-date and costs one API call each. If
        constraints.dates_flexible is set (user asked us to find the best
        day), _scan_for_best_date runs a bounded search across the window
        first and resolves it down to one concrete date; otherwise this uses
        exactly date_range_start."""
        from travel_booking.agents import serpapi_client

        origin = constraints.origin_code or ORIGIN_AIRPORT

        if constraints.dates_flexible:
            checkin = self._scan_for_best_date(constraints, origin)
            # narrow the wide window down to the winning date so downstream
            # reads (UI, saved trips, confirmation text) see the real date
            constraints.date_range_start = checkin
            constraints.date_range_end = checkin
            constraints.dates_flexible = False
            constraints.dates_were_scanned = True
        else:
            checkin = constraints.date_range_start
        checkout = (date.fromisoformat(checkin) + timedelta(days=constraints.nights)).isoformat()
        hotel_query = DESTINATION_HOTEL_QUERY.get(constraints.destination_code, constraints.destination_raw)

        hotels = serpapi_client.search_hotels(hotel_query, checkin, checkout, adults=constraints.party_size)
        flights = serpapi_client.search_flights(origin, constraints.destination_code, checkin, adults=constraints.party_size)

        # round trip, not one-way: two separate one-way fares (outbound on
        # checkin, return on checkout) rather than SerpApi's stateful
        # round-trip flow. Cheapest return is paired onto every outbound
        # candidate as `flight["return"]`; None if no return flight exists
        # for that route/date, so the budget check doesn't silently price it
        # as one-way.
        return_flights = sorted(
            serpapi_client.search_flights(constraints.destination_code, origin, checkout, adults=constraints.party_size),
            key=lambda f: f["price"],
        )
        cheapest_return = return_flights[0] if return_flights else None

        hotels = sorted(hotels, key=lambda h: h["price_per_night"])[:8]
        flights = sorted(flights, key=lambda f: f["price"])[:8]
        for f in flights:
            f["return"] = cheapest_return
        self._last_hotels_by_id = {h["id"]: h for h in hotels}
        self._last_flights_by_id = {f["id"]: f for f in flights}

        pairs = []
        for f in flights:
            round_trip_price = f["price"] + (f["return"]["price"] if f["return"] else 0)
            for h in hotels:
                pairs.append((h["price_per_night"] + round_trip_price, h, f))
        pairs.sort(key=lambda p: p[0])
        queue = [(h, f) for _, h, f in pairs]
        return queue, len(hotels), len(flights)

    # -- public API --------------------------------------------------------
    def run(self, raw_request: str) -> ItineraryOutcome:
        """One-shot convenience entry point: parses the request and resolves
        immediately with best-effort defaults for anything ambiguous, WITHOUT
        asking a clarifying question. Used by the battery/smoke tests, which
        write fully-specified requests up front. Real interactive intake goes
        through intent_agent.start()/continue_conversation() + run_from_state()
        instead (see travel_booking/frontend for the real multi-turn UI)."""
        state = self.intent_agent.start(raw_request)
        return self.run_from_state(state)

    def _rank_options(
        self, options: list[VerificationResult], constraints: ResolvedConstraints, rank_by: str
    ) -> list[VerificationResult]:
        if len(options) <= 1:
            return options
        pairs = [(self._last_hotels_by_id[o.hotel_id], self._last_flights_by_id[o.flight_id]) for o in options]
        scored = ranking.score_candidates(pairs, constraints, preset=rank_by)
        by_ids = {(o.hotel_id, o.flight_id): o for o in options}
        return [by_ids[(sc.hotel["id"], sc.flight["id"])] for sc in scored]

    def run_from_state(self, state: ConversationState, rank_by: str = ranking.DEFAULT_PRESET) -> ItineraryOutcome:
        """Run search+verify from an already-parsed ConversationState (status
        'ready' or 'best_effort'). Does not make any further clarification calls.
        rank_by picks a weight preset from ranking.WEIGHT_PRESETS for ordering
        the verified options (default: "best_value")."""
        constraints = self.intent_agent.resolve_from_conversation(state)

        if constraints.destination_code is None:
            return ItineraryOutcome(
                status="unsatisfiable",
                constraints=constraints,
                attempts_tried=0,
                candidates_hotels=0,
                candidates_flights=0,
            )

        queue, n_hotels, n_flights = self._build_candidate_queue(constraints)

        init_state: TravelAgentState = {
            "constraints": constraints,
            "queue": queue,
            "current": None,
            "attempts": 0,
            "unavailable_skipped": 0,
            "best_failed": None,
            "best_failed_count": 99,
            "final": None,
            "accepted": None,
            "accepted_options": [],
            "attempt_log": [],
        }
        final_state: Any = self.graph.invoke(init_state, config={"recursion_limit": 200})
        attempt_log = final_state.get("attempt_log", [])

        if final_state.get("accepted"):
            options = self._rank_options(final_state.get("accepted_options", []), constraints, rank_by)[:MAX_OPTIONS]
            top_options = [
                TripOption(
                    hotel_record=self._last_hotels_by_id[o.hotel_id],
                    flight_record=self._last_flights_by_id[o.flight_id],
                    verification=o,
                )
                for o in options
            ]
            result: VerificationResult = options[0]
            outcome = self._finalize(constraints, result, n_hotels, n_flights, final_state["attempts"])
            outcome.all_attempts = attempt_log
            outcome.top_options = top_options
            return outcome

        return ItineraryOutcome(
            status="unsatisfiable",
            constraints=constraints,
            closest_attempt=final_state.get("best_failed"),
            attempts_tried=final_state.get("attempts", 0),
            candidates_hotels=n_hotels,
            candidates_flights=n_flights,
            hotel_record=self._last_hotels_by_id.get(final_state["best_failed"].hotel_id) if final_state.get("best_failed") else None,
            flight_record=self._last_flights_by_id.get(final_state["best_failed"].flight_id) if final_state.get("best_failed") else None,
            all_attempts=attempt_log,
        )

    def _finalize(self, constraints, result: VerificationResult, n_hotels, n_flights, attempts) -> ItineraryOutcome:
        hotel = self._last_hotels_by_id[result.hotel_id]
        flight = self._last_flights_by_id[result.flight_id]
        return ItineraryOutcome(
            status="verified",
            constraints=constraints,
            verification=result,
            attempts_tried=attempts,
            candidates_hotels=n_hotels,
            candidates_flights=n_flights,
            hotel_record=hotel,
            flight_record=flight,
        )
