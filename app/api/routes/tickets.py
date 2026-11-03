import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.agents.supervisor import SupervisorAgent
from app.config import settings
from app.db.models import AgentDecisionLog, DraftedResponseLog, Ticket
from app.db.session import get_db
from app.domain.loader import DomainPackNotFoundError, get_domain_pack, list_available_packs
from app.schemas.response import TicketResolutionResponse
from app.schemas.ticket import TicketCreate, TicketResponse

logger = logging.getLogger(__name__)

router = APIRouter()
# Keep native embedding inference serial on small MVP hosts; HTTP reads remain responsive.
_pipeline_capacity = threading.BoundedSemaphore(1)

supervisor = SupervisorAgent()
_active_ticket_ids = set()
_active_ticket_guard = threading.Lock()


def _claim_ticket(ticket_id: str):
    with _active_ticket_guard:
        if ticket_id in _active_ticket_ids:
            raise HTTPException(status_code=409, detail="This ticket is already being processed")
        _active_ticket_ids.add(ticket_id)


def _release_ticket(ticket_id: str):
    with _active_ticket_guard:
        _active_ticket_ids.discard(ticket_id)


def _ticket_or_404(db: Session, ticket_id: str) -> Ticket:
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if ticket is None:
        raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} not found")
    return ticket


@router.get("/domain-packs")
async def get_domain_packs():
    """Lists available domain packs for the UI's pack selector."""
    packs = []
    for pack_id in list_available_packs():
        pack = get_domain_pack(pack_id)
        packs.append(
            {
                "id": pack.config.id,
                "display_name": pack.config.display_name,
                "description": pack.config.description,
                "intent_eval_available": pack.config.intent_eval_available,
            }
        )
    return {"packs": packs, "default": settings.domain_pack}


@router.post("/tickets", response_model=TicketResolutionResponse, status_code=status.HTTP_201_CREATED)
def submit_ticket(ticket_data: TicketCreate, db: Session = Depends(get_db)):
    logger.info(f"Received ticket submission from {ticket_data.user_email}")

    domain_pack_id = ticket_data.domain_pack or settings.domain_pack
    try:
        get_domain_pack(domain_pack_id)
    except DomainPackNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    try:
        ticket = Ticket(
            title=ticket_data.title,
            description=ticket_data.description,
            user_email=ticket_data.user_email,
            category=ticket_data.category,
            domain_pack=domain_pack_id,
        )

        db.add(ticket)
        db.commit()
        db.refresh(ticket)

        logger.info(f"Created ticket: {ticket.id}")

        return _process_ticket(ticket, db)

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception("Ticket submission failed")
        raise HTTPException(
            status_code=500, detail="Ticket processing failed; the open ticket can be retried"
        ) from e


