"""Tests for TimeoutEnforcer: config management, deadline tracking, and enforcement."""
import asyncio
import pytest
from unittest.mock import AsyncMock, patch

from app.orchestrator.timeouts import TimeoutEnforcer, TimeoutConfig
from app.orchestrator.errors import AgentOSError, ErrorType, ErrorCode


@pytest.fixture
def enforcer():
    return TimeoutEnforcer(redis_prefix="test:timeout:")


@pytest.fixture
def mock_redis():
    with patch("app.orchestrator.timeouts.redis_client") as mock:
        yield mock


class TestConfigManagement:
    """Test timeout configuration get/set."""

    @pytest.mark.asyncio
    async def test_set_and_get_config(self, enforcer, mock_redis):
        mock_redis.client.set = AsyncMock(return_value=True)
        mock_redis.client.get = AsyncMock(
            return_value='{"agent_timeout_seconds":120,"tool_timeout_seconds":45,"workflow_timeout_seconds":600,"step_timeout_seconds":90,"max_total_seconds":900}'
        )

        config = TimeoutConfig(tool_timeout_seconds=45, agent_timeout_seconds=120)
        result = await enforcer.set_config("task-1", config)
        assert result is True

        retrieved = await enforcer.get_config("task-1")
        assert retrieved.tool_timeout_seconds == 45
        assert retrieved.agent_timeout_seconds == 120

    @pytest.mark.asyncio
    async def test_get_config_fallback_to_default(self, enforcer, mock_redis):
        mock_redis.client.get = AsyncMock(return_value=None)

        config = await enforcer.get_config("task-unknown")

        assert config.tool_timeout_seconds == 30
        assert config.agent_timeout_seconds == 60
        assert config.workflow_timeout_seconds == 300

    @pytest.mark.asyncio
    async def test_set_config_redis_failure(self, enforcer, mock_redis):
        mock_redis.client.set = AsyncMock(side_effect=Exception("Redis down"))

        config = TimeoutConfig()
        result = await enforcer.set_config("task-1", config)

        assert result is False


class TestDeadlineTracking:
    """Test deadline set/check/cleanup."""

    @pytest.mark.asyncio
    async def test_set_deadline(self, enforcer, mock_redis):
        mock_redis.client.set = AsyncMock(return_value=True)

        record = await enforcer.set_deadline("task-1", "tool:shell", 30)

        assert record.task_id == "task-1"
        assert record.scope == "tool:shell"
        assert record.configured_seconds == 30
        assert record.deadline_timestamp > 0
        mock_redis.client.set.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_check_deadline_not_exceeded(self, enforcer, mock_redis):
        import time
        future_time = time.time() + 300
        mock_redis.client.get = AsyncMock(
            return_value=f'{{"task_id":"task-1","scope":"tool:shell","deadline_timestamp":{future_time},"configured_seconds":30,"started_at":"2024-01-01T00:00:00","triggered":false}}'
        )

        exceeded = await enforcer.check_deadline("task-1", "tool:shell")

        assert exceeded is False

    @pytest.mark.asyncio
    async def test_check_deadline_exceeded(self, enforcer, mock_redis):
        import time
        past_time = time.time() - 10
        mock_redis.client.get = AsyncMock(
            return_value=f'{{"task_id":"task-1","scope":"tool:shell","deadline_timestamp":{past_time},"configured_seconds":30,"started_at":"2024-01-01T00:00:00","triggered":false}}'
        )
        mock_redis.client.set = AsyncMock(return_value=True)

        exceeded = await enforcer.check_deadline("task-1", "tool:shell")

        assert exceeded is True

    @pytest.mark.asyncio
    async def test_check_deadline_no_deadline_set(self, enforcer, mock_redis):
        mock_redis.client.get = AsyncMock(return_value=None)

        exceeded = await enforcer.check_deadline("task-1", "tool:shell")

        assert exceeded is False

    @pytest.mark.asyncio
    async def test_cleanup(self, enforcer, mock_redis):
        mock_redis.client.scan_iter = AsyncMock(return_value=[])
        mock_redis.client.delete = AsyncMock(return_value=1)

        result = await enforcer.cleanup("task-1")

        assert result is True


