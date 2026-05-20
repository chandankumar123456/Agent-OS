"""Local in-process event bus using asyncio.

Replaces the Redis pub/sub event bus with a simple asyncio-based
implementation suitable for the desktop-native single-process runtime.
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import AsyncIterator, Dict, List, Optional

from ..logs.logger import logger
from .types import Event

# Re-export Event for backward compatibility
__all__ = ["EventBus", "event_bus", "Event"]


class EventBus:
    """Local in-process event bus using asyncio.Queue per subscriber.

    Provides publish/subscribe semantics without Redis dependency.
    Each subscriber gets its own queue, and publish fans out to all
    subscribers on a channel.
    """

    def __init__(self):
        self._subscribers: Dict[str, List[asyncio.Queue]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def publish(self, channel: str, event: Event) -> None:
        """Publish an event to all subscribers on a channel."""
        async with self._lock:
            subscribers = list(self._subscribers.get(channel, []))

        for queue in subscribers:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning(f"Event bus subscriber queue full on channel {channel}")
            except Exception as e:
                logger.warning(f"Event bus publish error on channel {channel}: {e}")

    async def subscribe(self, channel: str) -> AsyncIterator[Event]:
        """Subscribe to events on a channel. Yields events as they arrive."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        async with self._lock:
            self._subscribers[channel].append(queue)
        try:
            while True:
                event = await queue.get()
                yield event
        except asyncio.CancelledError:
            pass
        finally:
            async with self._lock:
                try:
                    self._subscribers[channel].remove(queue)
                except ValueError:
                    pass
                if not self._subscribers[channel]:
                    del self._subscribers[channel]

    async def unsubscribe_all(self, channel: str) -> None:
        """Remove all subscribers from a channel."""
        async with self._lock:
            self._subscribers.pop(channel, None)


# Module-level singleton
event_bus = EventBus()
