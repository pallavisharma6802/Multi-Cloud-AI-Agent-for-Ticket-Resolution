"""FastAPI backend for the travel-booking demo. Local only, single process
serves both the JSON API and the static frontend (no separate dev server).

Run: uvicorn travel_booking.api:app --reload --port 8200
"""
from __future__ import annotations

import json
import secrets
import sys
import uuid
from pathlib import Path
from typing import List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fastapi import Cookie, FastAPI, HTTPException, Response  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from travel_booking import auth as auth_mod  # noqa: E402
from travel_booking.agents import browse as browse_mod  # noqa: E402
from travel_booking.agents.explanation import build_explanation, build_explanation_for_option  # noqa: E402
from travel_booking.agents.intent_agent import IntentAgent  # noqa: E402
from travel_booking.agents.orchestrator import TravelAgent, TravelAgentState, TripOption  # noqa: E402
from travel_booking.agents.preference_aggregator import MemberPreference, aggregate, record_reward  # noqa: E402
from travel_booking.agents.schemas import DESTINATIONS, ConversationState, ItineraryOutcome, ResolvedConstraints  # noqa: E402
from travel_booking.agents.verification_agent import VerificationAgent  # noqa: E402
from travel_booking.db import get_connection, init_db, now  # noqa: E402

app = FastAPI(title="Travel Booking Demo")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8200", "http://127.0.0.1:8200"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)
init_db()

_travel_agent: Optional[TravelAgent] = None
_intent_agent: Optional[IntentAgent] = None
_conversations: dict[str, ConversationState] = {}


def _agents() -> tuple[TravelAgent, IntentAgent]:
    global _travel_agent, _intent_agent
    if _travel_agent is None:
        _travel_agent = TravelAgent()
        _intent_agent = _travel_agent.intent_agent
    return _travel_agent, _intent_agent


def _require_user(session_token: Optional[str]) -> dict:
    user = auth_mod.get_user_from_session(session_token)
    if user is None:
        raise HTTPException(401, "not logged in")
    return user


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class SignupRequest(BaseModel):
    username: str
    password: str
    display_name: str


class LoginRequest(BaseModel):
    username: str
    password: str


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie("session_token", token, httponly=True, samesite="lax", max_age=60 * 60 * 24 * 14)


@app.post("/api/auth/signup")
def signup(req: SignupRequest, response: Response):
    if len(req.password) < 8:
        raise HTTPException(400, "password must be at least 8 characters")
    if not req.username.strip():
        raise HTTPException(400, "username required")
    try:
        user = auth_mod.create_user(req.username.strip(), req.password, req.display_name.strip() or req.username.strip())
    except ValueError as e:
        raise HTTPException(409, str(e))
    token = auth_mod.create_session(user["id"])
    _set_session_cookie(response, token)
    return {"user": user}


@app.post("/api/auth/login")
def login(req: LoginRequest, response: Response):
    user = auth_mod.authenticate(req.username.strip(), req.password)
    if user is None:
        raise HTTPException(401, "invalid username or password")
    token = auth_mod.create_session(user["id"])
    _set_session_cookie(response, token)
    return {"user": user}


@app.post("/api/auth/logout")
def logout(response: Response, session_token: Optional[str] = Cookie(None)):
    if session_token:
        auth_mod.delete_session(session_token)
    response.delete_cookie("session_token")
    return {"ok": True}


@app.get("/api/auth/me")
def me(session_token: Optional[str] = Cookie(None)):
    user = auth_mod.get_user_from_session(session_token)
    if user is None:
        raise HTTPException(401, "not logged in")
    return {"user": user}


class StartRequest(BaseModel):
    message: str


class ReplyRequest(BaseModel):
    conversation_id: str
    message: str


class SearchFilters(BaseModel):
    """Optional overrides for refining a search without starting a new
    conversation -- e.g. the user widens the budget or changes dates after
    seeing the first set of results."""
    date_range_start: Optional[str] = None
    date_range_end: Optional[str] = None
    budget_amount: Optional[float] = None
    budget_scope: Optional[str] = None
    required_amenities: Optional[List[str]] = None


