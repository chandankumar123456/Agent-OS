"""Phase 5 Observability & Memory Redesign validation tests.

Tests the desktop-native observability and memory systems:
- LocalLogger (rotating file logs)
- LocalMetrics (in-memory + SQLite)
- LocalTracer (SQLite spans)
- LocalAlertManager (alerts + history)
- MemoryHierarchy (working, short-term, long-term, episodic)
"""

import asyncio
import json
import os
import sys
import tempfile
from datetime import datetime, timezone

import pytest
import pytest_asyncio

os.environ.setdefault("AGENTOS_RUNTIME_MODE", "grpc")
os.environ.setdefault("RUNTIME_MODE", "grpc")

from app.desktop_native.sqlite_store import sqlite_store
from app.desktop_native.local_logger import LocalLogger
from app.desktop_native.local_metrics import local_metrics, LocalMetrics
from app.desktop_native.local_tracer import local_tracer, LocalTracer
from app.desktop_native.local_alerts import local_alerts, LocalAlertManager, AlertRule
from app.desktop_native.memory_hierarchy import memory_hierarchy, MemoryHierarchy


@pytest_asyncio.fixture(autouse=True)
async def init_sqlite():
    await sqlite_store.initialize_schema()
    # Clear observability tables before each test to avoid shared state
    try:
        await sqlite_store.execute("DELETE FROM traces")
        await sqlite_store.execute("DELETE FROM alerts")
        await sqlite_store.execute("DELETE FROM metrics_snapshots")
        await sqlite_store.execute("DELETE FROM episodic_memory")
        await sqlite_store.execute("DELETE FROM short_term_memory")
        await sqlite_store.execute("DELETE FROM long_term_memory")
        await sqlite_store.commit()
    except Exception:
        pass
    yield


class TestLocalLogger:
    def _close_logger(self, logger: LocalLogger):
        """Close all file handlers so temp dirs can be cleaned up."""
        for handler in logger._logger.handlers[:]:
            if hasattr(handler, "close"):
                handler.close()
            logger._logger.removeHandler(handler)

    @pytest.mark.asyncio
    async def test_log_to_file(self):
        tmpdir = tempfile.mkdtemp()
        try:
            logger = LocalLogger(log_dir=tmpdir)
            logger.initialize()
            logger.info("Test message", task_id="task-1", extra={"key": "value"})

            # Force flush by reading log files
            log_files = logger.get_log_files()
            assert len(log_files) > 0

            with open(log_files[0], "r") as f:
                content = f.read()
                assert "Test message" in content
                # Should be JSON
                record = json.loads(content.strip().split("\n")[-1])
                assert record["message"] == "Test message"
                assert record["level"] == "INFO"
                assert record["data"]["key"] == "value"
        finally:
            logger = LocalLogger(log_dir=tmpdir)
            logger.initialize()
            self._close_logger(logger)

    @pytest.mark.asyncio
    async def test_log_levels(self):
        tmpdir = tempfile.mkdtemp()
        try:
            logger = LocalLogger(log_dir=tmpdir)
            logger.initialize()
            logger.debug("debug msg")
            logger.info("info msg")
            logger.warning("warning msg")
            logger.error("error msg")
            logger.critical("critical msg")

            log_files = logger.get_log_files()
            assert len(log_files) > 0
        finally:
            logger = LocalLogger(log_dir=tmpdir)
            logger.initialize()
            self._close_logger(logger)

    @pytest.mark.asyncio
    async def test_log_task_and_tool(self):
        tmpdir = tempfile.mkdtemp()
        try:
            logger = LocalLogger(log_dir=tmpdir)
            logger.initialize()
            logger.log_task("task-123", "completed", result="success")
            logger.log_tool("desktop_env__click", "task-123", "success", x=100, y=200)

            log_files = logger.get_log_files()
            with open(log_files[0], "r") as f:
                content = f.read()
                assert "task_lifecycle" in content
                assert "tool_execution" in content
        finally:
            logger = LocalLogger(log_dir=tmpdir)
            logger.initialize()
            self._close_logger(logger)


