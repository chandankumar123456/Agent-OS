import os
import asyncio
from uuid import uuid4

import pytest

if os.environ.get("AGENTOS_RUNTIME_MODE", "").lower() == "grpc":
    pytest.skip("Celery-dependent tests not applicable in gRPC/desktop mode", allow_module_level=True)

from app.api.routes.tasks import get_task
from app.memory.long_term import db
from app.memory.long_term import task_repo, workflow_repo, workflow_node_repo, workflow_edge_repo
from app.queue.tasks import execute_task as celery_execute_task


def test_persisted_task_lookup_includes_workflow_nodes_when_present():
    task_id = str(uuid4())

    async def run():
        try:
            await db.connect()
        except ModuleNotFoundError:
            pytest.skip("asyncpg is not installed in this environment")
        await task_repo.create(task_id=task_id, query="persist me", status="completed")
        workflow = await workflow_repo.create(task_id=task_id, name="wf", definition={"nodes": []})
        await workflow_node_repo.create(workflow_id=workflow.id, step_number=1, agent_type="executor", depends_on=[], input_data={"step": "do it"})
        nodes = await workflow_node_repo.get_by_workflow(workflow.id)
        await db.disconnect()
        return nodes

    steps = asyncio.run(run())

    assert len(steps) == 1
    assert steps[0].agent_type == "executor"


def test_get_task_returns_workflow_nodes_instead_of_legacy_steps():
    task_id = str(uuid4())

    async def run():
        try:
            await db.connect()
        except ModuleNotFoundError:
            pytest.skip("asyncpg is not installed in this environment")

        await task_repo.create(task_id=task_id, query="persist me", status="completed")
        workflow = await workflow_repo.create(task_id=task_id, name="wf", definition={"nodes": []})
        node = await workflow_node_repo.create(workflow_id=workflow.id, step_number=1, agent_type="executor", depends_on=[], input_data={"step": "do it"})
        await workflow_edge_repo.create(workflow.id, node.id, node.id)

        response = await get_task(uuid4(), None)

        await db.disconnect()
        return response

    with pytest.raises(Exception):
        asyncio.run(run())


def test_celery_worker_marks_failed_tasks_in_db_on_exception(monkeypatch):
    updates = []
    import app.memory.long_term as long_term
    import app.orchestrator.core as core
    import app.queue.tasks as queue_tasks

    async def fake_update(task_id, status=None, result=None, error=None):
        updates.append({"task_id": task_id, "status": status, "result": result, "error": error})

    class FakeOrchestrator:
        async def execute_task(self, query, config, task_id=None, user_id=None):
            raise RuntimeError("boom")

    monkeypatch.setattr(long_term.task_repo, "update", fake_update)
    monkeypatch.setattr(core, "orchestrator", FakeOrchestrator(), raising=False)

    task = queue_tasks.celery_app.tasks['agent_os.execute_task']
    task.max_retries = 0

    result = queue_tasks.execute_task.run(str(uuid4()), "query", {})

    assert result["status"] == "failed"
    assert updates[0]["status"] == "running"
    assert updates[-1]["status"] == "failed"
    assert updates[-1]["error"] == "boom"


def test_task_repo_get_raises_when_db_session_fails(monkeypatch):
    def fail_session():
        raise RuntimeError("db offline")

    monkeypatch.setattr("app.memory.long_term.db.get_session", fail_session)

    async def run():
        await task_repo.get("task-1")

    with pytest.raises(RuntimeError, match="db offline"):
        asyncio.run(run())
