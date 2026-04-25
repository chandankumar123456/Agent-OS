"""Stress test scenarios for AgentOS execution pipeline."""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_simple_tasks(stress_runner):
    """Baseline: simple single-step queries."""
    queries = ["What is 2+2?" for _ in range(10)]
    result = await stress_runner.run_scenario("simple", queries, concurrent=5)
    assert result.failed == 0, f"Unexpected failures: {result.errors}"
    assert result.avg_latency_ms > 0


@pytest.mark.asyncio
async def test_multi_step_tasks(stress_runner):
    """Multi-step tasks with file and shell interactions."""
    queries = ["Create a file on the desktop, then read it back" for _ in range(5)]
    result = await stress_runner.run_scenario("multi_step", queries, concurrent=2)
    assert result.success > 0, f"All tasks failed: {result.errors}"


@pytest.mark.asyncio
async def test_ambiguous_tasks(stress_runner):
    """Ambiguous queries that stress the planner and capability router."""
    queries = [
        "Do something useful",
        "Help me out",
        "I need assistance",
    ] * 3
    result = await stress_runner.run_scenario("ambiguous", queries, concurrent=3)
    assert result.success > 0


@pytest.mark.asyncio
async def test_high_concurrency(stress_runner):
    """High concurrency scenario to reveal connection pool bottlenecks."""
    queries = [f"Calculate {i} * {i}" for i in range(20)]
    result = await stress_runner.run_scenario("high_concurrency", queries, concurrent=10)
    assert result.success > 0
    assert result.p95_latency_ms > 0


@pytest.mark.asyncio
async def test_failure_injection(stress_runner):
    """Inject malformed requests to verify error handling resilience."""
    queries = ["Valid query" for _ in range(10)]
    result = await stress_runner.run_scenario_with_injection(
        "failure_injection", queries, concurrent=3, failure_rate=0.3
    )
    assert result.failed > 0, "Expected some failures due to injection"
    assert result.success > 0, "Expected some successes despite injection"
