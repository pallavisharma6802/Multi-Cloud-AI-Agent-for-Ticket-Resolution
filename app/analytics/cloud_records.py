"""Durable full-ticket snapshots in BigQuery, separate from analytics events."""

import hashlib
import json
import logging
import threading
from datetime import datetime, timedelta, timezone

from app.config import settings

logger = logging.getLogger(__name__)
_lock = threading.Lock()
_ready = False
_client = None


def save_ticket_record(record: dict) -> bool:
    """Return true only after BigQuery acknowledges the complete snapshot.

    Postgres remains the operational source of truth. A cloud failure is visible
    in the returned API trace and does not discard the completed local ticket.
    """
    if not settings.enable_bigquery:
        return False
    global _ready, _client
    try:
        from google.cloud import bigquery

        project = settings.bigquery_project_id or settings.gcp_project_id
        table_id = f"{project}.{settings.bigquery_dataset}.ticket_records"
        with _lock:
            if _client is None:
                _client = bigquery.Client(project=project)
            if not _ready:
                dataset = bigquery.Dataset(f"{project}.{settings.bigquery_dataset}")
                dataset.location = settings.gcp_region
                dataset.default_table_expiration_ms = 59 * 24 * 60 * 60 * 1000
                dataset.default_partition_expiration_ms = 59 * 24 * 60 * 60 * 1000
                _client.create_dataset(dataset, exists_ok=True, timeout=15)
                table = bigquery.Table(
                    table_id,
                    schema=[
                        bigquery.SchemaField("ticket_id", "STRING", mode="REQUIRED"),
                        bigquery.SchemaField("recorded_at", "TIMESTAMP", mode="REQUIRED"),
                        bigquery.SchemaField("status", "STRING"),
                        bigquery.SchemaField("payload", "STRING", mode="REQUIRED"),
                    ],
                )
                table.expires = datetime.now(timezone.utc) + timedelta(days=59)
                _client.create_table(table, exists_ok=True, timeout=15)
                _ready = True
        from google.cloud.exceptions import Conflict

        rows = [
            {
                "ticket_id": record["ticket_id"],
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "status": record["status"],
                "payload": json.dumps(record),
            }
        ]
        version = hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()[:20]
        job_id = "ticket_record_" + record["ticket_id"].replace("-", "_") + "_" + version
        try:
            job = _client.load_table_from_json(
                rows,
                table_id,
                job_id=job_id,
                job_config=bigquery.LoadJobConfig(
                    write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
                ),
                location=settings.gcp_region,
                timeout=20,
            )
        except Conflict:
            job = _client.get_job(job_id, location=settings.gcp_region, timeout=20)
        job.result(timeout=45)
        logger.info("Full ticket snapshot stored in BigQuery: %s", record["ticket_id"])
        return True
    except Exception:
        logger.exception("Cloud ticket snapshot failed for %s", record.get("ticket_id"))
        return False