class TestLocalMetrics:
    @pytest.mark.asyncio
    async def test_counter(self):
        metrics = LocalMetrics()
        metrics.inc_counter("tasks_completed", {"status": "success"}, 5)
        metrics.inc_counter("tasks_completed", {"status": "failed"}, 1)

        assert metrics.get_counter("tasks_completed", {"status": "success"}) == 5
        assert metrics.get_counter("tasks_completed", {"status": "failed"}) == 1

    @pytest.mark.asyncio
    async def test_gauge(self):
        metrics = LocalMetrics()
        metrics.set_gauge("memory_mb", 512.5)
        assert metrics.get_gauge("memory_mb") == 512.5

    @pytest.mark.asyncio
    async def test_histogram(self):
        metrics = LocalMetrics()
        metrics.observe_histogram("task_duration", 1.5)
        metrics.observe_histogram("task_duration", 2.5)
        stats = metrics.get_histogram_stats("task_duration")
        assert stats["count"] == 2
        assert stats["sum"] == 4.0
        assert stats["avg"] == 2.0

    @pytest.mark.asyncio
    async def test_snapshot_to_sqlite(self):
        metrics = LocalMetrics()
        metrics.inc_counter("test_counter", {}, 10)
        metrics.set_gauge("test_gauge", 100.0)
        metrics.observe_histogram("test_hist", 5.0)

        count = await metrics.snapshot()
        assert count > 0

        # After snapshot, in-memory data should be cleared
        assert metrics.get_counter("test_counter") == 0
        assert metrics.get_gauge("test_gauge") is None

    @pytest.mark.asyncio
    async def test_prometheus_format(self):
        metrics = LocalMetrics()
        metrics.inc_counter("http_requests", {"method": "GET"}, 10)
        metrics.set_gauge("active_tasks", 5.0, {})
        output = metrics.get_prometheus_format()
        assert "http_requests" in output
        assert "active_tasks" in output
        assert "counter" in output
        assert "gauge" in output

    @pytest.mark.asyncio
    async def test_query_history(self):
        metrics = LocalMetrics()
        metrics.inc_counter("my_metric", {}, 1)
        await metrics.snapshot()

        history = await metrics.query_history("my_metric", minutes=60)
        assert len(history) > 0
        assert history[0]["metric_name"] == "my_metric"


class TestLocalTracer:
    @pytest.mark.asyncio
    async def test_start_end_span(self):
        tracer = LocalTracer()
        span_id = tracer.start_span("trace-1", "planner", "plan_task", {"query": "hello"})
        assert span_id is not None
        tracer.end_span(span_id, status="success")

        span = tracer._spans[span_id]
        assert span.status == "success"
        assert span.end_time is not None

    @pytest.mark.asyncio
    async def test_persist_span(self):
        tracer = LocalTracer()
        span_id = tracer.start_span("trace-2", "executor", "execute_tool")
        tracer.end_span(span_id, status="success")
        result = await tracer.persist_span(span_id)
        assert result is True

        # Verify in SQLite
        db_span = await tracer.get_span(span_id)
        assert db_span is not None
        assert db_span["trace_id"] == "trace-2"
        assert db_span["status"] == "success"

    @pytest.mark.asyncio
    async def test_get_trace(self):
        tracer = LocalTracer()
        s1 = tracer.start_span("trace-3", "planner", "plan")
        s2 = tracer.start_span("trace-3", "executor", "execute")
        tracer.end_span(s1, "success")
        tracer.end_span(s2, "success")
        await tracer.persist_all()

        trace = await tracer.get_trace("trace-3")
        assert len(trace) == 2

    @pytest.mark.asyncio
    async def test_list_recent(self):
        tracer = LocalTracer()
        for i in range(5):
            sid = tracer.start_span(f"trace-{i}", "agent", f"op-{i}")
            tracer.end_span(sid, "success")
        await tracer.persist_all()

        recent = await tracer.list_recent(limit=3)
        assert len(recent) == 3


