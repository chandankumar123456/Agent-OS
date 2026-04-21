from pydantic import BaseModel, Field
from uuid import UUID, uuid4
from datetime import datetime
from typing import Any, Optional, Dict


class Payload(BaseModel):
    input_data: Any = None
    output_data: Any = None
    context_snapshot: Optional[Dict[str, Any]] = None


class Metadata(BaseModel):
    status: str = "pending"
    priority: int = 0
    retry_count: int = 0
    execution_time: Optional[float] = None


class MCPMessage(BaseModel):
    message_id: UUID = Field(default_factory=uuid4)
    task_id: UUID
    step_id: Optional[UUID] = None
    sender_agent: str = "system"
    receiver_agent: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    payload: Payload = Field(default_factory=Payload)
    metadata: Metadata = Field(default_factory=Metadata)
    
    class Config:
        json_schema_extra = {
            "example": {
                "message_id": "a1b2c3d4-...",
                "task_id": "e5f6g7h8-...",
                "step_id": "i9j0k1l2-...",
                "sender_agent": "orchestrator",
                "receiver_agent": "planner",
                "timestamp": "2026-04-20T10:00:00Z",
                "payload": {
                    "input_data": {"query": "find cheapest milk"},
                    "context_snapshot": {}
                },
                "metadata": {
                    "status": "pending",
                    "priority": 0,
                    "retry_count": 0
                }
            }
        }