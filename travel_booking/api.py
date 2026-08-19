"""FastAPI backend for the travel-booking demo. Local only, single process
serves both the JSON API and the static frontend (no separate dev server).

Run: uvicorn travel_booking.api:app --reload --port 8200
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from travel_booking.agents.explanation import build_explanation  # noqa: E402
from travel_booking.agents.intent_agent import IntentAgent  # noqa: E402
from travel_booking.agents.orchestrator import TravelAgent  # noqa: E402
from travel_booking.agents.schemas import ConversationState  # noqa: E402

app = FastAPI(title="Travel Booking Demo")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8200", "http://127.0.0.1:8200"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_travel_agent: Optional[TravelAgent] = None
_intent_agent: Optional[IntentAgent] = None
_conversations: dict[str, ConversationState] = {}


def _agents() -> tuple[TravelAgent, IntentAgent]:
    global _travel_agent, _intent_agent
    if _travel_agent is None:
        _travel_agent = TravelAgent()
        _intent_agent = _travel_agent.intent_agent
    return _travel_agent, _intent_agent


class StartRequest(BaseModel):
    message: str


class ReplyRequest(BaseModel):
    conversation_id: str
    message: str


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


@app.post("/api/search/{conversation_id}")
def run_search(conversation_id: str):
    travel_agent, _ = _agents()
    state = _conversations.get(conversation_id)
    if state is None:
        raise HTTPException(404, "unknown conversation_id")
    if state.status not in ("ready", "best_effort"):
        raise HTTPException(400, f"conversation not ready yet (status={state.status})")

    outcome = travel_agent.run_from_state(state)
    explanation = build_explanation(outcome)
    return {
        "status": outcome.status,
        "constraints": outcome.constraints.model_dump(),
        "hotel": outcome.hotel_record,
        "flight": outcome.flight_record,
        "explanation": explanation,
        "attempts_tried": outcome.attempts_tried,
    }


FRONTEND_DIR = Path(__file__).resolve().parent / "frontend"
app.mount("/images", StaticFiles(directory=str(Path(__file__).resolve().parent / "data" / "images")), name="images")
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/")
def index():
    return FileResponse(str(FRONTEND_DIR / "index.html"))
