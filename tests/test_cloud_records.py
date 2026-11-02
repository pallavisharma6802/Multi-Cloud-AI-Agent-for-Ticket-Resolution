import json
from unittest.mock import MagicMock

from app.analytics import cloud_records
from app.config import settings


def test_full_ticket_snapshot_is_acknowledged_by_cloud(monkeypatch):
    monkeypatch.setattr(settings, "enable_bigquery", True)
    monkeypatch.setattr(settings, "bigquery_project_id", "test-project")
    client = MagicMock()
    client.load_table_from_json.return_value.result.return_value = None
    monkeypatch.setattr(cloud_records, "_client", client)
    monkeypatch.setattr(cloud_records, "_ready", True)
    record = {
        "ticket_id": "TKT-DEMO",
        "status": "resolved",
        "title": "Password help",
        "description": "Forgot password",
        "trace": {"final_action": "auto_resolve"},
        "agent_decisions": [{"action": "review"}],
    }
    assert cloud_records.save_ticket_record(record) is True
    rows = client.load_table_from_json.call_args.args[0]
    assert json.loads(rows[0]["payload"]) == record


def test_cloud_rejection_is_reported_without_discarding_local_ticket(monkeypatch):
    monkeypatch.setattr(settings, "enable_bigquery", True)
    monkeypatch.setattr(settings, "bigquery_project_id", "test-project")
    client = MagicMock()
    client.load_table_from_json.return_value.result.side_effect = RuntimeError("access denied")
    monkeypatch.setattr(cloud_records, "_client", client)
    monkeypatch.setattr(cloud_records, "_ready", True)
    assert cloud_records.save_ticket_record({"ticket_id": "TKT-DEMO", "status": "resolved"}) is False


def test_snapshot_job_identity_changes_only_when_payload_changes(monkeypatch):
    monkeypatch.setattr(settings, "enable_bigquery", True)
    monkeypatch.setattr(settings, "bigquery_project_id", "test-project")
    client = MagicMock()
    monkeypatch.setattr(cloud_records, "_client", client)
    monkeypatch.setattr(cloud_records, "_ready", True)
    record = {"ticket_id": "TKT-DEMO", "status": "in_progress"}
    assert cloud_records.save_ticket_record(record)
    first = client.load_table_from_json.call_args.kwargs["job_id"]
    assert cloud_records.save_ticket_record(record)
    assert client.load_table_from_json.call_args.kwargs["job_id"] == first
    assert cloud_records.save_ticket_record({**record, "status": "resolved"})
    assert client.load_table_from_json.call_args.kwargs["job_id"] != first
