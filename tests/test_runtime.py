import pytest
from uuid import uuid4
from app.runtime.runtime import AgentRuntime
from app.runtime.worker import AgentWorker


def test_runtime_singleton():
    AgentRuntime().reset()
    r1 = AgentRuntime()
    r2 = AgentRuntime()
    assert r1 is r2


@pytest.mark.asyncio
async def test_runtime_initializes_core_agents():
    AgentRuntime().reset()
    runtime = AgentRuntime()
    await runtime.initialize()
    assert runtime.get("core_planner") is not None
    assert runtime.get("core_executor") is not None
    assert runtime.get("core_verifier") is not None


@pytest.mark.asyncio
async def test_runtime_register_and_get():
    AgentRuntime().reset()
    runtime = AgentRuntime()
    await runtime.initialize()
    worker = await runtime.register("test_agent", {"role": "executor"})
    assert worker is not None
    assert runtime.get("test_agent") is worker


@pytest.mark.asyncio
async def test_runtime_list_active():
    AgentRuntime().reset()
    runtime = AgentRuntime()
    await runtime.initialize()
    active = runtime.list_active()
    assert len(active) == 3  # core_planner, core_executor, core_verifier


@pytest.mark.asyncio
async def test_runtime_shutdown_all():
    AgentRuntime().reset()
    runtime = AgentRuntime()
    await runtime.initialize()
    await runtime.shutdown_all()
    assert len(runtime.list_active()) == 0


@pytest.mark.asyncio
async def test_agent_worker_executes():
    AgentRuntime().reset()
    runtime = AgentRuntime()
    await runtime.initialize()
    worker = runtime.get("core_executor")
    assert worker is not None
    from app.agents.base import AgentInput, AgentRole
    result = await worker.execute(AgentInput(
        task_id=uuid4(),
        step_id=uuid4(),
        role=AgentRole.EXECUTOR,
        input_data={"step": "test", "tools": []},
        context={},
    ))
    assert result is not None
    assert hasattr(result, 'status')
