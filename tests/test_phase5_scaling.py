import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from app.tools.cache import CacheOptimizer
from app.runtime.resource_limits import ResourceLimitEnforcer, ResourceGrant
from app.logs.anomaly import AnomalyDetector, AnomalySeverity
from app.logs.alerts import AlertManager, AlertRule, AlertChannel, AnomalySeverity as AlertSeverity
from app.logs.profiler import PerformanceProfiler
from app.runtime.scaling import HorizontalScalingCoordinator


# ---------------------------------------------------------------------------
# CacheOptimizer
# ---------------------------------------------------------------------------

class TestCacheOptimizer:
    @pytest.fixture
    def cache(self):
        return CacheOptimizer(default_ttl=60)

    @pytest.mark.asyncio
    async def test_cache_miss(self, cache):
        result = await cache.get_tool_result("filesystem__read_file", {"path": "/tmp/test"})
        assert result is None
        assert cache._misses == 1

    @pytest.mark.asyncio
    async def test_cache_hit_local(self, cache):
        await cache.set_tool_result("filesystem__read_file", {"path": "/tmp/test"}, {"content": "hello"})
        result = await cache.get_tool_result("filesystem__read_file", {"path": "/tmp/test"})
        assert result == {"content": "hello"}
        assert cache._hits == 1

    @pytest.mark.asyncio
    async def test_cache_key_determinism(self, cache):
        key1 = cache._cache_key("tool", {"a": 1, "b": 2})
        key2 = cache._cache_key("tool", {"b": 2, "a": 1})
        assert key1 == key2

    @pytest.mark.asyncio
    async def test_llm_cache(self, cache):
        await cache.set_llm_result([{"role": "user", "content": "hi"}], "openai", "gpt-4", "response")
        result = await cache.get_llm_result([{"role": "user", "content": "hi"}], "openai", "gpt-4")
        assert result == "response"

    @pytest.mark.asyncio
    async def test_stats(self, cache):
        await cache.set_tool_result("t", {"x": 1}, "v")
        await cache.get_tool_result("t", {"x": 1})
        await cache.get_tool_result("t", {"x": 2})
        stats = cache.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 0.5

    @pytest.mark.asyncio
    async def test_invalidate_tool(self, cache):
        await cache.set_tool_result("t", {"x": 1}, "v")
        count = await cache.invalidate_tool("t")
        assert count >= 1
        assert await cache.get_tool_result("t", {"x": 1}) is None

    @pytest.mark.asyncio
    async def test_redis_integration(self):
        mock_redis = MagicMock()
        mock_redis.client = AsyncMock()
        mock_redis.client.get = AsyncMock(return_value='{"cached": true}')
        mock_redis.client.set = AsyncMock(return_value=True)
        mock_redis.client.scan_iter = AsyncMock(return_value=[])

        cache = CacheOptimizer(redis=mock_redis)
        result = await cache.get_tool_result("tool", {"a": 1})
        assert result == {"cached": True}
        assert cache._hits == 1


# ---------------------------------------------------------------------------
# ResourceLimitEnforcer
# ---------------------------------------------------------------------------

class TestResourceLimitEnforcer:
    @pytest.fixture
    def enforcer(self):
        return ResourceLimitEnforcer(
            max_concurrent_agents=5,
            max_db_connections=10,
            max_redis_connections=8
        )

    @pytest.mark.asyncio
    async def test_acquire_agent(self, enforcer):
        assert await enforcer.acquire("agent") is True
        summary = await enforcer.get_usage_summary()
        assert summary["agents"]["used"] == 1
        await enforcer.release("agent")
        assert (await enforcer.get_usage_summary())["agents"]["used"] == 0

    @pytest.mark.asyncio
    async def test_agent_limit_enforced(self, enforcer):
        for _ in range(5):
            assert await enforcer.acquire("agent") is True
        assert await enforcer.acquire("agent") is False
        grant = await enforcer.check_resource_availability("agent", 1)
        assert grant.granted is False
        assert "limit reached" in grant.reason

    @pytest.mark.asyncio
    async def test_unknown_resource(self, enforcer):
        grant = await enforcer.check_resource_availability("gpu", 1)
        assert grant.granted is False
        assert "Unknown resource type" in grant.reason

    @pytest.mark.asyncio
    async def test_usage_summary(self, enforcer):
        await enforcer.acquire("db", 3)
        await enforcer.acquire("redis", 2)
        summary = await enforcer.get_usage_summary()
        assert summary["db_connections"]["used"] == 3
        assert summary["redis_connections"]["used"] == 2
        assert summary["agents"]["used"] == 0

    @pytest.mark.asyncio
    async def test_redis_integration(self):
        mock_redis = MagicMock()
        mock_redis.client = AsyncMock()
        mock_redis.client.get = AsyncMock(return_value="2")
        mock_redis.client.incrby = AsyncMock()

        enforcer = ResourceLimitEnforcer(max_concurrent_agents=5, redis=mock_redis)
        await enforcer.acquire("agent")
        mock_redis.client.incrby.assert_called()


