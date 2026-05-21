"""core.events - Unified event bus.

Merges:
- LocalEventBus (SQLite-backed, default)
- Observability bus (app/observability/bus.py)

Redis-backed event bus is dropped from the default code path.
"""

from .desktop_native.event_bus import Event, LocalEventBus, local_event_bus

__all__ = ["Event", "LocalEventBus", "local_event_bus"]
