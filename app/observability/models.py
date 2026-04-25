"""Structured observability event models for AgentOS."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class ObservabilityEventType(str, Enum):
    TASK_RECEIVED = "task.received"
    PLANNER_REASONING = "planner.reasoning"
    CAPABILITY_SELECTED = "capability.selected"
    ENVIRONMENT_SELECTED = "environment.selected"
    STEP_STARTED = "step.started"
    TOOL_INVOKED = "tool.invoked"
    TOOL_RESULT = "tool.result"
    RETRY_INITIATED = "retry.initiated"
    RECOVERY_ACTION = "recovery.action"
    VERIFICATION_COMPLETED = "verification.completed"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    SAFETY_CHECK = "safety.check"
    FALLBACK_TRIGGERED = "fallback.triggered"


class ObservabilityEvent(BaseModel):
    """A single structured observability event."""

    event_type: ObservabilityEventType
    task_id: str
    trace_id: Optional[str] = None
    step_id: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    source: str = "agentos"
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    def to_event_bus_payload(self) -> Dict[str, Any]:
        """Convert to the plain dict format expected by the legacy event bus."""
        return {
            "type": self.event_type.value,
            "payload": self.payload,
            "source": self.source,
            "timestamp": self.timestamp.isoformat(),
            "task_id": self.task_id,
            "trace_id": self.trace_id,
            "step_id": self.step_id,
        }
