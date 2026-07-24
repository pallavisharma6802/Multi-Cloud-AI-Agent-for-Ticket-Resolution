"""Async fire-and-forget BigQuery sink for ticket analytics.

Fed from the Supervisor's final_decision node (one row per completed ticket).
Uses streaming inserts; never blocks or fails ticket resolution. The
google-cloud-bigquery import is lazy so local/test runs without GCP stay light.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Optional

from app.config import settings

logger = logging.getLogger(__name__)

# Bounded pool so a degraded BigQuery cannot spawn unbounded threads.
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="bq-sink")


def _fact_table_schema():
    from google.cloud import bigquery

    return [
        bigquery.SchemaField("event_ts", "TIMESTAMP", mode="REQUIRED"),
        bigquery.SchemaField("ticket_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("domain_pack", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("intent", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("category", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("priority", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("sentiment", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("final_action", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("requires_human_review", "BOOLEAN", mode="NULLABLE"),
        bigquery.SchemaField("final_confidence", "FLOAT64", mode="NULLABLE"),
        bigquery.SchemaField("intent_confidence", "FLOAT64", mode="NULLABLE"),
        bigquery.SchemaField("intent_self_consistency", "FLOAT64", mode="NULLABLE"),
        bigquery.SchemaField("iteration_count", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("retrieval_iteration", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("drafting_iteration", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("num_kb_candidates", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("num_relevant_documents", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("judge_faithfulness_score", "FLOAT64", mode="NULLABLE"),
        bigquery.SchemaField("judge_relevance_score", "FLOAT64", mode="NULLABLE"),
        bigquery.SchemaField("judge_confidence", "FLOAT64", mode="NULLABLE"),
        bigquery.SchemaField("escalation_rationale", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("anomaly_flags", "STRING", mode="REPEATED"),
        bigquery.SchemaField("continuation_rationale", "STRING", mode="REPEATED"),
        bigquery.SchemaField("llm_call_count", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("total_tokens", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("total_latency_ms", "FLOAT64", mode="NULLABLE"),
        bigquery.SchemaField("wall_clock_seconds", "FLOAT64", mode="NULLABLE"),
        # Self-hosted Ollama has no per-token billing; left unused.
        bigquery.SchemaField("estimated_cost_usd", "FLOAT64", mode="NULLABLE"),
    ]


class BigQuerySink:
    """No-op unless settings.enable_bigquery is true and the client initializes."""

    def __init__(self):
        self._client = None
        self._table_ref = None
        self._table_ready = False
        self.enabled = settings.enable_bigquery

    def _client_and_table(self):
        if self._client is not None:
            return self._client, self._table_ref

        from google.cloud import bigquery

        project = settings.bigquery_project_id or settings.gcp_project_id
        self._client = bigquery.Client(project=project)
        dataset_ref = bigquery.DatasetReference(project, settings.bigquery_dataset)
        self._table_ref = dataset_ref.table(settings.bigquery_table)
        return self._client, self._table_ref

    def ensure_table(self) -> None:
        """Create dataset/table if missing. Partitioned by day, clustered by category/priority."""
        if not self.enabled:
            return
        from google.cloud import bigquery
        from google.cloud.exceptions import NotFound

        client, table_ref = self._client_and_table()

        try:
            client.get_dataset(table_ref.dataset_id)
        except NotFound:
            dataset = bigquery.Dataset(f"{client.project}.{table_ref.dataset_id}")
            dataset.location = settings.gcp_region
            client.create_dataset(dataset)
            logger.info(f"[bigquery_sink] created dataset {table_ref.dataset_id}")

        try:
            client.get_table(table_ref)
        except NotFound:
            table = bigquery.Table(table_ref, schema=_fact_table_schema())
            table.time_partitioning = bigquery.TimePartitioning(
                type_=bigquery.TimePartitioningType.DAY, field="event_ts"
            )
            table.clustering_fields = ["category", "priority"]
            client.create_table(table)
            logger.info(f"[bigquery_sink] created table {settings.bigquery_table}")

        self._table_ready = True

    def record_ticket_event(self, fields: dict[str, Any]) -> None:
        """Submit insert on a background thread. Never raises."""
        if not self.enabled:
            return
        row = self._build_row(fields)
        _executor.submit(self._insert_row_safe, row)

    @staticmethod
    def _build_row(fields: dict[str, Any]) -> dict[str, Any]:
        return {
            "event_ts": fields.get("event_ts") or datetime.now(timezone.utc).isoformat(),
            "ticket_id": fields["ticket_id"],
            "domain_pack": fields.get("domain_pack"),
            "intent": fields.get("intent"),
            "category": fields.get("category"),
            "priority": fields.get("priority"),
            "sentiment": fields.get("sentiment"),
            "final_action": fields.get("final_action"),
            "requires_human_review": fields.get("requires_human_review"),
            "final_confidence": fields.get("final_confidence"),
            "intent_confidence": fields.get("intent_confidence"),
            "intent_self_consistency": fields.get("intent_self_consistency"),
            "iteration_count": fields.get("iteration_count"),
            "retrieval_iteration": fields.get("retrieval_iteration"),
            "drafting_iteration": fields.get("drafting_iteration"),
            "num_kb_candidates": fields.get("num_kb_candidates"),
            "num_relevant_documents": fields.get("num_relevant_documents"),
            "judge_faithfulness_score": fields.get("judge_faithfulness_score"),
            "judge_relevance_score": fields.get("judge_relevance_score"),
            "judge_confidence": fields.get("judge_confidence"),
            "escalation_rationale": fields.get("escalation_rationale"),
            "anomaly_flags": fields.get("anomaly_flags") or [],
            "continuation_rationale": fields.get("continuation_rationale") or [],
            "llm_call_count": fields.get("llm_call_count"),
            "total_tokens": fields.get("total_tokens"),
            "total_latency_ms": fields.get("total_latency_ms"),
            "wall_clock_seconds": fields.get("wall_clock_seconds"),
            "estimated_cost_usd": None,
        }

    def _insert_row_safe(self, row: dict[str, Any]) -> None:
        try:
            if not self._table_ready:
                self.ensure_table()
            client, table_ref = self._client_and_table()
            errors = client.insert_rows_json(table_ref, [row])
            if errors:
                logger.warning(f"[bigquery_sink] insert_rows_json returned errors: {errors}")
        except Exception as e:
            # Any insert failure is non-fatal; lose the event, not the ticket.
            logger.warning(f"[bigquery_sink] failed to record ticket event (non-fatal): {e}")


_sink: Optional[BigQuerySink] = None


def get_bigquery_sink() -> BigQuerySink:
    global _sink
    if _sink is None:
        _sink = BigQuerySink()
    return _sink
