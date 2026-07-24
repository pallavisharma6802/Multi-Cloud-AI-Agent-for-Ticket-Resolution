"""BigQuery sink: disabled no-op, row shaping, and fail-safe inserts."""
from unittest.mock import MagicMock

from app.analytics.bigquery_sink import BigQuerySink


def test_disabled_sink_is_a_pure_noop(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "enable_bigquery", False)
    sink = BigQuerySink()
    assert sink.enabled is False
    sink.record_ticket_event({"ticket_id": "TKT-1"})
    sink.ensure_table()


def test_build_row_defaults_and_passthrough():
    row = BigQuerySink._build_row({
        "ticket_id": "TKT-2",
        "intent": "cancel_order",
        "final_action": "escalate",
        "anomaly_flags": ["safety_net"],
    })
    assert row["ticket_id"] == "TKT-2"
    assert row["intent"] == "cancel_order"
    assert row["final_action"] == "escalate"
    assert row["anomaly_flags"] == ["safety_net"]
    assert row["continuation_rationale"] == []
    assert row["estimated_cost_usd"] is None


def test_insert_row_safe_swallows_exceptions(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "enable_bigquery", True)
    sink = BigQuerySink()
    sink._table_ready = True
    sink._client_and_table = MagicMock(side_effect=RuntimeError("network is down"))
    sink._insert_row_safe({"ticket_id": "TKT-4"})
