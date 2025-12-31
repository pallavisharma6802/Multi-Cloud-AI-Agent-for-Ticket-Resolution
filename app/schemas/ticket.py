from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class TicketPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class TicketStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


class TicketCreate(BaseModel):
    title: str = Field(..., min_length=5, max_length=200, description="Ticket title")
    description: str = Field(..., min_length=10, description="Detailed description of the issue")
    user_email: str = Field(..., description="Email of user submitting ticket")
    category: Optional[str] = Field(None, description="Optional category tag")


class TicketIntentClassification(BaseModel):
    intent: str = Field(..., description="Classified intent")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score")
    entities: List[dict] = Field(default_factory=list, description="Extracted entities")
    sentiment: Optional[str] = Field(None, description="Sentiment analysis result")
    priority: TicketPriority = Field(default=TicketPriority.MEDIUM, description="Auto-assigned priority")


class TicketResponse(BaseModel):
    ticket_id: str = Field(..., description="Unique ticket identifier")
    title: str
    description: str
    user_email: str
    status: TicketStatus = Field(default=TicketStatus.OPEN)
    priority: TicketPriority = Field(default=TicketPriority.MEDIUM)
    intent: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
