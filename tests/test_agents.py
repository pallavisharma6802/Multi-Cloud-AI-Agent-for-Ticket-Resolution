"""Unit tests for agent logic with mocked LLM/Azure clients."""
import pytest

from app.agents.azure_nlp_agent import AzureNLPAgent
from app.agents.continuation_agent import ContinuationAgent, PostGradingDecision
from app.agents.document_grader import DocumentGrader, RelevanceGrade
from app.agents.intent_priority_agent import IntentPriorityAgent, IntentPrioritySample
from app.agents.judge_agent import JudgeAgent, JudgeResult
from app.domain.loader import load_domain_pack
from app.schemas.response import KBDocument
from app.schemas.ticket import NLPSignals
from tests.conftest import make_metadata


def test_azure_nlp_agent_returns_raw_signals_only(mock_azure_text_analytics):
    entity_result = type("R", (), {"is_error": False, "entities": []})()
    sentiment_result = type("R", (), {"is_error": False, "sentiment": "negative"})()
    keyphrase_result = type("R", (), {"is_error": False, "key_phrases": ["password reset"]})()

    mock_azure_text_analytics.recognize_entities.return_value = [entity_result]
    mock_azure_text_analytics.analyze_sentiment.return_value = [sentiment_result]
    mock_azure_text_analytics.extract_key_phrases.return_value = [keyphrase_result]

    agent = AzureNLPAgent()
    result = agent.analyze_ticket("Can't login", "I forgot my password")

    assert isinstance(result, NLPSignals)
    assert result.sentiment == "negative"
    assert not hasattr(result, "intent")


def test_intent_priority_agent_majority_vote(mock_llm_client):
    pack = load_domain_pack("it_saas")
    signals = NLPSignals(entities=[], sentiment="neutral", key_phrases=["cancel", "order"])
    mock_llm_client.generate_structured.side_effect = [
        (IntentPrioritySample(intent="cancel_order", priority="medium", rationale="wants to cancel", confidence=0.8), make_metadata()),
        (IntentPrioritySample(intent="cancel_order", priority="medium", rationale="wants to cancel", confidence=0.75), make_metadata()),
        (IntentPrioritySample(intent="change_order", priority="low", rationale="different guess", confidence=0.6), make_metadata()),
    ]

    result, metas = IntentPriorityAgent(num_samples=3).classify(
        pack, "Cancel my order", "Please cancel order #123", signals
    )
    assert result.intent == "cancel_order"
    assert result.self_consistency_agreement == pytest.approx(2 / 3)
    assert len(metas) == 3


def test_document_grader_fails_closed_and_marks_relevance(mock_llm_client):
    docs = [
        KBDocument(doc_id="d1", content="how to cancel an order", similarity_score=0.9, metadata={}),
        KBDocument(doc_id="d2", content="password reset", similarity_score=0.5, metadata={}),
    ]
    mock_llm_client.generate_structured.side_effect = [
        (RelevanceGrade(relevant=True, rationale="matches"), make_metadata()),
        RuntimeError("LLM down"),
    ]
    graded, metas = DocumentGrader().grade_documents("I want to cancel my order", docs)
    assert graded[0].relevant is True
    assert graded[1].relevant is False  # fail closed on error
    assert len(metas) == 1


def test_judge_agent_returns_structured_scores(mock_llm_client):
    mock_llm_client.generate_structured.return_value = (
        JudgeResult(
            faithfulness_score=0.9,
            relevance_score=0.85,
            confidence=0.88,
            unsupported_claims=[],
            rationale="well grounded",
        ),
        make_metadata(),
    )
    doc = KBDocument(doc_id="d1", content="steps to cancel", similarity_score=0.9, metadata={})
    result, _ = JudgeAgent().judge("cancel my order", "Here is how to cancel...", [doc])
    assert result.faithfulness_score == 0.9
    assert result.confidence == 0.88


def test_continuation_agent_post_grading_decision(mock_llm_client):
    mock_llm_client.generate_structured.return_value = (
        PostGradingDecision(action="rewrite_query", rationale="nothing relevant found"),
        make_metadata(),
    )
    decision, _ = ContinuationAgent().decide_post_grading(
        ticket_text="x",
        priority="high",
        num_relevant=0,
        num_candidates=5,
        grading_rationales=["off topic"] * 5,
        iteration_count=0,
        llm_calls_so_far=3,
    )
    assert decision.action == "rewrite_query"
