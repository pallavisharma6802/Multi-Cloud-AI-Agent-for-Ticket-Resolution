"""LangGraph supervisor for ticket resolution.

Orchestrates analyze → retrieve → grade → draft → judge, with Continuation
Agent routing for CRAG re-retrieval and Reflexion re-draft. Hard caps in
`_safety_net_reason` only force termination; they do not set business outcomes.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Dict, List, Literal, Optional, TypedDict

from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

from app.agents.azure_nlp_agent import AzureNLPAgent
from app.agents.continuation_agent import ContinuationAgent
from app.agents.document_grader import DocumentGrader, GradedDocument
from app.agents.drafting_agent import DraftingAgent
from app.agents.intent_priority_agent import IntentPriorityAgent
from app.agents.judge_agent import JudgeAgent
from app.agents.retrieval_agent import RetrievalAgent
from app.analytics.bigquery_sink import get_bigquery_sink
from app.config import settings
from app.domain.loader import get_domain_pack
from app.llm.bedrock_client import LLMCallMetadata, get_llm_client
from app.schemas.response import AgentDecision, DraftedResponse, KBDocument

logger = logging.getLogger(__name__)


class FinalDecision(BaseModel):
    final_action: Literal["auto_resolve", "escalate"] = Field(
        description="Whether this ticket can be auto-resolved with the drafted response, or must go to a human"
    )
    rationale: str = Field(description="Reasoning over the full trace: intent/priority, judge scores, "
                            "continuation history, and any anomalies")
    confidence: float = Field(ge=0.0, le=1.0)


class TicketState(TypedDict, total=False):
    ticket_id: str
    title: str
    description: str
    domain_pack_id: str

    entities: List[dict]
    sentiment: str
    key_phrases: List[str]

    intent: str
    category: Optional[str]
    priority: str
    intent_rationale: str
    intent_confidence: float
    intent_self_consistency: float

    query: str
    kb_candidates: List[KBDocument]
    graded_documents: List[GradedDocument]
    relevant_documents: List[KBDocument]
    grading_rationale: List[str]
    retrieval_iteration: int
    post_grading_action: str

    drafted_response: str
    judge_result: dict
    judge_score_history: List[dict]
    judge_feedback_text: Optional[str]
    drafting_iteration: int
    post_judging_action: str
    post_judging_rationale: str

    continuation_rationale: List[str]
    iteration_count: int
    anomaly_flags: List[str]

    llm_call_count: int
    total_tokens: int
    total_latency_ms: float
    start_time: float

    final_action: str
    final_rationale: str
    final_confidence: float
    requires_human_review: bool

    agent_decisions: List[AgentDecision]
    error: Optional[str]
    # True when judge_response exhausted/failed — draft must not be auto-resolved without Self-RAG scores.
    judge_failed: bool


def _record_calls(state: TicketState, metadatas: List[LLMCallMetadata]):
    state["llm_call_count"] = state.get("llm_call_count", 0) + len(metadatas)
    state["total_tokens"] = state.get("total_tokens", 0) + sum(
        m.prompt_tokens + m.completion_tokens for m in metadatas
    )
    state["total_latency_ms"] = state.get("total_latency_ms", 0.0) + sum(m.latency_ms for m in metadatas)


def _log_decision(state: TicketState, agent_name: str, action: str, output: dict, confidence: Optional[float] = None):
    state.setdefault("agent_decisions", []).append(
        AgentDecision(agent_name=agent_name, action=action, output=output, confidence=confidence,
                      timestamp=datetime.utcnow())
    )


def _safety_net_reason(state: TicketState) -> Optional[str]:
    """Return a reason if max iterations or wall-clock time was exceeded."""
    if state.get("iteration_count", 0) >= settings.max_iterations:
        return f"max_iterations ({settings.max_iterations}) reached"
    elapsed = time.monotonic() - state.get("start_time", time.monotonic())
    if elapsed >= settings.max_wall_clock_seconds:
        return f"max_wall_clock_seconds ({settings.max_wall_clock_seconds}) reached ({elapsed:.0f}s elapsed)"
    return None


class SupervisorAgent:
    def __init__(self):
        self.azure_nlp = AzureNLPAgent()
        self.intent_priority = IntentPriorityAgent(num_samples=settings.intent_num_samples)
        self.document_grader = DocumentGrader()
        self.judge = JudgeAgent()
        self.continuation = ContinuationAgent()
        self.drafting = DraftingAgent()
        self.llm_client = get_llm_client()
        self.bq_sink = get_bigquery_sink()
        self._retrieval_agents: Dict[str, RetrievalAgent] = {}
        self.graph = self._build_graph()

    def _get_retrieval_agent(self, domain_pack_id: str) -> RetrievalAgent:
        if domain_pack_id not in self._retrieval_agents:
            self._retrieval_agents[domain_pack_id] = RetrievalAgent(domain_pack_id=domain_pack_id)
        return self._retrieval_agents[domain_pack_id]

    # Graph construction
    def _build_graph(self):
        workflow = StateGraph(TicketState)

        workflow.add_node("analyze_ticket", self._analyze_ticket_node)
        workflow.add_node("retrieve_documents", self._retrieve_documents_node)
        workflow.add_node("grade_documents", self._grade_documents_node)
        workflow.add_node("continuation_post_grading", self._continuation_post_grading_node)
        workflow.add_node("draft_response", self._draft_response_node)
        workflow.add_node("judge_response", self._judge_response_node)
        workflow.add_node("continuation_post_judging", self._continuation_post_judging_node)
        workflow.add_node("final_decision", self._final_decision_node)

        workflow.set_entry_point("analyze_ticket")

        workflow.add_conditional_edges(
            "analyze_ticket", self._route_on_error,
            {"error": "final_decision", "ok": "retrieve_documents"},
        )
        workflow.add_conditional_edges(
            "retrieve_documents", self._route_on_error,
            {"error": "final_decision", "ok": "grade_documents"},
        )
        workflow.add_conditional_edges(
            "grade_documents", self._route_on_error,
            {"error": "final_decision", "ok": "continuation_post_grading"},
        )
        workflow.add_conditional_edges(
            "continuation_post_grading", lambda s: s.get("post_grading_action", "escalate"),
            {"rewrite_query": "retrieve_documents", "proceed": "draft_response", "escalate": "final_decision"},
        )
        workflow.add_conditional_edges(
            "draft_response", self._route_on_error,
            {"error": "final_decision", "ok": "judge_response"},
        )
        workflow.add_conditional_edges(
            "judge_response", self._route_on_error,
            {"error": "final_decision", "ok": "continuation_post_judging"},
        )
        workflow.add_conditional_edges(
            "continuation_post_judging", lambda s: s.get("post_judging_action", "escalate"),
            {"retry": "draft_response", "accept": "final_decision", "escalate": "final_decision"},
        )
        workflow.add_edge("final_decision", END)

        return workflow.compile()

    @staticmethod
    def _route_on_error(state: TicketState) -> str:
        return "error" if state.get("error") else "ok"

    # Nodes
    def _analyze_ticket_node(self, state: TicketState) -> TicketState:
        logger.info(f"[analyze_ticket] {state['ticket_id']}")
        try:
            pack = get_domain_pack(state["domain_pack_id"])
            signals = self.azure_nlp.analyze_ticket(state["title"], state["description"])

            result, metas = self.intent_priority.classify(
                pack=pack, title=state["title"], description=state["description"], signals=signals
            )
            _record_calls(state, metas)

            state["entities"] = signals.entities
            state["sentiment"] = signals.sentiment or "neutral"
            state["key_phrases"] = signals.key_phrases
            state["intent"] = result.intent
            state["category"] = result.category
            state["priority"] = result.priority
            state["intent_rationale"] = result.rationale
            state["intent_confidence"] = result.confidence
            state["intent_self_consistency"] = result.self_consistency_agreement
            state["query"] = f"{state['title']}. {state['description']}"
            state["iteration_count"] = 0
            state["anomaly_flags"] = []

            _log_decision(state, "azure_nlp_agent", "extract_signals", {
                "num_entities": len(signals.entities), "sentiment": signals.sentiment,
                "num_key_phrases": len(signals.key_phrases),
            })
            _log_decision(state, "intent_priority_agent", "classify", {
                "intent": result.intent, "priority": result.priority, "rationale": result.rationale,
                "self_consistency_agreement": result.self_consistency_agreement,
                "known_taxonomy_intent": result.known_taxonomy_intent,
            }, confidence=result.confidence)

            logger.info(f"[analyze_ticket] intent={result.intent} priority={result.priority} "
                        f"agreement={result.self_consistency_agreement:.2f}")
        except Exception as e:
            logger.error(f"[analyze_ticket] failed: {e}")
            state["error"] = f"Analysis failed: {e}"
        return state

    def _retrieve_documents_node(self, state: TicketState) -> TicketState:
        logger.info(f"[retrieve_documents] {state['ticket_id']} query='{state['query'][:60]}...'")
        try:
            agent = self._get_retrieval_agent(state["domain_pack_id"])
            candidates = agent.retrieve_relevant_documents(
                query_text=state["query"],
                intent=state.get("intent"),
                top_k=settings.retrieval_top_k,
            )
            state["kb_candidates"] = candidates
            state["retrieval_iteration"] = state.get("retrieval_iteration", 0) + 1

            _log_decision(state, "retrieval_agent", "retrieve_candidates", {
                "num_candidates": len(candidates),
                "retrieval_iteration": state["retrieval_iteration"],
                "methods": [c.metadata.get("retrieval_method") for c in candidates],
            })
        except Exception as e:
            logger.error(f"[retrieve_documents] failed: {e}")
            state["error"] = f"Retrieval failed: {e}"
            state["kb_candidates"] = []
        return state

    def _grade_documents_node(self, state: TicketState) -> TicketState:
        logger.info(f"[grade_documents] {state['ticket_id']}")
        try:
            ticket_text = f"{state['title']}. {state['description']}"
            graded, metas = self.document_grader.grade_documents(ticket_text, state["kb_candidates"])
            _record_calls(state, metas)

            state["graded_documents"] = graded
            state["relevant_documents"] = [g.document for g in graded if g.relevant]
            state["grading_rationale"] = [g.rationale for g in graded]

            _log_decision(state, "document_grader", "grade_documents", {
                "num_candidates": len(graded),
                "num_relevant": len(state["relevant_documents"]),
                # Per-doc rationale for the ticket-detail trace UI.
                "graded_documents": [
                    {
                        "doc_id": g.document.doc_id,
                        "relevant": g.relevant,
                        "rationale": g.rationale,
                        "content_preview": g.document.content[:200],
                    }
                    for g in graded
                ],
            })
            logger.info(f"[grade_documents] {len(state['relevant_documents'])}/{len(graded)} relevant")
        except Exception as e:
            logger.error(f"[grade_documents] failed: {e}")
            state["error"] = f"Grading failed: {e}"
        return state

    def _continuation_post_grading_node(self, state: TicketState) -> TicketState:
        safety_reason = _safety_net_reason(state)
        if safety_reason:
            logger.warning(f"[continuation_post_grading] SAFETY NET tripped: {safety_reason}")
            state.setdefault("anomaly_flags", []).append(f"post_grading_safety_net: {safety_reason}")
            # Prefer drafting with whatever we have over hard-escalating mid-loop when docs exist.
            if state.get("relevant_documents"):
                state["post_grading_action"] = "proceed"
                state.setdefault("continuation_rationale", []).append(
                    f"[safety net] wall/iter cap hit; proceeding to draft with "
                    f"{len(state['relevant_documents'])} relevant docs: {safety_reason}"
                )
            else:
                state["post_grading_action"] = "escalate"
                state.setdefault("continuation_rationale", []).append(
                    f"[safety net, not agentic] escalated: {safety_reason}"
                )
            return state

        # Cap CRAG rewrites — further loops mostly burn wall-clock on small models.
        retrieval_iters = state.get("retrieval_iteration", 0)
        if retrieval_iters > settings.max_query_rewrites and state.get("relevant_documents"):
            state["post_grading_action"] = "proceed"
            state.setdefault("continuation_rationale", []).append(
                f"[rewrite cap] max_query_rewrites={settings.max_query_rewrites} reached; proceeding to draft"
            )
            return state
        if retrieval_iters > settings.max_query_rewrites and not state.get("relevant_documents"):
            # One more chance via continuation LLM, but default bias to escalate without another rewrite.
            pass

        try:
            decision, meta = self.continuation.decide_post_grading(
                ticket_text=f"{state['title']}. {state['description']}",
                priority=state["priority"],
                num_relevant=len(state.get("relevant_documents", [])),
                num_candidates=len(state.get("kb_candidates", [])),
                grading_rationales=state.get("grading_rationale", []),
                iteration_count=state.get("iteration_count", 0),
                llm_calls_so_far=state.get("llm_call_count", 0),
            )
            _record_calls(state, [meta])
            action = decision.action
            if action == "rewrite_query" and retrieval_iters > settings.max_query_rewrites:
                action = "proceed" if state.get("relevant_documents") else "escalate"
                state.setdefault("continuation_rationale", []).append(
                    f"[rewrite cap] coerced {decision.action} -> {action}: {decision.rationale}"
                )
            else:
                state.setdefault("continuation_rationale", []).append(
                    f"[post_grading] {action}: {decision.rationale}"
                )
            state["post_grading_action"] = action

            _log_decision(state, "continuation_agent", "decide_post_grading", {
                "action": action, "rationale": decision.rationale,
            })

            if action == "rewrite_query":
                rewritten, meta2 = self.document_grader.rewrite_query(state["query"], state["graded_documents"])
                _record_calls(state, [meta2])
                # If rewrite was rejected (same as original), don't loop forever.
                if rewritten.rewritten_query.strip() == (state.get("query") or "").strip():
                    state["post_grading_action"] = "proceed" if state.get("relevant_documents") else "escalate"
                    state.setdefault("continuation_rationale", []).append(
                        "[rewrite rejected/noop] skipping another retrieval loop"
                    )
                else:
                    state["query"] = rewritten.rewritten_query
                    state["iteration_count"] = state.get("iteration_count", 0) + 1
                    _log_decision(state, "document_grader", "rewrite_query", {
                        "new_query": rewritten.rewritten_query, "rationale": rewritten.rationale,
                    })

            logger.info(f"[continuation_post_grading] action={state['post_grading_action']}")
        except Exception as e:
            logger.error(f"[continuation_post_grading] failed: {e}")
            state["post_grading_action"] = "escalate"
            state["error"] = state.get("error") or f"Continuation (post-grading) failed: {e}"
        return state

    def _draft_response_node(self, state: TicketState) -> TicketState:
        logger.info(f"[draft_response] {state['ticket_id']}")
        try:
            previous_draft = state.get("drafted_response") if state.get("judge_feedback_text") else None
            response_text, meta = self.drafting.draft_response(
                ticket_title=state["title"],
                ticket_description=state["description"],
                intent=state["intent"],
                kb_documents=state.get("relevant_documents", []),
                previous_draft=previous_draft,
                judge_feedback=state.get("judge_feedback_text"),
            )
            _record_calls(state, [meta])
            state["drafted_response"] = response_text
            state["drafting_iteration"] = state.get("drafting_iteration", 0) + 1

            _log_decision(state, "drafting_agent", "draft_response", {
                "response_length_words": len(response_text.split()),
                "drafting_iteration": state["drafting_iteration"],
                "is_reflexion_retry": previous_draft is not None,
            })
        except Exception as e:
            logger.error(f"[draft_response] failed: {e}")
            state["error"] = f"Drafting failed: {e}"
            state["drafted_response"] = "Unable to generate a response at this time."
        return state

    def _judge_response_node(self, state: TicketState) -> TicketState:
        logger.info(f"[judge_response] {state['ticket_id']}")
        try:
            ticket_text = f"{state['title']}. {state['description']}"
            result, meta = self.judge.judge(
                ticket_text=ticket_text,
                response_text=state["drafted_response"],
                relevant_documents=state.get("relevant_documents", []),
            )
            _record_calls(state, [meta])

            judge_dict = result.model_dump()
            state["judge_result"] = judge_dict
            state.setdefault("judge_score_history", []).append(judge_dict)
            if result.unsupported_claims or result.rationale:
                state["judge_feedback_text"] = (
                    f"{result.rationale} Unsupported claims: {result.unsupported_claims}"
                    if result.unsupported_claims else result.rationale
                )

            state["judge_failed"] = False
            _log_decision(state, "judge_agent", "judge_response", judge_dict, confidence=result.confidence)
            logger.info(f"[judge_response] faithfulness={result.faithfulness_score:.2f} "
                        f"relevance={result.relevance_score:.2f} confidence={result.confidence:.2f}")
        except Exception as e:
            logger.error(f"[judge_response] failed: {e}")
            state["error"] = f"Judging failed: {e}"
            state["judge_failed"] = True
        return state

    def _continuation_post_judging_node(self, state: TicketState) -> TicketState:
        safety_reason = _safety_net_reason(state)
        if safety_reason:
            logger.warning(f"[continuation_post_judging] SAFETY NET tripped: {safety_reason}")
            state.setdefault("anomaly_flags", []).append(f"post_judging_safety_net: {safety_reason}")
            state["post_judging_action"] = "escalate"
            state["post_judging_rationale"] = safety_reason
            state.setdefault("continuation_rationale", []).append(
                f"[safety net, not agentic] escalated: {safety_reason}"
            )
            return state

        try:
            judge_result = state["judge_result"]
            decision, meta = self.continuation.decide_post_judging(
                ticket_text=f"{state['title']}. {state['description']}",
                priority=state["priority"],
                faithfulness_score=judge_result["faithfulness_score"],
                relevance_score=judge_result["relevance_score"],
                judge_confidence=judge_result["confidence"],
                unsupported_claims=judge_result.get("unsupported_claims", []),
                judge_score_history=state.get("judge_score_history", [])[:-1],
                iteration_count=state.get("iteration_count", 0),
                llm_calls_so_far=state.get("llm_call_count", 0),
            )
            _record_calls(state, [meta])
            state["post_judging_action"] = decision.action
            state["post_judging_rationale"] = decision.rationale
            state.setdefault("continuation_rationale", []).append(f"[post_judging] {decision.action}: {decision.rationale}")

            _log_decision(state, "continuation_agent", "decide_post_judging", {
                "action": decision.action, "rationale": decision.rationale,
            })

            if decision.action == "retry":
                state["iteration_count"] = state.get("iteration_count", 0) + 1
            else:
                state["judge_feedback_text"] = None

            logger.info(f"[continuation_post_judging] action={decision.action}")
        except Exception as e:
            logger.error(f"[continuation_post_judging] failed: {e}")
            state["post_judging_action"] = "escalate"
            state["error"] = state.get("error") or f"Continuation (post-judging) failed: {e}"
        return state

    def _emit_analytics_event(self, state: TicketState) -> None:
        """Emit one BigQuery event from final_decision; never raises or blocks."""
        try:
            judge_result = state.get("judge_result") or {}
            self.bq_sink.record_ticket_event({
                "ticket_id": state["ticket_id"],
                "domain_pack": state.get("domain_pack_id"),
                "intent": state.get("intent"),
                "category": state.get("category"),
                "priority": state.get("priority"),
                "sentiment": state.get("sentiment"),
                "final_action": state.get("final_action"),
                "requires_human_review": state.get("requires_human_review"),
                "final_confidence": state.get("final_confidence"),
                "intent_confidence": state.get("intent_confidence"),
                "intent_self_consistency": state.get("intent_self_consistency"),
                "iteration_count": state.get("iteration_count", 0),
                "retrieval_iteration": state.get("retrieval_iteration"),
                "drafting_iteration": state.get("drafting_iteration"),
                "num_kb_candidates": len(state.get("kb_candidates", []) or []),
                "num_relevant_documents": len(state.get("relevant_documents", []) or []),
                "judge_faithfulness_score": judge_result.get("faithfulness_score"),
                "judge_relevance_score": judge_result.get("relevance_score"),
                "judge_confidence": judge_result.get("confidence"),
                "escalation_rationale": state.get("final_rationale") if state.get("requires_human_review") else None,
                "anomaly_flags": state.get("anomaly_flags", []),
                "continuation_rationale": state.get("continuation_rationale", []),
                "llm_call_count": state.get("llm_call_count", 0),
                "total_tokens": state.get("total_tokens", 0),
                "total_latency_ms": state.get("total_latency_ms", 0.0),
                "wall_clock_seconds": time.monotonic() - state.get("start_time", time.monotonic()),
            })
        except Exception as e:
            # Analytics must not fail ticket resolution.
            logger.warning(f"[final_decision] analytics event emission failed (non-fatal): {e}")

    def _final_decision_node(self, state: TicketState) -> TicketState:
        logger.info(f"[final_decision] {state['ticket_id']}")

        if state.get("error") and not state.get("drafted_response"):
            state["final_action"] = "escalate"
            state["final_rationale"] = f"Pipeline error before a response could be drafted: {state['error']}"
            state["final_confidence"] = 0.0
            state["requires_human_review"] = True
            _log_decision(state, "supervisor", "final_decision", {
                "final_action": "escalate", "rationale": state["final_rationale"],
            })
            self._emit_analytics_event(state)
            return state

        # Judge exhaustion / failure: never auto-resolve an unscored draft via the final LLM.
        if state.get("judge_failed"):
            state["final_action"] = "escalate"
            state["final_rationale"] = (
                "Judge stage failed; cannot auto-resolve a draft without Self-RAG scores. "
                f"{state.get('error') or ''}"
            ).strip()
            state["final_confidence"] = 0.0
            state["requires_human_review"] = True
            _log_decision(state, "supervisor", "final_decision", {
                "final_action": "escalate",
                "rationale": state["final_rationale"],
                "judge_failed": True,
            })
            self._emit_analytics_event(state)
            return state

        try:
            judge_result = state.get("judge_result", {})
            anomalies = state.get("anomaly_flags", [])
            trace_summary = f"""
