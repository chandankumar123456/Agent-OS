from typing import Dict, Any, Callable
from ..logs.logger import logger
from .bus import MCPBus, MemoryMCPBus
from .message import MCPMessage


class MessageRouter:
    """Routes MCP messages to the correct agent worker inbox."""

    def __init__(self, bus: MCPBus = None):
        self.bus = bus or MemoryMCPBus()
        self._registrations: Dict[str, Callable] = {}

    async def register(self, agent_name: str, handler: Callable[[MCPMessage], Any]):
        """Register an agent to receive messages."""
        if agent_name in self._registrations:
            logger.warning(f"MessageRouter: {agent_name} already registered, overwriting")
        self._registrations[agent_name] = handler
        channel = f"agent:{agent_name}"
        await self.bus.subscribe(channel, handler)
        logger.info(f"MessageRouter: registered {agent_name} on {channel}")

    async def unregister(self, agent_name: str):
        """Unregister an agent."""
        if agent_name in self._registrations:
            handler = self._registrations.pop(agent_name)
            channel = f"agent:{agent_name}"
            await self.bus.unsubscribe(channel, handler)
            logger.info(f"MessageRouter: unregistered {agent_name}")

    async def route(self, receiver: str, message: MCPMessage):
        """Route a message to a specific agent."""
        channel = f"agent:{receiver}"
        await self.bus.publish(channel, message)
        logger.info(f"MessageRouter: routed message to {receiver}")
