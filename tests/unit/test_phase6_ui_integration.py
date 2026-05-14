"""Phase 6 UI Integration & Polish validation tests.

Tests the Tauri GUI integration from the Python side:
- TauriBridge event emission
- Native notification triggers
- Task history recording and retrieval
- Task statistics for dashboard
"""

import asyncio
import os

import pytest
import pytest_asyncio

os.environ.setdefault("AGENTOS_RUNTIME_MODE", "grpc")
os.environ.setdefault("RUNTIME_MODE", "grpc")

from app.desktop_native.sqlite_store import sqlite_store
from app.desktop_native.tauri_bridge import tauri_bridge, TauriBridge


@pytest_asyncio.fixture(autouse=True)
async def init_sqlite():
    await sqlite_store.initialize_schema()
    # Clear GUI-related tables before each test
    try:
        await sqlite_store.execute("DELETE FROM gui_task_history")
        await sqlite_store.execute("DELETE FROM alerts")
        await sqlite_store.commit()
    except Exception:
        pass
    yield


class TestTauriBridge:
    @pytest.mark.asyncio
    async def test_emit_event(self):
        bridge = TauriBridge()
        result = await bridge.emit_event("test:event", {"key": "value"})
        assert result is True

    @pytest.mark.asyncio
    async def test_show_notification(self):
        bridge = TauriBridge()
        bridge.set_notifications_enabled(True)
        result = await bridge.show_notification("Test Title", "Test Body")
        assert result is True

    @pytest.mark.asyncio
    async def test_show_notification_disabled(self):
        bridge = TauriBridge()
        bridge.set_notifications_enabled(False)
        result = await bridge.show_notification("Test Title", "Test Body")
        assert result is False

    @pytest.mark.asyncio
    async def test_notify_task_complete_success(self):
        bridge = TauriBridge()
        result = await bridge.notify_task_complete("task-1", "Open Notepad", True, "Done")
        assert result is True

    @pytest.mark.asyncio
    async def test_notify_task_complete_failure(self):
        bridge = TauriBridge()
        result = await bridge.notify_task_complete("task-2", "Open Chrome", False, "Error")
        assert result is True

    @pytest.mark.asyncio
    async def test_notify_approval_required(self):
        bridge = TauriBridge()
        result = await bridge.notify_approval_required("task-3", "desktop_env__click", "Click on sensitive area")
        assert result is True

    @pytest.mark.asyncio
    async def test_record_and_get_task_history(self):
        bridge = TauriBridge()
        await bridge.record_task_for_gui(
            "task-gui-1",
            "Open Notepad",
            "completed",
            result="File opened",
            duration_seconds=5.0,
        )
        await bridge.record_task_for_gui(
            "task-gui-2",
            "Type hello",
            "failed",
            error="Window not found",
        )

        history = await bridge.get_task_history(limit=10)
        assert len(history) == 2

        # Check both tasks are present (ordering may vary if same timestamp)
        task_ids = {h["task_id"] for h in history}
        assert "task-gui-1" in task_ids
        assert "task-gui-2" in task_ids

    @pytest.mark.asyncio
    async def test_get_task_history_by_status(self):
        bridge = TauriBridge()
        await bridge.record_task_for_gui("t1", "Query 1", "completed")
        await bridge.record_task_for_gui("t2", "Query 2", "failed")
        await bridge.record_task_for_gui("t3", "Query 3", "completed")

        completed = await bridge.get_task_history(status="completed", limit=10)
        assert len(completed) == 2
        assert all(t["status"] == "completed" for t in completed)

    @pytest.mark.asyncio
    async def test_get_task_stats(self):
        bridge = TauriBridge()
        await bridge.record_task_for_gui("s1", "Q1", "completed")
        await bridge.record_task_for_gui("s2", "Q2", "completed")
        await bridge.record_task_for_gui("s3", "Q3", "failed")
        await bridge.record_task_for_gui("s4", "Q4", "running")

        stats = await bridge.get_task_stats()
        assert stats["total"] == 4
        assert stats["completed"] == 2
        assert stats["failed"] == 1
        assert stats["running"] == 1

    @pytest.mark.asyncio
    async def test_cleanup_old_history(self):
        bridge = TauriBridge()
        # Insert a record with an old timestamp directly
        from datetime import datetime, timezone, timedelta
        old_time = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        await sqlite_store.execute(
            """
            INSERT INTO gui_task_history (task_id, query, status, created_at)
            VALUES (?, ?, ?, ?)
            """,
            ("old1", "Old query", "completed", old_time),
        )
        await sqlite_store.commit()

        # Clean up everything older than 5 days
        count = await bridge.cleanup_old_history(max_age_days=5)
        assert count >= 1

        history = await bridge.get_task_history(limit=10)
        assert len(history) == 0

    @pytest.mark.asyncio
    async def test_empty_task_history(self):
        bridge = TauriBridge()
        history = await bridge.get_task_history(limit=10)
        assert history == []

        stats = await bridge.get_task_stats()
        assert stats == {"total": 0, "completed": 0, "failed": 0, "running": 0}


class TestTauriBridgeWithKernel:
    """Integration tests with AgentKernel."""

    @pytest.mark.asyncio
    async def test_kernel_notifies_on_task_complete(self):
        """Verify that AgentKernel sends notifications through TauriBridge."""
        from app.desktop_native.kernel import AgentKernel

        kernel = AgentKernel(max_concurrent_tasks=1)
        await kernel.start()

        try:
            task_id = await kernel.submit_task(
                query="Simple test task",
                user_id="test_user",
            )

            # Wait for completion
            result = await kernel.wait_for_task(task_id, timeout=30.0)
            assert result["status"] in ("completed", "failed")

            # Give a moment for async recording to complete
            await asyncio.sleep(0.2)

            # Check that task was recorded in GUI history
            history = await tauri_bridge.get_task_history(limit=10)
            task_ids = [h["task_id"] for h in history]
            assert task_id in task_ids

        finally:
            await kernel.stop()

    @pytest.mark.asyncio
    async def test_kernel_task_stats_updated(self):
        """Verify that task stats are updated after kernel execution."""
        from app.desktop_native.kernel import AgentKernel

        kernel = AgentKernel(max_concurrent_tasks=1)
        await kernel.start()

        try:
            # Submit a task
            task_id = await kernel.submit_task(
                query="Another test task",
                user_id="test_user",
            )

            # Wait for it
            await kernel.wait_for_task(task_id, timeout=30.0)

            # Give a moment for async recording to complete
            await asyncio.sleep(0.2)

            # Check stats
            stats = await tauri_bridge.get_task_stats()
            assert stats["total"] >= 1

        finally:
            await kernel.stop()