# ---------------------------------------------------------------------------
# AnomalyDetector
# ---------------------------------------------------------------------------

class TestAnomalyDetector:
    @pytest.fixture
    def detector(self):
        return AnomalyDetector()

    def test_no_anomalies(self, detector):
        report = detector.analyze()
        assert report.severity == AnomalySeverity.INFO
        assert report.anomalies == []

    def test_error_rate_anomaly(self, detector):
        detector.record_error_rate(0.05)
        detector.record_error_rate(0.6)
        report = detector.analyze()
        assert any(a.metric == "error_rate" for a in report.anomalies)
        assert report.severity == AnomalySeverity.CRITICAL

    def test_latency_anomaly(self, detector):
        detector.record_latency(100)
        detector.record_latency(50000)
        report = detector.analyze()
        assert any(a.metric == "latency_ms" for a in report.anomalies)

    def test_cost_anomaly(self, detector):
        detector.record_cost(0.1)
        detector.record_cost(10.0)
        report = detector.analyze()
        assert any(a.metric == "cost_usd" for a in report.anomalies)

    def test_loop_anomaly(self, detector):
        detector.record_loop_count(5)
        report = detector.analyze()
        assert any(a.metric == "loop_count" for a in report.anomalies)
        assert report.severity == AnomalySeverity.CRITICAL

    def test_recommendations(self, detector):
        detector.record_error_rate(0.6)
        detector.record_latency(50000)
        report = detector.analyze()
        assert len(report.recommendations) >= 2

    def test_statistical_range(self, detector):
        for i in range(10):
            detector.record_latency(1000.0)
        detector.record_latency(100000.0)
        report = detector.analyze()
        assert any(a.metric == "latency_ms" for a in report.anomalies)

    def test_reset(self, detector):
        detector.record_error_rate(0.5)
        detector.reset()
        report = detector.analyze()
        assert report.anomalies == []


# ---------------------------------------------------------------------------
# AlertManager
# ---------------------------------------------------------------------------

class TestAlertManager:
    @pytest.fixture
    def manager(self):
        return AlertManager()

    def test_default_rules(self, manager):
        assert len(manager.rules) == 4
        rule_names = [r.name for r in manager.rules]
        assert "high_error_rate" in rule_names
        assert "critical_error_rate" in rule_names

    def test_add_remove_rule(self, manager):
        rule = AlertRule(name="test", metric="cpu", threshold=0.8, severity=AlertSeverity.WARNING, channels=[AlertChannel.LOG])
        manager.add_rule(rule)
        assert len(manager.rules) == 5
        assert manager.remove_rule("test") is True
        assert len(manager.rules) == 4

    def test_evaluate_error_rate(self, manager):
        manager.anomaly_detector.record_error_rate(0.6)
        alerts = manager.evaluate()
        assert len(alerts) >= 1
        assert any(a.triggered_rule == "critical_error_rate" for a in alerts)

    def test_cooldown(self, manager):
        manager.anomaly_detector.record_error_rate(0.6)
        alerts1 = manager.evaluate()
        assert len(alerts1) >= 1
        alerts2 = manager.evaluate()
        assert len(alerts2) == 0

    def test_alert_history(self, manager):
        manager.anomaly_detector.record_error_rate(0.6)
        manager.evaluate()
        history = manager.get_alert_history()
        assert len(history) >= 1
        manager.clear_history()
        assert len(manager.get_alert_history()) == 0

    def test_evaluate_no_metrics(self, manager):
        alerts = manager.evaluate()
        assert alerts == []


# ---------------------------------------------------------------------------
# PerformanceProfiler
# ---------------------------------------------------------------------------