class TestLocalAlertManager:
    @pytest.mark.asyncio
    async def test_fire_and_acknowledge(self):
        alerts = LocalAlertManager()
        await alerts.initialize()

        fired = await alerts.fire("test_rule", "Test alert message", severity="warning")
        assert fired is True

        active = await alerts.list_active()
        assert len(active) == 1
        assert active[0]["message"] == "Test alert message"

        await alerts.acknowledge(active[0]["id"])
        active_after = await alerts.list_active()
        assert len(active_after) == 0

    @pytest.mark.asyncio
    async def test_cooldown(self):
        alerts = LocalAlertManager()
        await alerts.initialize()
        alerts.register_rule(AlertRule("cooldown_rule", "test", cooldown_seconds=3600))

        fired1 = await alerts.fire("cooldown_rule", "First alert")
        assert fired1 is True

        fired2 = await alerts.fire("cooldown_rule", "Second alert")
        assert fired2 is False  # Suppressed by cooldown

    @pytest.mark.asyncio
    async def test_handler(self):
        alerts = LocalAlertManager()
        await alerts.initialize()

        received = []
        def handler(rule, severity, message, details):
            received.append((rule, severity, message))

        alerts.add_handler(handler)
        await alerts.fire("handler_test", "Handler test message", severity="error")

        assert len(received) == 1
        assert received[0][0] == "handler_test"
        assert received[0][1] == "error"


class TestMemoryHierarchy:
    @pytest.mark.asyncio
    async def test_working_memory(self):
        mem = MemoryHierarchy()
        await mem.working.set("task-1", {"query": "hello"})
        result = await mem.working.get("task-1")
        assert result == {"query": "hello"}

        await mem.working.delete("task-1")
        result = await mem.working.get("task-1")
        assert result is None

    @pytest.mark.asyncio
    async def test_short_term_memory(self):
        mem = MemoryHierarchy()
        await mem.short_term.store("pref-theme", "dark", ttl_seconds=3600)
        result = await mem.short_term.retrieve("pref-theme")
        assert result == "dark"

        # Test expiration
        await mem.short_term.store("expiring", "value", ttl_seconds=-1)
        result = await mem.short_term.retrieve("expiring")
        assert result is None

    @pytest.mark.asyncio
    async def test_short_term_prune(self):
        mem = MemoryHierarchy()
        await mem.short_term.store("old", "value", ttl_seconds=-1)
        count = await mem.short_term.prune_expired()
        assert count >= 1

    @pytest.mark.asyncio
    async def test_long_term_memory(self):
        mem = MemoryHierarchy()
        await mem.long_term.store("doc-1", "AgentOS is a desktop AI runtime")
        result = await mem.long_term.retrieve("doc-1")
        assert result is not None
        assert result["content"] == "AgentOS is a desktop AI runtime"

    @pytest.mark.asyncio
    async def test_long_term_search(self):
        mem = MemoryHierarchy()
        await mem.long_term.store("doc-2", "Python asyncio is great")
        await mem.long_term.store("doc-3", "Machine learning basics")

        results = await mem.long_term.search("asyncio")
        assert len(results) >= 1
        assert any("asyncio" in r["content"] for r in results)

    @pytest.mark.asyncio
    async def test_episodic_memory(self):
        mem = MemoryHierarchy()
        await mem.episodic.record(
            task_id="task-1",
            query="Open Notepad",
            outcome="success",
            summary="Opened Notepad successfully",
            tools_used=["desktop_env__open_application"],
            duration_seconds=5.2,
        )

        episodes = await mem.episodic.list_recent(limit=10)
        assert len(episodes) == 1
        assert episodes[0]["outcome"] == "success"
        assert episodes[0]["tools_used"] == ["desktop_env__open_application"]

    @pytest.mark.asyncio
    async def test_episodic_similar(self):
        mem = MemoryHierarchy()
        await mem.episodic.record("task-2", "Open Notepad and type hello", "success")
        await mem.episodic.record("task-3", "Calculate 2+2", "success")

        similar = await mem.episodic.get_similar("Open Notepad", limit=5)
        assert len(similar) >= 1

    @pytest.mark.asyncio
    async def test_memory_gc(self):
        mem = MemoryHierarchy()
        await mem.short_term.store("gc_test", "value", ttl_seconds=-1)
        await mem.episodic.record("old-task", "Old query", "success")

        await mem.gc()
        # After GC, expired short-term entries should be gone
        result = await mem.short_term.retrieve("gc_test")
        assert result is None
