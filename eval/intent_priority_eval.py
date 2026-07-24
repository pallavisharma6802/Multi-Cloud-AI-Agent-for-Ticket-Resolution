"""Evaluate IntentPriorityAgent against each pack's held-out test set.

Requires a live Ollama server. Packs with intent_eval_available=False report
the metric as unavailable (see domains/*/config.yaml).
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sklearn.metrics import accuracy_score, classification_report, precision_recall_fscore_support

from app.agents.intent_priority_agent import IntentPriorityAgent
from app.domain.loader import load_domain_pack
from app.schemas.ticket import NLPSignals

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def evaluate_intent_priority(pack_id: str, max_examples: int | None = None, num_samples: int = 1) -> dict:
    pack = load_domain_pack(pack_id)

    if not pack.config.intent_eval_available:
        return {
            "pack": pack_id,
            "metric": "intent_classification_f1",
            "available": False,
            "reason": pack.config.source_dataset.limitations,
        }

    test_path = os.path.join(REPO_ROOT, "eval", "datasets", f"{pack_id}_test.jsonl")
    with open(test_path) as f:
        examples = [json.loads(line) for line in f]
    if max_examples:
        examples = examples[:max_examples]

    agent = IntentPriorityAgent(num_samples=num_samples)
    empty_signals = NLPSignals(entities=[], sentiment="neutral", key_phrases=[])

    y_true, y_pred, errors = [], [], 0
    for ex in examples:
        try:
            result, _ = agent.classify(pack, title="", description=ex["text"], signals=empty_signals)
            y_true.append(ex["true_intent"])
            y_pred.append(result.intent)
        except RuntimeError as e:
            errors += 1
            print(f"  [warn] classification failed for one example: {e}", file=sys.stderr)

    if not y_true:
        return {"pack": pack_id, "metric": "intent_classification_f1", "available": False,
                "reason": "all classification calls failed -- is Ollama reachable?"}

    precision, recall, f1, _ = precision_recall_fscore_support(
        y_true, y_pred, average="macro", zero_division=0
    )
    accuracy = accuracy_score(y_true, y_pred)

    return {
        "pack": pack_id,
        "metric": "intent_classification_f1",
        "available": True,
        "num_examples": len(y_true),
        "num_errors": errors,
        "accuracy": round(accuracy, 4),
        "macro_precision": round(precision, 4),
        "macro_recall": round(recall, 4),
        "macro_f1": round(f1, 4),
        "per_class_report": classification_report(y_true, y_pred, zero_division=0, output_dict=True),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pack", default="it_saas")
    parser.add_argument("--max-examples", type=int, default=100)
    parser.add_argument("--num-samples", type=int, default=1, help="Self-consistency samples per ticket (cost vs. stability tradeoff)")
    args = parser.parse_args()

    result = evaluate_intent_priority(args.pack, max_examples=args.max_examples, num_samples=args.num_samples)
    print(json.dumps(result, indent=2))
