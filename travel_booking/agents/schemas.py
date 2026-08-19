"""Shared Pydantic schemas for the travel-booking agents."""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

# destination airport code -> display name. Real-data mode (SerpApi) isn't actually
# limited to this list -- any valid IATA code works against live Google Flights/Hotels --
# but the LLM is steered toward these as reliably-known major destinations rather than
# guessing an airport code for every place on earth.
DESTINATIONS = {
    "AUS": "Austin, TX",
    "DEN": "Denver, CO",
    "MIA": "Miami, FL",
    "CDG": "Paris, France",
    "HND": "Tokyo, Japan",
    "LHR": "London, UK",
    "MEX": "Mexico City, Mexico",
    "SYD": "Sydney, Australia",
}
KNOWN_DESTINATIONS = tuple(DESTINATIONS.keys())
KNOWN_AMENITIES = ("wifi", "pool", "gym", "parking", "breakfast", "pet_friendly", "family_friendly")

BudgetScope = Literal["total_trip", "per_night_hotel"]
CheckName = Literal["arrival_vs_checkin", "budget", "amenities", "capacity"]

DEFAULT_ORIGIN_CODE = "ORD"
DEFAULT_ORIGIN_NAME = "Chicago O'Hare (ORD)"


class TravelConstraints(BaseModel):
    """Structured output of the Intent Agent's Bedrock call."""

    origin_code: Optional[str] = Field(
        default=None,
        description="3-letter IATA airport code for where the traveler is DEPARTING FROM, if stated "
        "(e.g. 'flying from Chicago', 'departing NYC', 'from Boston'). Null if not stated -- do not guess "
        "an origin the user never mentioned.",
    )
    origin_raw: Optional[str] = Field(
        default=None, description="The origin exactly as the user phrased it, verbatim. Null if not stated."
    )
    destination_code: Optional[str] = Field(
        default=None,
        description="3-letter IATA airport code for the destination, if the request clearly names one "
        "of the supported destinations or another major world city/airport recognizable with confidence; "
        "null if the destination is unclear, ambiguous, or not confidently resolvable to a real airport.",
    )
    destination_name: Optional[str] = Field(
        default=None,
        description="Clean display name for the destination_code, e.g. 'Paris, France'. Null if "
        "destination_code is null.",
    )
    destination_raw: str = Field(description="The destination exactly as the user phrased it, verbatim.")
    party_size: int = Field(ge=1, description="Number of travelers. Default to 1 only if nothing implies a group.")
    party_size_ambiguous: bool = Field(
        default=False,
        description="True if the text implies more than one traveler but gives no exact count (e.g. "
        "'a few of us', 'my family', 'we') -- do NOT silently default party_size to 1 in that case; "
        "still fill party_size with your best single-integer guess, but flag it here.",
    )
    nights: Optional[int] = Field(default=None, description="Number of nights requested, if stated.")
    date_range_start: Optional[str] = Field(
        default=None, description="ISO date (YYYY-MM-DD) the trip could start, if the user gave one or a narrow range. Null if unstated or only a vague month/season was given."
    )
    date_range_end: Optional[str] = Field(
        default=None, description="ISO date (YYYY-MM-DD) the trip could start by (end of the acceptable range). Equal to date_range_start if a single exact date was given."
    )
    dates_whole_month_ok: bool = Field(
        default=False,
        description="True if the user was asked whether to narrow dates or search the whole month, and "
        "explicitly chose to search the whole month (e.g. replied 'whole month', 'search the whole month', "
        "'any time works', 'no preference'). This is a resolved answer, not a missing one.",
    )
    budget_amount: Optional[float] = Field(default=None, description="Numeric budget amount if stated, else null.")
    budget_scope: Optional[BudgetScope] = Field(
        default=None,
        description="'per_night_hotel' if the budget was stated as a per-night hotel rate (e.g. "
        "'under $200/night'), 'total_trip' if it was stated as one total trip budget (e.g. 'under $1500 "
        "total'). Null if no budget was stated.",
    )
    budget_mentioned_vague: bool = Field(
        default=False,
        description="True if the user referenced cost without a number (e.g. 'not too expensive', "
        "'affordable', 'reasonable price') -- distinct from not mentioning budget at all.",
    )
    required_amenities: List[str] = Field(
        default_factory=list,
        description=f"Amenities explicitly required, drawn only from this vocabulary: {list(KNOWN_AMENITIES)}. "
        "Do not invent amenities not in this list and not implied by the request.",
    )
    raw_summary: str = Field(description="One-sentence restatement of what the user is asking for.")


