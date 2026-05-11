"""Tool-specific cost tracking per invocation.

Wraps the global CostTracker to provide tool-centric cost estimation,
invocation wrapping, and batch recording for multi-tool workflows.
"""
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from ..logs.cost_tracker import CostTracker, cost_tracker as global_cost_tracker
from ..logs.logger import logger
from .base import ToolInput, ToolOutput


class ToolInvocationCost(BaseModel):
    """Cost record for a single tool invocation."""
    task_id: str
    tool_name: str
    cost_usd: float
    duration_ms: float
    input_size_bytes: int = 0
    output_size_bytes: int = 0
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ToolCostEstimate(BaseModel):
    """Estimated cost before executing a tool."""
    tool_name: str
    estimated_cost_usd: float
    confidence: str  # low, medium, high
    factors: List[str] = Field(default_factory=list)


class ToolCostTracker:
    """Tracks costs for individual tool invocations.

    Usage:
        tracker = ToolCostTracker()
        # Wrap a single invocation
        cost = await tracker.record_invocation(
            task_id, "filesystem__read_file", lambda: tool.execute(input)
        )
        # Or use context manager
        async with tracker.track(task_id, "shell__execute_command") as t:
            result = await tool.execute(input)
            t.set_output_size(len(result.result or ""))
    """

    # Known baseline costs for specific tools (USD per invocation)
    BASELINE_COSTS: Dict[str, float] = {
        "filesystem__read_file": 0.0,
        "filesystem__write_file": 0.0,
        "filesystem__list_directory": 0.0,
        "filesystem__search_files": 0.0,
        "shell__execute_command": 0.0001,
        "shell__run_script": 0.0001,
        "shell__get_process_status": 0.0,
        "browser__http_request": 0.0005,
        "browser__scrape_page": 0.0005,
        "browser__search_web": 0.001,
        "cloud_api__search_web": 0.002,
        "cloud_api__http_request": 0.0005,
        "cloud_api__scrape_page": 0.0005,
        "cloud_api__send_email": 0.001,
        "cloud_api__send_message": 0.001,
    }

    def __init__(self, cost_tracker: Optional[CostTracker] = None):
        self.cost_tracker = cost_tracker or global_cost_tracker

    def estimate_cost(self, tool_name: str, tool_input: Optional[ToolInput] = None) -> ToolCostEstimate:
        """Estimate the cost of invoking a tool.

        Args:
            tool_name: Tool name.
            tool_input: Optional tool input for size-based estimation.

        Returns:
            ToolCostEstimate.
        """
        base = self.BASELINE_COSTS.get(tool_name, 0.0001)
        factors = [f"Baseline cost for {tool_name}"]
        confidence = "high"

        # Adjust based on input size heuristic
        if tool_input and tool_input.parameters:
            content = str(tool_input.parameters)
            size = len(content.encode("utf-8"))
            if size > 10000:
                base += 0.0005
                factors.append("Large input payload (>10KB)")
                confidence = "medium"
            elif size > 100000:
                base += 0.002
                factors.append("Very large input payload (>100KB)")
                confidence = "low"

        # Browser and search tools have variable costs
        if "browser" in tool_name or "search" in tool_name:
            confidence = "medium"
            factors.append("Variable external API latency/data transfer")

        return ToolCostEstimate(
            tool_name=tool_name,
            estimated_cost_usd=round(base, 6),
            confidence=confidence,
            factors=factors,
        )

    async def record_invocation(
        self,
        task_id: str,
        tool_name: str,
        coro_factory,
        agent_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> ToolOutput:
        """Execute a tool coroutine and record its cost.

        Args:
            task_id: Task identifier.
            tool_name: Tool name.
            coro_factory: Async callable that returns ToolOutput.
            agent_id: Optional agent identifier.
            user_id: Optional user identifier.

        Returns:
            ToolOutput from the coroutine.
        """
        start = time.perf_counter()
        try:
            result = await coro_factory()
        finally:
            duration_ms = (time.perf_counter() - start) * 1000

        # Compute cost
        estimated = self.estimate_cost(tool_name)
        cost_usd = estimated.estimated_cost_usd

        # Add duration-based overhead for long-running tools
        if duration_ms > 5000:
            cost_usd += 0.0001 * (duration_ms / 5000)

        cost_usd = round(cost_usd, 6)

        # Record via global cost tracker
        await self.cost_tracker.record_tool_cost(
            task_id=task_id,
            tool_name=tool_name,
            cost_usd=cost_usd,
            user_id=user_id,
        )

        # Also record task aggregate with agent info
        if agent_id:
            await self.cost_tracker._update_redis_aggregate(
                # Reuse CostRecord structure from logs/cost_tracker
                type("CostRecord", (), {
                    "task_id": task_id,
                    "scope": "agent",
                    "scope_id": agent_id,
                    "cost_usd": cost_usd,
                    "tokens_input": 0,
                    "tokens_output": 0,
                    "model": None,
                    "timestamp": datetime.now(timezone.utc),
                    "metadata": {"tool": tool_name, "duration_ms": duration_ms},
                })()
            )

        logger.debug(
            f"Tool invocation cost recorded",
            extra={
                "task_id": task_id,
                "tool_name": tool_name,
                "cost_usd": cost_usd,
                "duration_ms": round(duration_ms, 2),
                "agent_id": agent_id,
            },
        )

        # Attach cost metadata to result
        if result.metadata is None:
            result.metadata = {}
        result.metadata["cost_usd"] = cost_usd
        result.metadata["duration_ms"] = round(duration_ms, 2)

        return result

    @asynccontextmanager
    async def track(
        self,
        task_id: str,
        tool_name: str,
        agent_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ):
        """Context manager to track a tool invocation.

        Usage:
            async with tracker.track(task_id, "shell__execute") as t:
                result = await tool.execute(input)
                t.set_output_size(len(str(result.result)))
        """
        tracker = _ToolInvocationContext(
            task_id=task_id,
            tool_name=tool_name,
            cost_tracker=self.cost_tracker,
            tool_cost_tracker=self,
            agent_id=agent_id,
            user_id=user_id,
        )
        tracker.start()
        try:
            yield tracker
        finally:
            await tracker.finish()

    async def record_batch(
        self,
        task_id: str,
        invocations: List[Dict[str, Any]],
        user_id: Optional[str] = None,
    ) -> List[ToolInvocationCost]:
        """Record costs for a batch of tool invocations.

        Args:
            task_id: Task identifier.
            invocations: List of dicts with keys: tool_name, cost_usd, duration_ms, etc.
            user_id: Optional user identifier.

        Returns:
            List of ToolInvocationCost records.
        """
        records = []
        for inv in invocations:
            tool_name = inv.get("tool_name", "")
            cost_usd = inv.get("cost_usd", 0.0)
            duration_ms = inv.get("duration_ms", 0.0)

            await self.cost_tracker.record_tool_cost(
                task_id=task_id,
                tool_name=tool_name,
                cost_usd=cost_usd,
                user_id=user_id,
            )

            records.append(ToolInvocationCost(
                task_id=task_id,
                tool_name=tool_name,
                cost_usd=cost_usd,
                duration_ms=duration_ms,
                metadata=inv.get("metadata", {}),
            ))

        logger.debug(
            f"Batch tool costs recorded",
            extra={"task_id": task_id, "count": len(records)},
        )
        return records

    async def get_tool_cost_breakdown(
        self,
        task_id: str,
    ) -> Dict[str, float]:
        """Get per-tool cost breakdown for a task.

        Args:
            task_id: Task identifier.

        Returns:
            Dict mapping tool_name to total cost.
        """
        from ..logs.cost_tracker import CostBreakdown
        # Get task-level breakdown which includes tool metadata
        breakdown = await self.cost_tracker.get_cost_breakdown("task", task_id)
        # The Redis hash may contain tool metadata but for a clean breakdown
        # we rely on the tool-scope aggregates
        # Query all tool keys for this task is complex; return total for now
        return {
            "total": breakdown.total_cost_usd,
            "task_id": task_id,
        }


class _ToolInvocationContext:
    """Internal context object for track() context manager."""

    def __init__(
        self,
        task_id: str,
        tool_name: str,
        cost_tracker: CostTracker,
        tool_cost_tracker: ToolCostTracker,
        agent_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ):
        self.task_id = task_id
        self.tool_name = tool_name
        self.cost_tracker = cost_tracker
        self.tool_cost_tracker = tool_cost_tracker
        self.agent_id = agent_id
        self.user_id = user_id
        self.start_time: Optional[float] = None
        self.input_size_bytes = 0
        self.output_size_bytes = 0
        self.error: Optional[str] = None

    def start(self):
        self.start_time = time.perf_counter()

    def set_input_size(self, size: int):
        self.input_size_bytes = size

    def set_output_size(self, size: int):
        self.output_size_bytes = size

    def set_error(self, error: str):
        self.error = error

    async def finish(self):
        if self.start_time is None:
            return
        duration_ms = (time.perf_counter() - self.start_time) * 1000

        estimated = self.tool_cost_tracker.estimate_cost(self.tool_name)
        cost_usd = estimated.estimated_cost_usd

        if duration_ms > 5000:
            cost_usd += 0.0001 * (duration_ms / 5000)
        if self.error:
            cost_usd *= 0.5  # Failed invocations cost less (no output processing)

        cost_usd = round(cost_usd, 6)

        await self.cost_tracker.record_tool_cost(
            task_id=self.task_id,
            tool_name=self.tool_name,
            cost_usd=cost_usd,
            user_id=self.user_id,
        )

        logger.debug(
            f"Tool track finished",
            extra={
                "task_id": self.task_id,
                "tool_name": self.tool_name,
                "cost_usd": cost_usd,
                "duration_ms": round(duration_ms, 2),
                "error": self.error,
            },
        )


# Module-level singleton
tool_cost_tracker = ToolCostTracker()
