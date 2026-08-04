# Progress & status — Bedrock migration and live-run prep

Last updated: 2026-08-03

This note captures what was built, what was verified, and what still blocks a first live Bedrock run. It is a working log, not a substitute for `README.md`.

---

## Current architecture (runtime)

| Layer | Status |
|-------|--------|
| **LLM** | **Amazon Bedrock only** (Converse API, default `amazon.nova-lite-v1:0`) |
| **NLP** | Azure Text Analytics (unchanged) |
| **Vectors** | Pinecone (unchanged) |
| **OLTP** | PostgreSQL (API persistence only) |
| **Analytics** | BigQuery opt-in (`ENABLE_BIGQUERY=false` by default) |
| **UI** | Next.js (optional for eval/profiling) |

Shared client: `app/llm/bedrock_client.py` → `get_llm_client()` / `LLMCallMetadata`.  
Per-role model IDs: flat lookup in `app/llm/model_router.py` (no Ollama probing / auto-routing).

---

## Completed work (in order)

### Pipeline / latency (earlier sessions)

- Latency knobs: `INTENT_NUM_SAMPLES=1`, `RETRIEVAL_TOP_K=3`, `MAX_QUERY_REWRITES=1`, wall clock 900s.
- Healthcare retrieval skips intent `$eq` when metadata is null; IT retries unfiltered if filter zeros hits.
- Softened escalate bias / safety net can proceed to draft when relevant docs exist.
- Live smoke serialized one ticket at a time (`eval/live_smoke_runner.py`).
- Hard-ticket bare-graph profiler: `eval/profile_hard_tickets.py` → JSONL + `*.summary.json` under `eval/live_runs/` (e.g. `profile_hard_combined.summary.json`).

### Step 1.5 — Judge exhaustion → force escalate

When `JudgeAgent.judge()` raises but a draft exists, the graph must not let `final_decision` LLM-choose `auto_resolve`.

| Check | Location |
|-------|----------|
| `judge_failed = False` on success | `app/agents/supervisor.py` ~412 |
| `judge_failed = True` on exception | `app/agents/supervisor.py` ~416–419 |
| Escalate short-circuit before supervisor LLM | `app/agents/supervisor.py` ~516–531 |
| Regression test | `tests/test_supervisor_graph.py::test_judge_exhaustion_with_draft_forces_escalate` |

**Verified intact after Ollama consolidation** (pre-flight 2026-08-03); test still passes; full suite **37 passed**.

### Bedrock migration — Step 2

- `BedrockStructuredClient`: `generate_structured` + `generate_text`, Converse API, schema-hint retry, throttle backoff, AccessDenied / ValidationException fail-fast.
- Dual-backend factory (`llm_backend` bedrock vs ollama) — later removed in consolidation.
- Unit tests: `tests/test_bedrock_client.py`.

### Bedrock migration — Step 2.5

- Bedrock client tests: happy path, JSON retry, exhaust, throttle, AccessDenied, ValidationException, schema ge/le retry.

### Bedrock migration — Step 3

- `drafting_agent.py` wired to shared `client.generate_text(...)` (same prompt / temp `0.6` / `num_predict` `500` / timeout).
- Removed raw `requests.post` to Ollama from drafting.
- Tests: `tests/test_drafting_agent.py` (call args + throttle retry via shared client).

### Consolidation — Ollama removed (Bedrock-only)

| Action | Detail |
|--------|--------|
| Deleted | `app/llm/ollama_client.py`, `app/llm/client_factory.py` |
| Singleton home | `get_llm_client()` / `reset_llm_client()` in `bedrock_client.py` |
| Model router | Flat `settings.model_*` lookup only; deleted OOM probe / auto/unified/manual / `alternate_model_for_role` |
| Config | Dropped `llm_backend`, `OLLAMA_*`, routing/quality tier; plain `model_*` = Nova defaults; kept `aws_region` + `request_timeout_seconds` (boto timeouts) |
| Tests | Autouse MagicMock Bedrock client in `tests/conftest.py`; router tests rewritten |
| Docs / ops | `.env.example`, README, `docker-compose.yml` (no Ollama service), CI (no Ollama install; eval-gate skips without AWS secrets), `infra/README.md` (EC2 Ollama = legacy) |
| Agents | Import path only → `from app.llm.bedrock_client import ...` (prompts/graph unchanged) |

**Pytest after consolidation:** `37 passed`.

### Cloud cost cleanup (earlier)