def _process_ticket(ticket: Ticket, db: Session, *, allow_review: bool = False) -> TicketResolutionResponse:
    """Process an existing ticket once, retaining its ID and prior audit history."""
    ticket_id = ticket.id
    _claim_ticket(ticket_id)
    start_time = time.time()
    try:
        db.refresh(ticket)
        if ticket.status != "open" and not (allow_review and ticket.status == "in_progress"):
            raise HTTPException(status_code=409, detail="Only open or review tickets can be processed")
        if ticket.status == "in_progress":
            db.add(AgentDecisionLog(
                ticket_id=ticket.id, agent_name="retry_controller", action="reassess_review",
                output_data={"previous_status": ticket.status, "reason": "Requested AI reassessment; prior traces preserved"},
            ))
        with _pipeline_capacity:
            result = supervisor.process_ticket(
                ticket_id=ticket.id,
                title=ticket.title,
                description=ticket.description,
                domain_pack_id=ticket.domain_pack or settings.domain_pack,
            )
        trace = result.trace or {}

        ticket.status = "in_progress" if result.requires_human_review else "resolved"
        if not result.requires_human_review:
            ticket.resolved_at = datetime.utcnow()
        ticket.intent = trace.get("intent")
        ticket.priority = trace.get("priority") or "medium"
        ticket.sentiment = trace.get("sentiment")

        for decision in result.agent_decisions:
            agent_log = AgentDecisionLog(
                ticket_id=ticket.id,
                agent_name=decision.agent_name,
                action=decision.action,
                output_data=decision.output,
                confidence=decision.confidence,
            )
            db.add(agent_log)

        response_log = DraftedResponseLog(
            ticket_id=ticket.id,
            draft_text=result.draft_text,
            confidence=result.confidence,
            kb_documents=[doc.dict() for doc in result.kb_documents],
            requires_human_review=result.requires_human_review,
            iteration_count=trace.get("iteration_count"),
            intent_rationale=trace.get("intent_rationale"),
            escalation_rationale=trace.get("escalation_rationale"),
            final_action=trace.get("final_action"),
            judge_score_history=trace.get("judge_score_history"),
            continuation_rationale=trace.get("continuation_rationale"),
            anomaly_flags=trace.get("anomaly_flags"),
            cost_estimate=trace.get("cost_estimate"),
        )
        db.add(response_log)

        db.commit()

        from app.analytics.cloud_records import save_ticket_record

        cloud_saved = save_ticket_record(
            jsonable_encoder(
                {
                    "ticket_id": ticket.id,
                    "title": ticket.title,
                    "description": ticket.description,
                    "user_email": ticket.user_email,
                    "domain_pack": ticket.domain_pack,
                    "priority": ticket.priority,
                    "status": ticket.status,
                    "created_at": ticket.created_at,
                    "drafted_response": result.draft_text,
                    "trace": trace,
                    "agent_decisions": [d.model_dump(mode="json") for d in result.agent_decisions],
                    "supporting_documents": [d.model_dump(mode="json") for d in result.kb_documents],
                }
            )
        )
        trace["cloud_record_saved"] = cloud_saved
        processing_time = time.time() - start_time

        return TicketResolutionResponse(
            ticket_id=ticket.id,
            status=ticket.status,
            drafted_response=result.draft_text,
            confidence_score=result.confidence,
            supporting_documents=result.kb_documents,
            processing_time_seconds=round(processing_time, 2),
            requires_human_review=result.requires_human_review,
            trace=trace,
        )
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception("Ticket processing failed for %s", ticket_id)
        raise HTTPException(
            status_code=500, detail="Ticket processing failed; the open ticket can be retried"
        ) from e
    finally:
        _release_ticket(ticket_id)


@router.post("/tickets/{ticket_id}/retry", response_model=TicketResolutionResponse)
def retry_ticket(ticket_id: str, db: Session = Depends(get_db)):
    ticket = _ticket_or_404(db, ticket_id)
    if ticket.status not in ("open", "in_progress"):
        raise HTTPException(status_code=409, detail="Only open or review tickets can be retried")
    return _process_ticket(ticket, db, allow_review=True)


@router.post("/tickets/{ticket_id}/resolve")
def resolve_ticket(ticket_id: str, db: Session = Depends(get_db)):
    """Record a human resolution without rewriting the AI's original assessment."""
    ticket = _ticket_or_404(db, ticket_id)
    _claim_ticket(ticket_id)
    try:
        db.refresh(ticket)
        if ticket.status != "in_progress":
            raise HTTPException(
                status_code=409, detail="Only tickets awaiting human review can be marked resolved"
            )
        ticket.status = "resolved"
        ticket.resolved_at = datetime.utcnow()
        db.add(
            AgentDecisionLog(
                ticket_id=ticket.id,
                agent_name="human_reviewer",
                action="mark_resolved",
                output_data={"resolution_source": "human", "previous_status": "in_progress"},
                confidence=None,
            )
        )
        db.commit()
        db.refresh(ticket)
        from app.analytics.cloud_records import save_ticket_record

        detail = get_ticket_trace(ticket.id, db)
        cloud_saved = save_ticket_record(
            jsonable_encoder(
                {
                    "ticket_id": ticket.id,
                    "title": ticket.title,
                    "description": ticket.description,
                    "user_email": ticket.user_email,
                    "domain_pack": ticket.domain_pack,
                    "priority": ticket.priority,
                    "status": ticket.status,
                    "created_at": ticket.created_at,
                    "resolved_at": ticket.resolved_at,
                    "resolution_source": "human",
                    "drafted_response": detail["drafted_response"],
                    "agent_decisions": detail["agent_decisions"],
                }
            )
        )
        return {
            "ticket_id": ticket.id,
            "status": ticket.status,
            "resolution_source": "human",
            "cloud_record_saved": cloud_saved,
        }
    finally:
        _release_ticket(ticket_id)