def _conversation_response(conv_id: str, state: ConversationState) -> dict:
    return {
        "conversation_id": conv_id,
        "status": state.status,
        "pending_question": state.pending_question,
        "turns": [{"role": t.role, "text": t.text} for t in state.turns],
        "missing": state.missing,
    }


@app.post("/api/chat/start")
def chat_start(req: StartRequest):
    _, intent_agent = _agents()
    state = intent_agent.start(req.message)
    conv_id = str(uuid.uuid4())
    _conversations[conv_id] = state
    return _conversation_response(conv_id, state)


@app.post("/api/chat/reply")
def chat_reply(req: ReplyRequest):
    _, intent_agent = _agents()
    state = _conversations.get(req.conversation_id)
    if state is None:
        raise HTTPException(404, "unknown conversation_id")
    state = intent_agent.continue_conversation(state, req.message)
    _conversations[req.conversation_id] = state
    return _conversation_response(req.conversation_id, state)


def _outcome_response(outcome) -> dict:
    return {
        "status": outcome.status,
        "constraints": outcome.constraints.model_dump(),
        "hotel": outcome.hotel_record,
        "flight": outcome.flight_record,
        "explanation": build_explanation(outcome),
        "attempts_tried": outcome.attempts_tried,
        "options": [
            {
                "hotel": o.hotel_record,
                "flight": o.flight_record,
                "explanation": build_explanation_for_option(o.verification),
            }
            for o in outcome.top_options
        ],
    }


@app.post("/api/search/{conversation_id}")
def run_search(conversation_id: str, filters: Optional[SearchFilters] = None):
    travel_agent, _ = _agents()
    state = _conversations.get(conversation_id)
    if state is None:
        raise HTTPException(404, "unknown conversation_id")
    if state.status not in ("ready", "best_effort"):
        raise HTTPException(400, f"conversation not ready yet (status={state.status})")

    if filters is not None:
        # Apply overrides directly on the parsed TravelConstraints before
        # resolving -- lets a user refine dates/budget/amenities without
        # re-running the whole clarification conversation.
        c = state.constraints
        if filters.date_range_start is not None:
            c.date_range_start = filters.date_range_start
            c.dates_whole_month_ok = False
        if filters.date_range_end is not None:
            c.date_range_end = filters.date_range_end
        if filters.budget_amount is not None:
            c.budget_amount = filters.budget_amount
            c.budget_mentioned_vague = False
        if filters.budget_scope is not None:
            c.budget_scope = filters.budget_scope
        if filters.required_amenities is not None:
            c.required_amenities = filters.required_amenities

    outcome = travel_agent.run_from_state(state)
    return _outcome_response(outcome)


# ---------------------------------------------------------------------------
# Browse -- hotels-only / flights-only, no chat, no paired-leg verification.
# Structured filters only, zero Bedrock calls.
# ---------------------------------------------------------------------------

class BrowseHotelsRequest(BaseModel):
    destination_code: str
    date_range_start: str
    nights: int = 3
    party_size: int = 1
    budget_amount: Optional[float] = None
    budget_scope: str = "per_night_hotel"
    required_amenities: List[str] = []


class BrowseFlightsRequest(BaseModel):
    destination_code: str
    date_range_start: str
    party_size: int = 1
    budget_amount: Optional[float] = None
    origin_code: Optional[str] = None


@app.post("/api/browse/hotels")
def browse_hotels(req: BrowseHotelsRequest):
    if req.destination_code not in DESTINATIONS:
        raise HTTPException(400, f"destination_code must be one of: {', '.join(DESTINATIONS)}")
    return {"results": browse_mod.browse_hotels(
        req.destination_code, req.date_range_start, req.nights, req.party_size,
        req.budget_amount, req.budget_scope, req.required_amenities,
    )}


