from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.api.routes.tasks import get_task, get_task_trace


class FakeUser(SimpleNamespace):
    pass


def test_tasks_require_authentication():
    client = TestClient(app)

    response = client.get("/api/v1/tasks")

    assert response.status_code == 401


def test_invalid_token_is_rejected():
    client = TestClient(app)

    response = client.get(
        "/api/v1/tasks",
        headers={"Authorization": "Bearer definitely-not-a-valid-token"},
    )

    assert response.status_code == 401


def test_user_cannot_access_another_users_task(monkeypatch):
    task_id = uuid4()
    owner_id = str(uuid4())
    other_user = FakeUser(id=str(uuid4()), role="user")

    async def fake_get(task_id_value: str):
        return SimpleNamespace(
            id=str(task_id),
            user_id=owner_id,
            status="completed",
            result={"trace_id": "trace-1"},
            error=None,
            created_at=None,
        )

    monkeypatch.setattr("app.api.routes.tasks.task_repo.get", fake_get)

    try:
        import asyncio

        asyncio.run(get_task(task_id, other_user))
        assert False, "expected task access to be denied"
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 404


def test_get_task_returns_lowercase_node_statuses(monkeypatch):
    task_id = uuid4()
    current_user = FakeUser(id=str(uuid4()), role="user")

    async def fake_task_get(task_id_value: str):
        return SimpleNamespace(
            id=str(task_id),
            user_id=current_user.id,
            status="completed",
            result={"trace_id": "trace-1"},
            error=None,
            created_at=None,
        )

    async def fake_workflow_state(task_id_value, user):
        return {
            "workflow": SimpleNamespace(id="wf-1", task_id=str(task_id), name="demo", definition={"nodes": []}, status="completed"),
            "nodes": [
                SimpleNamespace(
                    id="node-1",
                    step_number=1,
                    agent_type="executor",
                    status="completed",
                    depends_on=[],
                    input_data={"step": "one"},
                    output_data={"ok": True},
                    confidence=0.9,
                )
            ],
            "edges": [],
        }

    monkeypatch.setattr("app.api.routes.tasks.task_repo.get", fake_task_get)
    monkeypatch.setattr("app.api.routes.tasks._task_scoped_workflow_state", fake_workflow_state)

    import asyncio

    response = asyncio.run(get_task(task_id, current_user))

    assert response.workflow_state["nodes"][0]["status"] == "completed"


def test_get_task_trace_returns_full_workflow_trace(monkeypatch):
    task_id = uuid4()
    current_user = FakeUser(id=str(uuid4()), role="user")

    async def fake_task_get(task_id_value: str):
        return SimpleNamespace(
            id=str(task_id),
            user_id=current_user.id,
            status="completed",
            result={"trace_id": "trace-1"},
            error=None,
            created_at=None,
        )

    async def fake_trace_get(trace_id: str):
        return SimpleNamespace(
            id="trace-row",
            task_id=str(task_id),
            user_id=current_user.id,
            trace_id=trace_id,
            status="completed",
            created_at=None,
            updated_at=None,
        )

    async def fake_spans(trace_id: str):
        return [
            SimpleNamespace(
                span_id="span-1",
                operation="planning",
                agent_name="planner",
                status="success",
                error=None,
                start_time=None,
                end_time=None,
            )
        ]

    async def fake_node_traces(task_id_value: str):
        return [
            SimpleNamespace(
                id="node-trace-1",
                task_id=str(task_id),
                user_id=current_user.id,
                trace_id="trace-1",
                node_id="node-1",
                status="COMPLETED",
                input_data={"step": "one"},
                output_data={"ok": True},
                error=None,
                created_at=None,
                updated_at=None,
                started_at=None,
                finished_at=None,
            ),
            SimpleNamespace(
                id="node-trace-2",
                task_id=str(task_id),
                user_id=current_user.id,
                trace_id="trace-1",
                node_id="node-2",
                status="SKIPPED",
                input_data={"step": "two"},
                output_data=None,
                error=None,
                created_at=None,
                updated_at=None,
                started_at=None,
                finished_at=None,
            ),
        ]

    async def fake_workflow_state(task_id_value, user):
        return {
            "workflow": SimpleNamespace(id="wf-1", task_id=str(task_id), name="demo", definition={"nodes": []}, status="completed"),
            "nodes": [],
            "edges": [],
        }

    monkeypatch.setattr("app.api.routes.tasks.task_repo.get", fake_task_get)
    monkeypatch.setattr("app.api.routes.tasks.trace_repo.get_by_trace_id", fake_trace_get)
    monkeypatch.setattr("app.api.routes.tasks.span_repo.get_by_trace", fake_spans)
    monkeypatch.setattr("app.api.routes.tasks._task_scoped_workflow_state", fake_workflow_state)
    monkeypatch.setattr("app.api.routes.tasks.node_trace_repo.get_by_task", fake_node_traces)

    import asyncio

    response = asyncio.run(get_task_trace(task_id, current_user))

    assert response["trace_id"] == "trace-1"
    assert "workflow_state" in response
    assert "node_traces" in response
    assert len(response["node_traces"]) == 2