- AWS: stopped EC2 Ollama host / released EIP (8GB EBS may still exist if not terminated).
- GCP: no VMs / compute off where checked.
- Azure: may still need `az login` for Cognitive Services cleanup if desired.
- Azure Text Analytics + Pinecone still bill if provisioned.

---

## Pre-flight check (2026-08-03) — before first live Bedrock call

No live Bedrock call was made.

### Credentials

- Code uses **boto3 default credential chain** (`boto3.client("bedrock-runtime", region_name=...)`).
- `settings.aws_access_key_id` / `aws_secret_access_key` are **not** passed into boto3.
- This laptop: `~/.aws/credentials` profile `default` resolves; process env AWS keys unset.
- `.env` may contain AWS keys loaded into Settings only — those do not drive boto3 unless exported into the process env.

### Resolved config at pre-flight (live Settings, not test mocks)

| Setting | Value then |
|---------|------------|
| `aws_region` | `us-east-1` ✓ |
| All six `model_*` | **`qwen2.5:1.5b`** ← from local `.env` (legacy Ollama pins) |

**Hard blocker for live Bedrock:** update `.env` `MODEL_*` to `amazon.nova-lite-v1:0` (or remove them so code defaults apply). Leaving `qwen2.5:*` will produce invalid Bedrock `modelId`s.

Also harmless leftover in `.env`: `OLLAMA_BASE_URL` (ignored by Settings `extra=ignore`).

### Nova access

- Model access for Nova Lite in Bedrock console (`us-east-1`) still required — not verified without a live call.

---

## How to run without Docker (laptop resource-constrained)

### Per-node timing (preferred for Bedrock latency comparison)

Harness: `eval/profile_hard_tickets.py`  
**In-process LangGraph** — no FastAPI, no Postgres, no frontend/Grafana.

```bash
cd /path/to/Multi-Cloud-AI-Agent-for-Ticket-Resolution
export ENABLE_BIGQUERY=false
# Ensure .env MODEL_* are amazon.nova-lite-v1:0 (or unset)
python3 eval/profile_hard_tickets.py \
  --suite eval/datasets/live_smoke_suite.jsonl \
  --limit 8 \
  --out eval/live_runs/profile_hard_bedrock.jsonl
# writes also: profile_hard_bedrock.summary.json
```

Still needs: **AWS/Bedrock**, **Azure Text Analytics**, **seeded Pinecone**, local embeddings (sentence-transformers RAM).  
`DATABASE_URL` must be set for Settings to load but is unused by this script.

### API live smoke (optional)

`eval/live_smoke_runner.py` POSTs to FastAPI → needs uvicorn + real Postgres (local brew **or** Neon/Supabase free tier). Does **not** emit per-node timing JSON.

### Compose services (current)

| Service | For profiling? |
|---------|----------------|
| postgres | No |
| backend | No (profiler in-process) |
| frontend | No |
| grafana | No |

---

## Test suite

```bash
pytest tests/ -v
```

- Fully mocked Bedrock (MagicMock + boto3 stub in conftest).
- Last known count: **37 passed**.

---

## Explicitly not done yet

- [ ] Fix local `.env` `MODEL_*` → Nova IDs.
- [ ] First live Bedrock call / smoke.
- [ ] Re-run `profile_hard_tickets.py` on Bedrock and compare to Ollama-era `profile_hard_combined.summary.json`.
- [ ] Live eval gate with real AWS secrets in CI.
- [ ] Wire RAGAS judge to Bedrock (`eval/rag_eval.py` currently reports unavailable).
- [ ] Optional: terminate leftover AWS EBS / Azure resource cleanup.

---

## Key files (quick map)

```
app/llm/bedrock_client.py   # sole LLM transport + get_llm_client
app/llm/model_router.py      # flat role → model_* settings
app/agents/supervisor.py     # graph + judge_failed escalate
app/agents/drafting_agent.py # generate_text via shared client
eval/profile_hard_tickets.py # bare-graph per-node timings → JSON
eval/live_smoke_runner.py    # HTTP smoke against running API
tests/conftest.py            # default Bedrock mock for unit tests
.env.example                 # Bedrock-only template (no OLLAMA_*)
```

---

## Related artifacts

- Earlier hard-ticket profile (Ollama era): `eval/live_runs/profile_hard_combined.summary.json`
- Agent chat transcript for this migration thread: Cursor agent transcripts under the project’s `.cursor` projects folder (session work, not committed).
