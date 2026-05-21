import asyncio
from types import SimpleNamespace
from uuid import uuid4

from core.agents.base import AgentStatus
from core.orchestrator.core import Orchestrator
from core.api.routes.tasks import use_celery


def test_use_celery_defaults_to_enabled():
    assert use_celery() is True


def test_execute_task_preserves_provided_task_id():
    orchestrator = Orchestrator()
    provided_task_id = uuid4()
    import core.orchestrator.core as core

    async def fake_validate_input(*args, **kwargs):
        return True

    call_count = {"value": 0}

    async def fake_execute_agent(*args, **kwargs):
        call_count["value"] += 1
        if call_count["value"] == 1:
            return SimpleNamespace(
                status=AgentStatus.SUCCESS,
                output_data={"steps": [{"step": "one"}]},
                error_message=None,
                confidence=1.0,
            )
        return SimpleNamespace(
            status=AgentStatus.SUCCESS,
            output_data={"valid": True},
            error_message=None,
            confidence=1.0,
        )

    async def fake_build_workflow(task_id, user_id, steps):
        return {
            "workflow": SimpleNamespace(id="wf-1", task_id=str(task_id), definition={}, status="pending"),
            "nodes": [
                SimpleNamespace(
                    id="node-1",
                    step_number=1,
                    agent_type="executor",
                    depends_on=[],
                    input_data={},
                    status="pending",
                )
            ],
            "edges": [],
        }

    async def fake_execute_graph(nodes, handlers, context):
        return {"nodes": {"node-1": {"status": "completed", "output": {"ok": True}}}, "edges": []}

    async def fake_get_workflow_state(task_id):
        return {
            "workflow": SimpleNamespace(id="wf-1", task_id=str(task_id), name="wf", definition={}, status="completed"),
            "nodes": [],
            "edges": [],
        }

    async def fake_update(*args, **kwargs):
        return None

    async def fake_create(*args, **kwargs):
        return None

    async def fake_update_status(*args, **kwargs):
        return None

    def fake_start_span(*args, **kwargs):
        return "span-1"

    def fake_end_span(*args, **kwargs):
        return None

    def fake_get_agent(agent_type):
        class FakeAgent:
            async def execute(self, input_data):
                return await fake_execute_agent(None, None, input_data, None, None)
        return FakeAgent()

    orchestrator._validate_input = fake_validate_input
    orchestrator._execute_agent = fake_execute_agent
    orchestrator._build_workflow = fake_build_workflow
    orchestrator.workflow_engine.execute_graph = fake_execute_graph
    orchestrator._get_workflow_state = fake_get_workflow_state
    orchestrator._get_agent = fake_get_agent

    core.task_repo.update = fake_update
    core.trace_repo.create = fake_create
    core.trace_repo.update_status = fake_update_status
    core.trace_manager.start_span = fake_start_span
    core.trace_manager.end_span = fake_end_span

    async def run():
        result = await orchestrator.execute_task("test query", {}, task_id=provided_task_id)
        return result

    result = asyncio.run(run())

    assert result.task_id == provided_task_id
