# Grafana analytics stack

`docker compose up grafana` starts Grafana OSS with the BigQuery datasource
plugin and four provisioned dashboards, reading from `fact_ticket_events`
(`app/analytics/bigquery_sink.py`).

## One-time setup

1. **Enable BigQuery** (see main `README.md`): set `ENABLE_BIGQUERY=true`,
   `BIGQUERY_PROJECT_ID`, and `GOOGLE_APPLICATION_CREDENTIALS` in `.env`.
2. **Create a Grafana service account** with `BigQuery Data Viewer` +
   `BigQuery Job User`. Download its JSON key.
3. From that key, set in root `.env` before `docker compose up`:
   ```
   GCP_PROJECT_ID=<project id for fact_ticket_events>
   BIGQUERY_CLIENT_EMAIL=<key's client_email>
   BIGQUERY_PRIVATE_KEY=<key's private_key, keep \n escapes>
   ```
4. `docker compose up grafana` (or full stack). Grafana:
   http://localhost:3001 (admin / `$GRAFANA_ADMIN_PASSWORD`, default `admin`).
5. Dashboards use `` `ticket_analytics.fact_ticket_events` `` and inherit
   the project from `GCP_PROJECT_ID`. Open **Ticket Resolution Analytics**
   and set the time range to at least the last day.

Credentials are not auto-provisioned (no CI GCP project). See
`grafana/provisioning/datasources/bigquery.yaml` for the three env vars.

## Dashboards

| Dashboard | File | What it answers |
|---|---|---|
| Ticket Trends | `dashboards/ticket-trends.json` | Volume over time, by domain pack, by priority; 7-day rolling escalation rate |
| Agent Performance | `dashboards/agent-performance.json` | Confidence distributions, escalation rate, intent self-consistency |
| RAG Health | `dashboards/rag-health.json` | Faithfulness/relevance trends, retrieval-miss rate, relevant-doc ratio |
| Ops & Cost | `dashboards/ops-cost.json` | Iterations, LLM tokens, latency percentiles, safety-net trips |

Panels query `fact_ticket_events` with BigQuery standard SQL — see
`app/analytics/bigquery_sink.py` for the schema.
