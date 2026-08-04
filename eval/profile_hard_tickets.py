#!/usr/bin/env python3
"""Profile the LangGraph supervisor on hard smoke tickets — no FastAPI / UI / BQ.

Usage (from repo root, against a live Ollama+creds stack):

    # Prefer inside the backend container (same env as production):
    docker cp eval/profile_hard_tickets.py ticket-backend:/tmp/profile_hard_tickets.py
    docker cp eval/datasets/live_smoke_suite.jsonl ticket-backend:/tmp/live_smoke_suite.jsonl
    docker exec -e ENABLE_BIGQUERY=false -w /srv ticket-backend \\
      python /tmp/profile_hard_tickets.py --suite /tmp/live_smoke_suite.jsonl

Writes JSONL timings to eval/live_runs/profile_hard_*.jsonl (or --out).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

# Allow `python eval/profile_hard_tickets.py` from repo root or /srv in container.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("ENABLE_BIGQUERY", "false")

from langgraph.graph import END, StateGraph  # noqa: E402

from app.agents.document_grader import DocumentGrader  # noqa: E402
from app.agents.supervisor import SupervisorAgent, TicketState  # noqa: E402
from app.config import settings  # noqa: E402

NODE_NAMES = (
    "analyze_ticket",
    "retrieve_documents",
    "grade_documents",
    "continuation_post_grading",
    "draft_response",
    "judge_response",
    "continuation_post_judging",
    "final_decision",
)


class _NullBQSink:
    def record_ticket_event(self, *_a, **_k) -> None:
        return None


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _print(msg: str) -> None:
    print(msg, flush=True)


class ProfilingSupervisor(SupervisorAgent):
    """Same graph, every node wrapped with START/END wall timestamps."""

    def __init__(self) -> None:
        self.node_events: list[dict[str, Any]] = []
        self._grade_mode_events: list[dict[str, Any]] = []
        super().__init__()
        self.bq_sink = _NullBQSink()
        self._patch_grader_for_mode_logs()

    def _patch_grader_for_mode_logs(self) -> None:
        grader = self.document_grader
        orig_batch = grader.grade_documents
        orig_seq = grader._grade_documents_sequential

        def grade_documents(ticket_text, documents):
            t0 = time.perf_counter()
            _print(f"  [grader] batch attempt n_docs={len(documents)}")
            try:
                out = orig_batch(ticket_text, documents)
                # If sequential was used, orig_batch already delegated — detect via call stack flag
                dt = time.perf_counter() - t0
                mode = getattr(grader, "_last_grade_mode", "batch")
                _print(f"  [grader] done mode={mode} dt={dt:.3f}s")
                self._grade_mode_events.append(
                    {"ts": _iso(), "mode": mode, "n_docs": len(documents), "dt_s": round(dt, 3)}
                )
                return out
            finally:
                grader._last_grade_mode = "batch"

        def sequential(ticket_text, documents):
            grader._last_grade_mode = "per_doc_fallback"
            _print(f"  [grader] PER-DOC FALLBACK n_docs={len(documents)}")
            return orig_seq(ticket_text, documents)

        grader._last_grade_mode = "batch"
        grader.grade_documents = grade_documents  # type: ignore[method-assign]
        grader._grade_documents_sequential = sequential  # type: ignore[method-assign]

    def _timed_node(self, name: str, fn: Callable[[TicketState], TicketState]):
        def wrapped(state: TicketState) -> TicketState:
            ticket_id = state.get("ticket_id", "?")
            start_time = state.get("start_time", time.monotonic())
            elapsed_before = time.monotonic() - start_time
            t0 = time.perf_counter()
            wall0 = _iso()
            _print(
                f"NODE_START name={name} ticket={ticket_id} wall={wall0} "
                f"elapsed_before={elapsed_before:.1f}s "
                f"iter={state.get('iteration_count', 0)} "
                f"retr={state.get('retrieval_iteration', 0)} "
                f"draft={state.get('drafting_iteration', 0)}"
            )
            err = None
            try:
                out = fn(state)
                return out
            except Exception as e:
                err = str(e)
                raise
            finally:
                dt = time.perf_counter() - t0
                elapsed_after = time.monotonic() - start_time
                # `state` is mutated in place by nodes; read after call
                event = {
                    "ts_start": wall0,
                    "ts_end": _iso(),
                    "node": name,
                    "ticket_id": ticket_id,
                    "dt_s": round(dt, 3),
                    "elapsed_after_s": round(elapsed_after, 3),
                    "intent": state.get("intent"),
                    "priority": state.get("priority"),
                    "n_candidates": len(state.get("kb_candidates") or []),
                    "n_relevant": len(state.get("relevant_documents") or []),
                    "post_grading_action": state.get("post_grading_action"),
                    "post_judging_action": state.get("post_judging_action"),
                    "anomaly_flags": list(state.get("anomaly_flags") or []),
                    "error": state.get("error") or err,
                    "intent_num_samples_setting": settings.intent_num_samples,
                }
                if name == "judge_response":
                    judge_result = state.get("judge_result") or {}
                    event["judge_faithfulness_score"] = judge_result.get("faithfulness_score")
                    event["judge_relevance_score"] = judge_result.get("relevance_score")
                    event["judge_confidence"] = judge_result.get("confidence")
                    event["judge_unsupported_claims"] = judge_result.get("unsupported_claims")
                    event["judge_rationale"] = judge_result.get("rationale")
                elif name == "continuation_post_judging":
                    event["post_judging_rationale"] = state.get("post_judging_rationale")
                self.node_events.append(event)
                _print(
                    f"NODE_END   name={name} ticket={ticket_id} dt={dt:.3f}s "
                    f"elapsed={elapsed_after:.1f}s intent={state.get('intent')} "
                    f"pri={state.get('priority')} "
                    f"cands={len(state.get('kb_candidates') or [])} "
                    f"rel={len(state.get('relevant_documents') or [])} "
                    f"post_grade={state.get('post_grading_action')} "
                    f"post_judge={state.get('post_judging_action')} "
                    f"anomalies={state.get('anomaly_flags') or []} "
                    f"err={state.get('error') or err}"
                )

        return wrapped

    def _build_graph(self):
        workflow = StateGraph(TicketState)

        workflow.add_node("analyze_ticket", self._timed_node("analyze_ticket", self._analyze_ticket_node))
        workflow.add_node("retrieve_documents", self._timed_node("retrieve_documents", self._retrieve_documents_node))
        workflow.add_node("grade_documents", self._timed_node("grade_documents", self._grade_documents_node))
        workflow.add_node(
            "continuation_post_grading",
            self._timed_node("continuation_post_grading", self._continuation_post_grading_node),
        )
        workflow.add_node("draft_response", self._timed_node("draft_response", self._draft_response_node))
        workflow.add_node("judge_response", self._timed_node("judge_response", self._judge_response_node))
        workflow.add_node(
            "continuation_post_judging",
            self._timed_node("continuation_post_judging", self._continuation_post_judging_node),
        )
        workflow.add_node("final_decision", self._timed_node("final_decision", self._final_decision_node))

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


def load_hard_tickets(suite_path: Path) -> list[dict[str, Any]]:
    rows = []
    with suite_path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("difficulty") == "hard":
                rows.append(row)
    if len(rows) != 8:
        _print(f"WARN: expected 8 hard tickets, got {len(rows)}")
    return rows


def summarize(all_events: list[dict[str, Any]], ticket_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    by_node: dict[str, list[float]] = defaultdict(list)
    for e in all_events:
        by_node[e["node"]].append(float(e["dt_s"]))

    node_totals = {
        name: {
            "calls": len(dts),
            "total_s": round(sum(dts), 3),
            "mean_s": round(sum(dts) / len(dts), 3) if dts else None,
            "max_s": round(max(dts), 3) if dts else None,
        }
        for name, dts in sorted(by_node.items(), key=lambda kv: -sum(kv[1]))
    }
    grand = sum(e["dt_s"] for e in all_events)
    return {
        "generated_at": _iso(),
        "settings": {
            "intent_num_samples": settings.intent_num_samples,
            "retrieval_top_k": settings.retrieval_top_k,
            "max_query_rewrites": settings.max_query_rewrites,
            "max_wall_clock_seconds": settings.max_wall_clock_seconds,
            "max_iterations": settings.max_iterations,
            "aws_region": settings.aws_region,
            "model_drafting": settings.model_drafting,
            "enable_bigquery": settings.enable_bigquery,
        },
        "node_totals": node_totals,
        "sum_node_dt_s": round(grand, 3),
        "tickets": ticket_summaries,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Per-node timing profile of hard smoke tickets")
    parser.add_argument(
        "--suite",
        type=Path,
        default=REPO_ROOT / "eval" / "datasets" / "live_smoke_suite.jsonl",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="JSONL of per-node events + final summary JSON beside it",
    )
    parser.add_argument("--limit", type=int, default=8, help="Max hard tickets to run")
    args = parser.parse_args()

    out_path = args.out
    if out_path is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        out_dir = REPO_ROOT / "eval" / "live_runs"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"profile_hard_{stamp}.jsonl"

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path = out_path.with_suffix(".summary.json")

    tickets = load_hard_tickets(args.suite)[: args.limit]

    _print("=" * 72)
    _print("HARD-TICKET GRAPH PROFILE (no FastAPI / no BQ / no frontend)")
    _print(
        f"settings: samples={settings.intent_num_samples} top_k={settings.retrieval_top_k} "
        f"rewrites={settings.max_query_rewrites} wall={settings.max_wall_clock_seconds}s "
        f"iters={settings.max_iterations} region={settings.aws_region} "
        f"draft_model={settings.model_drafting} bq={settings.enable_bigquery}"
    )
    _print(f"tickets={len(tickets)} out={out_path}")
    _print("=" * 72)

    supervisor = ProfilingSupervisor()
    all_events: list[dict[str, Any]] = []
    ticket_summaries: list[dict[str, Any]] = []

    for i, case in enumerate(tickets, 1):
        suite_id = case["id"]
        ticket_id = f"PROF-{suite_id}"
        supervisor.node_events = []
        supervisor._grade_mode_events = []

        _print("")
        _print("#" * 72)
        _print(f"TICKET_START [{i}/{len(tickets)}] {suite_id} pack={case['domain_pack']} id={ticket_id}")
        _print(f"  title={case['title']!r}")
        t_ticket0 = time.perf_counter()

        result_meta: dict[str, Any] = {}
        try:
            drafted = supervisor.process_ticket(
                ticket_id=ticket_id,
                title=case["title"],
                description=case["description"],
                domain_pack_id=case["domain_pack"],
            )
            trace = getattr(drafted, "trace", None) or {}
            result_meta = {
                "ok": True,
                "final_action": trace.get("final_action"),
                "intent": trace.get("intent"),
                "priority": trace.get("priority"),
                "anomaly_flags": trace.get("anomaly_flags") or [],
                "iteration_count": trace.get("iteration_count"),
                "cost_estimate": trace.get("cost_estimate"),
            }
        except Exception as e:
            result_meta = {"ok": False, "error": str(e), "traceback": traceback.format_exc()[-1500:]}
            _print(f"TICKET_ERROR {suite_id}: {e}")

        wall_s = time.perf_counter() - t_ticket0
        events = list(supervisor.node_events)
        grade_events = list(supervisor._grade_mode_events)

        by_node: dict[str, float] = defaultdict(float)
        by_node_calls: dict[str, int] = defaultdict(int)
        for e in events:
            by_node[e["node"]] += e["dt_s"]
            by_node_calls[e["node"]] += 1

        summary = {
            "suite_id": suite_id,
            "ticket_id": ticket_id,
            "domain_pack": case["domain_pack"],
            "wall_s": round(wall_s, 3),
            "node_total_s": round(sum(by_node.values()), 3),
            "node_calls": dict(by_node_calls),
            "node_seconds": {k: round(v, 3) for k, v in sorted(by_node.items(), key=lambda kv: -kv[1])},
            "grade_modes": grade_events,
            "safety_net_trips": [
                a for e in events for a in (e.get("anomaly_flags") or []) if "safety_net" in str(a)
            ],
            **result_meta,
        }
        ticket_summaries.append(summary)
        all_events.extend(events)

        with out_path.open("a") as f:
            f.write(json.dumps({"type": "ticket_summary", **summary}) + "\n")
            for e in events:
                f.write(json.dumps({"type": "node_event", "suite_id": suite_id, **e}) + "\n")

        _print(f"TICKET_END {suite_id} wall={wall_s:.1f}s action={result_meta.get('final_action')} "
               f"intent={result_meta.get('intent')}")
        _print(f"  node_seconds={summary['node_seconds']}")
        _print(f"  grade_modes={grade_events}")
        _print(f"  safety_net={summary['safety_net_trips']}")

    report = summarize(all_events, ticket_summaries)
    summary_path.write_text(json.dumps(report, indent=2) + "\n")
    with out_path.open("a") as f:
        f.write(json.dumps({"type": "run_summary", **report}) + "\n")

    _print("")
    _print("=" * 72)
    _print("RUN SUMMARY — time by node (all hard tickets)")
    for name, stats in report["node_totals"].items():
        _print(
            f"  {name:32} calls={stats['calls']:3}  total={stats['total_s']:8.1f}s  "
            f"mean={stats['mean_s']}  max={stats['max_s']}"
        )
    _print(f"sum_node_dt_s={report['sum_node_dt_s']}")
    _print(f"wrote {out_path}")
    _print(f"wrote {summary_path}")
    _print("=" * 72)


if __name__ == "__main__":
    main()
