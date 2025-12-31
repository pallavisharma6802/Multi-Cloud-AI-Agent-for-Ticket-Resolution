from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import Ticket, AgentDecisionLog, DraftedResponseLog
from app.schemas.ticket import TicketCreate, TicketResponse
from app.schemas.response import TicketResolutionResponse, KBDocument
from app.agents.supervisor import SupervisorAgent
from typing import List
import logging
import time

logger = logging.getLogger(__name__)

router = APIRouter()

supervisor = SupervisorAgent()


@router.post("/tickets", response_model=TicketResolutionResponse, status_code=status.HTTP_201_CREATED)
async def submit_ticket(ticket_data: TicketCreate, db: Session = Depends(get_db)):
    logger.info(f"Received ticket submission from {ticket_data.user_email}")
    
    start_time = time.time()
    
    try:
        ticket = Ticket(
            title=ticket_data.title,
            description=ticket_data.description,
            user_email=ticket_data.user_email,
            category=ticket_data.category
        )
        
        db.add(ticket)
        db.commit()
        db.refresh(ticket)
        
        logger.info(f"Created ticket: {ticket.id}")
        
        result = supervisor.process_ticket(
            ticket_id=ticket.id,
            title=ticket.title,
            description=ticket.description
        )
        
        ticket.status = "in_progress"
        ticket.intent = result.agent_decisions[0].output.get("intent") if result.agent_decisions else None
        ticket.priority = result.agent_decisions[0].output.get("priority") if result.agent_decisions else "medium"
        ticket.sentiment = result.agent_decisions[0].output.get("sentiment") if result.agent_decisions else None
        
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
            requires_human_review=result.requires_human_review
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
            requires_human_review=result.requires_human_review
        )
        
    except Exception as e:
        logger.error(f"Ticket submission failed: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process ticket: {str(e)}"
        )


@router.get("/tickets/{ticket_id}", response_model=TicketResponse)
async def get_ticket(ticket_id: str, db: Session = Depends(get_db)):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    
    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ticket {ticket_id} not found"
        )
    
    return ticket


@router.get("/tickets", response_model=List[TicketResponse])
async def list_tickets(
    skip: int = 0,
    limit: int = 50,
    status_filter: str = None,
    db: Session = Depends(get_db)
):
    query = db.query(Ticket)
    
    if status_filter:
        query = query.filter(Ticket.status == status_filter)
    
    tickets = query.order_by(Ticket.created_at.desc()).offset(skip).limit(limit).all()
    
    return tickets
