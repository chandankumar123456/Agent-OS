"""ObservabilityBus — centralised emitter for structured execution traces.

Every emitted event is:
1. Logged to the application logger (structured text).
2. Broadcast over the real-time event bus (WebSocket delivery).
3. Persisted to the database as a span for historical querying.
"""
from __future__ import annotations

import asyncio
import traceback
from typing import Any, Dict, List, Optional

from .models import ObservabilityEvent, ObservabilityEventType
from ..logs.logger import logger
from ..memory.long_term import span_repo


class ObservabilityBus:
    """Emits observability events to logs, websockets, and persistent storage.

    DB writes are batched and flushed asynchronously to avoid I/O overhead
    on critical execution paths.
    """

    def __init__(self):
        self._batch_queue: asyncio.Queue = asyncio.Queue(maxsize=500)
        self._batch_flush_task: Optional[asyncio.Task] = None
        self._flush_interval = 2.0  # flush every 2 seconds
        self._batch_size = 50  # or after 50 events

    async def _flush_batch(self, events: List[ObservabilityEvent]) -> None:
        """Write a batch of events to span storage in a single transaction."""
        if not events:
            return
        try:
            for event in events:
                await span_repo.create(
                    trace_id=event.trace_id or event.task_id,
                    span_id=f"{event.event_type.value}:{event.timestamp.isoformat()}",
                    operation=event.event_type.value,
                    agent_name=event.source,
                    metadata=event.payload,
                )
        except Exception as e:
            if "session factory is unavailable" in str(e).lower() or "database" in str(e).lower():
                logger.debug(f"Observability DB persist skipped (DB unavailable): {e}")
            else:
                logger.warning(f"Batch observability DB persist failed: {e}")

    def _start_flush_loop(self):
        """Start background task that periodically flushes the event batch."""
        if self._batch_flush_task is None or self._batch_flush_task.done():
            self._batch_flush_task = asyncio.create_task(self._flush_loop())

    async def _flush_loop(self):
        """Background loop that flushes batched span writes."""
        while True:
            try:
                await asyncio.sleep(self._flush_interval)
                events: List[ObservabilityEvent] = []
                while not self._batch_queue.empty() and len(events) < self._batch_size:
                    try:
                        ev = self._batch_queue.get_nowait()
                        events.append(ev)
                    except asyncio.QueueEmpty:
                        break
                await self._flush_batch(events)
            except asyncio.CancelledError:
                # Flush remaining on cancel
                remaining = []
                while not self._batch_queue.empty():
                    try:
                        remaining.append(self._batch_queue.get_nowait())
                    except asyncio.QueueEmpty:
                        break
                await self._flush_batch(remaining)
                raise
            except Exception as e:
                logger.warning(f"Observability flush loop error: {e}")

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

        # 3. Queue for batched DB write
        try:
            self._start_flush_loop()
            self._batch_queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning("Observability event batch queue full, dropping event")
        except Exception as e:
            logger.warning(f"Observability queue failed: {e}")

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


    async def shutdown(self):
        """Flush remaining events and stop the flush loop."""
        if self._batch_flush_task and not self._batch_flush_task.done():
            self._batch_flush_task.cancel()
            try:
                await self._batch_flush_task
            except asyncio.CancelledError:
                pass
        # Flush any remaining
        remaining = []
        while not self._batch_queue.empty():
            try:
                remaining.append(self._batch_queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        await self._flush_batch(remaining)


# Module-level singleton
observability_bus = ObservabilityBus()
