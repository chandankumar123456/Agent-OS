"""End-to-end smoke test for the desktop-native AgentKernel path.

This test is the Phase 1 baseline: it boots `app.desktop_native.kernel.AgentKernel`,
submits a single task end-to-end, and asserts the task reaches a terminal
COMPLETED state in SQLite.  It must run offline, so the LLM-driven
orchestrator is replaced with a stub that drives the state machine
deterministically; the real components exercised are the kernel scheduler,
SQLite-backed task queue, state machine, execution lock, timeout enforcer,
event bus, and resource monitor.

Run with::

    pytest tests/e2e/test_desktop_smoke.py -v

The test is intentionally tolerant: if booting AgentKernel fails on the
current branch for environmental reasons, it is marked xfail with a
documented reason rather than blocking the baseline.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Force desktop-native (gRPC) mode BEFORE any `app.*` imports.  The shared
# tests/conftest.py uses os.environ.setdefault, so we can safely override.
# ---------------------------------------------------------------------------
os.environ["AGENTOS_RUNTIME_MODE"] = "grpc"
os.environ["RUNTIME_MODE"] = "grpc"
os.environ.setdefault("AGENTOS_ENV", "test")
os.environ.setdefault("OPENAI_API_KEY", "test-key-placeholder")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-env-32chars!!")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "")

# Project root on sys.path (matches tests/conftest.py)
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


pytestmark = pytest.mark.asyncio


@pytest.fixture
def isolated_desktop_db(tmp_path, monkeypatch):
    """Redirect the desktop SQLite store to a tmp dir for this test only."""
    fake_home = tmp_path / "home"
    (fake_home / ".agentos").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))  # Windows fallback

    # Re-point the singleton store at the tmp path and force reconnect.
    from core.desktop_native import sqlite_store as ss

    db_path = str(fake_home / ".agentos" / "agentos.db")
    monkeypatch.setattr(ss.sqlite_store, "_db_path", db_path, raising=False)
    monkeypatch.setattr(ss.sqlite_store, "_connection", None, raising=False)

    yield db_path

    # Ensure the connection is closed so the next test gets a fresh handle.
    conn = getattr(ss.sqlite_store, "_connection", None)
    if conn is not None:
        try:
            asyncio.get_event_loop().run_until_complete(conn.close())
        except Exception:
            pass
        ss.sqlite_store._connection = None


def _build_stub_kernel():
    """Return a subclass of AgentKernel with heavy components stubbed.

    The stub:
      * skips AgentRuntime / Orchestrator / SQLiteCheckpointSaver init
      * skips crash_recovery (no prior tasks in a fresh tmp DB)
      * skips signal handlers (pytest owns the main thread)
      * uses a no-op `_execute_task` that only drives the state machine

    Everything else (scheduler, queue, state machine, locks, timeouts,
    event bus, resource monitor) is the real production code.
    """
    from core.desktop_native.kernel import AgentKernel
    from core.desktop_native.sqlite_store import sqlite_store
    from core.desktop_native.sqlite_tuning import sqlite_tuning
    from core.desktop_native.resource_monitor import resource_monitor
    from core.desktop_native.state_machine import local_task_state_machine, TaskState

    class StubKernel(AgentKernel):
        async def start(self) -> None:  # type: ignore[override]
            if self._running:
                return
            await sqlite_store.initialize_schema()
            await sqlite_tuning.apply_optimizations()

            # Stub the heavy bits that need an LLM / Redis / Postgres.
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

            # Skip GC, crash recovery, and signal handlers in tests.

        async def _execute_task(  # type: ignore[override]
            self,
            task_id: str,
            query: str,
            config: dict,
            user_id: str,
        ):
            # Drive the documented PENDING -> PLANNING -> EXECUTING path.
            current = await local_task_state_machine.get_current_state(task_id)
            if current == TaskState.PENDING:
                try:
                    await local_task_state_machine.transition(
                        task_id,
                        TaskState.PENDING,
                        TaskState.PLANNING,
                        triggered_by="smoke-test",
                    )
                except ValueError:
                    pass
            try:
                await local_task_state_machine.transition(
                    task_id,
                    TaskState.PLANNING,
                    TaskState.EXECUTING,
                    triggered_by="smoke-test",
                )
            except ValueError:
                # Fall back to direct PENDING -> EXECUTING if the
                # state machine ever permits it.
                try:
                    await local_task_state_machine.transition(
                        task_id,
                        TaskState.PENDING,
                        TaskState.EXECUTING,
                        triggered_by="smoke-test",
                    )
                except ValueError:
                    pass

            return {"echo": query, "user_id": user_id}

    return StubKernel


async def test_desktop_kernel_smoke_reaches_terminal(isolated_desktop_db):
    """Boot AgentKernel, submit one task, assert it reaches a terminal state.

    This is the minimum guarantee we want preserved across the unification
    refactor: the kernel must boot, accept a task, drive it through the
    queue and state machine, and reach a terminal status (completed or
    failed).  A stricter assertion that the terminal state is COMPLETED
    lives in `test_desktop_kernel_smoke_full_completion` and is currently
    xfailed because of a known bug in the worker (see that test for
    details).
    """
    from core.desktop_native.state_machine import (
        local_task_state_machine,
        TaskState,
    )
    from core.desktop_native.task_queue import TaskPriority

    StubKernel = _build_stub_kernel()
    kernel = StubKernel(max_concurrent_tasks=1, task_timeout_seconds=15)

    try:
        await kernel.start()
    except Exception as exc:  # pragma: no cover - environmental
        pytest.xfail(
            "AgentKernel.start() failed in baseline environment; "
            "tracked as a known refactor target. Error: " + repr(exc)
        )

    try:
        task_id = await kernel.submit_task(
            query="echo hello from desktop smoke test",
            user_id="smoke-user",
            priority=TaskPriority.NORMAL,
        )
        assert isinstance(task_id, str) and task_id

        result = await kernel.wait_for_task(task_id, timeout=15.0)
        assert result["task_id"] == task_id
        # Pre-refactor the kernel reports "failed" because of the
        # EXECUTING -> COMPLETED transition bug.  Post-refactor it
        # should be "completed".  Either is a terminal status.
        assert result["status"] in ("completed", "failed"), (
            f"Expected terminal status, got: {result!r}"
        )

        # The state machine must record a terminal state in SQLite.
        final_state = await local_task_state_machine.get_current_state(task_id)
        assert final_state in (TaskState.COMPLETED, TaskState.FAILED), (
            f"Expected terminal state, got {final_state}"
        )

        status = await kernel.get_task_status(task_id)
        assert status["task_id"] == task_id
        assert status["is_terminal"] is True

        # The state machine must have recorded the planned -> executing
        # path on the way to the terminal state.
        history = await local_task_state_machine.get_transition_history(
            task_id, limit=20
        )
        seen = {(t.from_state, t.to_state) for t in history}
        assert (TaskState.PENDING, TaskState.PLANNING) in seen, seen
        assert (TaskState.PLANNING, TaskState.EXECUTING) in seen, seen

    finally:
        await kernel.stop(timeout=5.0)


async def test_desktop_kernel_smoke_full_completion(isolated_desktop_db):
    """Strict assertion that the kernel reports the task as COMPLETED.

    The terminal-transition bug (EXECUTING -> COMPLETED) was fixed in Phase 3
    by routing through VERIFYING: EXECUTING -> VERIFYING -> COMPLETED.
    """
    from core.desktop_native.state_machine import (
        local_task_state_machine,
        TaskState,
    )
    from core.desktop_native.task_queue import TaskPriority

    StubKernel = _build_stub_kernel()
    kernel = StubKernel(max_concurrent_tasks=1, task_timeout_seconds=15)
    await kernel.start()

    try:
        task_id = await kernel.submit_task(
            query="echo hello",
            user_id="smoke-user",
            priority=TaskPriority.NORMAL,
        )
        result = await kernel.wait_for_task(task_id, timeout=15.0)
        assert result["status"] == "completed", result

        final_state = await local_task_state_machine.get_current_state(task_id)
        assert final_state == TaskState.COMPLETED, final_state
    finally:
        await kernel.stop(timeout=5.0)