@router.get("/tickets/{ticket_id}", response_model=TicketResponse)
async def get_ticket(ticket_id: str, db: Session = Depends(get_db)):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()

    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Ticket {ticket_id} not found")

    return ticket


@router.get("/tickets/{ticket_id}/trace")
def get_ticket_trace(ticket_id: str, db: Session = Depends(get_db)):
    """Full agentic trace for the UI's ticket-detail view: every agent
    decision plus the drafted response's judge/continuation/escalation trace.
    """
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Ticket {ticket_id} not found")

    decisions = sorted(ticket.agent_decisions, key=lambda d: d.created_at)
    response_log = (
        max(ticket.drafted_responses, key=lambda r: r.created_at) if ticket.drafted_responses else None
    )

    return {
        "ticket": {
            "id": ticket.id,
            "title": ticket.title,
            "description": ticket.description,
            "status": ticket.status,
            "priority": ticket.priority,
            "intent": ticket.intent,
            "sentiment": ticket.sentiment,
            "domain_pack": ticket.domain_pack,
            "created_at": ticket.created_at,
        },
        "agent_decisions": [
            {
                "agent_name": d.agent_name,
                "action": d.action,
                "output": d.output_data,
                "confidence": d.confidence,
                "created_at": d.created_at,
            }
            for d in decisions
        ],
        "drafted_response": None
        if not response_log
        else {
            "draft_text": response_log.draft_text,
            "confidence": response_log.confidence,
            "requires_human_review": response_log.requires_human_review,
            "iteration_count": response_log.iteration_count,
            "intent_rationale": response_log.intent_rationale,
            "escalation_rationale": response_log.escalation_rationale,
            "final_action": response_log.final_action,
            "judge_score_history": response_log.judge_score_history,
            "continuation_rationale": response_log.continuation_rationale,
            "anomaly_flags": response_log.anomaly_flags,
            "cost_estimate": response_log.cost_estimate,
            "kb_documents": response_log.kb_documents,
        },
    }


@router.get("/tickets", response_model=List[TicketResponse])
async def list_tickets(
    skip: int = 0,
    limit: int = Query(50, ge=1, le=500),
    status_filter: str = None,
    priority_filter: str = None,
    domain_pack_filter: str = None,
    db: Session = Depends(get_db),
):
    query = db.query(Ticket)

    if status_filter:
        query = query.filter(Ticket.status == status_filter)
    if priority_filter:
        query = query.filter(Ticket.priority == priority_filter)
    if domain_pack_filter:
        query = query.filter(Ticket.domain_pack == domain_pack_filter)

    tickets = query.order_by(Ticket.created_at.desc()).offset(skip).limit(limit).all()

    return tickets


@router.get("/overview")
def workspace_overview(days: int = Query(7, ge=1, le=90), db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    first_day = now.date() - timedelta(days=days - 1)
    tickets = (
        db.query(Ticket).filter(Ticket.created_at >= datetime.combine(first_day, datetime.min.time())).all()
    )
    daily = {
        str(first_day + timedelta(days=i)): {
            "date": str(first_day + timedelta(days=i)),
            "total": 0,
            "resolved": 0,
        }
        for i in range(days)
    }
    for ticket in tickets:
        bucket = daily.get(str(ticket.created_at.date()))
        if bucket:
            bucket["total"] += 1
            bucket["resolved"] += int(ticket.status in ("resolved", "closed"))
    return {
        "total": len(tickets),
        "resolved": sum(t.status in ("resolved", "closed") for t in tickets),
        "needs_review": sum(t.status == "in_progress" for t in tickets),
        "open": sum(t.status == "open" for t in tickets),
        "ai_resolved": sum(
            t.status in ("resolved", "closed")
            and bool(t.drafted_responses)
            and not max(t.drafted_responses, key=lambda r: r.created_at).requires_human_review
            and not any(d.agent_name == "human_reviewer" for d in t.agent_decisions)
            for t in tickets
        ),
        "human_resolved": sum(
            t.status in ("resolved", "closed")
            and any(d.agent_name == "human_reviewer" for d in t.agent_decisions)
            for t in tickets
        ),
        "as_of": now.isoformat(),
        "daily": list(daily.values()),
        "recent": [
            TicketResponse.model_validate(t).model_dump(mode="json")
            for t in sorted(tickets, key=lambda t: t.created_at, reverse=True)[:6]
        ],
    }
