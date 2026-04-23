# Phase 7 Cleanup + Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove legacy execution paths, align API contracts end-to-end, and strip broken or placeholder UI behavior without adding new features.

**Architecture:** Make the database the only source of truth for persisted backend state, normalize task/workflow status casing in API responses, and tighten frontend types so they mirror backend payloads exactly. Remove dead UI controls that do not map to real backend behavior and keep auth enforced on all protected routes.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy async, React, TypeScript, Vite, pytest, npm build.

---

### Task 1: Normalize task API contract

**Files:**
- Modify: `app/api/routes/tasks.py`
- Modify: `tests/test_phase6_observability.py`

- [ ] **Step 1: Write the failing test**

```python
def test_get_task_returns_lowercase_statuses(monkeypatch):
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

    assert response.steps[0]["status"] == "completed"
    assert response.workflow_state["nodes"][0]["status"] == "completed"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_phase6_observability.py::test_get_task_returns_lowercase_statuses -v`
Expected: FAIL because the route still uppercases node/workflow statuses.

- [ ] **Step 3: Write minimal implementation**

```python
def _status_label(value: Any) -> Any:
    return value.lower() if isinstance(value, str) else value
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_phase6_observability.py::test_get_task_returns_lowercase_statuses -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/api/routes/tasks.py tests/test_phase6_observability.py
git commit -m "fix: align task API status casing"
```

### Task 2: Remove backend fallback state

**Files:**
- Modify: `app/memory/long_term.py`
- Modify: `tests/test_task_steps_persisted.py`

- [ ] **Step 1: Write the failing test**

```python
import pytest

from app.memory.long_term import task_repo


def test_task_repo_get_raises_without_db(monkeypatch):
    async def fail_session():
        raise RuntimeError("db offline")

    monkeypatch.setattr("app.memory.long_term.db.get_session", fail_session)

    async def run():
        await task_repo.get("task-1")

    with pytest.raises(RuntimeError, match="db offline"):
        asyncio.run(run())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_task_steps_persisted.py::test_task_repo_get_raises_without_db -v`
Expected: FAIL because the repository still falls back to in-memory task storage.

- [ ] **Step 3: Write minimal implementation**

```python
class TaskRepository:
    async def get(self, task_id: str) -> Optional[TaskModel]:
        async with db.get_session() as session:
            result = await session.execute(select(TaskModel).where(TaskModel.id == task_id))
            return result.scalar_one_or_none()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_task_steps_persisted.py::test_task_repo_get_raises_without_db -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/memory/long_term.py tests/test_task_steps_persisted.py
git commit -m "refactor: remove task repository fallback state"
```

### Task 3: Remove broken UI actions

**Files:**
- Modify: `frontend/src/pages/Orchestrator.tsx`
- Modify: `frontend/src/pages/Landing.tsx`
- Modify: `frontend/src/pages/AgentBuilder.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
import { render, screen } from '@testing-library/react';
import Landing from './Landing';

test('landing does not expose a fake documentation action', () => {
  render(<Landing />);
  expect(screen.queryByText('View Documentation')).toBeNull();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- --runInBand src/pages/Landing.test.tsx`
Expected: FAIL because the placeholder button still renders.

- [ ] **Step 3: Write minimal implementation**

```tsx
// Remove the placeholder button and the demo execute button.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- --runInBand src/pages/Landing.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Orchestrator.tsx frontend/src/pages/Landing.tsx frontend/src/pages/AgentBuilder.tsx frontend/src/pages/Landing.test.tsx
git commit -m "fix: remove placeholder frontend actions"
```