class TestToolEnforcement:
    """Test tool timeout enforcement."""

    @pytest.mark.asyncio
    async def test_enforce_tool_success(self, enforcer, mock_redis):
        mock_redis.client.set = AsyncMock(return_value=True)
        mock_redis.client.get = AsyncMock(return_value=None)
        mock_redis.client.delete = AsyncMock(return_value=1)

        async def success_coro():
            return "success"

        result = await enforcer.enforce_tool("task-1", "shell__execute", success_coro())

        assert result == "success"

    @pytest.mark.asyncio
    async def test_enforce_tool_timeout(self, enforcer, mock_redis):
        mock_redis.client.set = AsyncMock(return_value=True)
        mock_redis.client.get = AsyncMock(return_value=None)
        mock_redis.client.delete = AsyncMock(return_value=1)

        async def slow_coro():
            await asyncio.sleep(10)
            return "too late"

        with pytest.raises(AgentOSError) as exc_info:
            await enforcer.enforce_tool(
                "task-1", "shell__execute", slow_coro(), override_seconds=0.01
            )

        assert exc_info.value.code == ErrorCode.TIMEOUT_ERROR
        assert "timed out" in exc_info.value.message


class TestAgentEnforcement:
    """Test agent timeout enforcement."""

    @pytest.mark.asyncio
    async def test_enforce_agent_success(self, enforcer, mock_redis):
        mock_redis.client.set = AsyncMock(return_value=True)
        mock_redis.client.get = AsyncMock(return_value=None)
        mock_redis.client.delete = AsyncMock(return_value=1)

        async def success_coro():
            return "agent result"

        result = await enforcer.enforce_agent("task-1", "planner", success_coro())

        assert result == "agent result"

    @pytest.mark.asyncio
    async def test_enforce_agent_timeout(self, enforcer, mock_redis):
        mock_redis.client.set = AsyncMock(return_value=True)
        mock_redis.client.get = AsyncMock(return_value=None)
        mock_redis.client.delete = AsyncMock(return_value=1)

        async def slow_coro():
            await asyncio.sleep(10)

        with pytest.raises(AgentOSError) as exc_info:
            await enforcer.enforce_agent(
                "task-1", "planner", slow_coro(), override_seconds=0.01
            )

        assert exc_info.value.code == ErrorCode.TIMEOUT_ERROR


class TestStepEnforcement:
    """Test step timeout enforcement."""

    @pytest.mark.asyncio
    async def test_enforce_step_success(self, enforcer, mock_redis):
        mock_redis.client.set = AsyncMock(return_value=True)
        mock_redis.client.get = AsyncMock(return_value=None)
        mock_redis.client.delete = AsyncMock(return_value=1)

        async def success_coro():
            return "step done"

        result = await enforcer.enforce_step("task-1", 0, success_coro())

        assert result == "step done"

    @pytest.mark.asyncio
    async def test_enforce_step_timeout(self, enforcer, mock_redis):
        mock_redis.client.set = AsyncMock(return_value=True)
        mock_redis.client.get = AsyncMock(return_value=None)
        mock_redis.client.delete = AsyncMock(return_value=1)

        async def slow_coro():
            await asyncio.sleep(10)

        with pytest.raises(AgentOSError) as exc_info:
            await enforcer.enforce_step(
                "task-1", 2, slow_coro(), override_seconds=0.01
            )

        assert "Step 2 timed out" in exc_info.value.message


class TestWorkflowEnforcement:
    """Test workflow timeout enforcement."""

    @pytest.mark.asyncio
    async def test_enforce_workflow_timeout(self, enforcer, mock_redis):
        mock_redis.client.set = AsyncMock(return_value=True)
        mock_redis.client.get = AsyncMock(return_value=None)
        mock_redis.client.delete = AsyncMock(return_value=1)

        async def slow_coro():
            await asyncio.sleep(10)

        with pytest.raises(AgentOSError) as exc_info:
            await enforcer.enforce_workflow(
                "task-1", slow_coro(), override_seconds=0.01
            )

        assert "Workflow timed out" in exc_info.value.message


class TestTimeoutScope:
    """Test timeout context manager."""

    @pytest.mark.asyncio
    async def test_timeout_scope_success(self, enforcer, mock_redis):
        mock_redis.client.set = AsyncMock(return_value=True)
        mock_redis.client.delete = AsyncMock(return_value=1)

        async with enforcer.timeout_scope("task-1", "custom_scope", 60):
            pass  # Success

    @pytest.mark.asyncio
    async def test_timeout_scope_cleanup(self, enforcer, mock_redis):
        mock_redis.client.set = AsyncMock(return_value=True)
        mock_redis.client.delete = AsyncMock(return_value=1)

        try:
            async with enforcer.timeout_scope("task-1", "custom_scope", 60):
                raise ValueError("boom")
        except ValueError:
            pass

        # Verify cleanup happened
        mock_redis.client.delete.assert_awaited()
