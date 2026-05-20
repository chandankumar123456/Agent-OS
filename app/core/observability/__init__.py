"""Observability subsystem re-exports.

Provides unified access to logging, metrics, tracing, and alerting
from the desktop-native implementations.

Usage:
    from app.core.observability import local_logger, local_metrics
    from app.core.observability import local_tracer, local_alerts
"""
from __future__ import annotations

from ...desktop_native.local_logger import local_logger
from ...desktop_native.local_metrics import local_metrics
from ...desktop_native.local_tracer import local_tracer
from ...desktop_native.local_alerts import local_alerts

__all__ = [
    "local_logger",
    "local_metrics",
    "local_tracer",
    "local_alerts",
]
