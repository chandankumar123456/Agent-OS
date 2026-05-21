"""Kernel soak test: rapid task submission and completion under load.

Marked with @pytest.mark.slow so it can be excluded from quick CI runs.
Tests:
- Submit ~10 tasks rapidly
- Verify they all reach a terminal state
- Basic validation that the scheduler handles concurrent work

Run with::

    pytest tests/e2e/test_kernel_soak.py -v --timeout=60
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

os.environ["AGENTOS_RUNTIME_MODE"] = "grpc"
os.environ["RUNTIME_MODE"] = "grpc"
os.environ.setdefault("AGENTOS_ENV", "test")
os.environ.setdefault("OPENAI_API_KEY", "test-key-placeholder")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-env-32chars!!")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "")

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


pytestmark = [pytest.mark.asyncio, pytest.mark.slow]


def _build_soak_kernel():
    """Build a stub kernel for soak testing with fast execution."""
    from core.desktop_native.kernel import AgentKernel
    from core.desktop_native.sqlite_store import sqlite_store
    from core.desktop_native.sqlite_tuning import sqlite_tuning
    from core.desktop_native.resource_monitor import resource_monitor

    class SoakKernel(AgentKernel):
        async def start(self):
            if self._running:
                return
            await sqlite_store.initialize_schema()
            await sqlite_tuning.apply_optimizations()
            self._runtime = MagicMock()
            self._orchestrator = MagicMock()
            self._checkpointer = MagicMock()
            await resource_monitor.start()
            self._running = True
            for i in range(self.max_concurrent):
                worker = asyncio.create_task(
                    self._worker_loop(f"worker-{i}"),
                    name=f"kernel_worker_{i}",
                )
                self._worker_tasks.add(worker)
                worker.add_done_callback(self._worker_tasks.discard)

        async def _execute_task(self, task_id, query, config, user_id):
            from core.desktop_native.state_machine import local_task_state_machine, TaskState

            current = await local_task_state_machine.get_current_state(task_id)
            if current == TaskState.PENDING:
                try:
                    await local_task_state_machine.transition(
                        task_id, TaskState.PENDING, TaskState.PLANNING,
                        triggered_by="soak-test",
                    )
                except ValueError:
                    pass
            try:
                await local_task_state_machine.transition(
                    task_id, TaskState.PLANNING, TaskState.EXECUTING,
                    triggered_by="soak-test",
                )
            except ValueError:
                pass
            # Simulate brief work
            await asyncio.sleep(0.05)
            return {"echo": query, "task_id": task_id}

    return SoakKernel


@pytest.fixture
async def soak_kernel(tmp_path, monkeypatch):
    """Create and start a kernel isolated to a temp DB."""
    from core.desktop_native.sqlite_store import sqlite_store

    db_path = str(tmp_path / "soak.db")
    monkeypatch.setattr(sqlite_store, "_db_path", db_path, raising=False)
    monkeypatch.setattr(sqlite_store, "_connection", None, raising=False)

    SoakKernel = _build_soak_kernel()
    kernel = SoakKernel(max_concurrent_tasks=4, task_timeout_seconds=30)
    await kernel.start()

    yield kernel

    await kernel.stop(timeout=5.0)

    conn = getattr(sqlite_store, "_connection", None)
    if conn is not None:
        try:
            await conn.close()
        except Exception:
            pass
        sqlite_store._connection = None


async def test_rapid_task_submission(soak_kernel):
    """Submit 10 tasks rapidly and verify they all reach terminal state."""
    from core.desktop_native.task_queue import TaskPriority
    from core.desktop_native.state_machine import local_task_state_machine, TaskState

    kernel = soak_kernel
    task_ids = []

    # Submit 10 tasks rapidly
    for i in range(10):
        task_id = await kernel.submit_task(
            query=f"soak task {i}",
            user_id="soak-user",
            priority=TaskPriority.NORMAL,
        )
        task_ids.append(task_id)
        assert task_id, f"Task {i} submission returned empty ID"

    assert len(task_ids) == 10

    # Wait for all tasks to reach terminal state
    results = await asyncio.gather(
        *[kernel.wait_for_task(tid, timeout=20.0) for tid in task_ids],
        return_exceptions=True,
    )

    completed = 0
    failed = 0
    errors = []

    for i, result in enumerate(results):
        if isinstance(result, Exception):
            errors.append((task_ids[i], str(result)))
            continue
        status = result.get("status", "unknown")
        if status == "completed":
            completed += 1
        elif status == "failed":
            failed += 1
        else:
            errors.append((task_ids[i], f"unexpected status: {status}"))

    # All tasks must reach terminal state
    terminal_count = completed + failed
    assert terminal_count == 10, (
        f"Expected all 10 tasks terminal, got {completed} completed, "
        f"{failed} failed, {len(errors)} errors: {errors}"
    )


async def test_concurrent_submission_no_crash(soak_kernel):
    """Submit tasks concurrently from multiple coroutines without crash."""
    from core.desktop_native.task_queue import TaskPriority

    kernel = soak_kernel

    async def submit_batch(start: int, count: int):
        ids = []
        for i in range(start, start + count):
            tid = await kernel.submit_task(
                query=f"concurrent task {i}",
                user_id="soak-user",
                priority=TaskPriority.NORMAL,
            )
            ids.append(tid)
        return ids

    # Launch 3 concurrent batches of 3 tasks each
    batches = await asyncio.gather(
        submit_batch(0, 3),
        submit_batch(3, 3),
        submit_batch(6, 3),
    )

    all_ids = [tid for batch in batches for tid in batch]
    assert len(all_ids) == 9

    # Wait for all to complete
    results = await asyncio.gather(
        *[kernel.wait_for_task(tid, timeout=20.0) for tid in all_ids],
        return_exceptions=True,
    )

    terminal = sum(
        1 for r in results
        if not isinstance(r, Exception) and r.get("status") in ("completed", "failed")
    )
    assert terminal == 9, f"Expected 9 terminal tasks, got {terminal}"
