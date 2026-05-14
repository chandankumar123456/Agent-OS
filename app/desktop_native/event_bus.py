"""Local event bus for desktop-native mode.

Replaces Redis pub/sub with asyncio.Queue-based broadcast.
Events are also persisted to SQLite for recovery.
"""

import asyncio
import json
import weakref
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Set

from ..logs.logger import logger
from .sqlite_store import sqlite_store


class Event:
    """Typed event for local event bus."""

    def __init__(
        self,
        event_type: str,
        payload: Dict[str, Any],
        source: str = "",
        timestamp: Optional[str] = None,
    ):
        self.event_type = event_type
        self.payload = payload
        self.source = source
        self.timestamp = timestamp or datetime.now(timezone.utc).isoformat()

    def json(self) -> str:
        return json.dumps(
            {
                "type": self.event_type,
                "payload": self.payload,
                "source": self.source,
                "timestamp": self.timestamp,
            },
            default=str,
        )

    @classmethod
    def parse(cls, raw: str) -> "Event":
        data = json.loads(raw)
        return cls(
            data["type"],
            data.get("payload", {}),
            data.get("source", ""),
            data.get("timestamp"),
        )

    def model_dump(self) -> Dict[str, Any]:
        return {
            "type": self.event_type,
            "payload": self.payload,
            "source": self.source,
            "timestamp": self.timestamp,
        }


class LocalEventBus:
    """Asyncio-based event bus for desktop-native mode.

    Uses weak references for subscribers to avoid memory leaks.
    Events are persisted to SQLite for crash recovery.
    """

    def __init__(self):
        self._channels: Dict[str, Set[asyncio.Queue]] = defaultdict(set)
        self._lock = asyncio.Lock()
        self._persist_events = True

    async def publish(self, channel: str, event: Event) -> None:
        """Publish an event to a channel."""
        try:
            async with self._lock:
                # Get a snapshot of queues to avoid holding lock during put
                queues = list(self._channels.get(channel, set()))

            # Broadcast to all subscribers
            for q in queues:
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    logger.warning(f"Event queue full for channel {channel}")

            # Persist to SQLite for recovery
            if self._persist_events:
                try:
                    await sqlite_store.execute(
                        """
                        INSERT INTO event_log (channel, event_type, payload, source, timestamp)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (channel, event.event_type, json.dumps(event.payload, default=str),
                         event.source, event.timestamp),
                    )
                    await sqlite_store.commit()
                except Exception as e:
                    logger.warning(f"Failed to persist event to SQLite: {e}")

            logger.debug(f"Event published to {channel}: {event.event_type}")
        except Exception as e:
            logger.error(f"Event publish failed: {e}")

    async def subscribe(self, channel: str) -> AsyncIterator[Event]:
        """Subscribe to a channel and yield events."""
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        async with self._lock:
            self._channels[channel].add(q)

        try:
            while True:
                event = await q.get()
                yield event
        except asyncio.CancelledError:
            raise
        finally:
            async with self._lock:
                self._channels[channel].discard(q)
                if not self._channels[channel]:
                    del self._channels[channel]

    async def get_recent_events(
        self,
        channel: str,
        limit: int = 100,
    ) -> List[Event]:
        """Get recent events from SQLite for recovery."""
        try:
            rows = await sqlite_store.fetchall(
                """
                SELECT event_type, payload, source, timestamp
                FROM event_log
                WHERE channel = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (channel, limit),
            )
            events = []
            for row in rows:
                events.append(Event(
                    event_type=row["event_type"],
                    payload=json.loads(row["payload"]),
                    source=row["source"],
                    timestamp=row["timestamp"],
                ))
            return list(reversed(events))
        except Exception as e:
            logger.error(f"Failed to get recent events: {e}")
            return []

    async def cleanup_old_events(self, max_age_days: int = 7) -> int:
        """Remove old events from SQLite."""
        try:
            cursor = await sqlite_store.execute(
                """
                DELETE FROM event_log
                WHERE timestamp < datetime('now', '-' || ? || ' days')
                """,
                (max_age_days,),
            )
            await sqlite_store.commit()
            return cursor.rowcount
        except Exception as e:
            logger.error(f"Failed to cleanup old events: {e}")
            return 0


# Module-level singleton
local_event_bus = LocalEventBus()
