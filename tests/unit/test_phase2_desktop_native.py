"""Phase 2 validation tests for desktop-native dependency elimination.

Verifies that all desktop-native components work correctly without Redis or PostgreSQL.
"""

import asyncio
import os
import pytest
import pytest_asyncio

# Must set before any app imports
os.environ["AGENTOS_RUNTIME_MODE"] = "grpc"
os.environ["RUNTIME_MODE"] = "grpc"

from core.desktop_native.sqlite_store import sqlite_store
from core.desktop_native.event_bus import local_event_bus, Event
from core.desktop_native.locks import local_execution_lock
from core.desktop_native.timeouts import local_timeout_enforcer, TimeoutConfig
from core.desktop_native.task_queue import local_task_queue, TaskPriority
from core.desktop_native.state_machine import local_task_state_machine, TaskState
from core.desktop_native.cost_tracker import local_cost_tracker


@pytest_asyncio.fixture(autouse=True)
async def init_sqlite():
    """Initialize SQLite schema before each test."""
    await sqlite_store.initialize_schema()
    yield
    # Cleanup after test
    try:
        await sqlite_store.execute("DELETE FROM task_queue")
        await sqlite_store.execute("DELETE FROM task_state")
        await sqlite_store.execute("DELETE FROM state_transitions")
        await sqlite_store.execute("DELETE FROM execution_locks")
        await sqlite_store.execute("DELETE FROM timeout_configs")
        await sqlite_store.execute("DELETE FROM timeout_deadlines")
        await sqlite_store.execute("DELETE FROM cost_records")
        await sqlite_store.execute("DELETE FROM event_log")
        await sqlite_store.commit()
    except Exception:
        pass


class TestLocalEventBus:
    @pytest.mark.asyncio
    async def test_publish_subscribe(self):
        received = []

        async def subscriber():
            async for event in local_event_bus.subscribe("test_channel"):
                received.append(event)
                if len(received) >= 2:
                    break

        task = asyncio.create_task(subscriber())
        await asyncio.sleep(0.05)  # Let subscriber register

        await local_event_bus.publish("test_channel", Event("test", {"msg": "hello"}))
        await local_event_bus.publish("test_channel", Event("test", {"msg": "world"}))

        await asyncio.wait_for(task, timeout=1.0)
        assert len(received) == 2
        assert received[0].payload["msg"] == "hello"
        assert received[1].payload["msg"] == "world"

    @pytest.mark.asyncio
    async def test_persistence(self):
        await local_event_bus.publish("persist_channel", Event("persist", {"data": 123}))
        await asyncio.sleep(0.05)

        events = await local_event_bus.get_recent_events("persist_channel", limit=10)
        assert len(events) >= 1
        assert events[-1].payload["data"] == 123


class TestLocalExecutionLock:
    @pytest.mark.asyncio
    async def test_acquire_release(self):
        record = await local_execution_lock.acquire("task-1", owner="worker-1", ttl_seconds=60)
        assert record is not None
        assert record.task_id == "task-1"

        assert await local_execution_lock.is_locked("task-1") is True

        released = await local_execution_lock.release("task-1", record.lock_id)
        assert released is True
        assert await local_execution_lock.is_locked("task-1") is False

    @pytest.mark.asyncio
    async def test_ownership_check(self):
        record = await local_execution_lock.acquire("task-2", owner="worker-1", ttl_seconds=60)
        bad_release = await local_execution_lock.release("task-2", "wrong-lock-id")
        assert bad_release is False

        # Should still be locked
        assert await local_execution_lock.is_locked("task-2") is True

        # Force release
        assert await local_execution_lock.force_release("task-2") is True
        assert await local_execution_lock.is_locked("task-2") is False


class TestLocalTimeoutEnforcer:
    @pytest.mark.asyncio
    async def test_set_get_config(self):
        config = TimeoutConfig(tool_timeout_seconds=45)
        assert await local_timeout_enforcer.set_config("task-3", config) is True

        retrieved = await local_timeout_enforcer.get_config("task-3")
        assert retrieved.tool_timeout_seconds == 45

    @pytest.mark.asyncio
    async def test_tool_timeout(self):
        async def slow_coro():
            await asyncio.sleep(10)
            return "done"

        from core.orchestrator.errors import AgentOSError
        with pytest.raises(AgentOSError):
            await local_timeout_enforcer.enforce_tool("task-4", "slow_tool", slow_coro(), override_seconds=1)


