"""Agreement checks for supervisor decisions.

Human agreement: Cohen's kappa vs filled-in eval/human_review/*.csv.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _cohen_kappa(a: list[bool], b: list[bool]) -> float:
    """Cohen's kappa for two boolean sequences (no sklearn/numpy dependency)."""
    n = len(a)
    po = sum(1 for x, y in zip(a, b) if x == y) / n
    p_a_true, p_b_true = sum(a) / n, sum(b) / n
    pe = p_a_true * p_b_true + (1 - p_a_true) * (1 - p_b_true)
    if pe == 1.0:
        return 1.0
    return (po - pe) / (1 - pe)


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


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--review-file", default=os.path.join(REPO_ROOT, "eval", "human_review", "review_template.csv"))
    args = parser.parse_args()

    output = {"human_agreement": evaluate_human_agreement(args.review_file)}

    print(json.dumps(output, indent=2))
