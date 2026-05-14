"""Local task state machine for desktop-native mode.

Replaces Redis cache + PostgreSQL with SQLite as the single source of truth.
All state transitions are persisted to SQLite for durability.
"""

import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import uuid4

from pydantic import BaseModel, Field

from ..logs.logger import logger
from .sqlite_store import sqlite_store


class TaskState(str, Enum):
    PENDING = "pending"
    PLANNING = "planning"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED = "rejected"


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


class LocalTaskStateMachine:
    """SQLite-backed task state machine for desktop-native mode.

    All state reads and writes go through SQLite. No Redis, no PostgreSQL.
    """

    VALID_TRANSITIONS: Dict[TaskState, Set[TaskState]] = {
        TaskState.PENDING: {TaskState.PLANNING, TaskState.FAILED},
        TaskState.PLANNING: {TaskState.EXECUTING, TaskState.FAILED},
        TaskState.EXECUTING: {TaskState.VERIFYING, TaskState.FAILED},
        TaskState.VERIFYING: {
            TaskState.AWAITING_APPROVAL,
            TaskState.COMPLETED,
            TaskState.EXECUTING,
            TaskState.FAILED,
        },
        TaskState.AWAITING_APPROVAL: {
            TaskState.COMPLETED,
            TaskState.REJECTED,
            TaskState.FAILED,
        },
        TaskState.COMPLETED: set(),
        TaskState.FAILED: set(),
        TaskState.REJECTED: set(),
    }

    def __init__(
        self,
        history_ttl_days: int = 30,
    ):
        self.history_ttl_days = history_ttl_days

    async def get_current_state(self, task_id: str) -> TaskState:
        """Get the current state of a task from SQLite."""
        try:
            row = await sqlite_store.fetchone(
                "SELECT state FROM task_state WHERE task_id = ?",
                (task_id,),
            )
            if row and row["state"]:
                return TaskState(row["state"])
        except Exception as e:
            logger.warning(f"SQLite state read failed for {task_id}: {e}")
        return TaskState.PENDING

    async def transition(
        self,
        task_id: str,
        from_state: TaskState,
        to_state: TaskState,
        triggered_by: str = "system",
        context: Optional[Dict[str, Any]] = None,
    ) -> StateTransition:
        """Execute a state transition and persist to SQLite."""
        now = datetime.now(timezone.utc)
        validation_errors: List[str] = []

        # Validate transition
        allowed = self.VALID_TRANSITIONS.get(from_state, set())
        if to_state not in allowed:
            validation_errors.append(
                f"Invalid transition: {from_state.value} -> {to_state.value}"
            )

        # Check current state matches expected
        current = await self.get_current_state(task_id)
        if current != from_state:
            validation_errors.append(
                f"State mismatch: expected {from_state.value}, got {current.value}"
            )

        transition = StateTransition(
            task_id=task_id,
            from_state=from_state,
            to_state=to_state,
            timestamp=now,
            triggered_by=triggered_by,
            context=context or {},
            validation_errors=validation_errors,
        )

        if validation_errors:
            from ..orchestrator.errors import AgentOSError, ErrorCode, ErrorType
            logger.warning(f"State transition rejected for {task_id}: {validation_errors}")
            raise AgentOSError(
                message=f"State transition rejected: {'; '.join(validation_errors)}",
                error_type=ErrorType.VALIDATION_ERROR,
                recoverable=False,
                code=ErrorCode.VALIDATION_ERROR,
                context={
                    "task_id": task_id,
                    "from_state": from_state.value,
                    "to_state": to_state.value,
                    "errors": validation_errors,
                },
                http_status=409,
            )

        # Persist new state
        try:
            await sqlite_store.execute(
                """
                INSERT OR REPLACE INTO task_state (task_id, state, updated_at)
                VALUES (?, ?, ?)
                """,
                (task_id, to_state.value, now.isoformat()),
            )
        except Exception as e:
            logger.error(f"Failed to persist task state for {task_id}: {e}")

        # Record transition history
        await self._record_history(transition)

        logger.info(f"Task {task_id} transitioned: {from_state.value} -> {to_state.value}")
        return transition

    async def get_transition_history(self, task_id: str, limit: int = 50) -> List[StateTransition]:
        """Get transition history for a task."""
        try:
            rows = await sqlite_store.fetchall(
                """
                SELECT * FROM state_transitions
                WHERE task_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (task_id, limit),
            )
            transitions = []
            for row in rows:
                transitions.append(StateTransition(
                    transition_id=row["transition_id"],
                    task_id=row["task_id"],
                    from_state=TaskState(row["from_state"]),
                    to_state=TaskState(row["to_state"]),
                    timestamp=datetime.fromisoformat(row["timestamp"]),
                    triggered_by=row["triggered_by"],
                    context=json.loads(row["context"]),
                    validation_errors=json.loads(row["validation_errors"]),
                ))
            return list(reversed(transitions))
        except Exception as e:
            logger.warning(f"Failed to get transition history for {task_id}: {e}")
            return []

    async def can_transition(
        self,
        task_id: str,
        to_state: TaskState,
    ) -> Tuple[bool, Optional[str]]:
        """Check if a transition is valid from current state."""
        current = await self.get_current_state(task_id)
        allowed = self.VALID_TRANSITIONS.get(current, set())
        if to_state in allowed:
            return True, None
        return False, f"Cannot transition from {current.value} to {to_state.value}"

    async def reset_state(self, task_id: str, new_state: TaskState = TaskState.PENDING) -> None:
        """Reset a task to a specific state."""
        now = datetime.now(timezone.utc)
        try:
            await sqlite_store.execute(
                """
                INSERT OR REPLACE INTO task_state (task_id, state, updated_at)
                VALUES (?, ?, ?)
                """,
                (task_id, new_state.value, now.isoformat()),
            )
            await sqlite_store.commit()
            logger.info(f"Task {task_id} state reset to {new_state.value}")
        except Exception as e:
            logger.error(f"Failed to reset state for {task_id}: {e}")

    async def is_terminal(self, task_id: str) -> bool:
        """Check if a task is in a terminal state."""
        current = await self.get_current_state(task_id)
        return current in {TaskState.COMPLETED, TaskState.FAILED, TaskState.REJECTED}

    async def _record_history(self, transition: StateTransition) -> None:
        """Append transition to SQLite history."""
        try:
            await sqlite_store.execute(
                """
                INSERT INTO state_transitions
                (transition_id, task_id, from_state, to_state, timestamp,
                 triggered_by, context, validation_errors)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (transition.transition_id, transition.task_id,
                 transition.from_state.value, transition.to_state.value,
                 transition.timestamp.isoformat() if transition.timestamp else datetime.now(timezone.utc).isoformat(),
                 transition.triggered_by,
                 json.dumps(transition.context, default=str),
                 json.dumps(transition.validation_errors)),
            )
            await sqlite_store.commit()
        except Exception as e:
            logger.warning(f"Failed to record transition history: {e}")

    async def cleanup_old_history(self, max_age_days: int = None) -> int:
        """Remove old transition history."""
        max_age = max_age_days or self.history_ttl_days
        try:
            cursor = await sqlite_store.execute(
                """
                DELETE FROM state_transitions
                WHERE timestamp < datetime('now', '-' || ? || ' days')
                """,
                (max_age,),
            )
            await sqlite_store.commit()
            return cursor.rowcount
        except Exception as e:
            logger.error(f"Failed to cleanup old history: {e}")
            return 0


# Module-level singleton
local_task_state_machine = LocalTaskStateMachine()