class ResolvedConstraints(BaseModel):
    """TravelConstraints after code-level defaults are applied (nights, party_size, dates)."""

    origin_code: str = DEFAULT_ORIGIN_CODE
    origin_name: str = DEFAULT_ORIGIN_NAME
    origin_defaulted: bool = False
    destination_code: Optional[str]
    destination_name: Optional[str] = None
    destination_raw: str
    party_size: int
    nights: int
    nights_defaulted: bool
    date_range_start: str
    date_range_end: str
    dates_defaulted: bool
    dates_flexible: bool = False  # True: date_range is a wide window to scan for the cheapest workable day,
    # not a literal single date -- see orchestrator._build_candidate_queue_serpapi's date-scan branch.
    dates_were_scanned: bool = False  # set True once the scan above actually ran and picked a real date
    # (dates_flexible itself gets reset to False right after, so this is what explanation.py checks).
    budget_amount: Optional[float]
    budget_scope: Optional[BudgetScope]
    required_amenities: List[str]
    raw_request: str
    assumptions: List[str] = Field(default_factory=list)


class ClarificationTurn(BaseModel):
    role: Literal["user", "agent"]
    text: str


class ConversationState(BaseModel):
    """Accumulating multi-turn intake state -- re-derived each turn from the
    full transcript so later corrections naturally override earlier answers."""

    turns: List[ClarificationTurn] = Field(default_factory=list)
    constraints: Optional[TravelConstraints] = None
    status: Literal["needs_clarification", "ready", "best_effort"] = "needs_clarification"
    pending_question: Optional[str] = None
    missing: List[str] = Field(default_factory=list)
    exchange_count: int = 0


class SearchCandidate(BaseModel):
    kind: Literal["hotel", "flight"]
    record: dict
    score: float
    retrieval_method: Literal["dense", "sparse", "hybrid"]


class CheckResult(BaseModel):
    name: CheckName
    passed: bool
    detail: str
    expected: str
    actual: str
    data_available: bool = Field(
        default=True,
        description="False when this check could not actually be evaluated because the data source "
        "doesn't provide the needed field (e.g. real Google Hotels data has no room-capacity field). "
        "When False, `passed` is a placeholder (True) so it never blocks a booking on missing data, "
        "but the UI must show this as 'not verifiable', never as a real pass.",
    )


class VerificationResult(BaseModel):
    hotel_id: str
    flight_id: str
    passed: bool
    checks: List[CheckResult]
    total_cost: float

    def failed_checks(self) -> List[CheckResult]:
        return [c for c in self.checks if not c.passed]


class TripOption(BaseModel):
    """One candidate itinerary: a specific hotel+flight pair and its full
    verification result. `run_from_state` collects up to 3 of these,
    deliberately kept distinct by hotel."""

    hotel_record: dict
    flight_record: dict
    verification: VerificationResult


class ItineraryOutcome(BaseModel):
    """Final result of one full run: either up to 3 verified itineraries, or
    the closest miss."""

    status: Literal["verified", "unsatisfiable"]
    constraints: ResolvedConstraints
    verification: Optional[VerificationResult] = None
    closest_attempt: Optional[VerificationResult] = None
    attempts_tried: int = 0
    candidates_hotels: int = 0
    candidates_flights: int = 0
    hotel_record: Optional[dict] = None
    flight_record: Optional[dict] = None
    all_attempts: List[VerificationResult] = Field(default_factory=list)
    top_options: List[TripOption] = Field(
        default_factory=list,
        description="Up to 3 distinct-hotel passing itineraries, ranked in the order they were found "
        "(cheapest/most-relevant-first, since the candidate queue is pre-sorted that way). Empty when "
        "status is unsatisfiable -- see closest_attempt instead.",
    )
