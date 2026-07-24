# Frontend

Next.js 14 (App Router) + Tailwind UI for the FastAPI backend in `app/`.
Pages call existing routes via `lib/api.ts` (covered by `tests/test_integration.py`).

## Pages

- `/submit` — ticket submission form (domain-pack selector from
  `GET /api/v1/domain-packs`, title/description/email, calls
  `POST /api/v1/tickets` and shows the drafted response + a link to the
  full trace).
- `/triage` — triage queue: `GET /api/v1/tickets` with status/priority/
  domain filters.
- `/tickets/[id]` — full agentic trace: Supervisor decision, intent/priority,
  CRAG grading, Self-RAG judge scores, Continuation Agent history, drafted
  response, and agent decision log.
- `/analytics` — embeds Grafana dashboards in iframes (falls back with a note
  if Grafana/BigQuery aren't configured — see `grafana/README.md`).

## Local development

```bash
cp .env.local.example .env.local   # point at your backend + Grafana
npm install
npm run dev                        # http://localhost:3000
```

Requires the FastAPI backend running (see the root `README.md`) for
anything beyond the home page to render real data.

## Build

```bash
npm run build && npm run start
```

## Known `npm audit` findings

`npm audit` reports 3 remaining vulnerabilities after pinning `next@15.5.21`
and `postcss@^8.5.10`: they sit in packages Next.js bundles internally
(`postcss@8.4.31`, `sharp@0.34.5`), not top-level deps this app controls.
This app does not call `next/image` or process untrusted CSS. Re-run
`npm audit` after any `next` version bump.
