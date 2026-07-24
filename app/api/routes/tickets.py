import logging
import time
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
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

supervisor = SupervisorAgent()


@router.get("/domain-packs")
async def get_domain_packs():
    """Lists available domain packs for the UI's pack selector."""
    packs = []
    for pack_id in list_available_packs():
        pack = get_domain_pack(pack_id)
        packs.append({
            "id": pack.config.id,
            "display_name": pack.config.display_name,
            "description": pack.config.description,
            "intent_eval_available": pack.config.intent_eval_available,
        })
    return {"packs": packs, "default": settings.domain_pack}


@router.post("/tickets", response_model=TicketResolutionResponse, status_code=status.HTTP_201_CREATED)
async def submit_ticket(ticket_data: TicketCreate, db: Session = Depends(get_db)):
    logger.info(f"Received ticket submission from {ticket_data.user_email}")

    domain_pack_id = ticket_data.domain_pack or settings.domain_pack
    try:
        get_domain_pack(domain_pack_id)
    except DomainPackNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    start_time = time.time()

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

        result = supervisor.process_ticket(
            ticket_id=ticket.id,
            title=ticket.title,
            description=ticket.description,
            domain_pack_id=domain_pack_id,
        )
        trace = result.trace or {}

        ticket.status = "in_progress"
        ticket.intent = trace.get("intent")
        ticket.priority = trace.get("priority") or "medium"
        ticket.sentiment = trace.get("sentiment")

        for decision in result.agent_decisions:
            agent_log = AgentDecisionLog(
                ticket_id=ticket.id,
                agent_name=decision.agent_name,
                action=decision.action,
                output_data=decision.output,
                confidence=decision.confidence
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

    except Exception as e:
        logger.error(f"Ticket submission failed: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process ticket: {str(e)}"
        ) from e


@router.get("/tickets/{ticket_id}", response_model=TicketResponse)
async def get_ticket(ticket_id: str, db: Session = Depends(get_db)):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()

    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ticket {ticket_id} not found"
        )

    return ticket


@router.get("/tickets/{ticket_id}/trace")
async def get_ticket_trace(ticket_id: str, db: Session = Depends(get_db)):
    """Full agentic trace for the UI's ticket-detail view: every agent
    decision plus the drafted response's judge/continuation/escalation trace.
    """
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Ticket {ticket_id} not found")

    decisions = sorted(ticket.agent_decisions, key=lambda d: d.created_at)
    response_log = ticket.drafted_responses[-1] if ticket.drafted_responses else None

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
        "drafted_response": None if not response_log else {
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
    limit: int = 50,
    status_filter: str = None,
    priority_filter: str = None,
    domain_pack_filter: str = None,
    db: Session = Depends(get_db)
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
