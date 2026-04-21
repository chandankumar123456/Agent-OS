from typing import Dict, Any, Optional, List, Callable
from uuid import UUID, uuid4
from datetime import datetime
from .message import MCPMessage, Payload, Metadata
from ..logs.logger import logger


class MCPProtocol:
    def __init__(self):
        self.message_log: List[MCPMessage] = []
        self.routers: Dict[str, Callable] = {}
    
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
        
        self.message_log.append(message)
        logger.info(
            f"MCP message {message.message_id}: {sender} -> {receiver} "
            f"(task: {task_id}, step: {message.step_id})"
        )
        
        return message
    
    def route_message(self, message: MCPMessage) -> Any:
        receiver = message.receiver_agent
        
        if receiver in self.routers:
            handler = self.routers[receiver]
            return handler(message)
        
        logger.warning(f"No handler for agent: {receiver}")
        return None
    
    def register_router(self, agent_name: str, handler: Callable):
        self.routers[agent_name] = handler
        logger.info(f"Registered router for: {agent_name}")
    
    def get_message_history(self, task_id: UUID) -> List[MCPMessage]:
        return [m for m in self.message_log if m.task_id == task_id]
    
    def clear_history(self, task_id: Optional[UUID] = None):
        if task_id:
            self.message_log = [
                m for m in self.message_log if m.task_id != task_id
            ]
        else:
            self.message_log.clear()
        
        logger.info(f"Cleared MCP message history")


mcp_protocol = MCPProtocol()