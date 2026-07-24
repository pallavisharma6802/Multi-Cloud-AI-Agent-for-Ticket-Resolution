"""LangGraph supervisor path tests with mocked sub-agents."""
from unittest.mock import MagicMock

import pytest

from app.agents.continuation_agent import PostGradingDecision, PostJudgingDecision
from app.agents.document_grader import GradedDocument, RewrittenQuery
from app.agents.intent_priority_agent import IntentPriorityResult
from app.agents.judge_agent import JudgeResult
from app.agents.supervisor import FinalDecision, SupervisorAgent
from app.config import settings
from app.schemas.response import KBDocument
from app.schemas.ticket import NLPSignals
from tests.conftest import make_metadata


@pytest.fixture
def supervisor(monkeypatch):
    monkeypatch.setattr("app.agents.azure_nlp_agent.TextAnalyticsClient", lambda *a, **kw: MagicMock())
    agent = SupervisorAgent()
    agent.azure_nlp.analyze_ticket = MagicMock(
        return_value=NLPSignals(entities=[], sentiment="neutral", key_phrases=["cancel", "order"])
    )
    agent.intent_priority.classify = MagicMock(
        return_value=(
            IntentPriorityResult(
                intent="cancel_order",
                category="ORDER",
                priority="medium",
                rationale="wants to cancel",
                confidence=0.85,
                self_consistency_agreement=1.0,
                num_samples=3,
                known_taxonomy_intent=True,
            ),
            [make_metadata()],
        )
    )
    mock_retrieval_agent = MagicMock()
    mock_retrieval_agent.retrieve_relevant_documents.return_value = [
        KBDocument(doc_id="d1", content="how to cancel an order", similarity_score=0.9, metadata={})
    ]
    agent._retrieval_agents["it_saas"] = mock_retrieval_agent
    agent._mock_retrieval_agent = mock_retrieval_agent
    return agent


def _mock_final(agent, action="auto_resolve", confidence=0.9):
    agent.llm_client.generate_structured = MagicMock(
        return_value=(
            FinalDecision(final_action=action, rationale="reasoned over trace", confidence=confidence),
            make_metadata(),
        )
    )


def test_happy_path_auto_resolves(supervisor):
    supervisor.document_grader.grade_documents = MagicMock(
        return_value=(
            [
                GradedDocument(
                    document=KBDocument(doc_id="d1", content="how to cancel an order", similarity_score=0.9, metadata={}),
                    relevant=True,
                    rationale="matches",
                )
            ],
            [make_metadata()],
        )
    )
    supervisor.continuation.decide_post_grading = MagicMock(
        return_value=(PostGradingDecision(action="proceed", rationale="enough relevant docs"), make_metadata())
    )
    supervisor.drafting.draft_response = MagicMock(return_value=("Here's how to cancel your order...", make_metadata()))
    supervisor.judge.judge = MagicMock(
        return_value=(
            JudgeResult(
                faithfulness_score=0.95,
                relevance_score=0.9,
                confidence=0.9,
                unsupported_claims=[],
                rationale="well grounded",
            ),
            make_metadata(),
        )
    )
    supervisor.continuation.decide_post_judging = MagicMock(
        return_value=(PostJudgingDecision(action="accept", rationale="good enough"), make_metadata())
    )
    _mock_final(supervisor, action="auto_resolve", confidence=0.92)

    result = supervisor.process_ticket("TKT-1", "Cancel order", "Please cancel order #123", domain_pack_id="it_saas")
    assert result.requires_human_review is False
    assert result.trace["final_action"] == "auto_resolve"


def test_escalate_and_rewrite_loop(supervisor):
    supervisor.document_grader.grade_documents = MagicMock(
        return_value=(
            [
                GradedDocument(
                    document=KBDocument(doc_id="d1", content="unrelated", similarity_score=0.5, metadata={}),
                    relevant=False,
                    rationale="off topic",
                )
            ],
            [make_metadata()],
        )
    )
    supervisor.document_grader.rewrite_query = MagicMock(
        return_value=(RewrittenQuery(rewritten_query="cancel subscription refund", rationale="broaden"), make_metadata())
    )
    supervisor.continuation.decide_post_grading = MagicMock(
        side_effect=[
            (PostGradingDecision(action="rewrite_query", rationale="try again"), make_metadata()),
            (PostGradingDecision(action="escalate", rationale="still nothing"), make_metadata()),
        ]
    )
    supervisor.drafting.draft_response = MagicMock()
    _mock_final(supervisor, action="escalate", confidence=0.3)

    result = supervisor.process_ticket("TKT-2", "Weird issue", "Something odd", domain_pack_id="it_saas")
    assert result.requires_human_review is True
    assert supervisor._mock_retrieval_agent.retrieve_relevant_documents.call_count == 2
    supervisor.drafting.draft_response.assert_not_called()


def test_analytics_and_safety_net(supervisor, monkeypatch):
    supervisor.bq_sink = MagicMock()
    supervisor.document_grader.grade_documents = MagicMock(
        return_value=(
            [
                GradedDocument(
                    document=KBDocument(doc_id="d1", content="how to cancel", similarity_score=0.9, metadata={}),
                    relevant=True,
                    rationale="matches",
                )
            ],
            [make_metadata()],
        )
    )
    supervisor.continuation.decide_post_grading = MagicMock(
        return_value=(PostGradingDecision(action="proceed", rationale="enough"), make_metadata())
    )
    supervisor.drafting.draft_response = MagicMock(return_value=("draft", make_metadata()))
    supervisor.judge.judge = MagicMock(
        return_value=(
            JudgeResult(
                faithfulness_score=0.9,
                relevance_score=0.9,
                confidence=0.9,
                unsupported_claims=[],
                rationale="ok",
            ),
            make_metadata(),
        )
    )
    supervisor.continuation.decide_post_judging = MagicMock(
        return_value=(PostJudgingDecision(action="accept", rationale="ok"), make_metadata())
    )
    _mock_final(supervisor, action="auto_resolve")

    supervisor.process_ticket("TKT-6", "Cancel order", "Please cancel", domain_pack_id="it_saas")
    supervisor.bq_sink.record_ticket_event.assert_called_once()

    monkeypatch.setattr(settings, "max_iterations", 0)
    supervisor.continuation.decide_post_grading = MagicMock(side_effect=AssertionError("should not be called"))
    _mock_final(supervisor, action="escalate", confidence=0.1)
    result = supervisor.process_ticket("TKT-5", "Some ticket", "Some description", domain_pack_id="it_saas")
    assert result.requires_human_review is True
    assert any("safety_net" in flag for flag in result.trace["anomaly_flags"])
