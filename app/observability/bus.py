"""ObservabilityBus — centralised emitter for structured execution traces.

Every emitted event is:
1. Logged to the application logger (structured text).
2. Broadcast over the real-time event bus (WebSocket delivery).
3. Persisted to the database as a span for historical querying.
"""
from __future__ import annotations

import traceback
from typing import Any, Dict

from .models import ObservabilityEvent, ObservabilityEventType
from ..logs.logger import logger
from ..memory.long_term import span_repo
from ..memory.redis_pubsub import redis_pubsub_client


class ObservabilityBus:
    """Emits observability events to logs, websockets, and persistent storage."""

    async def emit(self, event: ObservabilityEvent) -> None:
        # 1. Console / file log
        logger.info(
            f"[{event.event_type.value}] task={event.task_id} "
            f"source={event.source} step={event.step_id} payload_keys={list(event.payload.keys())}"
        )

        # 2. Real-time event bus (WebSocket)
        try:
            from ..orchestrator.event_bus import event_bus, Event

            await event_bus.publish(
                f"task:{event.task_id}",
                Event(
                    event_type=event.event_type.value,
                    payload=event.to_event_bus_payload(),
                    source=event.source,
                    timestamp=event.timestamp.isoformat(),
                ),
            )
        except Exception as e:
            logger.warning(f"Observability real-time publish failed: {e}")

        # 3. Persistent span storage
        try:
            await span_repo.create(
                trace_id=event.trace_id or event.task_id,
                span_id=f"{event.event_type.value}:{event.timestamp.isoformat()}",
                operation=event.event_type.value,
                agent_name=event.source,
                metadata=event.payload,
            )
        except Exception as e:
            # Downgrade to debug when DB is not initialized (common in tests/benchmarks)
            if "session factory is unavailable" in str(e).lower() or "database" in str(e).lower():
                logger.debug(f"Observability DB persist skipped (DB unavailable): {e}")
            else:
                logger.warning(f"Observability DB persist failed: {e}")

    async def emit_safe(
        self,
        event_type: ObservabilityEventType,
        task_id: str,
        trace_id: Optional[str] = None,
        step_id: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
        source: str = "agentos",
    ) -> None:
        """Convenience wrapper that builds the event and emits it, swallowing errors."""
        try:
            event = ObservabilityEvent(
                event_type=event_type,
                task_id=task_id,
                trace_id=trace_id,
                step_id=step_id,
                payload=payload or {},
                source=source,
            )
            await self.emit(event)
        except Exception as e:
            logger.error(f"Observability emit_safe failed: {e}\n{traceback.format_exc()}")


# Module-level singleton
observability_bus = ObservabilityBus()
