"""Shared Pydantic schemas for the travel-booking agents."""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

KNOWN_DESTINATIONS = ("AUS", "DEN", "MIA")
KNOWN_AMENITIES = ("wifi", "pool", "gym", "parking", "breakfast", "pet_friendly", "family_friendly")

BudgetScope = Literal["total_trip", "per_night_hotel"]
CheckName = Literal["arrival_vs_checkin", "budget", "amenities", "capacity"]


class TravelConstraints(BaseModel):
    """Structured output of the Intent Agent's Bedrock call."""

    destination_code: Optional[Literal["AUS", "DEN", "MIA"]] = Field(
        default=None,
        description="3-letter destination airport code if the request clearly names Austin (AUS), "
        "Denver (DEN), or Miami (MIA); null if the destination is unclear or not one of these three.",
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

    destination_code: Optional[str]
    destination_raw: str
    party_size: int
    nights: int
    nights_defaulted: bool
    date_range_start: str
    date_range_end: str
    dates_defaulted: bool
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


class VerificationResult(BaseModel):
    hotel_id: str
    flight_id: str
    passed: bool
    checks: List[CheckResult]
    total_cost: float

    def failed_checks(self) -> List[CheckResult]:
        return [c for c in self.checks if not c.passed]


class ItineraryOutcome(BaseModel):
    """Final result of one full run: either a verified itinerary, or the closest miss."""

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
