"""Orchestrator type definitions.

Lightweight Pydantic models and enums that were previously defined in the
Redis-backed orchestrator modules (queue.py, locks.py, state_machine.py,
event_bus.py). Extracted so in-memory and desktop-native backends can
import them without pulling in Redis dependencies.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from uuid import uuid4


# ---------------------------------------------------------------------------
# From orchestrator.locks
# ---------------------------------------------------------------------------

class LockRecord(BaseModel):
    """Record of a distributed lock acquisition."""
    lock_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str
    owner: str = Field(default="system")
    acquired_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    ttl_seconds: int = 300


# ---------------------------------------------------------------------------
# From orchestrator.queue
# ---------------------------------------------------------------------------

class TaskPriority(int, Enum):
    """Priority levels for task queue. Lower value = higher priority."""
    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3


class QueuePosition(BaseModel):
    """Position of a task in the queue."""
    task_id: str
    position: int
    estimated_wait_seconds: float
    assigned_worker: Optional[str] = None
    queue_length: int


class QueuedTask(BaseModel):
    """Task metadata stored in the queue."""
    task_id: str
    user_id: str
    query: str
    priority: TaskPriority
    config: Dict[str, Any] = Field(default_factory=dict)
    idempotency_key: Optional[str] = None
    enqueued_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    scheduled_for: Optional[datetime] = None
    worker_id: Optional[str] = None
    status: str = "queued"
    retry_count: int = 0


# ---------------------------------------------------------------------------
# From orchestrator.state_machine
# ---------------------------------------------------------------------------

class TaskState(str, Enum):
    PENDING = "pending"
    PLANNING = "planning"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED = "rejected"


# Terminal states - no valid transitions out of these
TERMINAL_STATES = {TaskState.COMPLETED, TaskState.FAILED, TaskState.REJECTED}

# Valid transitions: from_state -> set of allowed to_states
VALID_TRANSITIONS: Dict[TaskState, set] = {
    TaskState.PENDING: {TaskState.PLANNING, TaskState.FAILED},
    TaskState.PLANNING: {TaskState.EXECUTING, TaskState.FAILED},
    TaskState.EXECUTING: {TaskState.VERIFYING, TaskState.FAILED},
    TaskState.VERIFYING: {TaskState.COMPLETED, TaskState.AWAITING_APPROVAL, TaskState.EXECUTING, TaskState.FAILED},
    TaskState.AWAITING_APPROVAL: {TaskState.COMPLETED, TaskState.REJECTED, TaskState.FAILED},
    TaskState.COMPLETED: set(),
    TaskState.FAILED: set(),
    TaskState.REJECTED: set(),
}


class StateTransition(BaseModel):
    """Record of a state transition."""
    transition_id: str = Field(default_factory=lambda: str(uuid4()))
    task_id: str
    from_state: TaskState
    to_state: TaskState
    timestamp: Optional[datetime] = None
    triggered_by: str = Field(default="system", description="Component that triggered transition")
    context: Dict[str, Any] = Field(default_factory=dict)
    validation_errors: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# From orchestrator.event_bus
# ---------------------------------------------------------------------------

class Event(BaseModel):
    """Event published on the event bus."""
    event_type: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    source: str = "agentos"
    timestamp: Optional[str] = None
