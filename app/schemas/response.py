from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


class KBDocument(BaseModel):
    doc_id: str = Field(..., description="Document ID from knowledge base")
    content: str = Field(..., description="Document content")
    similarity_score: float = Field(..., ge=0.0, le=1.0, description="Similarity score from RAG")
    metadata: dict = Field(default_factory=dict, description="Additional document metadata")


class AgentDecision(BaseModel):
    agent_name: str = Field(..., description="Name of agent that made decision")
    action: str = Field(..., description="Action taken by agent")
    output: dict = Field(default_factory=dict, description="Agent output data")
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0, description="Confidence score if applicable")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class DraftedResponse(BaseModel):
    ticket_id: str = Field(..., description="Associated ticket ID")
    draft_text: str = Field(..., description="AI-generated response draft")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Overall confidence in response")
    kb_documents: List[KBDocument] = Field(default_factory=list, description="Supporting KB documents")
    agent_decisions: List[AgentDecision] = Field(default_factory=list, description="Audit trail of agent decisions")
    requires_human_review: bool = Field(default=False, description="Flag if human review needed")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class TicketResolutionResponse(BaseModel):
    ticket_id: str
    status: str
    drafted_response: str
    confidence_score: float
    supporting_documents: List[KBDocument]
    processing_time_seconds: float
    requires_human_review: bool
    
    class Config:
        json_schema_extra = {
            "example": {
                "ticket_id": "TKT-12345",
                "status": "in_progress",
                "drafted_response": "Based on your issue, here's the recommended solution...",
                "confidence_score": 0.92,
                "supporting_documents": [],
                "processing_time_seconds": 2.34,
                "requires_human_review": False
            }
        }
