import asyncio
import json
from typing import AsyncIterator, Dict, Any
from ...memory.short_term import redis_client
from ...logs.logger import logger

class Event:
    def __init__(self, event_type: str, payload: Dict[str, Any], source: str = ""):
        self.event_type = event_type
        self.payload = payload
        self.source = source
    
    def json(self) -> str:
        return json.dumps({"type": self.event_type, "payload": self.payload, "source": self.source})
    
    @classmethod
    def parse(cls, raw: str) -> "Event":
        data = json.loads(raw)
        return cls(data["type"], data.get("payload", {}), data.get("source", ""))

class RedisEventBus:
    async def publish(self, channel: str, event: Event):
        try:
            await redis_client.client.publish(f"agentos:{channel}", event.json())
        except Exception as e:
            logger.error(f"Event publish failed: {e}")
    
    async def subscribe(self, channel: str) -> AsyncIterator[Event]:
        try:
            pubsub = redis_client.client.pubsub()
            await pubsub.subscribe(f"agentos:{channel}")
            async for message in pubsub.listen():
                if message["type"] == "message":
                    try:
                        yield Event.parse(message["data"])
                    except Exception as e:
                        logger.warning(f"Failed to parse event: {e}")
        except Exception as e:
            logger.error(f"Event subscribe failed: {e}")
        finally:
            try:
                await pubsub.unsubscribe(f"agentos:{channel}")
            except:
                pass

event_bus = RedisEventBus()
