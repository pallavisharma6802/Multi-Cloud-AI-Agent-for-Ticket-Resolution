"""Orchestrate the eval harness and gate CI on regressions.

    python eval/run_eval.py                     # run + compare to baseline
    python eval/run_eval.py --update-baseline    # overwrite baseline
    python eval/run_eval.py --skip-rag           # skip ragas (needs live services)

Metrics are either computed numbers or `"available": false` with a reason.
CI fails on regressions of available metrics and on metrics that become unavailable.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Heavy deps (sklearn/ragas/numpy) are imported lazily inside run_full_eval so
# pure helpers used by tests/test_eval.py stay importable without them.
from app.domain.loader import list_available_packs
from eval.agreement_eval import evaluate_healthcare_priority_correlation, evaluate_human_agreement
from eval.ner_eval import evaluate_ner

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASELINE_PATH = os.path.join(REPO_ROOT, "eval", "report_baseline.json")
REPORT_PATH = os.path.join(REPO_ROOT, "eval", "report.json")

REGRESSION_EPSILON = 0.03  # tolerate small run-to-run LLM sampling noise


def _flatten_available_numeric(report: dict) -> dict[str, float]:
    """Flatten available numeric fields into dotted keys for baseline compare."""
    flat = {}

    def walk(prefix: str, value):
        if isinstance(value, dict):
            if value.get("available") is False:
                return
            for k, v in value.items():
                if k in ("available", "reason", "per_class_report", "report", "context_metrics_note", "note", "interpretation", "expected_direction"):
                    continue
                walk(f"{prefix}.{k}" if prefix else k, v)
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            flat[prefix] = float(value)

    walk("", report)
    return flat


def run_full_eval(packs: list[str], skip_rag: bool, max_examples: int) -> dict:
    from eval.intent_priority_eval import evaluate_intent_priority
    from eval.rag_eval import evaluate_rag

    report = {"generated_at": datetime.now(timezone.utc).isoformat(), "packs": {}}

    for pack_id in packs:
        pack_report = {}
        print(f"=== {pack_id}: intent/priority classification ===")
        pack_report["intent_classification"] = evaluate_intent_priority(pack_id, max_examples=max_examples)
        print(json.dumps(pack_report["intent_classification"], indent=2)[:500])

        if not skip_rag:
            print(f"=== {pack_id}: RAG quality (ragas) ===")
            try:
                pack_report["rag_quality"] = evaluate_rag(pack_id, max_examples=min(max_examples, 30))
            except Exception as e:
                pack_report["rag_quality"] = {"metric": "rag_quality", "available": False, "reason": str(e)}
            print(json.dumps(pack_report["rag_quality"], indent=2)[:500])

        report["packs"][pack_id] = pack_report

    print("=== NER (entity-level, seqeval) ===")
    report["ner"] = evaluate_ner(gold_file=None)

    print("=== Human agreement (Cohen's kappa) ===")
    report["human_agreement"] = evaluate_human_agreement(
        os.path.join(REPO_ROOT, "eval", "human_review", "review_template.csv")
    )

    if "healthcare" in packs:
        print("=== Healthcare priority vs. real star_rating correlation ===")
        report["healthcare_priority_correlation"] = evaluate_healthcare_priority_correlation(
            max_examples=max_examples
        )

    return report


def compare_to_baseline(current: dict, baseline: dict) -> list[str]:
    current_flat = _flatten_available_numeric(current)
    baseline_thresholds = baseline.get("thresholds", {})

    failures = []
    for key, threshold in baseline_thresholds.items():
        if key not in current_flat:
            failures.append(f"REGRESSION: '{key}' was available in the baseline (>= {threshold}) but is "
                             f"missing/unavailable in this run -- something that used to work broke.")
            continue
        if current_flat[key] < threshold - REGRESSION_EPSILON:
            failures.append(f"REGRESSION: '{key}' = {current_flat[key]:.4f}, below baseline threshold "
                             f"{threshold:.4f} (tolerance {REGRESSION_EPSILON})")
    return failures


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pack", default="all")
    parser.add_argument("--max-examples", type=int, default=100)
    parser.add_argument("--skip-rag", action="store_true", help="Skip ragas metrics (needs live Ollama + seeded Pinecone)")
    parser.add_argument("--update-baseline", action="store_true")
    args = parser.parse_args()

    packs = list_available_packs() if args.pack == "all" else [args.pack]
    report = run_full_eval(packs, skip_rag=args.skip_rag, max_examples=args.max_examples)

    with open(REPORT_PATH, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nFull report written to {REPORT_PATH}")

    if args.update_baseline:
        flat = _flatten_available_numeric(report)
        baseline = {
            "generated_at": report["generated_at"],
            "thresholds": flat,
            "notes": "Baseline regenerated from a real evaluation run via `run_eval.py --update-baseline`. "
            "CI fails a PR if any of these numbers regress by more than the epsilon in run_eval.py.",
        }
        with open(BASELINE_PATH, "w") as f:
            json.dump(baseline, f, indent=2)
        print(f"Baseline updated: {BASELINE_PATH}")
        return 0

    if not os.path.isfile(BASELINE_PATH):
        print(f"No baseline found at {BASELINE_PATH}; run with --update-baseline first. Not failing this run.")
        return 0

    with open(BASELINE_PATH) as f:
        baseline = json.load(f)

    failures = compare_to_baseline(report, baseline)
    if failures:
        print("\n".join(["", "=" * 70, "EVAL GATE FAILED:"] + failures))
        return 1

    print("\nEval gate passed: no regressions vs. baseline.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