class TestPerformanceProfiler:
    @pytest.fixture
    def profiler(self):
        return PerformanceProfiler()

    def test_start_task(self, profiler):
        profiler.start_task("task-1")
        assert "task-1" in profiler._task_start_times

    def test_record_step(self, profiler):
        profiler.start_task("task-1")
        profiler.record_step("task-1", "planner", 100)
        profiler.record_step("task-1", "executor", 200)
        assert len(profiler._profiles["task-1"]) == 2

    def test_profile_execution(self, profiler):
        profiler.start_task("task-1")
        profiler.record_step("task-1", "setup", 100)
        profiler.record_step("task-1", "llm_call", 8000)
        profiler.record_step("task-1", "tool_execute", 200)
        report = profiler.profile_execution("task-1")
        assert report.task_id == "task-1"
        assert report.bottleneck == "llm_call"
        assert any("LLM calls are slow" in s for s in report.optimization_suggestions)

    def test_orchestration_overhead(self, profiler):
        profiler.start_task("task-1")
        profiler.record_step("task-1", "step1", 10)
        import time
        time.sleep(0.05)
        report = profiler.profile_execution("task-1")
        assert any("overhead" in s.lower() for s in report.optimization_suggestions)

    def test_too_many_steps(self, profiler):
        profiler.start_task("task-1")
        for i in range(25):
            profiler.record_step("task-1", f"step_{i}", 10)
        report = profiler.profile_execution("task-1")
        assert any("many steps" in s.lower() for s in report.optimization_suggestions)

    def test_reset(self, profiler):
        profiler.start_task("task-1")
        profiler.record_step("task-1", "s", 1)
        profiler.reset()
        assert profiler.get_task_ids() == []


# ---------------------------------------------------------------------------
# HorizontalScalingCoordinator
# ---------------------------------------------------------------------------

class TestHorizontalScalingCoordinator:
    @pytest.fixture
    def coordinator(self):
        return HorizontalScalingCoordinator()

    @pytest.mark.asyncio
    async def test_register_instance_standalone(self, coordinator):
        result = await coordinator.register_instance("inst-1", ["filesystem", "shell"])
        assert result.accepted is True
        assert result.cluster_state.get("standalone") is True

    @pytest.mark.asyncio
    async def test_heartbeat(self, coordinator):
        await coordinator.register_instance("inst-1", ["fs"])
        await coordinator.heartbeat()

    @pytest.mark.asyncio
    async def test_cluster_state_standalone(self, coordinator):
        state = await coordinator.get_cluster_state()
        assert state["instance_count"] == 0

    @pytest.mark.asyncio
    async def test_assign_task_standalone(self, coordinator):
        await coordinator.register_instance("inst-1", ["fs"])
        instance = await coordinator.assign_task("task-1")
        assert instance == "inst-1"

    @pytest.mark.asyncio
    async def test_task_lock_standalone(self, coordinator):
        assert await coordinator.acquire_task_lock("task-1", "inst-1") is True
        await coordinator.release_task_lock("task-1")

    @pytest.mark.asyncio
    async def test_redis_integration(self):
        async def _mock_scan_iter(**kwargs):
            yield "agentos:instance:inst-2"

        mock_redis = MagicMock()
        mock_redis.client = AsyncMock()
        mock_redis.client.set = AsyncMock(return_value=True)
        mock_redis.client.get = AsyncMock(return_value={
            "instance_id": "inst-2",
            "capabilities": ["fs"],
            "active_tasks": 0
        })
        mock_redis.client.scan_iter = _mock_scan_iter
        mock_redis.client.delete = AsyncMock()

        coord = HorizontalScalingCoordinator(redis=mock_redis)
        result = await coord.register_instance("inst-1", ["fs"])
        assert result.accepted is True
        mock_redis.client.set.assert_called()

        await coord.deregister_instance("inst-1")
        mock_redis.client.delete.assert_called()

    @pytest.mark.asyncio
    async def test_cluster_state_with_redis(self):
        async def _mock_scan_iter(**kwargs):
            yield "agentos:instance:inst-a"

        mock_redis = MagicMock()
        mock_redis.client = AsyncMock()
        mock_redis.client.scan_iter = _mock_scan_iter
        mock_redis.client.get = AsyncMock(return_value={
            "instance_id": "inst-a",
            "capabilities": ["browser"],
            "active_tasks": 2,
            "healthy": True
        })

        coord = HorizontalScalingCoordinator(redis=mock_redis)
        state = await coord.get_cluster_state()
        assert state["instance_count"] == 1
        assert "inst-a" in state["instances"]

    @pytest.mark.asyncio
    async def test_task_assignment_least_loaded(self):
        async def _mock_scan_iter(**kwargs):
            yield "agentos:instance:inst-a"
            yield "agentos:instance:inst-b"

        mock_redis = MagicMock()
        mock_redis.client = AsyncMock()
        mock_redis.client.scan_iter = _mock_scan_iter
        mock_redis.client.get = AsyncMock(side_effect=[
            {"instance_id": "inst-a", "capabilities": ["fs"], "active_tasks": 5},
            {"instance_id": "inst-b", "capabilities": ["fs"], "active_tasks": 1},
        ])

        coord = HorizontalScalingCoordinator(redis=mock_redis)
        assigned = await coord.assign_task("task-1", ["fs"])
        assert assigned == "inst-b"
