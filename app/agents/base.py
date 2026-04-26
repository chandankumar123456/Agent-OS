from pydantic import BaseModel, Field
from uuid import UUID
from typing import Any, Optional, Dict, List, Protocol, runtime_checkable
from enum import Enum


class AgentRole(str, Enum):
    PLANNER = "planner"
    EXECUTOR = "executor"
    VERIFIER = "verifier"
    RESEARCHER = "researcher"


class AgentStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILURE = "failure"
    PAUSED = "paused"


class AgentInput(BaseModel):
    task_id: UUID
    step_id: UUID
    role: AgentRole
    input_data: Dict[str, Any] = Field(default_factory=dict)
    context: Dict[str, Any] = Field(default_factory=dict)
    constraints: Optional[Dict[str, Any]] = None
    allowed_tools: Optional[List[str]] = None
    fallback_tools: Optional[List[str]] = None


class AgentOutput(BaseModel):
    task_id: UUID
    step_id: UUID
    status: AgentStatus
    output_data: Dict[str, Any] = Field(default_factory=dict)
    confidence: float = 1.0
    reasoning_trace: Optional[List[str]] = None
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    recoverable: bool = True


@runtime_checkable
class BaseAgent(Protocol):
    name: str
    role: AgentRole
    
    async def execute(self, input_data: AgentInput) -> AgentOutput:
        ...