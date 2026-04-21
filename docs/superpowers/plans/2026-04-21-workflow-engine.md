# Workflow Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace linear step batching with persisted graph-based workflow execution supporting parallel and conditional nodes.

**Architecture:** Add workflow header/node/edge models to the existing SQLAlchemy layer, then replace the current batching loop with a DAG executor that runs ready nodes in parallel. The orchestrator will still manage planner, executor, and verifier phases, but planner output will be normalized into a workflow graph before execution and persisted alongside the task.

**Tech Stack:** Python, FastAPI, SQLAlchemy async, asyncio, pytest.

---

### Task 1: Add workflow persistence models

**Files:**
- Modify: `app/memory/models.py:1-132`
- Modify: `app/memory/long_term.py:1-608`
- Test: `tests/test_workflow_persistence.py`

- [ ] **Step 1: Write the failing test**

```python
import asyncio
from uuid import uuid4

import pytest

from app.memory.long_term import db, workflow_repo


def test_workflow_can_persist_nodes_and_edges():
    workflow_id = str(uuid4())
    task_id = str(uuid4())

    async def run():
        try:
            await db.connect()
        except ModuleNotFoundError:
            pytest.skip("asyncpg is not installed in this environment")
        workflow = await workflow_repo.create(task_id=task_id, name="demo", definition={"nodes": []})
        await db.disconnect()
        return workflow

    workflow = asyncio.run(run())

    assert workflow.task_id == task_id
    assert workflow.name == "demo"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_workflow_persistence.py -v`
Expected: FAIL because `workflow_repo` and workflow models do not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
class WorkflowModel(Base):
    __tablename__ = "workflows"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    task_id = Column(String(36), nullable=False, index=True)
    name = Column(String(100), nullable=True)
    definition = Column(JSON, nullable=True)
    status = Column(String(20), default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

```python
class WorkflowRepository:
    async def create(self, task_id: str, name: str, definition: Optional[Dict[str, Any]] = None):
        async with db.get_session() as session:
            workflow = WorkflowModel(task_id=task_id, name=name, definition=definition or {})
            session.add(workflow)
            await session.commit()
            await session.refresh(workflow)
            return workflow


workflow_repo = WorkflowRepository()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_workflow_persistence.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/memory/models.py app/memory/long_term.py tests/test_workflow_persistence.py
git commit -m "feat: persist workflow graphs"
```

### Task 2: Replace placeholder workflow engine with DAG execution

**Files:**
- Modify: `app/orchestrator/workflow.py:1-64`
- Test: `tests/test_workflow_engine_graph.py`

- [ ] **Step 1: Write the failing test**

```python
def test_execute_graph_runs_dependencies_before_dependents_and_skips_false_conditions():
    ...
    result = asyncio.run(engine.execute_graph(workflow, {"run_node": run_node}, {}))
    assert seen == ["a", "b"]
    assert result["nodes"]["c"]["status"] == "skipped"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_workflow_engine_graph.py -v`
Expected: FAIL because `execute_graph` does not exist.

- [ ] **Step 3: Write minimal implementation**

```python
async def execute_graph(self, nodes: List[WorkflowNode], runtime: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    ...
```

Implement:
- ready-node discovery from dependencies
- parallel execution with `asyncio.gather`
- per-node condition evaluation
- `SKIPPED` state when condition is false
- terminal-state aggregation

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_workflow_engine_graph.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/orchestrator/workflow.py tests/test_workflow_engine_graph.py
git commit -m "feat: execute workflows as graphs"
```

### Task 3: Integrate workflow graphs into the orchestrator

**Files:**
- Modify: `app/orchestrator/core.py:1-495`
- Modify: `app/api/routes/tasks.py:1-270`
- Test: `tests/test_orchestrator_task_identity.py`

- [ ] **Step 1: Write the failing test**

```python
def test_execute_task_persists_workflow_and_preserves_provided_task_id():
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_orchestrator_task_identity.py -v`
Expected: FAIL because workflow persistence is not wired into task execution.

- [ ] **Step 3: Write minimal implementation**

Replace `_batch_steps` usage with workflow persistence + graph execution.
Persist the workflow snapshot before execution and update task result payloads to include workflow/node status output.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_orchestrator_task_identity.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/orchestrator/core.py app/api/routes/tasks.py tests/test_orchestrator_task_identity.py
git commit -m "feat: route orchestration through workflows"
```

### Task 4: Verify the full stack and clean up response shapes

**Files:**
- Modify: `app/api/routes/tasks.py:1-270`
- Modify: `app/memory/long_term.py:1-608`
- Modify: `app/orchestrator/core.py:1-495`
- Test: `tests/test_task_steps_persisted.py`

- [ ] **Step 1: Write the failing test**

```python
def test_task_details_include_workflow_nodes_after_execution():
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_task_steps_persisted.py -v`
Expected: FAIL until the task detail endpoint can surface workflow-backed execution data.

- [ ] **Step 3: Write minimal implementation**

Expose workflow-backed node summaries from the task detail endpoint while keeping the existing `steps` response field intact for compatibility.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_task_steps_persisted.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/api/routes/tasks.py app/memory/long_term.py app/orchestrator/core.py tests/test_task_steps_persisted.py
git commit -m "feat: expose workflow execution details"
```

### Task 5: Run full verification

**Files:**
- No code changes expected

- [ ] **Step 1: Run the full test suite**

Run: `pytest`
Expected: PASS.

- [ ] **Step 2: Build or sanity-check the app**

Run: `python -m compileall app tests`
Expected: PASS.

- [ ] **Step 3: Review for regressions**

Confirm:
- graph execution respects dependency order
- conditional nodes are skipped
- skipped nodes are terminal
- workflows are persisted and linked to tasks
- orchestrator still returns task results successfully
