from typing import Dict, Any, Optional, List, Callable
from uuid import UUID, uuid4
from .message import MCPMessage, Payload, Metadata
from .bus import MCPBus, MemoryMCPBus
from .router import MessageRouter
from ..logs.logger import logger


class MCPProtocol:
    def __init__(self, bus: MCPBus = None):
        self.bus = bus or MemoryMCPBus()
        self.router = MessageRouter(self.bus)
        self.message_log: List[MCPMessage] = []
        self._max_log_size = 10000

    def create_message(
        self,
        task_id: UUID,
        sender: str,
        receiver: str,
        payload: Dict[str, Any],
        step_id: Optional[UUID] = None
    ) -> MCPMessage:
        message = MCPMessage(
            message_id=uuid4(),
            task_id=task_id,
            step_id=step_id or uuid4(),
            sender_agent=sender,
            receiver_agent=receiver,
            payload=Payload(
                input_data=payload.get("input_data"),
                output_data=payload.get("output_data"),
                context_snapshot=payload.get("context_snapshot")
            ),
            metadata=Metadata(
                status="sent",
                priority=payload.get("priority", 0),
                retry_count=0
            )
        )

        self._append_to_log(message)
        logger.info(
            f"MCP message {message.message_id}: {sender} -> {receiver} "
            f"(task: {task_id}, step: {message.step_id})"
        )

        return message

    async def send_message(self, message: MCPMessage) -> Any:
        """Send a message via the router to the receiver agent and persist it."""
        receiver = message.receiver_agent
        await self.router.route(receiver, message)
        await self._persist_message(message)
        return None

    async def _persist_message(self, message: MCPMessage) -> None:
        """Persist MCP message to the database for audit."""
        try:
            from ..memory.long_term import message_repo
            await message_repo.create(
                task_id=str(message.task_id),
                step_id=str(message.step_id) if message.step_id else None,
                sender=message.sender_agent,
                receiver=message.receiver_agent,
                payload={
                    "input_data": message.payload.input_data if message.payload else None,
                    "output_data": message.payload.output_data if message.payload else None,
                    "context_snapshot": message.payload.context_snapshot if message.payload else None,
                    "metadata": {
                        "status": message.metadata.status if message.metadata else None,
                        "priority": message.metadata.priority if message.metadata else None,
                        "retry_count": message.metadata.retry_count if message.metadata else None,
                    },
                },
            )
        except Exception as e:
            logger.warning(f"Failed to persist MCP message to DB: {e}")

    def register_router(self, agent_name: str, handler: Callable):
        """Register a handler for an agent. Async wrapper for router.register."""
        import asyncio
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        asyncio.create_task(self.router.register(agent_name, handler))

    def get_message_history(self, task_id: UUID) -> List[MCPMessage]:
        return [m for m in self.message_log if m.task_id == task_id]

    def clear_history(self, task_id: Optional[UUID] = None):
        if task_id:
            self.message_log = [
                m for m in self.message_log if m.task_id != task_id
            ]
        else:
            self.message_log.clear()
        logger.info("Cleared MCP message history")

    def _append_to_log(self, message: MCPMessage):
        self.message_log.append(message)
        if len(self.message_log) > self._max_log_size:
            self.message_log.pop(0)


mcp_protocol = MCPProtocol()
