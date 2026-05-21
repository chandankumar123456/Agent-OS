import os
import pytest
from unittest.mock import patch

if os.environ.get("AGENTOS_RUNTIME_MODE", "").lower() == "grpc":
    pytest.skip("Celery tests not applicable in gRPC/desktop mode", allow_module_level=True)

from core.queue.tasks import _ensure_runtime_initialized
from core.runtime.runtime import AgentRuntime


@pytest.fixture(autouse=True)
def reset_runtime():
    """Reset the AgentRuntime singleton before each test to ensure isolation."""
    runtime = AgentRuntime()
    runtime.reset()
    yield
    runtime.reset()


@pytest.mark.asyncio
async def test_ensure_runtime_initializes_core_agents():
    """AgentRuntime must register core_planner, core_executor, and core_verifier
    when _ensure_runtime_initialized() is called in a fresh process boundary.
    """
    runtime = await _ensure_runtime_initialized()

    planner = runtime.get("core_planner")
    executor = runtime.get("core_executor")
    verifier = runtime.get("core_verifier")

    assert planner is not None, "core_planner should be registered"
    assert executor is not None, "core_executor should be registered"
    assert verifier is not None, "core_verifier should be registered"

    # Verify idempotency: second call should be a no-op and still succeed
    runtime2 = await _ensure_runtime_initialized()
    assert runtime2 is runtime, "Should return the same singleton instance"

    assert runtime.get("core_planner") is planner
    assert runtime.get("core_executor") is executor
    assert runtime.get("core_verifier") is verifier


@pytest.mark.asyncio
async def test_celery_task_runtime_verification():
    """Simulate the runtime verification step that occurs inside the Celery task.

    This mirrors the safety check added to execute_task() before delegating
    to the orchestrator.
    """
    runtime = await _ensure_runtime_initialized()

    worker = runtime.get("core_planner")
    assert worker is not None, (
        "Agent core_planner not found in runtime. "
        "Ensure AgentRuntime.initialize() was called at startup."
    )
    assert worker.agent_instance is not None


@pytest.mark.asyncio
async def test_runtime_initialization_logs():
    """Initialization should produce INFO-level logs for each core agent."""
    runtime = AgentRuntime()
    runtime.reset()

    with patch("core.runtime.runtime.logger") as mock_logger:
        await runtime.initialize()

        # Should log that initialization happened
        info_calls = [call for call in mock_logger.info.call_args_list]
        messages = [str(call[0][0]) for call in info_calls]

        assert any("AgentRuntime initializing core agents" in m for m in messages)
        assert any("Registered core agent: core_planner" in m for m in messages)
        assert any("Registered core agent: core_executor" in m for m in messages)
        assert any("Registered core agent: core_verifier" in m for m in messages)
        assert any("AgentRuntime initialized with core agents" in m for m in messages)
