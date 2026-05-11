"""Task state machine with explicit state transitions.

Manages task lifecycle states and validates all transitions.
Integrates with PostgreSQL for persistence and Redis for fast state access.
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import uuid4

from pydantic import BaseModel, Field

from ..memory.short_term import redis_client
from ..memory.long_term import db
from ..logs.logger import logger
from .errors import AgentOSError, ErrorCode, ErrorType


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


class TaskStateMachine:
    """Explicit state machine for task lifecycle management.

    Defines valid transitions between task states and enforces them.
    Persists state history to PostgreSQL and caches current state in Redis.

    Usage:
        tsm = TaskStateMachine()
        await tsm.transition(task_id, TaskState.PENDING, TaskState.PLANNING)
        current = await tsm.get_current_state(task_id)
    """

    # Valid transitions: from_state -> set of allowed to_states
    VALID_TRANSITIONS: Dict[TaskState, Set[TaskState]] = {
        TaskState.PENDING: {TaskState.PLANNING, TaskState.FAILED},
        TaskState.PLANNING: {TaskState.EXECUTING, TaskState.FAILED},
        TaskState.EXECUTING: {TaskState.VERIFYING, TaskState.FAILED},
        TaskState.VERIFYING: {
            TaskState.AWAITING_APPROVAL,
            TaskState.COMPLETED,
            TaskState.EXECUTING,  # Replan / retry
            TaskState.FAILED,
        },
        TaskState.AWAITING_APPROVAL: {
            TaskState.COMPLETED,
            TaskState.REJECTED,
            TaskState.FAILED,
        },
        TaskState.COMPLETED: set(),  # Terminal
        TaskState.FAILED: set(),  # Terminal
        TaskState.REJECTED: set(),  # Terminal
    }

    def __init__(
        self,
        redis_prefix: str = "agentos:state:",
        history_ttl_days: int = 30,
    ):
        self.redis_prefix = redis_prefix
        self.history_ttl_days = history_ttl_days
        # In-memory fallback when Redis/DB unavailable (tests, edge cases)
        self._local_state: Dict[str, TaskState] = {}
        self._local_history: Dict[str, List[Dict[str, Any]]] = {}

    def _redis_key(self, task_id: str) -> str:
        return f"{self.redis_prefix}{task_id}"

    def _history_key(self, task_id: str) -> str:
        return f"{self.redis_prefix}history:{task_id}"

    async def get_current_state(self, task_id: str) -> TaskState:
        """Get the current state of a task.

        Args:
            task_id: The task identifier.

        Returns:
            Current TaskState (defaults to PENDING if not found).
        """
        redis_key = self._redis_key(task_id)
        try:
            data = await redis_client.get(redis_key)
            if data and "state" in data:
                return TaskState(data["state"])
        except Exception as e:
            logger.warning(f"Redis state read failed for {task_id}: {e}")

        # Fallback to DB via TaskModel
        try:
            async with db.get_session() as session:
                from sqlalchemy import select
                from .models import TaskModel
                result = await session.execute(
                    select(TaskModel).where(TaskModel.id == task_id)
                )
                row = result.scalar_one_or_none()
                if row and row.status:
                    # Map status string to TaskState
                    try:
                        return TaskState(row.status.lower())
                    except ValueError:
                        return TaskState.PENDING
        except Exception as e:
            logger.warning(f"DB state read failed for {task_id}: {e}")

        # Final fallback: in-memory local state
        if task_id in self._local_state:
            return self._local_state[task_id]

        return TaskState.PENDING

    async def transition(
        self,
        task_id: str,
        from_state: TaskState,
        to_state: TaskState,
        triggered_by: str = "system",
        context: Optional[Dict[str, Any]] = None,
    ) -> StateTransition:
        """Execute a state transition.

        Args:
            task_id: The task identifier.
            from_state: Expected current state.
            to_state: Target state.
            triggered_by: Component triggering the transition.
            context: Additional transition context.

        Returns:
            StateTransition record.

        Raises:
            AgentOSError: If transition is invalid or current state mismatch.
        """
        now = datetime.now(timezone.utc)
        validation_errors: List[str] = []

        # Validate transition
        allowed = self.VALID_TRANSITIONS.get(from_state, set())
        if to_state not in allowed:
            validation_errors.append(
                f"Invalid transition: {from_state.value} -> {to_state.value}"
            )

        # Check current state matches expected (if strict)
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

        # Update local state (always succeeds, shadows external stores)
        self._local_state[task_id] = to_state

        # Update Redis cache
        redis_key = self._redis_key(task_id)
        try:
            await redis_client.set(
                redis_key,
                {"state": to_state.value, "updated_at": now.isoformat()},
                expire=self.history_ttl_days * 86400,
            )
        except Exception as e:
            logger.warning(f"Redis state update failed for {task_id}: {e}")

        # Append to history
        await self._record_history(transition)

        # Update DB task status
        await self._update_task_status(task_id, to_state)

        logger.info(f"Task {task_id} transitioned: {from_state.value} -> {to_state.value}")
        return transition

    async def get_transition_history(self, task_id: str, limit: int = 50) -> List[StateTransition]:
        """Get transition history for a task.

        Args:
            task_id: The task identifier.
            limit: Maximum number of transitions.

        Returns:
            List of StateTransition records.
        """
        history_key = self._history_key(task_id)
        try:
            data = await redis_client.get(history_key)
            if data and "transitions" in data:
                transitions = [StateTransition(**t) for t in data["transitions"]]
                return transitions[-limit:]
        except Exception as e:
            logger.warning(f"Redis history read failed for {task_id}: {e}")

        # Fallback to DB
        try:
            async with db.get_session() as session:
                from sqlalchemy import select
                from .models import ContextModel
                result = await session.execute(
                    select(ContextModel).where(
                        ContextModel.task_id == f"state_history:{task_id}"
                    )
                )
                rows = result.scalars().all()
                transitions = []
                for row in rows:
                    if row.value and isinstance(row.value, dict):
                        try:
                            transitions.append(StateTransition(**row.value))
                        except Exception:
                            pass
                return transitions[-limit:]
        except Exception as e:
            logger.warning(f"DB history read failed for {task_id}: {e}")

        # Final fallback: local history
        if task_id in self._local_history:
            transitions = [StateTransition(**t) for t in self._local_history[task_id]]
            return transitions[-limit:]

        return []

    async def can_transition(
        self,
        task_id: str,
        to_state: TaskState,
    ) -> Tuple[bool, Optional[str]]:
        """Check if a transition is valid from current state.

        Args:
            task_id: The task identifier.
            to_state: Desired target state.

        Returns:
            (is_valid, reason_or_none)
        """
        current = await self.get_current_state(task_id)
        allowed = self.VALID_TRANSITIONS.get(current, set())
        if to_state in allowed:
            return True, None
        return False, f"Cannot transition from {current.value} to {to_state.value}"

    async def reset_state(self, task_id: str, new_state: TaskState = TaskState.PENDING) -> None:
        """Reset a task to a specific state (admin/recovery use).

        Args:
            task_id: The task identifier.
            new_state: State to reset to.
        """
        # Update local state
        self._local_state[task_id] = new_state

        redis_key = self._redis_key(task_id)
        try:
            await redis_client.set(
                redis_key,
                {"state": new_state.value, "updated_at": datetime.now(timezone.utc).isoformat()},
                expire=self.history_ttl_days * 86400,
            )
        except Exception as e:
            logger.warning(f"Redis state reset failed for {task_id}: {e}")

        await self._update_task_status(task_id, new_state)
        logger.info(f"Task {task_id} state reset to {new_state.value}")

    async def is_terminal(self, task_id: str) -> bool:
        """Check if a task is in a terminal state.

        Args:
            task_id: The task identifier.

        Returns:
            True if terminal (COMPLETED, FAILED, REJECTED).
        """
        current = await self.get_current_state(task_id)
        return current in {TaskState.COMPLETED, TaskState.FAILED, TaskState.REJECTED}

    async def _record_history(self, transition: StateTransition) -> None:
        """Append transition to Redis history."""
        # Update local history
        task_id = transition.task_id
        if task_id not in self._local_history:
            self._local_history[task_id] = []
        self._local_history[task_id].append(transition.model_dump(mode="json"))
        if len(self._local_history[task_id]) > 100:
            self._local_history[task_id] = self._local_history[task_id][-100:]

        history_key = self._history_key(transition.task_id)
        try:
            data = await redis_client.get(history_key) or {"transitions": []}
            data["transitions"].append(transition.model_dump(mode="json"))
            # Trim to last 100
            if len(data["transitions"]) > 100:
                data["transitions"] = data["transitions"][-100:]
            await redis_client.set(
                history_key,
                data,
                expire=self.history_ttl_days * 86400,
            )
        except Exception as e:
            logger.warning(f"Redis history append failed: {e}")

        # Also persist to DB for durability
        try:
            async with db.get_session() as session:
                from .models import ContextModel
                ctx = ContextModel(
                    task_id=f"state_history:{transition.task_id}",
                    key=f"transition:{transition.transition_id}",
                    value=transition.model_dump(mode="json"),
                )
                session.add(ctx)
                await session.commit()
        except Exception as e:
            logger.warning(f"DB history persist failed: {e}")

    async def _update_task_status(self, task_id: str, state: TaskState) -> None:
        """Update TaskModel status in PostgreSQL."""
        try:
            async with db.get_session() as session:
                from sqlalchemy import select
                from .models import TaskModel
                result = await session.execute(
                    select(TaskModel).where(TaskModel.id == task_id)
                )
                task = result.scalar_one_or_none()
                if task:
                    task.status = state.value
                    await session.commit()
        except Exception as e:
            logger.warning(f"DB task status update failed for {task_id}: {e}")


# Module-level singleton
task_state_machine = TaskStateMachine()
