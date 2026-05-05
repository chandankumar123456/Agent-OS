"""Tests for TaskStateMachine transitions, invalid transitions, and checkpoint recovery."""
import pytest
from datetime import datetime

from app.orchestrator.state_machine import (
    TaskStateMachine,
    TaskState,
    StateTransition,
    AgentOSError,
    ErrorCode,
)


@pytest.fixture
def tsm():
    return TaskStateMachine()


@pytest.fixture
def task_id():
    return "test-task-001"


class TestValidTransitions:
    """Test all valid state transitions."""

    @pytest.mark.asyncio
    async def test_pending_to_planning(self, tsm, task_id):
        transition = await tsm.transition(
            task_id, TaskState.PENDING, TaskState.PLANNING, triggered_by="test"
        )
        assert transition.from_state == TaskState.PENDING
        assert transition.to_state == TaskState.PLANNING
        assert transition.validation_errors == []
        current = await tsm.get_current_state(task_id)
        assert current == TaskState.PLANNING

    @pytest.mark.asyncio
    async def test_planning_to_executing(self, tsm, task_id):
        await tsm.transition(task_id, TaskState.PENDING, TaskState.PLANNING)
        transition = await tsm.transition(
            task_id, TaskState.PLANNING, TaskState.EXECUTING
        )
        assert transition.to_state == TaskState.EXECUTING

    @pytest.mark.asyncio
    async def test_executing_to_verifying(self, tsm, task_id):
        await tsm.transition(task_id, TaskState.PENDING, TaskState.PLANNING)
        await tsm.transition(task_id, TaskState.PLANNING, TaskState.EXECUTING)
        transition = await tsm.transition(
            task_id, TaskState.EXECUTING, TaskState.VERIFYING
        )
        assert transition.to_state == TaskState.VERIFYING

    @pytest.mark.asyncio
    async def test_verifying_to_completed(self, tsm, task_id):
        await tsm.transition(task_id, TaskState.PENDING, TaskState.PLANNING)
        await tsm.transition(task_id, TaskState.PLANNING, TaskState.EXECUTING)
        await tsm.transition(task_id, TaskState.EXECUTING, TaskState.VERIFYING)
        transition = await tsm.transition(
            task_id, TaskState.VERIFYING, TaskState.COMPLETED
        )
        assert transition.to_state == TaskState.COMPLETED

    @pytest.mark.asyncio
    async def test_verifying_to_awaiting_approval(self, tsm, task_id):
        await tsm.transition(task_id, TaskState.PENDING, TaskState.PLANNING)
        await tsm.transition(task_id, TaskState.PLANNING, TaskState.EXECUTING)
        await tsm.transition(task_id, TaskState.EXECUTING, TaskState.VERIFYING)
        transition = await tsm.transition(
            task_id, TaskState.VERIFYING, TaskState.AWAITING_APPROVAL
        )
        assert transition.to_state == TaskState.AWAITING_APPROVAL

    @pytest.mark.asyncio
    async def test_awaiting_approval_to_completed(self, tsm, task_id):
        await tsm.transition(task_id, TaskState.PENDING, TaskState.PLANNING)
        await tsm.transition(task_id, TaskState.PLANNING, TaskState.EXECUTING)
        await tsm.transition(task_id, TaskState.EXECUTING, TaskState.VERIFYING)
        await tsm.transition(
            task_id, TaskState.VERIFYING, TaskState.AWAITING_APPROVAL
        )
        transition = await tsm.transition(
            task_id, TaskState.AWAITING_APPROVAL, TaskState.COMPLETED
        )
        assert transition.to_state == TaskState.COMPLETED

    @pytest.mark.asyncio
    async def test_awaiting_approval_to_rejected(self, tsm, task_id):
        await tsm.transition(task_id, TaskState.PENDING, TaskState.PLANNING)
        await tsm.transition(task_id, TaskState.PLANNING, TaskState.EXECUTING)
        await tsm.transition(task_id, TaskState.EXECUTING, TaskState.VERIFYING)
        await tsm.transition(
            task_id, TaskState.VERIFYING, TaskState.AWAITING_APPROVAL
        )
        transition = await tsm.transition(
            task_id, TaskState.AWAITING_APPROVAL, TaskState.REJECTED
        )
        assert transition.to_state == TaskState.REJECTED

    @pytest.mark.asyncio
    async def test_verifying_to_executing_replan(self, tsm, task_id):
        await tsm.transition(task_id, TaskState.PENDING, TaskState.PLANNING)
        await tsm.transition(task_id, TaskState.PLANNING, TaskState.EXECUTING)
        await tsm.transition(task_id, TaskState.EXECUTING, TaskState.VERIFYING)
        transition = await tsm.transition(
            task_id, TaskState.VERIFYING, TaskState.EXECUTING
        )
        assert transition.to_state == TaskState.EXECUTING

    @pytest.mark.asyncio
    async def test_pending_to_failed(self, tsm, task_id):
        transition = await tsm.transition(
            task_id, TaskState.PENDING, TaskState.FAILED
        )
        assert transition.to_state == TaskState.FAILED