class TestLocalTaskQueue:
    @pytest.mark.asyncio
    async def test_enqueue_dequeue(self):
        pos = await local_task_queue.enqueue("task-5", "user-1", "test query", priority=TaskPriority.HIGH)
        assert pos.position == 0

        task = await local_task_queue.dequeue("worker-1")
        assert task is not None
        assert task.task_id == "task-5"
        assert task.status == "assigned"

    @pytest.mark.asyncio
    async def test_complete_fail(self):
        await local_task_queue.enqueue("task-6", "user-1", "test query")
        await local_task_queue.dequeue("worker-1")

        assert await local_task_queue.complete("task-6") is True

        await local_task_queue.enqueue("task-7", "user-1", "test query")
        await local_task_queue.dequeue("worker-1")
        assert await local_task_queue.fail("task-7", "error msg") is True


class TestLocalTaskStateMachine:
    @pytest.mark.asyncio
    async def test_transition(self):
        transition = await local_task_state_machine.transition(
            "task-8", TaskState.PENDING, TaskState.PLANNING, triggered_by="test"
        )
        assert transition.from_state == TaskState.PENDING
        assert transition.to_state == TaskState.PLANNING

        current = await local_task_state_machine.get_current_state("task-8")
        assert current == TaskState.PLANNING

    @pytest.mark.asyncio
    async def test_invalid_transition(self):
        from core.orchestrator.errors import AgentOSError
        with pytest.raises(AgentOSError):
            await local_task_state_machine.transition(
                "task-9", TaskState.PENDING, TaskState.COMPLETED
            )

    @pytest.mark.asyncio
    async def test_history(self):
        await local_task_state_machine.transition("task-10", TaskState.PENDING, TaskState.PLANNING)
        await local_task_state_machine.transition("task-10", TaskState.PLANNING, TaskState.EXECUTING)

        history = await local_task_state_machine.get_transition_history("task-10")
        assert len(history) == 2

    @pytest.mark.asyncio
    async def test_terminal(self):
        await local_task_state_machine.transition("task-11", TaskState.PENDING, TaskState.PLANNING)
        await local_task_state_machine.transition("task-11", TaskState.PLANNING, TaskState.EXECUTING)
        await local_task_state_machine.transition("task-11", TaskState.EXECUTING, TaskState.VERIFYING)
        await local_task_state_machine.transition("task-11", TaskState.VERIFYING, TaskState.COMPLETED)

        assert await local_task_state_machine.is_terminal("task-11") is True


class TestLocalCostTracker:
    @pytest.mark.asyncio
    async def test_record_llm_cost(self):
        record = await local_cost_tracker.record_llm_cost(
            "task-12", "gpt-4o", 1000, 500, agent_id="agent-1"
        )
        assert record.cost_usd > 0

        breakdown = await local_cost_tracker.get_cost_breakdown("task", "task-12")
        assert breakdown.total_cost_usd > 0

    @pytest.mark.asyncio
    async def test_record_tool_cost(self):
        record = await local_cost_tracker.record_tool_cost("task-13", "browser__navigate", 0.001)
        assert record.cost_usd == 0.001

        breakdown = await local_cost_tracker.get_cost_breakdown("tool", "browser__navigate")
        assert breakdown.total_cost_usd == 0.001


class TestIntegrationNoRedisPostgres:
    """Verify that desktop-native components function without Redis/PG."""

    @pytest.mark.asyncio
    async def test_end_to_end_task_lifecycle(self):
        task_id = "task-e2e-1"

        # Enqueue
        await local_task_queue.enqueue(task_id, "user-1", "e2e test")

        # State transition to planning
        await local_task_state_machine.transition(task_id, TaskState.PENDING, TaskState.PLANNING)

        # Acquire lock
        lock = await local_execution_lock.acquire(task_id, owner="worker-1")
        assert lock is not None

        # Dequeue
        task = await local_task_queue.dequeue("worker-1")
        assert task is not None

        # Record cost
        await local_cost_tracker.record_llm_cost(task_id, "gpt-4o", 100, 50)

        # Publish event
        await local_event_bus.publish("tasks", Event("task_updated", {"task_id": task_id, "status": "completed"}))

        # Transition through valid states to completed
        await local_task_state_machine.transition(task_id, TaskState.PLANNING, TaskState.EXECUTING)
        await local_task_state_machine.transition(task_id, TaskState.EXECUTING, TaskState.VERIFYING)
        await local_task_state_machine.transition(task_id, TaskState.VERIFYING, TaskState.COMPLETED)
        await local_task_queue.complete(task_id)
        await local_execution_lock.release(task_id, lock.lock_id)

        # Verify final state
        assert await local_task_state_machine.is_terminal(task_id) is True
        assert await local_execution_lock.is_locked(task_id) is False

        cost = await local_cost_tracker.get_cost_breakdown("task", task_id)
        assert cost.total_cost_usd > 0
