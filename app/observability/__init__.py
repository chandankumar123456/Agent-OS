"""AgentOS Execution Observability Layer.

Emits structured, queryable traces for every agent reasoning step, tool invocation,
and system decision.  Events are broadcast in real-time via the event bus and
persisted to the database for historical analysis.
"""
from .models import ObservabilityEvent, ObservabilityEventType
from .bus import ObservabilityBus, observability_bus

__all__ = [
    "ObservabilityEvent",
    "ObservabilityEventType",
    "ObservabilityBus",
    "observability_bus",
]
