import asyncio
import json
from typing import AsyncIterator, Dict, Any, Optional
from datetime import datetime, timezone

from ..logs.logger import logger
from ..config.settings import settings


def _is_desktop_mode() -> bool:
    """Check if running in desktop-native gRPC mode."""
    mode = settings.RUNTIME_MODE or "http"
    return mode.lower() == "grpc"


class Event:
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


class RedisEventBus:
    """Reliable event bus backed by a dedicated Redis pub/sub connection pool."""

    async def publish(self, channel: str, event: Event) -> None:
        try:
            from ..memory.redis_pubsub import redis_pubsub_client
            await redis_pubsub_client.publish(f"agentos:{channel}", event.json())
        except Exception as e:
            logger.error(f"Event publish failed: {e}")

    async def subscribe(self, channel: str) -> AsyncIterator[Event]:
        """Yield events from a channel.  Propagates CancelledError and unexpected exceptions
        so that callers can decide whether to reconnect.
        """
        try:
            from ..memory.redis_pubsub import redis_pubsub_client
            async for raw in redis_pubsub_client.subscribe(f"agentos:{channel}"):
                try:
                    yield Event.parse(raw)
                except Exception as e:
                    logger.warning(f"Failed to parse event: {e}")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Event subscribe failed: {e}")
            raise


def get_event_bus():
    """Get the appropriate event bus for the current runtime mode."""
    if _is_desktop_mode():
        from ..desktop_native.event_bus import local_event_bus
        return local_event_bus
    return RedisEventBus()


event_bus = get_event_bus()
