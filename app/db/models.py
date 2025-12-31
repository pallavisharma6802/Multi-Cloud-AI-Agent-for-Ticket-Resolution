from sqlalchemy import Column, String, Text, DateTime, Float, Boolean, JSON, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid


Base = declarative_base()


def generate_ticket_id():
    return f"TKT-{uuid.uuid4().hex[:8].upper()}"


class Ticket(Base):
    __tablename__ = "tickets"
    
    id = Column(String(50), primary_key=True, default=generate_ticket_id)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    user_email = Column(String(255), nullable=False, index=True)
    category = Column(String(100), nullable=True)
    
    status = Column(String(50), default="open", nullable=False, index=True)
    priority = Column(String(50), default="medium", nullable=False)
    intent = Column(String(100), nullable=True)
    sentiment = Column(String(50), nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    resolved_at = Column(DateTime, nullable=True)
    
    agent_decisions = relationship("AgentDecisionLog", back_populates="ticket", cascade="all, delete-orphan")
    drafted_responses = relationship("DraftedResponseLog", back_populates="ticket", cascade="all, delete-orphan")


class AgentDecisionLog(Base):
    __tablename__ = "agent_decisions"
    
    id = Column(String(50), primary_key=True, default=lambda: f"DEC-{uuid.uuid4().hex[:8].upper()}")
    ticket_id = Column(String(50), ForeignKey("tickets.id"), nullable=False, index=True)
    
    agent_name = Column(String(100), nullable=False)
    action = Column(String(200), nullable=False)
    output_data = Column(JSON, nullable=True)
    confidence = Column(Float, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    ticket = relationship("Ticket", back_populates="agent_decisions")


class DraftedResponseLog(Base):
    __tablename__ = "drafted_responses"
    
    id = Column(String(50), primary_key=True, default=lambda: f"RESP-{uuid.uuid4().hex[:8].upper()}")
    ticket_id = Column(String(50), ForeignKey("tickets.id"), nullable=False, index=True)
    
    draft_text = Column(Text, nullable=False)
    confidence = Column(Float, nullable=False)
    kb_documents = Column(JSON, nullable=True)
    requires_human_review = Column(Boolean, default=False, nullable=False)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    ticket = relationship("Ticket", back_populates="drafted_responses")