Intent: {state.get('intent')} (priority: {state.get('priority')}, confidence: {state.get('intent_confidence', 0):.2f})
Relevant documents found: {len(state.get('relevant_documents', []))}
Judge scores (final attempt): faithfulness={judge_result.get('faithfulness_score', 0):.2f}, \
relevance={judge_result.get('relevance_score', 0):.2f}, confidence={judge_result.get('confidence', 0):.2f}
Total drafting attempts: {state.get('drafting_iteration', 0)}
Continuation Agent history: {state.get('continuation_rationale', [])}
Engineering safety-net anomalies: {anomalies if anomalies else 'none'}
Pipeline errors encountered: {state.get('error') or 'none'}
""".strip()

            prompt = f"""You are the Supervisor making the final call on a support ticket resolution pipeline.

Ticket: {state['title']}. {state['description']}

Drafted response:
{state.get('drafted_response', '')}

Full pipeline trace:
{trace_summary}

Decide: should this drafted response be sent to the customer automatically (auto_resolve), or should this ticket \
be escalated to a human agent instead (escalate)?

Guidance:
- Prefer auto_resolve when a draft exists, judge faithfulness/relevance are reasonable (>= ~0.5), \
and the reply gives concrete next steps for a routine FAQ (track/cancel/password/refund/shipping).
- Escalate when the customer asked for a human, the issue is high-risk/billing dispute with missing facts, \
the draft is empty/ungrounded, or judge scores are clearly poor.
- Engineering safety-net anomalies mean the run was slow or hit a cap — that alone is NOT a reason to escalate \
if the draft and judge scores look adequate. Use them as a weak signal only."""

            decision, meta = self.llm_client.generate_structured(
                prompt=prompt, schema=FinalDecision, model=settings.model_supervisor,
                role="final_decision", temperature=0.0, num_predict=250,
            )
            _record_calls(state, [meta])

            state["final_action"] = decision.final_action
            state["final_rationale"] = decision.rationale
            state["final_confidence"] = decision.confidence
            state["requires_human_review"] = decision.final_action == "escalate"

            _log_decision(state, "supervisor", "final_decision", {
                "final_action": decision.final_action, "rationale": decision.rationale,
                "anomalies": anomalies,
            }, confidence=decision.confidence)

            logger.info(f"[final_decision] action={decision.final_action} confidence={decision.confidence:.2f}")
        except Exception as e:
            logger.error(f"[final_decision] LLM decision failed, failing safe to escalate: {e}")
            state["final_action"] = "escalate"
            state["final_rationale"] = f"Supervisor decision call failed, failing safe: {e}"
            state["final_confidence"] = 0.0
            state["requires_human_review"] = True

        self._emit_analytics_event(state)
        return state

    # Public entrypoint
    def process_ticket(
        self, ticket_id: str, title: str, description: str, domain_pack_id: Optional[str] = None
    ) -> DraftedResponse:
        domain_pack_id = domain_pack_id or settings.domain_pack
        logger.info(f"[Supervisor] Starting ticket processing: {ticket_id} (pack={domain_pack_id})")

        initial_state: TicketState = {
            "ticket_id": ticket_id,
            "title": title,
            "description": description,
            "domain_pack_id": domain_pack_id,
            "agent_decisions": [],
            "start_time": time.monotonic(),
            "iteration_count": 0,
            "llm_call_count": 0,
            "total_tokens": 0,
            "total_latency_ms": 0.0,
        }

        final_state = self.graph.invoke(initial_state, config={"recursion_limit": 50})

        cost_estimate = {
            "llm_call_count": final_state.get("llm_call_count", 0),
            "total_tokens": final_state.get("total_tokens", 0),
            "total_latency_ms": round(final_state.get("total_latency_ms", 0.0), 1),
        }

        result = DraftedResponse(
            ticket_id=ticket_id,
            draft_text=final_state.get("drafted_response", ""),
            confidence=final_state.get("final_confidence", 0.0),
            kb_documents=final_state.get("relevant_documents", []),
            agent_decisions=final_state.get("agent_decisions", []),
            requires_human_review=final_state.get("requires_human_review", True),
            created_at=datetime.utcnow(),
        )

        # Extra trace fields for DB/API persistence beyond DraftedResponse.
        result.trace = {
            "domain_pack": domain_pack_id,
            "intent": final_state.get("intent"),
            "category": final_state.get("category"),
            "priority": final_state.get("priority"),
            "intent_rationale": final_state.get("intent_rationale"),
            "intent_confidence": final_state.get("intent_confidence"),
            "iteration_count": final_state.get("iteration_count", 0),
            "judge_score_history": final_state.get("judge_score_history", []),
            "continuation_rationale": final_state.get("continuation_rationale", []),
            "escalation_rationale": final_state.get("final_rationale") if final_state.get("requires_human_review") else None,
            "final_action": final_state.get("final_action"),
            "anomaly_flags": final_state.get("anomaly_flags", []),
            "cost_estimate": cost_estimate,
            "sentiment": final_state.get("sentiment"),
        }

        logger.info(f"[Supervisor] Ticket processing complete: {ticket_id} -> {final_state.get('final_action')}")
        return result