class TestInvalidTransitions:
    """Test that invalid transitions are rejected."""

    @pytest.mark.asyncio
    async def test_cannot_go_from_completed_to_anything(self, tsm, task_id):
        await tsm.transition(task_id, TaskState.PENDING, TaskState.PLANNING)
        await tsm.transition(task_id, TaskState.PLANNING, TaskState.EXECUTING)
        await tsm.transition(task_id, TaskState.EXECUTING, TaskState.VERIFYING)
        await tsm.transition(task_id, TaskState.VERIFYING, TaskState.COMPLETED)

        with pytest.raises(AgentOSError) as exc_info:
            await tsm.transition(
                task_id, TaskState.COMPLETED, TaskState.EXECUTING
            )
        assert exc_info.value.code == ErrorCode.VALIDATION_ERROR
        assert "Invalid transition" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_cannot_skip_planning(self, tsm, task_id):
        with pytest.raises(AgentOSError) as exc_info:
            await tsm.transition(
                task_id, TaskState.PENDING, TaskState.EXECUTING
            )
        assert "Invalid transition" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_cannot_go_from_pending_to_completed(self, tsm, task_id):
        with pytest.raises(AgentOSError) as exc_info:
            await tsm.transition(
                task_id, TaskState.PENDING, TaskState.COMPLETED
            )
        assert "Invalid transition" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_cannot_reject_from_executing(self, tsm, task_id):
        await tsm.transition(task_id, TaskState.PENDING, TaskState.PLANNING)
        await tsm.transition(task_id, TaskState.PLANNING, TaskState.EXECUTING)
        with pytest.raises(AgentOSError) as exc_info:
            await tsm.transition(
                task_id, TaskState.EXECUTING, TaskState.REJECTED
            )
        assert "Invalid transition" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_state_mismatch_rejection(self, tsm, task_id):
        # Task is in PLANNING, but we claim it's in EXECUTING
        await tsm.transition(task_id, TaskState.PENDING, TaskState.PLANNING)
        with pytest.raises(AgentOSError) as exc_info:
            await tsm.transition(
                task_id, TaskState.EXECUTING, TaskState.VERIFYING
            )
        assert "State mismatch" in exc_info.value.message


class TestTransitionHistory:
    """Test transition history tracking."""

    @pytest.mark.asyncio
    async def test_history_recorded(self, tsm, task_id):
        await tsm.transition(task_id, TaskState.PENDING, TaskState.PLANNING)
        await tsm.transition(task_id, TaskState.PLANNING, TaskState.EXECUTING)

        history = await tsm.get_transition_history(task_id)
        assert len(history) == 2
        assert history[0].from_state == TaskState.PENDING
        assert history[0].to_state == TaskState.PLANNING
        assert history[1].from_state == TaskState.PLANNING
        assert history[1].to_state == TaskState.EXECUTING

    @pytest.mark.asyncio
    async def test_history_limit(self, tsm, task_id):
        # Create more transitions than default limit
        await tsm.transition(task_id, TaskState.PENDING, TaskState.PLANNING)
        await tsm.transition(task_id, TaskState.PLANNING, TaskState.EXECUTING)
        await tsm.transition(task_id, TaskState.EXECUTING, TaskState.VERIFYING)
        await tsm.transition(
            task_id, TaskState.VERIFYING, TaskState.COMPLETED
        )

        history = await tsm.get_transition_history(task_id, limit=2)
        assert len(history) == 2


