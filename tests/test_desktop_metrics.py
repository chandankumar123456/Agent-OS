"""Tests for desktop-specific metrics helpers (OR2)."""
from core.logs.metrics import MetricsCollector


def test_metrics_collector_has_desktop_helpers():
    """OR2: MetricsCollector must expose desktop-specific recording helpers."""
    mc = MetricsCollector()
    assert hasattr(mc, "record_desktop_task")
    assert hasattr(mc, "record_desktop_action")
    assert hasattr(mc, "record_desktop_retry")
    assert hasattr(mc, "record_desktop_perception_layer")