@app.post("/api/browse/flights")
def browse_flights(req: BrowseFlightsRequest):
    if req.destination_code not in DESTINATIONS:
        raise HTTPException(400, f"destination_code must be one of: {', '.join(DESTINATIONS)}")
    return {"results": browse_mod.browse_flights(
        req.destination_code, req.date_range_start, req.party_size, req.budget_amount, req.origin_code,
    )}


# ---------------------------------------------------------------------------
# Planner (saved trips)
# ---------------------------------------------------------------------------

class SaveTripRequest(BaseModel):
    hotel: dict
    flight: dict
    verification: dict
    label: Optional[str] = None


@app.post("/api/planner/save")
def save_trip(req: SaveTripRequest, session_token: Optional[str] = Cookie(None)):
    user = _require_user(session_token)
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO saved_trips (user_id, hotel_json, flight_json, verification_json, label, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user["id"], json.dumps(req.hotel), json.dumps(req.flight), json.dumps(req.verification), req.label, now()),
        )
        conn.commit()
        return {"id": cur.lastrowid}
    finally:
        conn.close()


@app.get("/api/planner")
def list_saved_trips(session_token: Optional[str] = Cookie(None)):
    user = _require_user(session_token)
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM saved_trips WHERE user_id = ? ORDER BY created_at DESC", (user["id"],)
        ).fetchall()
        return {
            "trips": [
                {
                    "id": r["id"],
                    "hotel": json.loads(r["hotel_json"]),
                    "flight": json.loads(r["flight_json"]),
                    "verification": json.loads(r["verification_json"]),
                    "label": r["label"],
                    "created_at": r["created_at"],
                }
                for r in rows
            ]
        }
    finally:
        conn.close()


