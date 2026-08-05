"""Submit curated live-smoke tickets to the running API (same path as the UI).

    python eval/live_smoke_runner.py --once
    python eval/live_smoke_runner.py --interval 3600
    python eval/live_smoke_runner.py --from-id smoke-it-05 --once

Requires a healthy stack (`docker compose up -d`) and seeded KB.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
SUITE_PATH = REPO_ROOT / "eval" / "datasets" / "live_smoke_suite.jsonl"
LIVE_RUNS_DIR = REPO_ROOT / "eval" / "live_runs"
STATE_PATH = LIVE_RUNS_DIR / "state.json"

DEFAULT_API_BASE = os.environ.get("API_BASE_URL", "http://localhost:8000")
# Tickets often take 2–5+ minutes on small local models; allow headroom past the 300s safety net.
DEFAULT_TIMEOUT_S = int(os.environ.get("LIVE_SMOKE_TIMEOUT_S", "600"))


def _load_suite(path: Path) -> list[dict[str, Any]]:
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
    if not rows:
        raise SystemExit(f"Suite is empty: {path}")
    return rows


def _load_state() -> dict[str, Any]:
    if not STATE_PATH.is_file():
        return {"next_index": 0, "completed_ids": []}
    with STATE_PATH.open() as f:
        return json.load(f)


def _save_state(state: dict[str, Any]) -> None:
    LIVE_RUNS_DIR.mkdir(parents=True, exist_ok=True)
    with STATE_PATH.open("w") as f:
        json.dump(state, f, indent=2)
        f.write("\n")


def _run_path_for_today() -> Path:
    LIVE_RUNS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    return LIVE_RUNS_DIR / f"run_{stamp}.jsonl"


def check_health(api_base: str, timeout_s: float = 10.0) -> None:
    url = f"{api_base.rstrip('/')}/health"
    try:
        resp = requests.get(url, timeout=timeout_s)
    except requests.RequestException as exc:
        raise SystemExit(
            f"Backend health check failed ({url}): {exc}\n"
            "Start the stack with `docker compose up -d` and ensure Bedrock is reachable."
        ) from exc
    if resp.status_code != 200:
        raise SystemExit(
            f"Backend health check returned HTTP {resp.status_code} from {url}: {resp.text[:200]}"
        )
    try:
        body = resp.json()
    except ValueError:
        body = {}
    if isinstance(body, dict) and body.get("status") not in (None, "healthy", "ok"):
        raise SystemExit(f"Backend reports unhealthy status at {url}: {body}")
    print(f"Health OK: {url}")


def resolve_index(suite: list[dict[str, Any]], state: dict[str, Any], from_id: Optional[str]) -> int:
    if from_id:
        for i, row in enumerate(suite):
            if row.get("id") == from_id:
                return i
        raise SystemExit(f"--from-id {from_id!r} not found in suite ({SUITE_PATH})")
    idx = int(state.get("next_index", 0))
    if idx < 0:
        return 0
    return idx


def submit_ticket(api_base: str, case: dict[str, Any], timeout_s: int) -> dict[str, Any]:
    url = f"{api_base.rstrip('/')}/api/v1/tickets"
    payload = {
        "title": case["title"],
        "description": case["description"],
        "user_email": case.get("user_email") or "smoke@example.com",
        "domain_pack": case["domain_pack"],
    }
    started = time.perf_counter()
    try:
        resp = requests.post(url, json=payload, timeout=timeout_s)
        latency_s = time.perf_counter() - started
    except requests.Timeout:
        latency_s = time.perf_counter() - started
        return {
            "ok": False,
            "http_status": None,
            "error": f"request timed out after {timeout_s}s",
            "latency_s": round(latency_s, 3),
            "response": None,
        }
    except requests.RequestException as exc:
        latency_s = time.perf_counter() - started
        return {
            "ok": False,
            "http_status": None,
            "error": str(exc),
            "latency_s": round(latency_s, 3),
            "response": None,
        }

    try:
        body = resp.json()
    except ValueError:
        body = {"raw_text": resp.text[:2000]}

    return {
        "ok": resp.status_code in (200, 201),
        "http_status": resp.status_code,
        "error": None if resp.status_code in (200, 201) else str(body)[:1000],
        "latency_s": round(latency_s, 3),
        "response": body if isinstance(body, dict) else {"raw": body},
    }


def _extract_predictions(response: Optional[dict[str, Any]]) -> dict[str, Any]:
    if not response:
        return {
            "predicted_intent": None,
            "predicted_priority": None,
            "predicted_final_action": None,
            "draft_snippet": None,
            "anomaly_flags": [],
            "confidence_score": None,
            "ticket_id": None,
            "processing_time_seconds": None,
        }
    trace = response.get("trace") or {}
    draft = response.get("drafted_response") or ""
    return {
        "predicted_intent": trace.get("intent"),
        "predicted_priority": trace.get("priority"),
        "predicted_final_action": trace.get("final_action"),
        "draft_snippet": (draft[:280] + ("…" if len(draft) > 280 else "")) if draft else None,
        "anomaly_flags": list(trace.get("anomaly_flags") or []),
        "confidence_score": response.get("confidence_score"),
        "ticket_id": response.get("ticket_id"),
        "processing_time_seconds": response.get("processing_time_seconds"),
    }


def append_result(result: dict[str, Any]) -> Path:
    path = _run_path_for_today()
    with path.open("a") as f:
        f.write(json.dumps(result) + "\n")
    return path


def run_one(
    suite: list[dict[str, Any]],
    state: dict[str, Any],
    api_base: str,
    timeout_s: int,
    from_id: Optional[str] = None,
) -> bool:
    """Submit the next suite ticket. Returns False when the suite is finished."""
    idx = resolve_index(suite, state, from_id)
    if idx >= len(suite):
        print(f"Suite complete ({len(suite)} tickets). Reset state or pass --from-id to re-run.")
        return False

    case = suite[idx]
    print(
        f"[{idx + 1}/{len(suite)}] Submitting {case['id']} "
        f"({case['difficulty']}, {case['domain_pack']}) …"
    )
    submit = submit_ticket(api_base, case, timeout_s)
    preds = _extract_predictions(submit.get("response"))

    result = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "suite_id": case["id"],
        "suite_index": idx,
        "domain_pack": case["domain_pack"],
        "difficulty": case["difficulty"],
        "title": case.get("title"),
        "description": case.get("description"),
        "expected_intent": case.get("expected_intent"),
        "expected_priority_in": case.get("expected_priority_in"),
        "expected_final_action": case.get("expected_final_action"),
        "http_status": submit["http_status"],
        "error": submit["error"],
        "ok": submit["ok"],
        "latency_s": submit["latency_s"],
        **preds,
    }
    out_path = append_result(result)
    print(
        f"  ok={result['ok']} http={result['http_status']} latency={result['latency_s']}s "
        f"intent={result['predicted_intent']} priority={result['predicted_priority']} "
        f"action={result['predicted_final_action']} ticket_id={result['ticket_id']}"
    )
    if result["anomaly_flags"]:
        print(f"  anomaly_flags={result['anomaly_flags']}")
    if result["error"]:
        print(f"  error={result['error']}")
    print(f"  appended → {out_path}")

    completed = list(state.get("completed_ids") or [])
    if case["id"] not in completed:
        completed.append(case["id"])
    state["completed_ids"] = completed
    state["next_index"] = idx + 1
    state["last_suite_id"] = case["id"]
    state["last_ticket_id"] = result.get("ticket_id")
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    _save_state(state)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Live smoke: submit one suite ticket via the API")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true", help="Submit only the next ticket then exit")
    mode.add_argument(
        "--interval",
        type=int,
        metavar="SECONDS",
        help="Loop: submit one ticket, sleep SECONDS, repeat until suite done (e.g. 3600)",
    )
    parser.add_argument("--from-id", type=str, default=None, help="Jump/resume at this suite id")
    parser.add_argument(
        "--api-base",
        default=DEFAULT_API_BASE,
        help=f"API base URL (default: {DEFAULT_API_BASE} or API_BASE_URL)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_S,
        help=f"HTTP timeout seconds per ticket (default: {DEFAULT_TIMEOUT_S})",
    )
    parser.add_argument(
        "--suite",
        type=Path,
        default=SUITE_PATH,
        help=f"Suite JSONL path (default: {SUITE_PATH})",
    )
    args = parser.parse_args()

    if not args.once and args.interval is None:
        args.once = True

    suite = _load_suite(args.suite)
    state = _load_state()
    check_health(args.api_base)

    if args.once:
        run_one(suite, state, args.api_base, args.timeout, from_id=args.from_id)
        return

    interval = max(0, int(args.interval))
    first = True
    while True:
        from_id = args.from_id if first else None
        first = False
        progressed = run_one(suite, state, args.api_base, args.timeout, from_id=from_id)
        if not progressed:
            break
        if state.get("next_index", 0) >= len(suite):
            print("Suite finished.")
            break
        print(f"Sleeping {interval}s before next ticket …")
        time.sleep(interval)


if __name__ == "__main__":
    main()