class TestCanTransition:
    """Test the can_transition helper."""

    @pytest.mark.asyncio
    async def test_can_transition_valid(self, tsm, task_id):
        await tsm.transition(task_id, TaskState.PENDING, TaskState.PLANNING)
        valid, reason = await tsm.can_transition(task_id, TaskState.EXECUTING)
        assert valid is True
        assert reason is None

    @pytest.mark.asyncio
    async def test_can_transition_invalid(self, tsm, task_id):
        await tsm.transition(task_id, TaskState.PENDING, TaskState.PLANNING)
        valid, reason = await tsm.can_transition(
            task_id, TaskState.COMPLETED
        )
        assert valid is False
        assert "Cannot transition" in reason


class TestTerminalStates:
    """Test terminal state detection."""

    @pytest.mark.asyncio
    async def test_completed_is_terminal(self, tsm, task_id):
        await tsm.transition(task_id, TaskState.PENDING, TaskState.PLANNING)
        await tsm.transition(task_id, TaskState.PLANNING, TaskState.EXECUTING)
        await tsm.transition(task_id, TaskState.EXECUTING, TaskState.VERIFYING)
        await tsm.transition(
            task_id, TaskState.VERIFYING, TaskState.COMPLETED
        )
        assert await tsm.is_terminal(task_id) is True

    @pytest.mark.asyncio
    async def test_failed_is_terminal(self, tsm, task_id):
        await tsm.transition(task_id, TaskState.PENDING, TaskState.FAILED)
        assert await tsm.is_terminal(task_id) is True

    @pytest.mark.asyncio
    async def test_executing_is_not_terminal(self, tsm, task_id):
        await tsm.transition(task_id, TaskState.PENDING, TaskState.PLANNING)
        await tsm.transition(task_id, TaskState.PLANNING, TaskState.EXECUTING)
        assert await tsm.is_terminal(task_id) is False


class TestResetState:
    """Test state reset functionality."""

    @pytest.mark.asyncio
    async def test_reset_to_pending(self, tsm, task_id):
        await tsm.transition(task_id, TaskState.PENDING, TaskState.PLANNING)
        await tsm.transition(task_id, TaskState.PLANNING, TaskState.EXECUTING)
        await tsm.reset_state(task_id, TaskState.PENDING)
        current = await tsm.get_current_state(task_id)
        assert current == TaskState.PENDING

    @pytest.mark.asyncio
    async def test_reset_allows_replay(self, tsm, task_id):
        # Run to completion
        await tsm.transition(task_id, TaskState.PENDING, TaskState.PLANNING)
        await tsm.transition(task_id, TaskState.PLANNING, TaskState.EXECUTING)
        await tsm.transition(task_id, TaskState.EXECUTING, TaskState.VERIFYING)
        await tsm.transition(
            task_id, TaskState.VERIFYING, TaskState.COMPLETED
        )

        # Reset and replay
        await tsm.reset_state(task_id, TaskState.PENDING)
        transition = await tsm.transition(
            task_id, TaskState.PENDING, TaskState.PLANNING
        )
        assert transition.to_state == TaskState.PLANNING


class TestTaskStateEnum:
    """Test TaskState enum values."""

    def test_all_states_present(self):
        states = set(TaskState)
        expected = {
            TaskState.PENDING,
            TaskState.PLANNING,
            TaskState.EXECUTING,
            TaskState.VERIFYING,
            TaskState.AWAITING_APPROVAL,
            TaskState.COMPLETED,
            TaskState.FAILED,
            TaskState.REJECTED,
        }
        assert states == expected

    def test_state_values(self):
        assert TaskState.PENDING.value == "pending"
        assert TaskState.COMPLETED.value == "completed"
        assert TaskState.FAILED.value == "failed"
