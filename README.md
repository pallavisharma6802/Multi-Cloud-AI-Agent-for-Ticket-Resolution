# Agentic Multi-Cloud Ticket Resolution

An agentic support-ticket resolution system: a cyclic [LangGraph](https://github.com/langchain-ai/langgraph) of six
LLM agents (intent/priority classification, CRAG document grading, Self-RAG response judging, and an agentic
Continuation Agent that replaces every fixed retry-cap/threshold with a reasoned decision), running against two
real, labeled domain pack (IT/SaaS), with a from-scratch evaluation harness, a BigQuery/Grafana
analytics layer, and a Next.js UI — all runnable for free on a laptop via Docker Compose.

This is a rebuild of an earlier keyword-heuristic pipeline. See [Why this rebuild](#why-this-rebuild) for what
changed and why, and [Evaluation](#evaluation) for how "agentic, not guessed" is actually measured rather than
asserted.

## Table of contents

- [Architecture](#architecture)
- [Why this rebuild](#why-this-rebuild)
- [Domain packs](#domain-packs)
- [Running locally](#running-locally)
- [Evaluation](#evaluation)
- [Analytics (BigQuery + Grafana)](#analytics-bigquery--grafana)
- [Observability (LangSmith)](#observability-langsmith)
- [Frontend](#frontend)
- [CI/CD](#cicd)
- [Project structure](#project-structure)
- [Multimodal: considered and rejected](#multimodal-considered-and-rejected)
- [Extending with a new domain pack](#extending-with-a-new-domain-pack)

## Architecture

```mermaid
flowchart TB
    subgraph domainPacks ["Domain Packs (config-driven, swappable)"]
        itPack["it_saas: 27 intents — resolution assist"]
    end

    subgraph agenticGraph ["LangGraph Supervisor (cyclic, conditional edges)"]
        analyze["analyze_ticket\n(Azure NER/sentiment +\nLLM Intent+Priority Agent)"]
        retrieve["retrieve_documents\n(hybrid dense + BM25)"]
        grade["grade_documents\n(CRAG relevance grader)"]
        cont1["continuation_agent\n(rewrite/proceed/escalate)"]
        draft["draft_response"]
        judge["judge_response\n(Self-RAG faithfulness critic)"]
        cont2["continuation_agent\n(retry/accept/escalate)"]
        final["final_decision\n(Supervisor: auto-resolve\nor escalate, rationale)"]

        analyze --> retrieve --> grade --> cont1
        cont1 -->|rewrite_query| retrieve
        cont1 -->|proceed| draft
        cont1 -->|escalate| final
        draft --> judge --> cont2
        cont2 -->|retry| draft
        cont2 -->|accept| final
        cont2 -->|escalate| final
    end

    domainPacks -.->|active pack config| analyze

    final --> postgres[("PostgreSQL\n(OLTP)")]
    final --> bqSink["Async BigQuery sink\n(fire-and-forget)"]
    bqSink --> bigquery[("BigQuery fact table")]
    bigquery --> grafana["Grafana OSS\n(trends, agent performance,\nRAG health, ops/cost)"]

    ui["Next.js UI\n(submit / triage /\nticket detail / analytics)"] --> api["FastAPI"]
    api --> agenticGraph
```

Every box that makes a judgment call is an LLM call against the active domain pack's taxonomy and few-shot
examples — there is no keyword dictionary, fixed confidence formula, or hardcoded retry counter anywhere in the
decision path. See [`app/agents/supervisor.py`](app/agents/supervisor.py) for the actual graph wiring.

| Agent | File | Real work it does |
|---|---|---|
| Azure NLP | [`app/agents/azure_nlp_agent.py`](app/agents/azure_nlp_agent.py) | Real Azure Text Analytics calls for entity extraction, sentiment, key phrases. No intent/priority logic — that's fully LLM-owned now. |
| Intent + Priority | [`app/agents/intent_priority_agent.py`](app/agents/intent_priority_agent.py) | LLM classifies intent + priority against the active pack's taxonomy, with self-consistency sampling and a rationale. |
| Retrieval | [`app/agents/retrieval_agent.py`](app/agents/retrieval_agent.py) | Hybrid dense (Pinecone) + sparse (BM25) candidate retrieval, chunked 200–500 words with overlap. No similarity-score cutoff — grading is the real filter. |
| Document Grader (CRAG) | [`app/agents/document_grader.py`](app/agents/document_grader.py) | Per-document relevance grading + query rewriting on retry. |
| Drafting | [`app/agents/drafting_agent.py`](app/agents/drafting_agent.py) | Generates the response from graded-relevant context. No hand-rolled confidence formula — confidence comes only from the Judge. |
| Judge (Self-RAG) | [`app/agents/judge_agent.py`](app/agents/judge_agent.py) | Faithfulness + relevance critique of the draft against only the graded-relevant documents. |
| Continuation Agent | [`app/agents/continuation_agent.py`](app/agents/continuation_agent.py) | Reads the full trace and decides `rewrite_query` / `proceed` / `retry` / `accept` / `escalate`. |
| Supervisor | [`app/agents/supervisor.py`](app/agents/supervisor.py) | Owns the LangGraph state machine; `final_decision` is itself an LLM call reasoning over the whole trace, not a hardcoded boolean check. |

Shared infrastructure: [`app/llm/bedrock_client.py`](app/llm/bedrock_client.py) wraps every Amazon Bedrock
Converse call with structured-output validation (Pydantic schema + retry-on-malformed-output), throttle
backoff, and fail-fast on access-denied. Per-role model IDs
(`model_intent_priority`, `model_grader`, `model_judge`, `model_continuation`, `model_drafting`,
`model_supervisor` in [`app/config.py`](app/config.py)) are resolved by a flat lookup in
[`app/llm/model_router.py`](app/llm/model_router.py) — any single role's Bedrock model can be swapped
independently once an eval run shows it needs a different SKU (e.g. Nova Micro vs Lite).

**Engineering safety net, not a business rule**: `max_iterations` and `max_wall_clock_seconds`
(`app/config.py`) put a hard ceiling on worst-case cost/latency if a bug causes runaway looping. Trips are logged
as anomalies and surfaced on the ops/cost Grafana dashboard — they never influence what an agent decides, only
guarantee the system can't run forever.

## Why this rebuild

Researched during planning: commercial agentic support platforms (Decagon, Sierra, Intercom Fin, Ada, Forethought)
report 65–85% autonomous resolution in 2026, driven primarily by knowledge-base quality and retrieval accuracy,
not model choice. Open-source reference implementations (`saqiba123/Support-Ticket-Resolution-Agent-with-Multi-Step-Review-Loop`,
`PrAtHaM-0707/Agentic-Support-AI`, `Sari95/langgraph-multi-agent-ticket-triage`) all use a **fixed retry counter**
for their review loop, and none combine per-document relevance grading (CRAG) + faithfulness critique (Self-RAG)
+ feedback-injected retry (Reflexion) + an agentic continuation decision in one graph.

What the original version of this repo had instead: keyword-dictionary intent classification, a hardcoded
`min_similarity = 0.65` retrieval cutoff, a hand-rolled confidence formula, and a fixed escalation threshold — none
of which reasoned over the actual content of a ticket. The rebuild replaces all of that with the agent table above,
plus a real evaluation harness (below) so "agentic" is a measured property, not a marketing claim.

## Domain packs

Packs ship under [`domains/`](domains/) and are auto-discovered — the LangGraph is generic and swappable
across whichever packs are present.

- **`it_saas`** — resolution assist. 27 Bitext intents with labeled eval + intent-tagged FAQ KB.
  `intent_eval_available: true`.

Each pack directory contains `config.yaml`, `few_shot_examples.json`, and `kb/`.

### Per-role Bedrock models

[`app/llm/model_router.py`](app/llm/model_router.py) maps each agent role to a Bedrock model ID from settings
(`MODEL_INTENT_PRIORITY`, `MODEL_GRADER`, `MODEL_JUDGE`, `MODEL_CONTINUATION`, `MODEL_DRAFTING`,
`MODEL_SUPERVISOR`). Defaults are `amazon.nova-lite-v1:0`; pin Micro on cheaper roles if you want.
`GET /health` returns the current assignments under `model_routing`.

## Running locally

Compose brings up local Postgres / API / UI / Grafana. **LLM inference is Amazon Bedrock** (external) —
enable Nova access in the Bedrock console for your AWS account/region and provide credentials via
`aws configure`, env vars, or an instance role.

### Option A — Docker Compose (recommended)

```bash
cp .env.example .env
# Fill in managed-service credentials Compose can't stand up locally:
#   AZURE_TEXT_ANALYTICS_ENDPOINT / AZURE_TEXT_ANALYTICS_KEY
#   PINECONE_API_KEY / PINECONE_ENVIRONMENT
#   AWS credentials + AWS_REGION (Bedrock)

docker compose up --build
```

- Backend API: http://localhost:8000/docs
- Frontend: http://localhost:3000
- Grafana: http://localhost:3001 (admin/admin by default; anonymous viewer access is also enabled for the
  frontend's embedded analytics page)

Then seed the knowledge base:

```bash
docker compose exec backend python seed_kb.py --pack all
# or: --pack it_saas
```

**What Docker Compose does *not* provide**, because they're real external managed services: Amazon Bedrock
(LLM), Azure Text Analytics (NLP signals), and Pinecone (vector storage). BigQuery analytics is opt-in and
off by default (`ENABLE_BIGQUERY=false`).

The EC2/Ollama Terraform under [`infra/aws/`](infra/aws/) is a **legacy artifact** (self-hosted Ollama is no
longer a runtime option). See [`infra/README.md`](infra/README.md).

### Option B — Native Python (no Docker)

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env   # Azure, Pinecone, AWS/Bedrock, DATABASE_URL
# aws configure   # or export AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY

python app/db/init_db.py
python seed_kb.py --pack all
uvicorn app.api.main:app --reload
```

### Running tests

```bash
pytest tests/ -v
```

Tests are fully mocked (Bedrock via MagicMock / boto3 stub, Azure, Pinecone, BigQuery — see
`tests/conftest.py`) so they run in a few seconds with zero live credentials or network access.

## Evaluation

`eval/` measures each agent that makes a judgment call:

| Script | Metric | What it measures |
|---|---|---|
| [`eval/intent_priority_eval.py`](eval/intent_priority_eval.py) | Macro-F1 | IT intent labels |
| [`eval/ner_eval.py`](eval/ner_eval.py) | Entity P/R/F1 | Azure NER when gold CoNLL provided |
| [`eval/rag_eval.py`](eval/rag_eval.py) | Faithfulness / relevancy | ragas against seeded KB |
| [`eval/agreement_eval.py`](eval/agreement_eval.py) | Kappa | Human escalate labels |
| [`eval/run_eval.py`](eval/run_eval.py) | CI gate | Orchestrates + baseline compare |
| [`eval/live_smoke_runner.py`](eval/live_smoke_runner.py) | Live continuous smoke | IT/SaaS labeled suite via `POST /api/v1/tickets` |
| [`eval/score_live_run.py`](eval/score_live_run.py) | Live spot-check | Scores smoke JSONL vs suite labels |

```bash
python eval/run_eval.py --pack all --skip-rag
python eval/run_eval.py --pack it_saas --update-baseline
```

### Live smoke (continuous)

Labeled suite: [`eval/datasets/live_smoke_suite.jsonl`](eval/datasets/live_smoke_suite.jsonl) (IT/SaaS, easy→hard).

```bash
python eval/live_smoke_runner.py --once
python eval/live_smoke_runner.py --interval 10    # continuous
python eval/score_live_run.py --run eval/live_runs/run_YYYYMMDD.jsonl
```

Latency knobs: `INTENT_NUM_SAMPLES`, `RETRIEVAL_TOP_K`, `MAX_QUERY_REWRITES`. Per-role models: `MODEL_*`.

## Analytics (BigQuery + Grafana)

[`app/analytics/bigquery_sink.py`](app/analytics/bigquery_sink.py) is an async, fire-and-forget sink
(`insert_rows_json`, not the Storage Write API — unnecessary complexity at this volume) called from the
Supervisor's `final_decision` node. It never blocks or fails ticket resolution — exceptions are caught and
logged, not raised. Opt-in via `ENABLE_BIGQUERY=true`; uses BigQuery's free sandbox tier (10GB storage, 1TB
query/month, no billing account required).

Schema: `fact_ticket_events`, partitioned by `DATE(event_ts)`, clustered by `category, priority` — every trace
field from the graph (iteration count, judge scores, escalation rationale, cost estimate, domain pack) plus
latency/model metadata per agent call.

Four Grafana dashboards are provisioned automatically (`grafana/dashboards/`, wired up via
`grafana/provisioning/`) once BigQuery is enabled and Grafana is given real service-account JWT credentials (see
`grafana/README.md`):

- **`ticket-trends.json`** — volume by domain pack/priority, 7-day rolling escalation rate.
- **`agent-performance.json`** — confidence distributions, escalation rate, intent self-consistency.
- **`rag-health.json`** — faithfulness/relevance trend, retrieval-miss rate, relevant/candidate ratio.
- **`ops-cost.json`** — iterations, LLM calls/tokens, latency percentiles, safety-net trip counts.

## Observability (LangSmith)

Optional, opt-in, alongside (not instead of) the BigQuery/Grafana analytics above — traces the LangGraph
supervisor's node-by-node execution at [smith.langchain.com](https://smith.langchain.com). The app runs
identically with this unset.

1. Sign up and create an API key at smith.langchain.com if you don't already have one.
2. Set in `.env`: `LANGSMITH_TRACING=true`, `LANGSMITH_API_KEY=<your-key>`, `LANGSMITH_PROJECT=ticket-agent`
   (see `.env.example`).
3. **These must reach the real process environment, not just `.env`.** Like `GOOGLE_APPLICATION_CREDENTIALS`
   for BigQuery, the LangSmith SDK reads `os.environ` directly — pydantic-settings parsing `.env` into
   `Settings` does not populate that. Export them in the shell before starting the server (or set them under
   Docker Compose's `environment:` block), e.g.:
   ```bash
   export LANGSMITH_TRACING=true LANGSMITH_API_KEY=<your-key> LANGSMITH_PROJECT=ticket-agent
   python3 -m uvicorn app.api.main:app --host 0.0.0.0 --port 8000
   ```

No code changes are required for node-level tracing — LangGraph wraps every node (including plain Python
functions) in its own traced `Runnable`, so each node in a run shows up as its own span automatically. What's
**not** captured automatically: the individual Bedrock calls inside each node. [`app/llm/bedrock_client.py`](app/llm/bedrock_client.py)
calls `boto3` directly rather than a LangChain-wrapped LLM client, so a node's span shows its input/output state
but not a nested per-call LLM trace (prompt, token counts, etc.) — that would need explicit `@traceable`
instrumentation, not done here.

Verified working against a live run: submitting a real ticket through the running backend with
`LANGSMITH_TRACING=true` produced a full node-by-node trace in the LangSmith UI (`analyze_ticket` →
`retrieve_documents` → `grade_documents` → `continuation_post_grading` → `draft_response` ↔ `judge_response` →
`continuation_post_judging`, looping to `max_iterations`), with correct intent/final_action and judge scores
all visible per span — zero code changes, as predicted above.

## Frontend

`frontend/` is a Next.js 15 (App Router) + Tailwind app calling the FastAPI backend directly:

- **`/submit`** — ticket submission form (domain-pack selector, title/description), shows the immediate
  processing result.
- **`/triage`** — ticket queue with domain/priority/status/escalation filters.
- **`/tickets/[id]`** — full agentic trace view: per-document CRAG grading rationale, judge scores per
  iteration, continuation rationale at every branch point, and the final Supervisor rationale. This is the
  project's best demonstration piece — the whole point of the rebuild is that every decision has a reasoned
  trace, and this page renders exactly that trace, not a summary of it.
- **`/analytics`** — embeds the Grafana dashboards above via iframe.

```bash
cd frontend
npm install
npm run dev   # http://localhost:3000, expects the backend at NEXT_PUBLIC_API_URL (default http://localhost:8000)
```

## CI/CD

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs on every push/PR to `main`, four sequential jobs:

1. **Lint** — `ruff check .` (config in `pyproject.toml`).
2. **Test** — `pytest tests/` with mocked cloud clients (see `tests/conftest.py`) — no real credentials needed.
3. **Eval gate** — when `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` repo secrets are set, runs
   `eval/run_eval.py --pack all --skip-rag` against Bedrock and gates on `eval/report_baseline.json`.
   Without those secrets the job skips the live LLM step (unit tests still block merges). `--skip-rag`
   remains: ragas needs a seeded Pinecone index and a Bedrock-wired judge (not yet restored).
4. **Build** — builds both the backend and frontend Docker images (no push).

A separate, optional Terraform plan/Checkov workflow for `infra/` (targeting only free-tier-eligible resources)
is intentionally not wired up as a merge-blocking gate, since the Terraform path itself is now optional/legacy —
see [`infra/README.md`](infra/README.md).

## Project structure

```
app/
├── agents/            # 8 agents — see the table in Architecture above
├── analytics/         # Async BigQuery sink
├── api/
│   ├── main.py         # FastAPI app, CORS
│   └── routes/         # tickets.py, health.py
├── db/                 # SQLAlchemy models/session/init
├── domain/             # Domain-pack loader + schema
├── embeddings/         # SentenceTransformers + chunking + Pinecone client
├── llm/                # Bedrock client (structured output, per-role model IDs)
├── schemas/            # Pydantic request/response schemas
└── config.py           # Central Pydantic settings

domains/                # it_saas/ — config.yaml, few-shot examples, KB
eval/                   # Evaluation harness — see Evaluation above
frontend/               # Next.js UI
grafana/                # Dashboards + provisioning
infra/                  # Optional/legacy Terraform (see infra/README.md)
tests/                  # Fully mocked Bedrock/Azure/Pinecone/BigQuery
docker-compose.yml      # Local stack: postgres, backend, frontend, grafana (Bedrock external)
```

## Multimodal: considered and rejected

Image and voice input were researched and explicitly rejected for this build. The "real" image datasets found
(`ImageR` Bugzilla screenshots, `SROIE` receipts) don't actually pair with ticket text — using them would mean
synthetically stapling unrelated data together, which conflicts with the no-guessing/no-fabrication standard
applied everywhere else in this rebuild (see [Evaluation](#evaluation)). Voice has real transcripts
(`CallCenterEN`) but no free raw audio to evaluate speech-to-text on this domain. If a real, paired
multimodal ticket dataset surfaces, this is the first place to revisit — not before.

## Extending with a new domain pack

1. Create `domains/<your_pack>/config.yaml` following `domains/it_saas/config.yaml`'s shape: intent taxonomy,
   priority guidance (prose, not rules), KB category map, and `source_dataset` provenance (including honest
   `limitations`).
2. Add `domains/<your_pack>/few_shot_examples.json` and `domains/<your_pack>/kb/*.json` (or similar) knowledge
   base articles.
3. If you have labeled ground-truth intents, add `eval/datasets/<your_pack>_test.jsonl` and set
   `intent_eval_available: true`; otherwise set it to `false` with a `limitations` string explaining why.
4. `python seed_kb.py --pack <your_pack>` to index the KB into its own Pinecone namespace.
5. `python eval/run_eval.py --pack <your_pack>` to get real numbers before shipping it.

No code changes required — the agents, graph, and eval harness are all pack-agnostic by construction.
