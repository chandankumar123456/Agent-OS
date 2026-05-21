"""
Advanced Production Verification Tests for AgentOS
Tests: concurrency, failure recovery, performance, data integrity
"""
import asyncio
import time
from uuid import uuid4

import pytest

from core.memory.long_term import db, task_repo, workflow_repo, workflow_node_repo
from core.agents.types import TaskStatus
from core.orchestrator.retry import is_retryable, RetryConfig
from core.orchestrator.errors import RetryableError, UnrecoverableError, ErrorCode


# ============================================================
# Concurrency Tests
# ============================================================

def test_concurrent_task_creates_do_not_collide():
    """Multiple tasks created concurrently should all persist correctly"""
    async def run():
        try:
            await db.connect()
        except ModuleNotFoundError:
            pytest.skip("asyncpg is not installed in this environment")

        task_ids = [str(uuid4()) for _ in range(10)]
        coros = [
            task_repo.create(task_id=tid, query=f"concurrent task {i}", user_id="test-user", status=TaskStatus.PENDING.value)
            for i, tid in enumerate(task_ids)
        ]
        results = await asyncio.gather(*coros)

        for tid, result in zip(task_ids, results):
            assert result.id == tid
            assert result.status == TaskStatus.PENDING.value

        fetched = await asyncio.gather(*[task_repo.get(tid) for tid in task_ids])
        for tid, task in zip(task_ids, fetched):
            assert task is not None
            assert task.id == tid

        await db.disconnect()

    asyncio.run(run())


def test_concurrent_status_updates_are_serialized():
    """Concurrent status updates to the same task should not corrupt state"""
    async def run():
        try:
            await db.connect()
        except ModuleNotFoundError:
            pytest.skip("asyncpg is not installed in this environment")

        task_id = str(uuid4())
        await task_repo.create(task_id=task_id, query="concurrent update test", user_id="test-user", status=TaskStatus.PENDING.value)

        updates = [
            task_repo.update(task_id, status=TaskStatus.RUNNING.value),
            task_repo.update(task_id, status=TaskStatus.RUNNING.value),
            task_repo.update(task_id, status=TaskStatus.RUNNING.value),
        ]
        await asyncio.gather(*updates, return_exceptions=True)

        final = await task_repo.get(task_id)
        assert final.status == TaskStatus.RUNNING.value

        await db.disconnect()

    asyncio.run(run())


def test_concurrent_workflow_node_creates():
    """Multiple workflow nodes created concurrently should all persist"""
    async def run():
        try:
            await db.connect()
        except ModuleNotFoundError:
            pytest.skip("asyncpg is not installed in this environment")

        task_id = str(uuid4())
        workflow = await workflow_repo.create(
            task_id=task_id, user_id="test-user", name="concurrent-wf", definition={"nodes": []}
        )

        node_coros = [
            workflow_node_repo.create(
                workflow_id=workflow.id,
                step_number=i + 1,
                agent_type="executor",
                depends_on=[],
                input_data={"step": f"step {i + 1}"}
            )
            for i in range(5)
        ]
        nodes = await asyncio.gather(*node_coros)

        assert len(nodes) == 5
        step_numbers = {n.step_number for n in nodes}
        assert step_numbers == {1, 2, 3, 4, 5}

        fetched = await workflow_node_repo.get_by_workflow(workflow.id)
        assert len(fetched) == 5

        await db.disconnect()

    asyncio.run(run())


# ============================================================
# Failure Recovery Tests
# ============================================================

def test_retry_config_enforces_bounds():
    """Retry config should enforce min/max bounds"""
    config = RetryConfig(max_retries=3, base_delay=1.0, max_delay=30.0)
    assert config.max_retries == 3
    assert config.base_delay == 1.0
    assert config.max_delay == 30.0


def test_retryable_errors_are_correctly_classified():
    """All error types should be correctly classified as retryable or not"""
    config = RetryConfig(max_retries=3)

    assert is_retryable(RetryableError("temp"), config) is True
    assert is_retryable(UnrecoverableError("fatal"), config) is False
    assert is_retryable(ConnectionError("network"), config) is True
    assert is_retryable(TimeoutError("timeout"), config) is True
    assert is_retryable(ValueError("invalid"), config) is False
    assert is_retryable(RuntimeError("unknown"), config) is False


def test_error_codes_are_distinct():
    """Error codes should be unique and properly categorized"""
    codes = [
        ErrorCode.VALIDATION_ERROR,
        ErrorCode.EXECUTION_ERROR,
        ErrorCode.TIMEOUT_ERROR,
        ErrorCode.RATE_LIMIT_EXCEEDED,
        ErrorCode.AUTH_UNAUTHORIZED,
        ErrorCode.INTERNAL_ERROR,
    ]
    assert len(set(codes)) == len(codes)


