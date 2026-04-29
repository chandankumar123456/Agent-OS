"""Action V1 data models."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum


class Capability(Enum):
    BROWSER = "browser"
    DESKTOP = "desktop"
    FILESYSTEM = "filesystem"
    MULTI_STEP = "multi_step"
    UNKNOWN = "unknown"


class ActionStatus(Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    NEEDS_HUMAN = "needs_human"
    NEEDS_VISION = "needs_vision"
    PARTIAL = "partial"


@dataclass
class ExecutionContext:
    task_id: str
    query: str
    capability: Capability
    config: Dict[str, Any] = field(default_factory=dict)
    tools_available: List[str] = field(default_factory=list)
    human_approved: bool = False
    max_retries: int = 2


@dataclass
class ActionResult:
    status: ActionStatus
    task_id: str
    output: Any = None
    error: Optional[str] = None
    verification_passed: bool = False
    steps_executed: List[Dict[str, Any]] = field(default_factory=list)
    fallback_used: Optional[str] = None

    def to_agent_output(self) -> Dict[str, Any]:
        from ..agents.base import AgentStatus
        return {
            "task_id": self.task_id,
            "status": AgentStatus.SUCCESS if self.status == ActionStatus.SUCCESS else AgentStatus.FAILURE,
            "output_data": {
                "result": self.output,
                "verified": self.verification_passed,
                "steps": self.steps_executed,
                "fallback_used": self.fallback_used,
            },
            "error_message": self.error,
        }
