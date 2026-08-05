"""Score a live-smoke run JSONL against suite labels.

    python eval/score_live_run.py --run eval/live_runs/run_YYYYMMDD.jsonl

Writes:
  - eval/live_runs/score_YYYYMMDD.json
  - eval/human_review/live_smoke_review.csv  (mismatch rows for agreement_eval)
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
LIVE_RUNS_DIR = REPO_ROOT / "eval" / "live_runs"
REVIEW_CSV = REPO_ROOT / "eval" / "human_review" / "live_smoke_review.csv"


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open() as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise SystemExit(f"Invalid JSONL at {path}:{line_no}: {exc}") from exc
    return rows


def _percentile(sorted_vals: list[float], p: float) -> Optional[float]:
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return round(sorted_vals[0], 3)
    k = (len(sorted_vals) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return round(sorted_vals[int(k)], 3)
    d0 = sorted_vals[f] * (c - k)
    d1 = sorted_vals[c] * (k - f)
    return round(d0 + d1, 3)


def _final_action_ok(expected: Optional[str], predicted: Optional[str]) -> Optional[bool]:
    if not expected or expected == "either":
        return None  # not scored
    if not predicted:
        return False
    return predicted.strip().lower() == expected.strip().lower()


def _intent_ok(expected: Optional[str], predicted: Optional[str]) -> Optional[bool]:
    if not expected:
        return None
    if not predicted:
        return False
    return predicted.strip().lower() == expected.strip().lower()


def _priority_ok(expected_in: Optional[list], predicted: Optional[str]) -> Optional[bool]:
    if not expected_in:
        return None
    if not predicted:
        return False
    allowed = {str(x).strip().lower() for x in expected_in}
    return predicted.strip().lower() in allowed


def _is_mismatch(row: dict[str, Any], intent_ok: Optional[bool], priority_ok: Optional[bool], action_ok: Optional[bool]) -> bool:
    if not row.get("ok"):
        return True
    for flag in (intent_ok, priority_ok, action_ok):
        if flag is False:
            return True
    return False


def score_rows(rows: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    intent_hits = intent_n = 0
    priority_hits = priority_n = 0
    action_hits = action_n = 0
    safety_trips = 0
    latencies: list[float] = []
    http_ok = 0
    mismatches: list[dict[str, Any]] = []
    per_case: list[dict[str, Any]] = []

    for row in rows:
        if row.get("latency_s") is not None:
            try:
                latencies.append(float(row["latency_s"]))
            except (TypeError, ValueError):
                pass
        if row.get("ok"):
            http_ok += 1

        flags = row.get("anomaly_flags") or []
        if any("safety_net" in str(f) for f in flags):
            safety_trips += 1

        intent_ok = _intent_ok(row.get("expected_intent"), row.get("predicted_intent"))
        priority_ok = _priority_ok(row.get("expected_priority_in"), row.get("predicted_priority"))
        action_ok = _final_action_ok(row.get("expected_final_action"), row.get("predicted_final_action"))

        if intent_ok is not None:
            intent_n += 1
            if intent_ok:
                intent_hits += 1
        if priority_ok is not None:
            priority_n += 1
            if priority_ok:
                priority_hits += 1
        if action_ok is not None:
            action_n += 1
            if action_ok:
                action_hits += 1

        case = {
            "suite_id": row.get("suite_id"),
            "ticket_id": row.get("ticket_id"),
            "ok": row.get("ok"),
            "intent_ok": intent_ok,
            "priority_ok": priority_ok,
            "final_action_ok": action_ok,
            "predicted_intent": row.get("predicted_intent"),
            "predicted_priority": row.get("predicted_priority"),
            "predicted_final_action": row.get("predicted_final_action"),
            "anomaly_flags": flags,
            "latency_s": row.get("latency_s"),
        }
        per_case.append(case)

        if _is_mismatch(row, intent_ok, priority_ok, action_ok):
            mismatches.append(row)

    latencies_sorted = sorted(latencies)
    n = len(rows)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_rows": n,
        "http_success_rate": round(http_ok / n, 4) if n else None,
        "intent_accuracy": round(intent_hits / intent_n, 4) if intent_n else None,
        "intent_n": intent_n,
        "priority_hit_rate": round(priority_hits / priority_n, 4) if priority_n else None,
        "priority_n": priority_n,
        "escalation_agreement": round(action_hits / action_n, 4) if action_n else None,
        "escalation_n": action_n,
        "latency_p50_s": _percentile(latencies_sorted, 50),
        "latency_p95_s": _percentile(latencies_sorted, 95),
        "safety_net_trip_rate": round(safety_trips / n, 4) if n else None,
        "safety_net_trips": safety_trips,
        "mismatch_count": len(mismatches),
        "per_case": per_case,
    }
    return report, mismatches


def write_review_csv(mismatches: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "ticket_id",
        "ticket_text",
        "model_final_action",
        "model_confidence",
        "human_would_escalate",
        "suite_id",
        "expected_intent",
        "predicted_intent",
        "expected_priority_in",
        "predicted_priority",
        "expected_final_action",
        "mismatch_notes",
    ]
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in mismatches:
            notes = []
            if not row.get("ok"):
                notes.append(f"http_error:{row.get('error')}")
            if row.get("expected_intent") and row.get("predicted_intent") != row.get("expected_intent"):
                notes.append("intent_mismatch")
            expected_pri = row.get("expected_priority_in") or []
            pred_pri = (row.get("predicted_priority") or "").lower()
            if expected_pri and pred_pri not in {str(x).lower() for x in expected_pri}:
                notes.append("priority_mismatch")
            expected_action = row.get("expected_final_action")
            if expected_action and expected_action != "either":
                if row.get("predicted_final_action") != expected_action:
                    notes.append("final_action_mismatch")
            if row.get("anomaly_flags"):
                notes.append("anomaly:" + ";".join(str(a) for a in row["anomaly_flags"]))

            ticket_text = " ".join(
                p for p in (row.get("title"), row.get("description")) if p
            ).strip() or (row.get("draft_snippet") or "")
            writer.writerow(
                {
                    "ticket_id": row.get("ticket_id") or "",
                    "ticket_text": ticket_text[:800],
                    "model_final_action": row.get("predicted_final_action") or "",
                    "model_confidence": row.get("confidence_score") if row.get("confidence_score") is not None else "",
                    "human_would_escalate": "",  # left blank for reviewer
                    "suite_id": row.get("suite_id") or "",
                    "expected_intent": row.get("expected_intent") or "",
                    "predicted_intent": row.get("predicted_intent") or "",
                    "expected_priority_in": json.dumps(row.get("expected_priority_in") or []),
                    "predicted_priority": row.get("predicted_priority") or "",
                    "expected_final_action": row.get("expected_final_action") or "",
                    "mismatch_notes": ",".join(notes),
                }
            )


def _default_score_path(run_path: Path) -> Path:
    name = run_path.stem  # run_YYYYMMDD
    stamp = name.replace("run_", "", 1) if name.startswith("run_") else datetime.now(timezone.utc).strftime("%Y%m%d")
    return LIVE_RUNS_DIR / f"score_{stamp}.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Score a live-smoke run JSONL")
    parser.add_argument(
        "--run",
        type=Path,
        required=True,
        help="Path to eval/live_runs/run_YYYYMMDD.jsonl",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Score JSON output path (default: eval/live_runs/score_YYYYMMDD.json)",
    )
    parser.add_argument(
        "--review-csv",
        type=Path,
        default=REVIEW_CSV,
        help=f"Mismatch CSV for human review (default: {REVIEW_CSV})",
    )
    args = parser.parse_args()

    run_path = args.run if args.run.is_absolute() else REPO_ROOT / args.run
    if not run_path.is_file():
        raise SystemExit(f"Run file not found: {run_path}")

    rows = _load_jsonl(run_path)
    if not rows:
        raise SystemExit(f"No rows in {run_path}")

    report, mismatches = score_rows(rows)
    report["run_file"] = str(run_path.relative_to(REPO_ROOT)) if run_path.is_relative_to(REPO_ROOT) else str(run_path)

    out_path = args.out or _default_score_path(run_path)
    if not out_path.is_absolute():
        out_path = REPO_ROOT / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as f:
        json.dump(report, f, indent=2)
        f.write("\n")

    write_review_csv(mismatches, args.review_csv if args.review_csv.is_absolute() else REPO_ROOT / args.review_csv)

    print(f"Scored {report['n_rows']} rows from {run_path}")
    print(f"  intent_accuracy={report['intent_accuracy']} (n={report['intent_n']})")
    print(f"  priority_hit_rate={report['priority_hit_rate']} (n={report['priority_n']})")
    print(f"  escalation_agreement={report['escalation_agreement']} (n={report['escalation_n']})")
    print(f"  latency p50={report['latency_p50_s']}s p95={report['latency_p95_s']}s")
    print(f"  safety_net_trip_rate={report['safety_net_trip_rate']} ({report['safety_net_trips']} trips)")
    print(f"  mismatches={report['mismatch_count']}")
    print(f"  wrote {out_path}")
    print(f"  wrote {args.review_csv} (fill human_would_escalate, then agreement_eval.py)")


if __name__ == "__main__":
    main()