@app.delete("/api/planner/{trip_id}")
def delete_saved_trip(trip_id: int, session_token: Optional[str] = Cookie(None)):
    user = _require_user(session_token)
    conn = get_connection()
    try:
        row = conn.execute("SELECT user_id FROM saved_trips WHERE id = ?", (trip_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "not found")
        if row["user_id"] != user["id"]:
            raise HTTPException(403, "not your trip")
        conn.execute("DELETE FROM saved_trips WHERE id = ?", (trip_id,))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Friends
# ---------------------------------------------------------------------------

class FriendRequest(BaseModel):
    username: str


@app.post("/api/friends/request")
def send_friend_request(req: FriendRequest, session_token: Optional[str] = Cookie(None)):
    user = _require_user(session_token)
    conn = get_connection()
    try:
        target = conn.execute("SELECT id FROM users WHERE username = ?", (req.username.strip(),)).fetchone()
        if target is None:
            raise HTTPException(404, "no user with that username")
        if target["id"] == user["id"]:
            raise HTTPException(400, "can't friend yourself")

        # A friendship is an UNORDERED pair, but the table's UNIQUE constraint is
        # on the ordered (requester, addressee) columns -- so A->B and B->A were
        # both insertable, producing two rows for one relationship and listing
        # that friend twice. Check both directions explicitly.
        existing = conn.execute(
            """SELECT id, requester_id, status FROM friendships
               WHERE (requester_id = ? AND addressee_id = ?) OR (requester_id = ? AND addressee_id = ?)""",
            (user["id"], target["id"], target["id"], user["id"]),
        ).fetchone()

        if existing:
            if existing["status"] == "accepted":
                raise HTTPException(409, "you're already friends")
            if existing["requester_id"] == user["id"]:
                raise HTTPException(409, "you've already sent them a request")
            # They already requested US -- requesting back is mutual consent, so
            # accept it rather than making them wait on a redundant approval.
            conn.execute("UPDATE friendships SET status = 'accepted' WHERE id = ?", (existing["id"],))
            conn.commit()
            return {"ok": True, "auto_accepted": True}

        conn.execute(
            "INSERT INTO friendships (requester_id, addressee_id, status, created_at) VALUES (?, ?, 'pending', ?)",
            (user["id"], target["id"], now()),
        )
        conn.commit()
        return {"ok": True, "auto_accepted": False}
    finally:
        conn.close()


@app.post("/api/friends/accept/{request_id}")
def accept_friend_request(request_id: int, session_token: Optional[str] = Cookie(None)):
    user = _require_user(session_token)
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM friendships WHERE id = ?", (request_id,)).fetchone()
        if row is None or row["addressee_id"] != user["id"]:
            raise HTTPException(404, "no such request")
        conn.execute("UPDATE friendships SET status = 'accepted' WHERE id = ?", (request_id,))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@app.get("/api/friends")
def list_friends(session_token: Optional[str] = Cookie(None)):
    user = _require_user(session_token)
    conn = get_connection()
    try:
        accepted = conn.execute(
            """SELECT DISTINCT u.id, u.username, u.display_name FROM friendships f
               JOIN users u ON u.id = (CASE WHEN f.requester_id = ? THEN f.addressee_id ELSE f.requester_id END)
               WHERE (f.requester_id = ? OR f.addressee_id = ?) AND f.status = 'accepted'""",
            (user["id"], user["id"], user["id"]),
        ).fetchall()
        incoming = conn.execute(
            """SELECT f.id as request_id, u.username, u.display_name FROM friendships f
               JOIN users u ON u.id = f.requester_id
               WHERE f.addressee_id = ? AND f.status = 'pending'""",
            (user["id"],),
        ).fetchall()
        return {
            "friends": [dict(r) for r in accepted],
            "incoming_requests": [dict(r) for r in incoming],
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Group trips -- multiple friends submit structured preferences, an RL
# (multi-armed bandit) agent picks a combination strategy, then the real
# search+verification pipeline runs on the aggregated constraints.
# ---------------------------------------------------------------------------

class CreateGroupRequest(BaseModel):
    name: str
    destination_code: str  # any code in schemas.DESTINATIONS


class JoinGroupRequest(BaseModel):
    join_code: str


class GroupPreferenceRequest(BaseModel):
    date_range_start: str
    date_range_end: str
    # How long this member wants the trip to be. Separate from the date range,
    # which is the window they're AVAILABLE within -- deriving one from the
    # other produced badly wrong stays (see preference_aggregator).
    nights: int = 3
    party_size: int = 1
    budget_amount: Optional[float] = None
    budget_scope: str = "total_trip"
    required_amenities: List[str] = []


class GroupFeedbackRequest(BaseModel):
    accepted: bool


@app.get("/api/groups")
def list_my_groups(session_token: Optional[str] = Cookie(None)):
    user = _require_user(session_token)
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT g.* FROM trip_groups g JOIN trip_group_members m ON m.group_id = g.id
               WHERE m.user_id = ? ORDER BY g.created_at DESC""",
            (user["id"],),
        ).fetchall()
        return {"groups": [dict(r) for r in rows]}
    finally:
        conn.close()


@app.post("/api/groups")
def create_group(req: CreateGroupRequest, session_token: Optional[str] = Cookie(None)):
    user = _require_user(session_token)
    if req.destination_code not in DESTINATIONS:
        raise HTTPException(400, f"destination_code must be one of: {', '.join(DESTINATIONS)}")
    conn = get_connection()
    try:
        join_code = secrets.token_hex(3).upper()
        t = now()
        cur = conn.execute(
            "INSERT INTO trip_groups (name, owner_id, destination_code, join_code, status, created_at) VALUES (?, ?, ?, ?, 'collecting', ?)",
            (req.name, user["id"], req.destination_code, join_code, t),
        )
        group_id = cur.lastrowid
        conn.execute(
            "INSERT INTO trip_group_members (group_id, user_id, joined_at) VALUES (?, ?, ?)",
            (group_id, user["id"], t),
        )
        conn.commit()
        return {"group_id": group_id, "join_code": join_code, "destination_code": req.destination_code}
    finally:
        conn.close()


@app.post("/api/groups/join")
def join_group(req: JoinGroupRequest, session_token: Optional[str] = Cookie(None)):
    user = _require_user(session_token)
    conn = get_connection()
    try:
        group = conn.execute("SELECT * FROM trip_groups WHERE join_code = ?", (req.join_code.strip().upper(),)).fetchone()
        if group is None:
            raise HTTPException(404, "no group with that join code")
        conn.execute(
            "INSERT OR IGNORE INTO trip_group_members (group_id, user_id, joined_at) VALUES (?, ?, ?)",
            (group["id"], user["id"], now()),
        )
        conn.commit()
        return {"group_id": group["id"], "name": group["name"]}
    finally:
        conn.close()


def _group_or_404(conn, group_id: int, user_id: int) -> dict:
    group = conn.execute("SELECT * FROM trip_groups WHERE id = ?", (group_id,)).fetchone()
    if group is None:
        raise HTTPException(404, "no such group")
    member = conn.execute(
        "SELECT 1 FROM trip_group_members WHERE group_id = ? AND user_id = ?", (group_id, user_id)
    ).fetchone()
    if member is None:
        raise HTTPException(403, "not a member of this group")
    return dict(group)


@app.get("/api/groups/{group_id}")
def get_group(group_id: int, session_token: Optional[str] = Cookie(None)):
    user = _require_user(session_token)
    conn = get_connection()
    try:
        group = _group_or_404(conn, group_id, user["id"])
        members = conn.execute(
            """SELECT u.id, u.username, u.display_name,
                      (SELECT COUNT(*) FROM trip_group_preferences p WHERE p.group_id = ? AND p.user_id = u.id) as submitted
               FROM trip_group_members m JOIN users u ON u.id = m.user_id WHERE m.group_id = ?""",
            (group_id, group_id),
        ).fetchall()
        return {
            "group": group,
            "members": [dict(r) for r in members],
        }
    finally:
        conn.close()


@app.post("/api/groups/{group_id}/preferences")
def submit_group_preferences(group_id: int, req: GroupPreferenceRequest, session_token: Optional[str] = Cookie(None)):
    user = _require_user(session_token)
    conn = get_connection()
    try:
        _group_or_404(conn, group_id, user["id"])
        prefs = req.model_dump()
        conn.execute(
            """INSERT INTO trip_group_preferences (group_id, user_id, preferences_json, submitted_at) VALUES (?, ?, ?, ?)
               ON CONFLICT(group_id, user_id) DO UPDATE SET preferences_json = excluded.preferences_json, submitted_at = excluded.submitted_at""",
            (group_id, user["id"], json.dumps(prefs), now()),
        )
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@app.post("/api/groups/{group_id}/search")
def search_group_trip(group_id: int, session_token: Optional[str] = Cookie(None)):
    """Aggregates every member's submitted preferences via the bandit
    strategy-selection agent, then runs the SAME real search+verification
    pipeline as a solo search -- zero Bedrock calls, since preferences are
    already structured (no freeform text to parse)."""
    user = _require_user(session_token)
    conn = get_connection()
    try:
        group = _group_or_404(conn, group_id, user["id"])
        rows = conn.execute(
            "SELECT preferences_json FROM trip_group_preferences WHERE group_id = ?", (group_id,)
        ).fetchall()
        if not rows:
            raise HTTPException(400, "no group members have submitted preferences yet")
        dest = group["destination_code"]
    finally:
        conn.close()

    members = []
    for r in rows:
        p = json.loads(r["preferences_json"])
        members.append(MemberPreference(
            date_range_start=p["date_range_start"], date_range_end=p["date_range_end"],
            party_size=p["party_size"], budget_amount=p.get("budget_amount"),
            budget_scope=p.get("budget_scope", "total_trip"), required_amenities=p.get("required_amenities", []),
            nights=p.get("nights", 3),
        ))

    agg = aggregate(members)
    # Persist the chosen arm so the feedback/reward endpoint still works after a
    # server restart -- an in-memory dict silently dropped every 👍/👎 on restart.
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE trip_groups SET last_strategy = ?, status = 'searched' WHERE id = ?",
            (agg["strategy"], group_id),
        )
        conn.commit()
    finally:
        conn.close()

    constraints = ResolvedConstraints(
        origin_defaulted=True,  # group trips don't collect a per-member origin yet -- always the app default
        destination_code=dest, destination_raw=dest,
        party_size=agg["party_size"], nights=agg["nights"],
        nights_defaulted=False, date_range_start=agg["date_range_start"], date_range_end=agg["date_range_end"],
        dates_defaulted=False, budget_amount=agg["budget_amount"], budget_scope=agg["budget_scope"],
        required_amenities=agg["required_amenities"], raw_request=f"group trip #{group_id}",
        assumptions=[f"combined via the '{agg['strategy']}' strategy: {agg['strategy_description']}"],
    )

    travel_agent, _ = _agents()
    queue, n_hotels, n_flights = travel_agent._build_candidate_queue(constraints)
    init_state: TravelAgentState = {
        "constraints": constraints, "queue": queue, "current": None, "attempts": 0,
        "unavailable_skipped": 0, "best_failed": None, "best_failed_count": 99,
        "final": None, "accepted": None, "accepted_options": [], "attempt_log": [],
    }
    final_state = travel_agent.graph.invoke(init_state, config={"recursion_limit": 200})
    if final_state.get("accepted"):
        options = final_state.get("accepted_options", [])
        top_options = [
            TripOption(
                hotel_record=travel_agent._last_hotels_by_id[o.hotel_id],
                flight_record=travel_agent._last_flights_by_id[o.flight_id],
                verification=o,
            ) for o in options
        ]
        outcome = travel_agent._finalize(constraints, options[0], n_hotels, n_flights, final_state["attempts"])
        outcome.top_options = top_options
    else:
        outcome = _unsatisfiable_outcome(travel_agent, constraints, final_state, n_hotels, n_flights)

    resp = _outcome_response(outcome)
    resp["strategy"] = agg["strategy"]
    resp["strategy_description"] = agg["strategy_description"]
    resp["members_count"] = len(members)
    resp["nights"] = agg["nights"]
    resp["warnings"] = agg["warnings"]
    return resp


@app.post("/api/groups/{group_id}/feedback")
def group_feedback(group_id: int, req: GroupFeedbackRequest, session_token: Optional[str] = Cookie(None)):
    """The reward signal for the bandit: did the group actually accept the
    trip the chosen strategy produced?"""
    user = _require_user(session_token)
    conn = get_connection()
    try:
        group = _group_or_404(conn, group_id, user["id"])
        strategy = group.get("last_strategy")
    finally:
        conn.close()
    if not strategy:
        raise HTTPException(400, "no search has been run for this group yet")
    record_reward(strategy, req.accepted)
    return {"ok": True, "strategy": strategy, "accepted": req.accepted}


def _unsatisfiable_outcome(travel_agent, constraints, final_state, n_hotels, n_flights):
    return ItineraryOutcome(
        status="unsatisfiable",
        constraints=constraints,
        closest_attempt=final_state.get("best_failed"),
        attempts_tried=final_state.get("attempts", 0),
        candidates_hotels=n_hotels,
        candidates_flights=n_flights,
        hotel_record=travel_agent._last_hotels_by_id.get(final_state["best_failed"].hotel_id) if final_state.get("best_failed") else None,
        flight_record=travel_agent._last_flights_by_id.get(final_state["best_failed"].flight_id) if final_state.get("best_failed") else None,
        all_attempts=final_state.get("attempt_log", []),
    )


FRONTEND_DIR = Path(__file__).resolve().parent / "frontend"
app.mount("/images", StaticFiles(directory=str(Path(__file__).resolve().parent / "data" / "images")), name="images")
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/")
def index():
    return FileResponse(str(FRONTEND_DIR / "index.html"))
