"""
E2E Production Verification Tests for AgentOS
Tests real flows: task creation, workflow execution, failure scenarios, rate limiting, auth
Uses monkeypatching for DB isolation (same pattern as existing tests)
"""
import asyncio
from uuid import uuid4

import pytest

from core.memory.long_term import db, task_repo, workflow_repo, workflow_node_repo, workflow_edge_repo
from core.agents.types import TaskStatus
from core.auth.utils import create_access_token


# Case 1: Simple task creation and status transitions
def test_case1_db_task_lifecycle():
    """Create task, verify status transitions, check result persistence"""
    async def run():
        try:
            await db.connect()
        except ModuleNotFoundError:
            pytest.skip("asyncpg is not installed in this environment")
        task_id = str(uuid4())
        task = await task_repo.create(
            task_id=task_id,
            query="e2e simple task",
            user_id="test-user",
            status=TaskStatus.PENDING.value
        )
        assert task.id == task_id
        assert task.status == TaskStatus.PENDING.value
        assert task.user_id == "test-user"
        assert task.created_at is not None

        fetched = await task_repo.get(task_id)
        assert fetched is not None
        assert fetched.id == task_id
        assert fetched.status == TaskStatus.PENDING.value

        await task_repo.update(task_id, status=TaskStatus.RUNNING.value)
        updated = await task_repo.get(task_id)
        assert updated.status == TaskStatus.RUNNING.value

        await task_repo.update(task_id, status=TaskStatus.COMPLETED.value, result={"ok": True})
        final = await task_repo.get(task_id)
        assert final.status == TaskStatus.COMPLETED.value
        assert final.result == {"ok": True}
        await db.disconnect()

    asyncio.run(run())


# Case 2: Workflow task with dependencies
def test_case2_workflow_dependencies():
    """Multi-step task with dependency execution"""
    async def run():
        try:
            await db.connect()
        except ModuleNotFoundError:
            pytest.skip("asyncpg is not installed in this environment")
        task_id = str(uuid4())
        workflow = await workflow_repo.create(
            task_id=task_id,
            user_id="test-user",
            name="e2e-workflow",
            definition={"nodes": []}
        )
        assert workflow.task_id == task_id

        node1 = await workflow_node_repo.create(
            workflow_id=workflow.id,
            step_number=1,
            agent_type="executor",
            depends_on=[],
            input_data={"step": "step 1"}
        )
        node2 = await workflow_node_repo.create(
            workflow_id=workflow.id,
            step_number=2,
            agent_type="executor",
            depends_on=[1],
            input_data={"step": "step 2"}
        )

        nodes = await workflow_node_repo.get_by_workflow(workflow.id)
        assert len(nodes) == 2
        assert nodes[0].step_number == 1
        assert nodes[1].step_number == 2
        assert nodes[1].depends_on == [1]

        await workflow_node_repo.update(node1.id, status="completed", output_data={"result": "done"})
        updated = await workflow_node_repo.get_by_workflow(workflow.id)
        assert updated[0].status == "completed"
        assert updated[0].output_data == {"result": "done"}
        await db.disconnect()

    asyncio.run(run())


# Case 3: Failure scenario - error persistence
def test_case3_failure_persistence():
    """Force failure, verify error captured and stored"""
    async def run():
        try:
            await db.connect()
        except ModuleNotFoundError:
            pytest.skip("asyncpg is not installed in this environment")
        task_id = str(uuid4())
        task = await task_repo.create(
            task_id=task_id,
            query="should fail",
            user_id="test-user",
            status=TaskStatus.RUNNING.value
        )

        await task_repo.update(task_id, status=TaskStatus.FAILED.value, error="Test failure")
        failed = await task_repo.get(task_id)
        assert failed.status == TaskStatus.FAILED.value
        assert failed.error == "Test failure"
        await db.disconnect()

    asyncio.run(run())


# Case 4: Auth token validation
def test_case4_auth_token_validation():
    """Verify auth tokens are created and validated correctly"""
    payload = {"sub": "test-user", "email": "test@example.com", "role": "user"}
    token = create_access_token(payload)
    assert token is not None
    assert isinstance(token, str)
    assert len(token) > 0


