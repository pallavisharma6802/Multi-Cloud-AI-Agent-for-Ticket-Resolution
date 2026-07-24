"""Eval harness pure-logic tests (no live Ollama/Pinecone)."""
import csv
import os
import tempfile

from eval.agreement_eval import evaluate_human_agreement
from eval.run_eval import _flatten_available_numeric, compare_to_baseline


def test_flatten_and_baseline_regression():
    report = {
        "packs": {
            "it_saas": {
                "intent_classification": {"available": True, "macro_f1": 0.50},
                "rag_quality": {"available": False, "reason": "skipped"},
            }
        }
    }
    flat = _flatten_available_numeric(report)
    assert flat["packs.it_saas.intent_classification.macro_f1"] == 0.50
    assert not any("rag_quality" in k for k in flat)

    baseline = {"thresholds": {"packs.it_saas.intent_classification.macro_f1": 0.80}}
    failures = compare_to_baseline(report, baseline)
    assert len(failures) == 1
    assert "REGRESSION" in failures[0]


def test_human_agreement_kappa():
    rows = [
        {"model_final_action": "escalate", "human_would_escalate": "true"},
        {"model_final_action": "auto_resolve", "human_would_escalate": "false"},
        {"model_final_action": "escalate", "human_would_escalate": "true"},
        {"model_final_action": "auto_resolve", "human_would_escalate": "false"},
        {"model_final_action": "escalate", "human_would_escalate": "false"},
        {"model_final_action": "auto_resolve", "human_would_escalate": "true"},
    ]
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="") as f:
        fields = ["ticket_id", "ticket_text", "model_final_action", "model_confidence", "human_would_escalate"]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for i, r in enumerate(rows):
            writer.writerow({"ticket_id": f"T{i}", "ticket_text": "x", "model_confidence": 0.5, **r})
        path = f.name
    try:
        result = evaluate_human_agreement(path)
        assert result["available"] is True
        assert result["num_reviewed"] == 6
        assert -1.0 <= result["cohens_kappa"] <= 1.0
    finally:
        os.unlink(path)
