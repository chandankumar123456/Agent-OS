from abc import ABC, abstractmethod
from typing import Callable, Dict, Any, List
from ..logs.logger import logger
from .message import MCPMessage


class MCPBus(ABC):
    """Abstract message bus for inter-agent communication."""

    @abstractmethod
    async def publish(self, channel: str, message: MCPMessage) -> None:
        """Publish a message to a channel."""
        pass

    @abstractmethod
    async def subscribe(self, channel: str, handler: Callable[[MCPMessage], Any]) -> None:
        """Subscribe to a channel with a handler."""
        pass

    @abstractmethod
    async def unsubscribe(self, channel: str, handler: Callable[[MCPMessage], Any]) -> None:
        """Unsubscribe a handler from a channel."""
        pass


class MemoryMCPBus(MCPBus):
    """In-memory message bus for local development and testing."""

    def __init__(self):
        self._handlers: Dict[str, List[Callable]] = {}
        self._history: List[MCPMessage] = []
        self._max_history = 10000

    async def publish(self, channel: str, message: MCPMessage) -> None:
        self._history.append(message)
        if len(self._history) > self._max_history:
            self._history.pop(0)

        handlers = self._handlers.get(channel, [])
        for handler in handlers:
            try:
                await handler(message)
            except Exception as e:
                logger.error(f"MemoryMCPBus handler error on {channel}: {e}")

    async def subscribe(self, channel: str, handler: Callable[[MCPMessage], Any]) -> None:
        if channel not in self._handlers:
            self._handlers[channel] = []
        self._handlers[channel].append(handler)

    async def unsubscribe(self, channel: str, handler: Callable[[MCPMessage], Any]) -> None:
        if channel in self._handlers:
            self._handlers[channel] = [h for h in self._handlers[channel] if h != handler]


class RedisMCPBus(MCPBus):
    """Redis-backed message bus for production."""

    def __init__(self, redis_client):
        self._redis = redis_client
        self._handlers: Dict[str, List[Callable]] = {}

    async def publish(self, channel: str, message: MCPMessage) -> None:
        payload = message.model_dump_json() if hasattr(message, 'model_dump_json') else str(message)
        await self._redis.publish(channel, payload)

    async def subscribe(self, channel: str, handler: Callable[[MCPMessage], Any]) -> None:
        if channel not in self._handlers:
            self._handlers[channel] = []
        self._handlers[channel].append(handler)
        # Note: In production, a background listener task would be needed
        # to consume Redis pub/sub messages and dispatch to handlers.

    async def unsubscribe(self, channel: str, handler: Callable[[MCPMessage], Any]) -> None:
        if channel in self._handlers:
            self._handlers[channel] = [h for h in self._handlers[channel] if h != handler]