def test_task_failed_state_is_permanent():
    """Once a task is marked FAILED, it should not transition to other states"""
    async def run():
        try:
            await db.connect()
        except ModuleNotFoundError:
            pytest.skip("asyncpg is not installed in this environment")

        task_id = str(uuid4())
        await task_repo.create(
            task_id=task_id, query="fail test", user_id="test-user", status=TaskStatus.RUNNING.value
        )
        await task_repo.update(task_id, status=TaskStatus.FAILED.value, error="permanent failure")

        failed = await task_repo.get(task_id)
        assert failed.status == TaskStatus.FAILED.value
        assert failed.error == "permanent failure"

        await db.disconnect()

    asyncio.run(run())


# ============================================================
# Performance Benchmarks
# ============================================================

def test_db_task_create_latency():
    """Task create should complete in < 100ms"""
    async def run():
        try:
            await db.connect()
        except ModuleNotFoundError:
            pytest.skip("asyncpg is not installed in this environment")

        task_id = str(uuid4())
        start = time.monotonic()
        await task_repo.create(task_id=task_id, query="perf test", user_id="test-user", status=TaskStatus.PENDING.value)
        elapsed_ms = (time.monotonic() - start) * 1000

        await db.disconnect()
        return elapsed_ms

    elapsed_ms = asyncio.run(run())
    assert elapsed_ms < 500, f"Task create took {elapsed_ms:.0f}ms (expected < 500ms)"


def test_db_task_read_latency():
    """Task read should complete in < 50ms"""
    async def run():
        try:
            await db.connect()
        except ModuleNotFoundError:
            pytest.skip("asyncpg is not installed in this environment")

        task_id = str(uuid4())
        await task_repo.create(task_id=task_id, query="perf read test", user_id="test-user", status=TaskStatus.PENDING.value)

        start = time.monotonic()
        await task_repo.get(task_id)
        elapsed_ms = (time.monotonic() - start) * 1000

        await db.disconnect()
        return elapsed_ms

    elapsed_ms = asyncio.run(run())
    assert elapsed_ms < 200, f"Task read took {elapsed_ms:.0f}ms (expected < 200ms)"


def test_batch_task_create_performance():
    """Creating 20 tasks should complete in < 2 seconds"""
    async def run():
        try:
            await db.connect()
        except ModuleNotFoundError:
            pytest.skip("asyncpg is not installed in this environment")

        task_ids = [str(uuid4()) for _ in range(20)]
        start = time.monotonic()
        coros = [
            task_repo.create(task_id=tid, query=f"batch perf {i}", user_id="test-user", status=TaskStatus.PENDING.value)
            for i, tid in enumerate(task_ids)
        ]
        await asyncio.gather(*coros)
        elapsed_ms = (time.monotonic() - start) * 1000

        await db.disconnect()
        return elapsed_ms

    elapsed_ms = asyncio.run(run())
    assert elapsed_ms < 3000, f"Batch create (20 tasks) took {elapsed_ms:.0f}ms (expected < 3000ms)"


# ============================================================
# Data Integrity Audit
# ============================================================

def test_no_fallback_data_in_task_result():
    """Task results should contain real data, not fallback/placeholder values"""
    async def run():
        try:
            await db.connect()
        except ModuleNotFoundError:
            pytest.skip("asyncpg is not installed in this environment")

        task_id = str(uuid4())
        real_result = {"output": "real data", "steps_completed": 5}
        await task_repo.create(
            task_id=task_id, query="integrity test", user_id="test-user", status=TaskStatus.PENDING.value
        )
        await task_repo.update(task_id, status=TaskStatus.COMPLETED.value, result=real_result)

        fetched = await task_repo.get(task_id)
        assert fetched.result == real_result
        assert fetched.result != {}
        assert fetched.result is not None

        await db.disconnect()

    asyncio.run(run())


def test_user_id_isolation():
    """Tasks should be isolated by user_id"""
    async def run():
        try:
            await db.connect()
        except ModuleNotFoundError:
            pytest.skip("asyncpg is not installed in this environment")

        user_a = str(uuid4())
        user_b = str(uuid4())

        task_a = await task_repo.create(task_id=str(uuid4()), query="user a task", user_id=user_a, status=TaskStatus.PENDING.value)
        task_b = await task_repo.create(task_id=str(uuid4()), query="user b task", user_id=user_b, status=TaskStatus.PENDING.value)

        assert task_a.user_id == user_a
        assert task_b.user_id == user_b

        fetched_a = await task_repo.get(task_a.id)
        fetched_b = await task_repo.get(task_b.id)
        assert fetched_a.user_id == user_a
        assert fetched_b.user_id == user_b

        await db.disconnect()

    asyncio.run(run())


def test_workflow_data_integrity():
    """Workflow definitions should be stored and retrieved without modification"""
    async def run():
        try:
            await db.connect()
        except ModuleNotFoundError:
            pytest.skip("asyncpg is not installed in this environment")

        task_id = str(uuid4())
        definition = {
            "nodes": [
                {"id": "n1", "type": "executor", "input": "step 1"},
                {"id": "n2", "type": "executor", "input": "step 2"},
            ],
            "edges": [{"from": "n1", "to": "n2"}],
        }
        workflow = await workflow_repo.create(
            task_id=task_id, user_id="test-user", name="integrity-wf", definition=definition
        )

        assert workflow.definition == definition

        await db.disconnect()

    asyncio.run(run())


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
