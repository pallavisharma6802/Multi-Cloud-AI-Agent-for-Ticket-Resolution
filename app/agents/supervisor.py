from typing import TypedDict, List, Annotated
from langgraph.graph import StateGraph, END
from app.agents.azure_nlp_agent import AzureNLPAgent
from app.agents.retrieval_agent import RetrievalAgent
from app.agents.drafting_agent import DraftingAgent
from app.schemas.response import KBDocument, AgentDecision, DraftedResponse
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class TicketState(TypedDict):
    ticket_id: str
    title: str
    description: str
    
    intent: str
    confidence: float
    entities: List[dict]
    sentiment: str
    priority: str
    
    kb_documents: List[KBDocument]
    
    drafted_response: str
    final_confidence: float
    
    agent_decisions: List[AgentDecision]
    requires_human_review: bool
    error: str


class SupervisorAgent:
    
    def __init__(self):
        self.azure_nlp = AzureNLPAgent()
        self.retrieval = RetrievalAgent()
        self.drafting = DraftingAgent()
        self.graph = self._build_graph()
    
    def _build_graph(self) -> StateGraph:
        workflow = StateGraph(TicketState)
        
        workflow.add_node("analyze_ticket", self._analyze_ticket_node)
        workflow.add_node("retrieve_documents", self._retrieve_documents_node)
        workflow.add_node("draft_response", self._draft_response_node)
        workflow.add_node("evaluate_quality", self._evaluate_quality_node)
        
        workflow.set_entry_point("analyze_ticket")
        
        workflow.add_edge("analyze_ticket", "retrieve_documents")
        workflow.add_edge("retrieve_documents", "draft_response")
        workflow.add_edge("draft_response", "evaluate_quality")
        workflow.add_edge("evaluate_quality", END)
        
        return workflow.compile()
    
    def _analyze_ticket_node(self, state: TicketState) -> TicketState:
        logger.info(f"[Supervisor] Analyzing ticket {state['ticket_id']}")
        
        try:
            result = self.azure_nlp.analyze_ticket(
                title=state["title"],
                description=state["description"]
            )
            
            state["intent"] = result.intent
            state["confidence"] = result.confidence
            state["entities"] = result.entities
            state["sentiment"] = result.sentiment
            state["priority"] = result.priority.value
            
            state["agent_decisions"].append(AgentDecision(
                agent_name="azure_nlp_agent",
                action="analyze_intent_and_entities",
                output={
                    "intent": result.intent,
                    "confidence": result.confidence,
                    "sentiment": result.sentiment,
                    "priority": result.priority.value
                },
                confidence=result.confidence,
                timestamp=datetime.utcnow()
            ))
            
            logger.info(f"[Supervisor] Analysis complete: intent={result.intent}, priority={result.priority.value}")
            
        except Exception as e:
            logger.error(f"[Supervisor] Analysis failed: {e}")
            state["error"] = f"NLP analysis failed: {str(e)}"
        
        return state
    
    def _retrieve_documents_node(self, state: TicketState) -> TicketState:
        logger.info(f"[Supervisor] Retrieving relevant documents for {state['ticket_id']}")
        
        try:
            query_text = f"{state['title']}. {state['description']}"
            
            kb_docs = self.retrieval.retrieve_relevant_documents(
                query_text=query_text,
                intent=state.get("intent"),
                top_k=5,
                min_similarity=0.65
            )
            
            state["kb_documents"] = kb_docs
            
            state["agent_decisions"].append(AgentDecision(
                agent_name="retrieval_agent",
                action="retrieve_kb_documents",
                output={
                    "num_documents": len(kb_docs),
                    "avg_similarity": sum(d.similarity_score for d in kb_docs) / len(kb_docs) if kb_docs else 0
                },
                timestamp=datetime.utcnow()
            ))
            
            logger.info(f"[Supervisor] Retrieved {len(kb_docs)} relevant documents")
            
        except Exception as e:
            logger.error(f"[Supervisor] Retrieval failed: {e}")
            state["error"] = f"Document retrieval failed: {str(e)}"
            state["kb_documents"] = []
        
        return state
    
    def _draft_response_node(self, state: TicketState) -> TicketState:
        logger.info(f"[Supervisor] Drafting response for {state['ticket_id']}")
        
        try:
            response_text, confidence = self.drafting.draft_response(
                ticket_title=state["title"],
                ticket_description=state["description"],
                intent=state["intent"],
                kb_documents=state["kb_documents"]
            )
            
            state["drafted_response"] = response_text
            state["final_confidence"] = confidence
            
            state["agent_decisions"].append(AgentDecision(
                agent_name="drafting_agent",
                action="generate_response",
                output={
                    "response_length": len(response_text),
                    "confidence": confidence
                },
                confidence=confidence,
                timestamp=datetime.utcnow()
            ))
            
            logger.info(f"[Supervisor] Response drafted with {confidence:.2f} confidence")
            
        except Exception as e:
            logger.error(f"[Supervisor] Drafting failed: {e}")
            state["error"] = f"Response drafting failed: {str(e)}"
            state["drafted_response"] = "Unable to generate response at this time."
            state["final_confidence"] = 0.0
        
        return state
    
    def _evaluate_quality_node(self, state: TicketState) -> TicketState:
        logger.info(f"[Supervisor] Evaluating response quality for {state['ticket_id']}")
        
        confidence_threshold = 0.7
        min_kb_docs = 2
        
        needs_review = (
            state["final_confidence"] < confidence_threshold or
            len(state["kb_documents"]) < min_kb_docs or
            state["priority"] == "urgent" or
            "error" in state
        )
        
        state["requires_human_review"] = needs_review
        
        state["agent_decisions"].append(AgentDecision(
            agent_name="supervisor",
            action="evaluate_quality",
            output={
                "requires_review": needs_review,
                "reason": self._get_review_reason(state, confidence_threshold, min_kb_docs)
            },
            timestamp=datetime.utcnow()
        ))
        
        logger.info(f"[Supervisor] Quality evaluation complete. Human review: {needs_review}")
        
        return state
    
    def _get_review_reason(self, state: TicketState, conf_threshold: float, min_docs: int) -> str:
        reasons = []
        
        if state["final_confidence"] < conf_threshold:
            reasons.append(f"low confidence ({state['final_confidence']:.2f})")
        
        if len(state["kb_documents"]) < min_docs:
            reasons.append(f"insufficient KB docs ({len(state['kb_documents'])})")
        
        if state["priority"] == "urgent":
            reasons.append("urgent priority")
        
        if "error" in state:
            reasons.append("processing error occurred")
        
        return ", ".join(reasons) if reasons else "passed all checks"
    
    def process_ticket(
        self,
        ticket_id: str,
        title: str,
        description: str
    ) -> DraftedResponse:
        logger.info(f"[Supervisor] Starting ticket processing: {ticket_id}")
        
        initial_state = TicketState(
            ticket_id=ticket_id,
            title=title,
            description=description,
            intent="",
            confidence=0.0,
            entities=[],
            sentiment="",
            priority="",
            kb_documents=[],
            drafted_response="",
            final_confidence=0.0,
            agent_decisions=[],
            requires_human_review=False,
            error=""
        )
        
        final_state = self.graph.invoke(initial_state)
        
        result = DraftedResponse(
            ticket_id=ticket_id,
            draft_text=final_state["drafted_response"],
            confidence=final_state["final_confidence"],
            kb_documents=final_state["kb_documents"],
            agent_decisions=final_state["agent_decisions"],
            requires_human_review=final_state["requires_human_review"],
            created_at=datetime.utcnow()
        )
        
        logger.info(f"[Supervisor] Ticket processing complete: {ticket_id}")
        
        return result
