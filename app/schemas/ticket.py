from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


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
    domain_pack: Optional[str] = Field(
        None, description="Domain pack id to route this ticket through (defaults to server config)"
    )


class NLPSignals(BaseModel):
    """Raw signals from Azure Text Analytics only -- no derived intent/priority."""
    entities: List[dict] = Field(default_factory=list, description="Extracted entities")
    sentiment: Optional[str] = Field(None, description="Sentiment analysis result")
    key_phrases: List[str] = Field(default_factory=list, description="Extracted key phrases")


class TicketIntentClassification(BaseModel):
    """Deprecated alias kept only so old imports don't hard-crash; new code
    should use NLPSignals for raw signals and IntentPriorityResult
    (app.agents.intent_priority_agent) for the agentic decision.
    """
    intent: str = Field(..., description="Classified intent")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score")
    entities: List[dict] = Field(default_factory=list, description="Extracted entities")
    sentiment: Optional[str] = Field(None, description="Sentiment analysis result")
    priority: TicketPriority = Field(default=TicketPriority.MEDIUM, description="Auto-assigned priority")


class TicketResponse(BaseModel):
    # The ORM model's primary-key attribute is `id` (see app/db/models.py's
    # Ticket.id), but the API contract exposes it as `ticket_id` everywhere
    # else (TicketResolutionResponse, DraftedResponse, etc.) -- validation_alias
    # tells pydantic to read the `id` attribute off the ORM object while still
    # serializing/naming the field `ticket_id` in the JSON response.
    ticket_id: str = Field(..., validation_alias="id", description="Unique ticket identifier")
    title: str
    description: str
    user_email: str
    status: TicketStatus = Field(default=TicketStatus.OPEN)
    priority: TicketPriority = Field(default=TicketPriority.MEDIUM)
    intent: Optional[str] = None
    domain_pack: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
        populate_by_name = True
