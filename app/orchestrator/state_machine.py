"""Task state machine - local in-process implementation.

This module provides the TaskStateMachine that manages task lifecycle states.
Previously backed by Redis+PostgreSQL, now uses a simple in-memory dictionary
for the desktop-native runtime (single-process).

NOTE: This orchestrator-level state machine is intentionally ephemeral. Task
state stored here does not survive process restarts. The persistent state
machine lives in app/desktop_native/state_machine.py (SQLite-backed) and is
used by the AgentKernel. Since all runtime execution flows through the
AgentKernel and desktop_native layer, crash recovery and persistence are
handled there. This in-memory implementation exists only to enforce valid
state transitions within a single process lifetime.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from ..logs.logger import logger
from .errors import AgentOSError, ErrorCode, ErrorType
from .types import (
    TaskState,
    StateTransition,
    VALID_TRANSITIONS,
    TERMINAL_STATES,
)

# Re-export for backward compatibility
__all__ = [
    "TaskStateMachine",
    "TaskState",
    "StateTransition",
    "AgentOSError",
    "ErrorCode",
]


class TaskStateMachine:
    """Explicit state machine for task lifecycle management.

    Defines valid transitions between task states and enforces them.
    Uses in-memory storage for the desktop-native single-process runtime.

    Usage:
        tsm = TaskStateMachine()
        await tsm.transition(task_id, TaskState.PENDING, TaskState.PLANNING)
        current = await tsm.get_current_state(task_id)
    """

    def __init__(self):
        self._states: Dict[str, TaskState] = {}
        self._history: Dict[str, List[StateTransition]] = {}

    async def transition(
        self,
        task_id: str,
        from_state: TaskState,
        to_state: TaskState,
        triggered_by: str = "system",
        context: Optional[Dict[str, Any]] = None,
    ) -> StateTransition:
        """Attempt a state transition.

        Raises AgentOSError if transition is invalid.
        """
        current = self._states.get(task_id)

        # If task has a recorded state, verify it matches from_state
        if current is not None and current != from_state:
            raise AgentOSError(
                message=f"State mismatch for task {task_id}: expected {from_state.value}, actual {current.value}",
                error_type=ErrorType.VALIDATION_ERROR,
                code=ErrorCode.VALIDATION_ERROR,
            )

        # Validate transition is allowed
        allowed = VALID_TRANSITIONS.get(from_state, set())
        if to_state not in allowed:
            raise AgentOSError(
                message=f"Invalid transition from {from_state.value} to {to_state.value} for task {task_id}",
                error_type=ErrorType.VALIDATION_ERROR,
                code=ErrorCode.VALIDATION_ERROR,
            )

        # Record transition
        now = datetime.now(timezone.utc)
        transition = StateTransition(
            task_id=task_id,
            from_state=from_state,
            to_state=to_state,
            timestamp=now,
            triggered_by=triggered_by,
            context=context or {},
            validation_errors=[],
        )

        self._states[task_id] = to_state
        if task_id not in self._history:
            self._history[task_id] = []
        self._history[task_id].append(transition)

        logger.debug(
            f"State transition: {task_id} {from_state.value} -> {to_state.value} "
            f"(triggered_by={triggered_by})"
        )
        return transition

    async def get_current_state(self, task_id: str) -> Optional[TaskState]:
        """Get the current state of a task."""
        return self._states.get(task_id)

    async def get_transition_history(
        self, task_id: str, limit: int = 50
    ) -> List[StateTransition]:
        """Get transition history for a task."""
        history = self._history.get(task_id, [])
        return history[:limit]

    async def can_transition(
        self, task_id: str, to_state: TaskState
    ) -> Tuple[bool, Optional[str]]:
        """Check if a transition is valid without performing it."""
        current = self._states.get(task_id)
        if current is None:
            return False, f"Task {task_id} has no recorded state"

        allowed = VALID_TRANSITIONS.get(current, set())
        if to_state in allowed:
            return True, None
        return False, f"Cannot transition from {current.value} to {to_state.value}"

    async def is_terminal(self, task_id: str) -> bool:
        """Check if a task is in a terminal state."""
        current = self._states.get(task_id)
        if current is None:
            return False
        return current in TERMINAL_STATES

    async def reset_state(
        self, task_id: str, to_state: TaskState = TaskState.PENDING
    ) -> None:
        """Force-reset a task's state. Used for replays and recovery."""
        self._states[task_id] = to_state
        logger.info(f"State reset: {task_id} -> {to_state.value}")