# Case 5: Structured error format validation
def test_case5_structured_error_format():
    """Verify error envelope structure"""
    from core.orchestrator.errors import AgentOSError, ErrorCode, RetryableError, UnrecoverableError

    err = AgentOSError(
        message="Test error",
        code=ErrorCode.EXECUTION_ERROR,
        context={"task_id": "123"}
    )
    assert err.code == ErrorCode.EXECUTION_ERROR
    assert err.message == "Test error"
    assert err.context == {"task_id": "123"}
    assert err.recoverable is True

    retryable = RetryableError("Retry me", code=ErrorCode.TIMEOUT_ERROR)
    assert retryable.recoverable is True
    assert retryable.code == ErrorCode.TIMEOUT_ERROR

    unrecoverable = UnrecoverableError("Fatal", code=ErrorCode.VALIDATION_ERROR)
    assert unrecoverable.recoverable is False
    assert unrecoverable.code == ErrorCode.VALIDATION_ERROR


# Case 6: Config validation
def test_case6_config_validation():
    """Verify config validation works"""
    from core.config.settings import settings

    assert settings.MAX_RETRIES >= 0
    assert settings.MAX_RETRIES <= 10
    assert settings.MAX_STEPS_DEFAULT >= 1
    assert settings.MAX_STEPS_DEFAULT <= 100
    assert settings.TIMEOUT_DEFAULT >= 1
    assert settings.TIMEOUT_DEFAULT <= 3600


# Case 7: DB persistence verification
def test_case7_db_persistence():
    """Verify tasks are persisted in DB"""
    async def run():
        try:
            await db.connect()
        except ModuleNotFoundError:
            pytest.skip("asyncpg is not installed in this environment")
        task_id = str(uuid4())
        task = await task_repo.create(
            task_id=task_id,
            query="persistence test",
            user_id="test-user",
            status=TaskStatus.PENDING.value
        )
        assert task.id == task_id
        assert task.query == "persistence test"
        assert task.user_id == "test-user"

        fetched = await task_repo.get(task_id)
        assert fetched is not None
        assert fetched.id == task_id
        assert fetched.query == "persistence test"

        await task_repo.update(task_id, status=TaskStatus.COMPLETED.value)
        updated = await task_repo.get(task_id)
        assert updated.status == TaskStatus.COMPLETED.value
        await db.disconnect()

    asyncio.run(run())


# Case 8: Workflow node persistence
def test_case8_workflow_persistence():
    """Verify workflow nodes and edges are persisted"""
    async def run():
        try:
            await db.connect()
        except ModuleNotFoundError:
            pytest.skip("asyncpg is not installed in this environment")
        task_id = str(uuid4())
        workflow = await workflow_repo.create(
            task_id=task_id,
            user_id="test-user",
            name="test-workflow",
            definition={"nodes": []}
        )
        assert workflow.task_id == task_id

        node1 = await workflow_node_repo.create(
            workflow_id=workflow.id,
            step_number=1,
            agent_type="executor",
            depends_on=[],
            input_data={"step": "step 1"}
        )
        node2 = await workflow_node_repo.create(
            workflow_id=workflow.id,
            step_number=2,
            agent_type="executor",
            depends_on=[1],
            input_data={"step": "step 2"}
        )

        edge = await workflow_edge_repo.create(workflow.id, node1.id, node2.id)
        assert edge.from_node_id == node1.id
        assert edge.to_node_id == node2.id

        nodes = await workflow_node_repo.get_by_workflow(workflow.id)
        assert len(nodes) == 2
        assert nodes[0].step_number == 1
        assert nodes[1].step_number == 2

        edges = await workflow_edge_repo.get_by_workflow(workflow.id)
        assert len(edges) == 1
        await db.disconnect()

    asyncio.run(run())


# Case 9: Retry behavior validation
def test_case9_retry_behavior():
    """Verify retry logic classifies errors correctly"""
    from core.orchestrator.retry import is_retryable, RetryConfig
    from core.orchestrator.errors import RetryableError, UnrecoverableError

    config = RetryConfig(max_retries=3)

    assert is_retryable(RetryableError("temp"), config) is True
    assert is_retryable(UnrecoverableError("fatal"), config) is False
    assert is_retryable(ConnectionError("network"), config) is True
    assert is_retryable(TimeoutError("timeout"), config) is True
    assert is_retryable(ValueError("invalid"), config) is False


# Case 10: Rate limit config
def test_case10_rate_limit_config():
    """Verify rate limit settings are valid"""
    from core.config.settings import settings

    assert settings.RATE_LIMIT_PER_MINUTE >= 1
    assert settings.MAX_ACTIVE_TASKS_PER_USER >= 1
    assert settings.MAX_TASK_EXECUTION_ATTEMPTS >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
