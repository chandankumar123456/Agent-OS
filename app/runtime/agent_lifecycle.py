"""Phase 3.5 — AgentLifecycle: State machine management for agent lifecycle transitions.

Implements the agent lifecycle state machine with validation for state transitions,
persistence to database, and hooks for monitoring state changes.

Spec: Build Plan Task 3.2.5, Section 6.5
Input Contract: transition(agent_id, from_state, to_state, context) → bool
Output Contract: State transition validated, persisted, and hooks invoked
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Callable, Set
from dataclasses import dataclass, field
import asyncio

from pydantic import BaseModel, Field

from ..logs.logger import logger
from ..memory.long_term import agent_repo
from ..orchestrator.errors import AgentOSError, ErrorCode, ErrorType


# ── Enums ────────────────────────────────────────────────────────────────────

class AgentState(str, Enum):
    """Agent lifecycle states.

    States follow the progression:
    CREATED → REGISTERED → ACTIVE → (EXECUTING ↔ IDLE) → DECOMMISSIONED

    State Descriptions:
    - CREATED: Agent config created but not yet registered with runtime
    - REGISTERED: Agent registered with AgentRuntime, ready for tasks
    - ACTIVE: Agent has been assigned to at least one task
    - EXECUTING: Agent is currently executing a task
    - IDLE: Agent is registered but not currently executing
    - DECOMMISSIONED: Agent has been removed from service
    """

    CREATED = "created"
    REGISTERED = "registered"
    ACTIVE = "active"
    EXECUTING = "executing"
    IDLE = "idle"
    DECOMMISSIONED = "decommissioned"


class StateTransitionResult(str, Enum):
    """Result of a state transition attempt."""

    SUCCESS = "success"
    INVALID_TRANSITION = "invalid_transition"
    AGENT_NOT_FOUND = "agent_not_found"
    VALIDATION_FAILED = "validation_failed"
    PERSISTENCE_FAILED = "persistence_failed"


# ── Pydantic Models ──────────────────────────────────────────────────────────

class StateTransitionEvent(BaseModel):
    """Event representing a state transition."""

    agent_id: str
    from_state: AgentState
    to_state: AgentState
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    triggered_by: str = Field(default="system")  # Component that triggered
    reason: Optional[str] = Field(default=None)  # Human-readable reason
    context: Dict[str, Any] = Field(default_factory=dict)  # Additional context


class StateTransitionRecord(BaseModel):
    """Database record for state transitions (for audit trail)."""

    transition_id: str
    agent_id: str
    from_state: str
    to_state: str
    timestamp: str
    triggered_by: str
    reason: Optional[str]
    context: Dict[str, Any]


class AgentLifecycleInfo(BaseModel):
    """Current lifecycle information for an agent."""

    agent_id: str
    current_state: AgentState
    previous_state: Optional[AgentState]
    state_history: List[StateTransitionEvent] = Field(default_factory=list)
    created_at: str
    last_transition_at: Optional[str] = None
    task_count: int = 0
    decommissioned_at: Optional[str] = None
    decommission_reason: Optional[str] = None


# ── AgentLifecycleManager ───────────────────────────────────────────────────

class AgentLifecycleManager:
    """Manages agent lifecycle state transitions with validation and hooks.

    Implements a finite state machine for agent lifecycle with:
    - Valid state transition rules
    - Pre/post-transition hooks
    - Persistence to database
    - Audit trail of all transitions

    Lifecycle Flow:
    ┌─────────┐    ┌──────────┐    ┌────────┐    ┌───────────┐
    │ CREATED │───▶│REGISTERED│───▶│ ACTIVE │───▶│EXECUTING  │
    └─────────┘    └──────────┘    └────────┘    └─────┬─────┘
                                                       │
                                                       ▼
                                              ┌───────────┐
                                              │   IDLE    │
                                              └─────┬─────┘
                                                    │
                               ┌────────────────────┘
                               ▼
                        ┌──────────────┐
                        │DECOMMISSIONED│
                        └──────────────┘

    Valid Transitions:
    - CREATED → REGISTERED: Agent registered with runtime
    - REGISTERED → ACTIVE: Agent assigned first task
    - REGISTERED → IDLE: Agent ready but no tasks yet
    - ACTIVE → EXECUTING: Task execution started
    - ACTIVE → IDLE: Between tasks
    - EXECUTING → IDLE: Task completed/failed
    - IDLE → EXECUTING: New task started
    - IDLE → ACTIVE: Implicitly active when assigned task
    - Any → DECOMMISSIONED: Agent removal (terminal state)
    """

    # Define valid state transitions
    _VALID_TRANSITIONS: Dict[AgentState, Set[AgentState]] = {
        AgentState.CREATED: {AgentState.REGISTERED, AgentState.DECOMMISSIONED},
        AgentState.REGISTERED: {
            AgentState.ACTIVE,
            AgentState.IDLE,
            AgentState.DECOMMISSIONED,
        },
        AgentState.ACTIVE: {
            AgentState.EXECUTING,
            AgentState.IDLE,
            AgentState.DECOMMISSIONED,
        },
        AgentState.EXECUTING: {
            AgentState.IDLE,
            AgentState.ACTIVE,
            AgentState.DECOMMISSIONED,
        },
        AgentState.IDLE: {
            AgentState.EXECUTING,
            AgentState.ACTIVE,
            AgentState.DECOMMISSIONED,
        },
        AgentState.DECOMMISSIONED: set(),  # Terminal state - no outgoing transitions
    }

    def __init__(self):
        self._agent_states: Dict[str, AgentLifecycleInfo] = {}
        self._transition_hooks: Dict[
            AgentState, List[Callable[[StateTransitionEvent], None]]
        ] = {state: [] for state in AgentState}
        self._global_hooks: List[Callable[[StateTransitionEvent], None]] = []
        self._pre_transition_hooks: List[Callable[[StateTransitionEvent], bool]] = []
        self._lock = asyncio.Lock()
        self._transition_count: int = 0

    # ── Hook Registration ────────────────────────────────────────────────────

    def register_post_transition_hook(
        self,
        callback: Callable[[StateTransitionEvent], None],
        state: Optional[AgentState] = None,
    ) -> None:
        """Register a hook to be called after state transitions.

        Args:
            callback: Function to call with the transition event
            state: If specified, only call for transitions TO this state
        """
        if state:
            self._transition_hooks[state].append(callback)
        else:
            self._global_hooks.append(callback)

    def register_pre_transition_hook(
        self, callback: Callable[[StateTransitionEvent], bool]
    ) -> None:
        """Register a hook to be called before state transitions.

        Args:
            callback: Function that returns False to block the transition
        """
        self._pre_transition_hooks.append(callback)

    def unregister_hook(
        self,
        callback: Callable,
        state: Optional[AgentState] = None,
    ) -> bool:
        """Unregister a previously registered hook.

        Args:
            callback: The callback function to remove
            state: The state-specific hook list, or None for global

        Returns:
            True if hook was found and removed
        """
        if state:
            if callback in self._transition_hooks[state]:
                self._transition_hooks[state].remove(callback)
                return True
        if callback in self._global_hooks:
            self._global_hooks.remove(callback)
            return True
        return False

    # ── State Management ─────────────────────────────────────────────────────

    async def initialize_agent(
        self, agent_id: str, initial_state: AgentState = AgentState.CREATED
    ) -> AgentLifecycleInfo:
        """Initialize lifecycle tracking for a new agent.

        Args:
            agent_id: The unique agent identifier
            initial_state: Starting state (default: CREATED)

        Returns:
            AgentLifecycleInfo for the initialized agent
        """
        async with self._lock:
            now = datetime.now(timezone.utc).isoformat()
            info = AgentLifecycleInfo(
                agent_id=agent_id,
                current_state=initial_state,
                previous_state=None,
                state_history=[],
                created_at=now,
                last_transition_at=None,
            )
            self._agent_states[agent_id] = info

            logger.info(f"AgentLifecycle: Initialized agent '{agent_id}' in state {initial_state.value}")
            return info

    async def transition(
        self,
        agent_id: str,
        to_state: AgentState,
        triggered_by: str = "system",
        reason: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> StateTransitionResult:
        """Attempt to transition an agent to a new state.

        Args:
            agent_id: The agent to transition
            to_state: The target state
            triggered_by: Component triggering the transition
            reason: Human-readable reason for transition
            context: Additional context data

        Returns:
            StateTransitionResult indicating success or failure reason
        """
        async with self._lock:
            # Check agent exists
            if agent_id not in self._agent_states:
                logger.error(f"AgentLifecycle: Agent '{agent_id}' not found for transition")
                return StateTransitionResult.AGENT_NOT_FOUND

            info = self._agent_states[agent_id]
            from_state = info.current_state

            # Validate transition
            if not self._is_valid_transition(from_state, to_state):
                logger.warning(
                    f"AgentLifecycle: Invalid transition {from_state.value} → {to_state.value} "
                    f"for agent '{agent_id}'"
                )
                return StateTransitionResult.INVALID_TRANSITION

            # Create transition event
            event = StateTransitionEvent(
                agent_id=agent_id,
                from_state=from_state,
                to_state=to_state,
                triggered_by=triggered_by,
                reason=reason,
                context=context or {},
            )

            # Run pre-transition hooks
            for hook in self._pre_transition_hooks:
                try:
                    if not hook(event):
                        logger.warning(
                            f"AgentLifecycle: Pre-transition hook blocked {from_state.value} → "
                            f"{to_state.value} for agent '{agent_id}'"
                        )
                        return StateTransitionResult.VALIDATION_FAILED
                except Exception as e:
                    logger.error(f"AgentLifecycle: Pre-transition hook failed: {e}")
                    return StateTransitionResult.VALIDATION_FAILED

            # Execute transition
            info.previous_state = from_state
            info.current_state = to_state
            info.state_history.append(event)
            info.last_transition_at = event.timestamp
            self._transition_count += 1

            # Persist to database
            try:
                await self._persist_transition(event)
            except Exception as e:
                logger.error(f"AgentLifecycle: Failed to persist transition: {e}")
                # Revert state on persistence failure
                info.current_state = from_state
                info.previous_state = None
                info.state_history.pop()
                return StateTransitionResult.PERSISTENCE_FAILED

            logger.info(
                f"AgentLifecycle: Agent '{agent_id}' transitioned {from_state.value} → "
                f"{to_state.value} (triggered by {triggered_by})"
            )

            # Run post-transition hooks
            await self._run_post_hooks(event)

            return StateTransitionResult.SUCCESS

    def _is_valid_transition(self, from_state: AgentState, to_state: AgentState) -> bool:
        """Check if a state transition is valid."""
        if from_state == to_state:
            return True  # Same-state transitions are allowed (no-op)
        valid_targets = self._VALID_TRANSITIONS.get(from_state, set())
        return to_state in valid_targets

    async def _persist_transition(self, event: StateTransitionEvent) -> None:
        """Persist state transition to database."""
        try:
            from ..memory.models import AgentStateTransitionModel
            from ..memory.connection import async_session

            async with async_session() as session:
                record = AgentStateTransitionModel(
                    agent_id=event.agent_id,
                    from_state=event.from_state.value,
                    to_state=event.to_state.value,
                    triggered_by=event.triggered_by,
                    reason=event.reason,
                    context=event.context,
                )
                session.add(record)
                await session.commit()
        except Exception as e:
            logger.error(f"AgentLifecycle: Database persistence failed: {e}")
            raise

    async def _run_post_hooks(self, event: StateTransitionEvent) -> None:
        """Run post-transition hooks."""
        # Run global hooks
        for hook in self._global_hooks:
            try:
                hook(event)
            except Exception as e:
                logger.error(f"AgentLifecycle: Post-transition hook error: {e}")

        # Run state-specific hooks
        for hook in self._transition_hooks[event.to_state]:
            try:
                hook(event)
            except Exception as e:
                logger.error(f"AgentLifecycle: State-specific hook error: {e}")

    # ── Convenience Methods ──────────────────────────────────────────────────

    async def register(self, agent_id: str, **context) -> StateTransitionResult:
        """Convenience: Transition from CREATED to REGISTERED."""
        return await self.transition(
            agent_id,
            AgentState.REGISTERED,
            triggered_by="AgentRuntime",
            reason="Agent registered with runtime",
            context=context,
        )

    async def activate(self, agent_id: str, **context) -> StateTransitionResult:
        """Convenience: Transition to ACTIVE."""
        info = self.get_info(agent_id)
        if info and info.current_state == AgentState.IDLE:
            # IDLE → EXECUTING is the path for task execution
            return await self.transition(
                agent_id,
                AgentState.EXECUTING,
                triggered_by="TaskAssignment",
                reason="Task execution started",
                context=context,
            )
        return await self.transition(
            agent_id,
            AgentState.ACTIVE,
            triggered_by="TaskAssignment",
            reason="Agent assigned to task",
            context=context,
        )

    async def start_execution(self, agent_id: str, task_id: str) -> StateTransitionResult:
        """Convenience: Transition to EXECUTING with task context."""
        info = self._agent_states.get(agent_id)
        if info:
            info.task_count += 1
        return await self.transition(
            agent_id,
            AgentState.EXECUTING,
            triggered_by="Executor",
            reason=f"Started executing task {task_id}",
            context={"task_id": task_id},
        )

    async def complete_execution(
        self, agent_id: str, task_id: str, success: bool = True
    ) -> StateTransitionResult:
        """Convenience: Transition from EXECUTING to IDLE."""
        return await self.transition(
            agent_id,
            AgentState.IDLE,
            triggered_by="Executor",
            reason=f"Task {task_id} {'completed' if success else 'failed'}",
            context={"task_id": task_id, "success": success},
        )

    async def decommission(
        self,
        agent_id: str,
        reason: str = "Requested",
        **context,
    ) -> StateTransitionResult:
        """Convenience: Transition to DECOMMISSIONED."""
        info = self._agent_states.get(agent_id)
        if info:
            info.decommissioned_at = datetime.now(timezone.utc).isoformat()
            info.decommission_reason = reason

        return await self.transition(
            agent_id,
            AgentState.DECOMMISSIONED,
            triggered_by="System",
            reason=reason,
            context=context,
        )

    # ── Query Methods ───────────────────────────────────────────────────────

    def get_info(self, agent_id: str) -> Optional[AgentLifecycleInfo]:
        """Get lifecycle info for an agent."""
        return self._agent_states.get(agent_id)

    def get_current_state(self, agent_id: str) -> Optional[AgentState]:
        """Get current state of an agent."""
        info = self._agent_states.get(agent_id)
        return info.current_state if info else None

    def is_in_state(self, agent_id: str, state: AgentState) -> bool:
        """Check if an agent is in a specific state."""
        info = self._agent_states.get(agent_id)
        return info.current_state == state if info else False

    def can_transition(self, agent_id: str, to_state: AgentState) -> bool:
        """Check if an agent can transition to a given state."""
        info = self._agent_states.get(agent_id)
        if not info:
            return False
        return self._is_valid_transition(info.current_state, to_state)

    def list_agents_in_state(self, state: AgentState) -> List[str]:
        """List all agent IDs in a given state."""
        return [
            agent_id
            for agent_id, info in self._agent_states.items()
            if info.current_state == state
        ]

    def list_all(self) -> Dict[str, AgentLifecycleInfo]:
        """List all agent lifecycle info."""
        return dict(self._agent_states)

    def get_transition_count(self) -> int:
        """Get total number of transitions performed."""
        return self._transition_count

    # ── Lifecycle Validation ─────────────────────────────────────────────────

    def validate_lifecycle(self, agent_id: str) -> Dict[str, Any]:
        """Validate an agent's lifecycle state and history.

        Returns:
            Validation report with status and any issues found
        """
        info = self._agent_states.get(agent_id)
        if not info:
            return {"valid": False, "error": "Agent not found"}

        issues = []

        # Check state history consistency
        if info.previous_state and info.state_history:
            last_event = info.state_history[-1]
            if last_event.to_state != info.current_state:
                issues.append("Current state doesn't match last transition")

        # Check for impossible state combinations
        if info.current_state == AgentState.DECOMMISSIONED:
            if not info.decommissioned_at:
                issues.append("Decommissioned agent missing timestamp")
            if info.task_count > 0:
                # This is a warning, not an error
                logger.warning(f"Agent '{agent_id}' decommissioned with {info.task_count} tasks")

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "current_state": info.current_state.value,
            "task_count": info.task_count,
            "transition_count": len(info.state_history),
        }

    # ── Cleanup ──────────────────────────────────────────────────────────────

    async def remove_agent(self, agent_id: str) -> bool:
        """Remove an agent from lifecycle tracking.

        Only allowed if agent is in DECOMMISSIONED state.

        Args:
            agent_id: Agent to remove

        Returns:
            True if removed successfully
        """
        async with self._lock:
            info = self._agent_states.get(agent_id)
            if not info:
                return False

            if info.current_state != AgentState.DECOMMISSIONED:
                logger.error(
                    f"AgentLifecycle: Cannot remove agent '{agent_id}' in state "
                    f"{info.current_state.value}. Must decommission first."
                )
                return False

            del self._agent_states[agent_id]
            logger.info(f"AgentLifecycle: Removed agent '{agent_id}' from tracking")
            return True

    def clear(self) -> None:
        """Clear all lifecycle data. Use only for testing."""
        self._agent_states.clear()
        self._transition_count = 0
        logger.warning("AgentLifecycle: All lifecycle data cleared")


# ── Singleton ────────────────────────────────────────────────────────────────

_lifecycle_manager_instance: Optional[AgentLifecycleManager] = None


def get_lifecycle_manager() -> AgentLifecycleManager:
    """Get or create the singleton AgentLifecycleManager instance.

    Returns:
        The global AgentLifecycleManager instance.
    """
    global _lifecycle_manager_instance
    if _lifecycle_manager_instance is None:
        _lifecycle_manager_instance = AgentLifecycleManager()
    return _lifecycle_manager_instance
