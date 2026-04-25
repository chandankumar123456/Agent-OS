"""Stress test runner for AgentOS.

Provides latency tracking, concurrency control, and structured results
for systematic load testing of the agent execution pipeline.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx


@dataclass
class StressResult:
    """Aggregated results from a stress test scenario."""

    scenario: str
    total_tasks: int
    success: int
    failed: int
    avg_latency_ms: float
    p95_latency_ms: float
    min_latency_ms: float
    max_latency_ms: float
    errors: List[str] = field(default_factory=list)
    raw_latencies: List[float] = field(default_factory=list)


class StressTestRunner:
    """Runs stress test scenarios against the AgentOS API."""

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        token: Optional[str] = None,
        client: Optional[httpx.AsyncClient] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.client = client
        self._headers: Dict[str, str] = {"Content-Type": "application/json"}
        if token:
            self._headers["Authorization"] = f"Bearer {token}"

    async def run_scenario(
        self,
        name: str,
        queries: List[str],
        concurrent: int = 5,
    ) -> StressResult:
        """Execute a list of queries with bounded concurrency.

        Args:
            name: Scenario identifier.
            queries: List of user queries to submit as tasks.
            concurrent: Maximum number of in-flight requests.

        Returns:
            StressResult with latency distribution and error summary.
        """
        semaphore = asyncio.Semaphore(concurrent)
        latencies: List[float] = []
        errors: List[str] = []

        async def _execute_one(query: str) -> None:
            async with semaphore:
                start = time.perf_counter()
                try:
                    if self.client is not None:
                        resp = await self.client.post(
                            f"{self.base_url}/api/v1/tasks",
                            json={"query": query},
                            headers=self._headers,
                        )
                        resp.raise_for_status()
                    else:
                        async with httpx.AsyncClient(timeout=60.0) as client:
                            resp = await client.post(
                                f"{self.base_url}/api/v1/tasks",
                                json={"query": query},
                                headers=self._headers,
                            )
                            resp.raise_for_status()
                except Exception as exc:
                    errors.append(str(exc))
                finally:
                    latencies.append((time.perf_counter() - start) * 1000)

        await asyncio.gather(*[_execute_one(q) for q in queries])

        sorted_latencies = sorted(latencies)
        count = len(sorted_latencies)
        p95_idx = int(count * 0.95) if count > 0 else 0
        return StressResult(
            scenario=name,
            total_tasks=len(queries),
            success=len(queries) - len(errors),
            failed=len(errors),
            avg_latency_ms=sum(sorted_latencies) / count if count else 0.0,
            p95_latency_ms=sorted_latencies[p95_idx] if count else 0.0,
            min_latency_ms=sorted_latencies[0] if count else 0.0,
            max_latency_ms=sorted_latencies[-1] if count else 0.0,
            errors=errors[:10],
            raw_latencies=sorted_latencies,
        )

    async def run_scenario_with_injection(
        self,
        name: str,
        queries: List[str],
        concurrent: int = 5,
        failure_rate: float = 0.0,
    ) -> StressResult:
        """Run a scenario with optional artificial failure injection.

        Args:
            failure_rate: Probability (0.0–1.0) of randomly failing a request
                          by sending malformed JSON.
        """
        semaphore = asyncio.Semaphore(concurrent)
        latencies: List[float] = []
        errors: List[str] = []

        async def _execute_one(query: str) -> None:
            async with semaphore:
                start = time.perf_counter()
                try:
                    import random

                    if self.client is not None:
                        if random.random() < failure_rate:
                            resp = await self.client.post(
                                f"{self.base_url}/api/v1/tasks",
                                content=b"not-json",
                                headers=self._headers,
                            )
                        else:
                            resp = await self.client.post(
                                f"{self.base_url}/api/v1/tasks",
                                json={"query": query},
                                headers=self._headers,
                            )
                        resp.raise_for_status()
                    else:
                        async with httpx.AsyncClient(timeout=60.0) as client:
                            if random.random() < failure_rate:
                                resp = await client.post(
                                    f"{self.base_url}/api/v1/tasks",
                                    content=b"not-json",
                                    headers=self._headers,
                                )
                            else:
                                resp = await client.post(
                                    f"{self.base_url}/api/v1/tasks",
                                    json={"query": query},
                                    headers=self._headers,
                                )
                            resp.raise_for_status()
                except Exception as exc:
                    errors.append(str(exc))
                finally:
                    latencies.append((time.perf_counter() - start) * 1000)

        await asyncio.gather(*[_execute_one(q) for q in queries])

        sorted_latencies = sorted(latencies)
        count = len(sorted_latencies)
        p95_idx = int(count * 0.95) if count > 0 else 0
        return StressResult(
            scenario=name,
            total_tasks=len(queries),
            success=len(queries) - len(errors),
            failed=len(errors),
            avg_latency_ms=sum(sorted_latencies) / count if count else 0.0,
            p95_latency_ms=sorted_latencies[p95_idx] if count else 0.0,
            min_latency_ms=sorted_latencies[0] if count else 0.0,
            max_latency_ms=sorted_latencies[-1] if count else 0.0,
            errors=errors[:10],
            raw_latencies=sorted_latencies,
        )
