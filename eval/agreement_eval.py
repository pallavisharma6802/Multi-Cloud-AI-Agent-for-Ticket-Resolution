"""Agreement checks for supervisor decisions and healthcare priority calibration.

1. Human agreement: Cohen's kappa vs filled-in eval/human_review/*.csv.
2. Healthcare: Spearman correlation of LLM priority vs real patient star_rating.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRIORITY_ORDINAL = {"low": 1, "medium": 2, "high": 3, "urgent": 4}


def _cohen_kappa(a: list[bool], b: list[bool]) -> float:
    """Cohen's kappa for two boolean sequences (no sklearn/numpy dependency)."""
    n = len(a)
    po = sum(1 for x, y in zip(a, b) if x == y) / n
    p_a_true, p_b_true = sum(a) / n, sum(b) / n
    pe = p_a_true * p_b_true + (1 - p_a_true) * (1 - p_b_true)
    if pe == 1.0:
        return 1.0
    return (po - pe) / (1 - pe)


def _spearman_correlation(x: list[float], y: list[float]) -> tuple[float, float]:
    """Spearman rank correlation with average ranks for ties. p-value is None (no scipy)."""
    def rank(values: list[float]) -> list[float]:
        sorted_idx = sorted(range(len(values)), key=lambda i: values[i])
        ranks = [0.0] * len(values)
        i = 0
        while i < len(sorted_idx):
            j = i
            while j + 1 < len(sorted_idx) and values[sorted_idx[j + 1]] == values[sorted_idx[i]]:
                j += 1
            avg_rank = (i + j) / 2 + 1
            for k in range(i, j + 1):
                ranks[sorted_idx[k]] = avg_rank
            i = j + 1
        return ranks

    rx, ry = rank(x), rank(y)
    n = len(x)
    mean_rx, mean_ry = sum(rx) / n, sum(ry) / n
    cov = sum((rx[i] - mean_rx) * (ry[i] - mean_ry) for i in range(n))
    var_x = sum((r - mean_rx) ** 2 for r in rx)
    var_y = sum((r - mean_ry) ** 2 for r in ry)
    denom = (var_x * var_y) ** 0.5
    rho = cov / denom if denom else 0.0
    return rho, None


def evaluate_human_agreement(review_file: str) -> dict:
    if not os.path.isfile(review_file):
        return {
            "metric": "supervisor_human_agreement_kappa",
            "available": False,
            "reason": f"{review_file} not found. See eval/human_review/README.md -- this requires "
            "an actual human review pass, there is no static dataset for this.",
        }

    with open(review_file) as f:
        rows = list(csv.DictReader(f))

    rows = [r for r in rows if r.get("human_would_escalate", "").strip() != ""]
    if len(rows) < 5:
        return {
            "metric": "supervisor_human_agreement_kappa",
            "available": False,
            "reason": f"only {len(rows)} filled-in rows found in {review_file}; need a meaningfully "
            "sized human-reviewed sample (recommend 30+) before this number means anything.",
        }

    model_escalated = [r["model_final_action"].strip().lower() == "escalate" for r in rows]
    human_escalated = [r["human_would_escalate"].strip().lower() in ("true", "1", "yes") for r in rows]

    kappa = _cohen_kappa(model_escalated, human_escalated)
    agreement_rate = sum(m == h for m, h in zip(model_escalated, human_escalated)) / len(rows)

    return {
        "metric": "supervisor_human_agreement_kappa",
        "available": True,
        "num_reviewed": len(rows),
        "raw_agreement_rate": round(agreement_rate, 4),
        "cohens_kappa": round(kappa, 4),
        "interpretation": _interpret_kappa(kappa),
    }


def _interpret_kappa(kappa: float) -> str:
    if kappa < 0:
        return "worse than chance -- investigate immediately"
    if kappa < 0.2:
        return "slight agreement"
    if kappa < 0.4:
        return "fair agreement"
    if kappa < 0.6:
        return "moderate agreement"
    if kappa < 0.8:
        return "substantial agreement"
    return "near-perfect agreement"


def evaluate_healthcare_priority_correlation(max_examples: int = 60) -> dict:
    # Lazy import keeps this module light for unit tests.
    from app.agents.intent_priority_agent import IntentPriorityAgent
    from app.domain.loader import load_domain_pack
    from app.schemas.ticket import NLPSignals

    pack = load_domain_pack("healthcare")
    test_path = os.path.join(REPO_ROOT, "eval", "datasets", "healthcare_test.jsonl")
    with open(test_path) as f:
        examples = [json.loads(line) for line in f][:max_examples]

    agent = IntentPriorityAgent(num_samples=1)
    empty_signals = NLPSignals(entities=[], sentiment="neutral", key_phrases=[])

    priorities, ratings = [], []
    for ex in examples:
        if ex.get("real_star_rating") is None:
            continue
        try:
            result, _ = agent.classify(pack, title="", description=ex["text"], signals=empty_signals)
        except RuntimeError:
            continue
        priorities.append(PRIORITY_ORDINAL.get(result.priority, 2))
        ratings.append(ex["real_star_rating"])

    if len(priorities) < 5:
        return {
            "metric": "healthcare_priority_vs_star_rating_correlation",
            "available": False,
            "reason": "too few successful classifications to compute a correlation -- is Ollama reachable?",
        }

    # Expect negative correlation: higher priority ↔ lower star rating.
    corr, _ = _spearman_correlation(priorities, ratings)

    return {
        "metric": "healthcare_priority_vs_star_rating_correlation",
        "available": True,
        "num_examples": len(priorities),
        "spearman_correlation": round(float(corr), 4),
        "expected_direction": "negative (higher assigned priority for lower real star rating)",
        "note": "Uses star_rating as a severity signal where intent/priority labels are absent "
        "(see domains/healthcare/config.yaml limitations).",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--review-file", default=os.path.join(REPO_ROOT, "eval", "human_review", "review_template.csv"))
    parser.add_argument("--skip-healthcare-correlation", action="store_true")
    args = parser.parse_args()

    output = {"human_agreement": evaluate_human_agreement(args.review_file)}
    if not args.skip_healthcare_correlation:
        output["healthcare_priority_correlation"] = evaluate_healthcare_priority_correlation()

    print(json.dumps(output, indent=2))
