# Phase 4: Celery Integration + Workflow Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move task execution fully into Celery and make workflow execution deterministic, validated, and observable in the database.

**Architecture:** The API will create the task row, enqueue a Celery job, and return immediately. The worker will own orchestration, persist task and node state through repositories, and treat workflow nodes as the single execution unit. Workflow execution will validate graph shape before running, evaluate conditions from deterministic context only, and persist skipped nodes so downstream dependency checks can treat them as satisfied.

**Tech Stack:** FastAPI, Celery, SQLAlchemy async repositories, pytest, Redis, PostgreSQL.

---

### Task 1: Add workflow graph validation coverage

**Files:**
- Modify: `tests/test_workflow_engine_graph.py`
- Modify: `app/orchestrator/workflow.py`

- [ ] **Step 1: Write the failing test**

```python
import pytest
from app.orchestrator.workflow import WorkflowEngine


def test_validate_graph_rejects_cycles():
    engine = WorkflowEngine()
    nodes = engine.load_workflow(
        {
            "nodes": [
                {"id": "a", "step": "one", "depends_on": ["b"]},
                {"id": "b", "step": "two", "depends_on": ["a"]},
            ]
        }
    )

    with pytest.raises(ValueError, match="cycle"):
        engine.validate_graph(nodes)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_workflow_engine_graph.py::test_validate_graph_rejects_cycles -v`
Expected: FAIL because `WorkflowEngine.validate_graph` does not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
def validate_graph(self, nodes: List[WorkflowNode]) -> None:
    # detect cycles with a depth-first traversal
    ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_workflow_engine_graph.py::test_validate_graph_rejects_cycles -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_workflow_engine_graph.py app/orchestrator/workflow.py
git commit -m "feat: validate workflow graphs before execution"
```

### Task 2: Make skipped workflow nodes persist and satisfy dependencies

**Files:**
- Modify: `tests/test_workflow_engine_graph.py`
- Modify: `app/orchestrator/workflow.py`
- Modify: `app/orchestrator/core.py`
- Modify: `app/memory/long_term.py`
- Modify: `app/memory/models.py`

- [ ] **Step 1: Write the failing test**

```python
import asyncio
from app.orchestrator.workflow import WorkflowEngine


def test_execute_graph_marks_false_condition_as_skipped_and_allows_downstream():
    engine = WorkflowEngine()
    workflow = engine.load_workflow(
        {
            "nodes": [
                {"id": "a", "step": "one", "depends_on": []},
                {"id": "b", "step": "two", "depends_on": ["a"], "condition": "context['run_b']"},
                {"id": "c", "step": "three", "depends_on": ["b"]},
            ]
        }
    )

    seen = []

    async def run_node(node, context):
        seen.append(node.id)
        return {"node_id": node.id}

    result = asyncio.run(engine.execute_graph(workflow, {"run_node": run_node}, {"run_b": False}))

    assert seen == ["a", "c"]
    assert result["nodes"]["b"]["status"] == "skipped"
    assert result["nodes"]["c"]["status"] == "completed"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_workflow_engine_graph.py::test_execute_graph_marks_false_condition_as_skipped_and_allows_downstream -v`
Expected: FAIL because skipped nodes are not treated as satisfied dependencies yet.

- [ ] **Step 3: Write minimal implementation**

```python
def _dependency_satisfied(self, node_id: str, completed: set[str], skipped: set[str]) -> bool:
    return node_id in completed or node_id in skipped
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_workflow_engine_graph.py::test_execute_graph_marks_false_condition_as_skipped_and_allows_downstream -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_workflow_engine_graph.py app/orchestrator/workflow.py app/orchestrator/core.py app/memory/long_term.py app/memory/models.py
git commit -m "fix: persist skipped workflow nodes"
```

### Task 3: Route execution through Celery only

**Files:**
- Modify: `tests/test_orchestrator_task_identity.py`
- Modify: `app/api/routes/tasks.py`
- Modify: `app/queue/tasks.py`
- Modify: `app/orchestrator/core.py`

- [ ] **Step 1: Write the failing test**

```python
from uuid import uuid4
from app.api.routes.tasks import use_celery


def test_create_task_enqueues_celery_task(monkeypatch):
    sent = {}

    class DummyCelery:
        def send_task(self, name, args, task_id):
            sent["name"] = name
            sent["args"] = args
            sent["task_id"] = task_id

    monkeypatch.setattr("app.api.routes.tasks.celery_app", DummyCelery())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_orchestrator_task_identity.py -v`
Expected: FAIL because the route still mixes background tasks and Celery fallback behavior.

- [ ] **Step 3: Write minimal implementation**

```python
# API creates DB row, then always enqueues Celery.
# Worker updates task status to running/completed/failed.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_orchestrator_task_identity.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_orchestrator_task_identity.py app/api/routes/tasks.py app/queue/tasks.py app/orchestrator/core.py
git commit -m "feat: move task execution behind celery"
```

### Task 4: Expose full workflow state in task responses

**Files:**
- Modify: `app/api/routes/tasks.py`
- Modify: `tests/test_task_steps_persisted.py`
- Modify: `app/memory/long_term.py`

- [ ] **Step 1: Write the failing test**

```python
def test_task_response_includes_workflow_nodes_and_edges():
    ...
    assert "workflow" in response.model_dump()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_task_steps_persisted.py -v`
Expected: FAIL because the API does not yet return workflow state.

- [ ] **Step 3: Write minimal implementation**

```python
return TaskStatusResponse(..., workflow={"nodes": ..., "edges": ...})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_task_steps_persisted.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_task_steps_persisted.py app/api/routes/tasks.py app/memory/long_term.py
git commit -m "feat: expose workflow state in task responses"
```

### Task 5: Verify end-to-end worker lifecycle and repository consistency

**Files:**
- Modify: `tests/test_task_steps_persisted.py`
- Modify: `tests/test_workflow_engine_graph.py`
- Modify: `app/queue/tasks.py`
- Modify: `app/orchestrator/workflow.py`

- [ ] **Step 1: Write the failing test**

```python
def test_worker_marks_task_running_before_execution(monkeypatch):
    ...
    assert task.status == "running"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests -v`
Expected: FAIL until the worker updates DB state before and after orchestration.

- [ ] **Step 3: Write minimal implementation**

```python
# worker updates task_repo to running, then calls orchestrator, then persists terminal status
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_task_steps_persisted.py tests/test_workflow_engine_graph.py app/queue/tasks.py app/orchestrator/workflow.py
git commit -m "test: harden workflow execution lifecycle"
```
