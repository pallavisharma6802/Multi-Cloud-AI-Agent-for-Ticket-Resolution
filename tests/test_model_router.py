"""Tests for flat per-role Bedrock model lookup (no Ollama probing)."""
from app.llm import model_router as mr


def test_resolve_model_for_role_reads_settings(monkeypatch):
    monkeypatch.setattr(mr.settings, "model_intent_priority", "amazon.nova-lite-v1:0")
    monkeypatch.setattr(mr.settings, "model_grader", "amazon.nova-micro-v1:0")
    monkeypatch.setattr(mr.settings, "model_judge", "amazon.nova-lite-v1:0")
    monkeypatch.setattr(mr.settings, "model_drafting", "amazon.nova-lite-v1:0")
    monkeypatch.setattr(mr.settings, "model_continuation", "amazon.nova-micro-v1:0")
    monkeypatch.setattr(mr.settings, "model_supervisor", "amazon.nova-lite-v1:0")

    assert mr.resolve_model_for_role("intent_priority") == "amazon.nova-lite-v1:0"
    assert mr.resolve_model_for_role("document_grader") == "amazon.nova-micro-v1:0"
    assert mr.resolve_model_for_role("document_grader_rewrite") == "amazon.nova-micro-v1:0"
    assert mr.resolve_model_for_role("judge") == "amazon.nova-lite-v1:0"
    assert mr.resolve_model_for_role("drafting") == "amazon.nova-lite-v1:0"
    assert mr.resolve_model_for_role("continuation") == "amazon.nova-micro-v1:0"
    assert mr.resolve_model_for_role("final_decision") == "amazon.nova-lite-v1:0"


def test_resolve_model_for_role_explicit_override(monkeypatch):
    monkeypatch.setattr(mr.settings, "model_judge", "amazon.nova-lite-v1:0")
    assert (
        mr.resolve_model_for_role("judge", explicit_model="amazon.nova-micro-v1:0")
        == "amazon.nova-micro-v1:0"
    )


def test_resolve_unknown_role_falls_back_to_supervisor(monkeypatch):
    monkeypatch.setattr(mr.settings, "model_supervisor", "amazon.nova-lite-v1:0")
    assert mr.resolve_model_for_role("unknown_role") == "amazon.nova-lite-v1:0"


def test_routing_summary_lists_assignments(monkeypatch):
    monkeypatch.setattr(mr.settings, "aws_region", "us-east-1")
    for attr in (
        "model_intent_priority",
        "model_grader",
        "model_judge",
        "model_continuation",
        "model_drafting",
        "model_supervisor",
    ):
        monkeypatch.setattr(mr.settings, attr, "amazon.nova-lite-v1:0")

    summary = mr.routing_summary()
    assert summary["backend"] == "bedrock"
    assert summary["region"] == "us-east-1"
    assert summary["assignments"]["intent_priority"] == "amazon.nova-lite-v1:0"
    assert summary["assignments"]["document_grader"] == "amazon.nova-lite-v1:0"
    assert summary["distinct_models"] == ["amazon.nova-lite-v1:0"]
