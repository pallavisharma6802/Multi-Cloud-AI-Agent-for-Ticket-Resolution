"""Unit tests for batch-grade helpers (no live Ollama)."""
from app.agents.document_grader import is_mostly_english


def test_is_mostly_english_accepts_ascii():
    assert is_mostly_english("track order ORD-123 shipping status")


def test_is_mostly_english_rejects_chinese():
    assert not is_mostly_english("如何确保及时有效的沟通")


def test_is_mostly_english_rejects_mixed_cjk():
    assert not is_mostly_english("order status 订单追踪")
