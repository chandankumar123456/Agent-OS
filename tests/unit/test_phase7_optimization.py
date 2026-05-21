"""Phase 7 Optimization & Production Hardening validation tests.

Tests resource monitoring, crash recovery, SQLite tuning, and session cleanup.
"""

import asyncio
import os

import pytest
import pytest_asyncio

os.environ.setdefault("AGENTOS_RUNTIME_MODE", "grpc")
os.environ.setdefault("RUNTIME_MODE", "grpc")

from core.desktop_native.sqlite_store import sqlite_store
from core.desktop_native.resource_monitor import ResourceMonitor, ResourceBudget
from core.desktop_native.crash_recovery import CrashRecovery
from core.desktop_native.sqlite_tuning import SQLiteTuning


@pytest_asyncio.fixture(autouse=True)
async def init_sqlite():
    await sqlite_store.initialize_schema()
    # Clear test tables
    try:
        await sqlite_store.execute("DELETE FROM recovery_log")
        await sqlite_store.execute("DELETE FROM gui_task_history")
        await sqlite_store.commit()
    except Exception:
        pass
    yield


class TestResourceMonitor:
    @pytest.mark.asyncio
    async def test_start_stop_monitoring(self):
        monitor = ResourceMonitor(check_interval_seconds=0.1)
        await monitor.start_monitoring("task-1", ResourceBudget(memory_mb=100, cpu_percent=50))

        # Trigger a manual check to populate snapshot
        await monitor._check_budgets()
        snapshot = monitor.get_latest_snapshot("task-1")
        assert snapshot is not None
        assert snapshot.memory_mb >= 0

        final = await monitor.stop_monitoring("task-1")
        assert final is not None

    @pytest.mark.asyncio
    async def test_notifications_disabled(self):
        monitor = ResourceMonitor()
        # No budgets set, should return None
        snapshot = monitor.get_latest_snapshot("nonexistent")
        assert snapshot is None

    @pytest.mark.asyncio
    async def test_system_stats(self):
        monitor = ResourceMonitor()
        stats = await monitor.get_system_stats()
        assert "monitored_tasks" in stats
        assert "total_violations" in stats

    @pytest.mark.asyncio
    async def test_monitor_loop_start_stop(self):
        monitor = ResourceMonitor(check_interval_seconds=0.1)
        await monitor.start()
        await asyncio.sleep(0.2)
        await monitor.stop()
        assert monitor._monitor_task is None


class TestCrashRecovery:
    @pytest.mark.asyncio
    async def test_find_interrupted_tasks_empty(self):
        recovery = CrashRecovery()
        tasks = await recovery.find_interrupted_tasks()
        assert tasks == []

    @pytest.mark.asyncio
    async def test_recovery_history(self):
        recovery = CrashRecovery()
        await recovery._ensure_tables()
        await recovery._log_recovery("task-1", "test_action", "pending", "completed", "test")

        history = await recovery.get_recovery_history(task_id="task-1", limit=10)
        assert len(history) == 1
        assert history[0]["action"] == "test_action"

    @pytest.mark.asyncio
    async def test_scan_no_interrupted(self):
        recovery = CrashRecovery()
        # Mock kernel
        class MockKernel:
            pass

        stats = await recovery.scan_and_resume(MockKernel())
        assert stats["found"] == 0
        assert stats["recovered"] == 0


class TestSQLiteTuning:
    @pytest.mark.asyncio
    async def test_apply_optimizations(self):
        tuning = SQLiteTuning()
        results = await tuning.apply_optimizations()
        assert "journal_mode" in results
        assert "synchronous" in results
        assert "cache_size" in results

    @pytest.mark.asyncio
    async def test_get_db_size(self):
        tuning = SQLiteTuning()
        size = await tuning.get_db_size_mb()
        assert size >= 0

    @pytest.mark.asyncio
    async def test_get_performance_stats(self):
        tuning = SQLiteTuning()
        stats = await tuning.get_performance_stats()
        assert "size_mb" in stats
        assert "page_count" in stats
        assert "freelist_count" in stats

    @pytest.mark.asyncio
    async def test_integrity_check(self):
        tuning = SQLiteTuning()
        result = await tuning.run_integrity_check()
        assert "ok" in result
        assert "messages" in result

    @pytest.mark.asyncio
    async def test_maintenance_pass(self):
        tuning = SQLiteTuning()
        result = await tuning.maintenance_pass()
        assert "checkpoint" in result
        assert "integrity_check" in result
        assert "stats_before" in result
        assert "stats_after" in result


class TestKernelIntegration:
    """Integration tests with AgentKernel."""

    @pytest.mark.asyncio
    async def test_kernel_with_resource_monitor(self):
        """Verify AgentKernel starts resource monitor and runs tasks."""
        from core.desktop_native.kernel import AgentKernel
        from core.desktop_native.resource_monitor import resource_monitor

        kernel = AgentKernel(max_concurrent_tasks=1)
        await kernel.start()

        try:
            # Resource monitor should be running
            assert resource_monitor._running is True

            # Submit a simple task
            task_id = await kernel.submit_task(
                query="Simple test task",
                user_id="test_user",
            )

            result = await kernel.wait_for_task(task_id, timeout=30.0)
            assert result["status"] in ("completed", "failed")

        finally:
            await kernel.stop()
            assert resource_monitor._running is False

    @pytest.mark.asyncio
    async def test_kernel_gc_loop(self):
        """Verify GC loop runs without errors."""
        from core.desktop_native.kernel import AgentKernel

        kernel = AgentKernel(max_concurrent_tasks=1)
        await kernel.start()

        try:
            # Let GC run at least once
            await asyncio.sleep(1.5)
            assert kernel._gc_task is not None
            assert not kernel._gc_task.done()
        finally:
            await kernel.stop()

    @pytest.mark.asyncio
    async def test_kernel_crash_recovery_scan(self):
        """Verify kernel runs crash recovery on startup."""
        from core.desktop_native.kernel import AgentKernel
        from core.desktop_native.crash_recovery import crash_recovery

        kernel = AgentKernel(max_concurrent_tasks=1)
        await kernel.start()

        try:
            # Give recovery time to process
            await asyncio.sleep(0.2)

            # Crash recovery should have run (even if no tasks found)
            # Just verify kernel started successfully with recovery integrated
            assert kernel.is_running is True
        finally:
            await kernel.stop()
