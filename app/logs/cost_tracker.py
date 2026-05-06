"""Cost tracking for tasks, agents, tools, and users.

Integrates with TokenUsageModel for LLM costs and Redis for real-time
aggregation. Provides cost breakdowns per task, agent, tool, and user.
"""
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from sqlalchemy import select, func

from ..memory.short_term import redis_client
from ..memory.long_term import db
from ..memory.models import TokenUsageModel
from ..logs.logger import logger


class CostRecord(BaseModel):
    """A single cost record."""
    task_id: str
    scope: str  # task, agent, tool, user
    scope_id: str
    cost_usd: float
    tokens_input: int = 0
    tokens_output: int = 0
    model: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CostBreakdown(BaseModel):
    """Aggregated cost breakdown."""
    scope: str
    scope_id: str
    total_cost_usd: float
    total_tokens_input: int = 0
    total_tokens_output: int = 0
    record_count: int = 0
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None


class CostTracker:
    """Tracks costs per task, agent, tool, and user.

    Usage:
        tracker = CostTracker()
        await tracker.record_llm_cost(task_id, model="gpt-4o", input_tokens=100, output_tokens=50)
        await tracker.record_tool_cost(task_id, tool_name="filesystem__read_file", cost_usd=0.001)
        breakdown = await tracker.get_cost_breakdown("task", task_id, period="24h")
    """

    # Cost per 1K tokens (approximate)
    MODEL_COSTS: Dict[str, Dict[str, float]] = {
        "gpt-4o": {"input": 0.005, "output": 0.015},
        "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
        "gpt-4": {"input": 0.03, "output": 0.06},
        "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},
    }

    def __init__(
        self,
        redis_prefix: str = "agentos:cost:",
    ):
        self.redis_prefix = redis_prefix

    def _cost_key(self, scope: str, scope_id: str, period: str = "daily") -> str:
        return f"{self.redis_prefix}{scope}:{scope_id}:{period}"

    def _estimate_llm_cost(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> float:
        """Estimate LLM cost in USD.

        Args:
            model: Model name.
            input_tokens: Number of input tokens.
            output_tokens: Number of output tokens.

        Returns:
            Estimated cost in USD.
        """
        costs = self.MODEL_COSTS.get(model, self.MODEL_COSTS["gpt-4o"])
        input_cost = (input_tokens / 1000.0) * costs["input"]
        output_cost = (output_tokens / 1000.0) * costs["output"]
        return round(input_cost + output_cost, 6)

    async def record_llm_cost(
        self,
        task_id: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        agent_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> CostRecord:
        """Record LLM API cost.

        Args:
            task_id: Task identifier.
            model: LLM model name.
            input_tokens: Input token count.
            output_tokens: Output token count.
            agent_id: Optional agent identifier.
            user_id: Optional user identifier.

        Returns:
            CostRecord.
        """
        cost_usd = self._estimate_llm_cost(model, input_tokens, output_tokens)
        total_tokens = input_tokens + output_tokens

        # Persist to PostgreSQL via TokenUsageModel
        try:
            async with db.get_session() as session:
                record = TokenUsageModel(
                    task_id=task_id,
                    model=model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=total_tokens,
                    cost_usd=cost_usd,
                )
                session.add(record)
                await session.commit()
        except Exception as e:
            logger.error(f"Failed to persist token usage for {task_id}: {e}")

        # Update Redis aggregates
        record_obj = CostRecord(
            task_id=task_id,
            scope="task",
            scope_id=task_id,
            cost_usd=cost_usd,
            tokens_input=input_tokens,
            tokens_output=output_tokens,
            model=model,
            metadata={"agent_id": agent_id, "user_id": user_id},
        )
        await self._update_redis_aggregate(record_obj)

        if agent_id:
            agent_record = CostRecord(
                task_id=task_id,
                scope="agent",
                scope_id=agent_id,
                cost_usd=cost_usd,
                tokens_input=input_tokens,
                tokens_output=output_tokens,
                model=model,
            )
            await self._update_redis_aggregate(agent_record)

        if user_id:
            user_record = CostRecord(
                task_id=task_id,
                scope="user",
                scope_id=user_id,
                cost_usd=cost_usd,
                tokens_input=input_tokens,
                tokens_output=output_tokens,
                model=model,
            )
            await self._update_redis_aggregate(user_record)

        logger.debug(
            f"LLM cost recorded",
            extra={
                "task_id": task_id,
                "model": model,
                "cost_usd": cost_usd,
                "total_tokens": total_tokens,
            },
        )

        return record_obj

    async def record_tool_cost(
        self,
        task_id: str,
        tool_name: str,
        cost_usd: float,
        user_id: Optional[str] = None,
    ) -> CostRecord:
        """Record tool invocation cost.

        Args:
            task_id: Task identifier.
            tool_name: Tool name.
            cost_usd: Cost in USD.
            user_id: Optional user identifier.

        Returns:
            CostRecord.
        """
        record = CostRecord(
            task_id=task_id,
            scope="tool",
            scope_id=tool_name,
            cost_usd=cost_usd,
            metadata={"user_id": user_id},
        )
        await self._update_redis_aggregate(record)

        # Also update task aggregate
        task_record = CostRecord(
            task_id=task_id,
            scope="task",
            scope_id=task_id,
            cost_usd=cost_usd,
            metadata={"tool": tool_name},
        )
        await self._update_redis_aggregate(task_record)

        if user_id:
            user_record = CostRecord(
                task_id=task_id,
                scope="user",
                scope_id=user_id,
                cost_usd=cost_usd,
                metadata={"tool": tool_name},
            )
            await self._update_redis_aggregate(user_record)

        logger.debug(
            f"Tool cost recorded",
            extra={"task_id": task_id, "tool": tool_name, "cost_usd": cost_usd},
        )
        return record

    async def _update_redis_aggregate(self, record: CostRecord) -> bool:
        """Update Redis aggregate counters for a cost record.

        Args:
            record: CostRecord to aggregate.

        Returns:
            True if updated.
        """
        try:
            key = self._cost_key(record.scope, record.scope_id)
            pipe = redis_client.client.pipeline()
            pipe.hincrbyfloat(key, "cost_usd", record.cost_usd)
            pipe.hincrby(key, "tokens_input", record.tokens_input)
            pipe.hincrby(key, "tokens_output", record.tokens_output)
            pipe.hincrby(key, "count", 1)
            pipe.hset(key, "last_updated", datetime.utcnow().isoformat())
            pipe.expire(key, 86400 * 30)  # 30 days
            await pipe.execute()
            return True
        except Exception as e:
            logger.error(f"Failed to update Redis cost aggregate: {e}")
            return False

    async def get_cost_breakdown(
        self,
        scope: str,
        scope_id: str,
        period: str = "24h",
    ) -> CostBreakdown:
        """Get cost breakdown for a scope.

        Args:
            scope: Scope type (task, agent, tool, user).
            scope_id: Scope identifier.
            period: Time period (24h, 7d, 30d).

        Returns:
            CostBreakdown.
        """
        key = self._cost_key(scope, scope_id)
        try:
            data = await redis_client.client.hgetall(key)
            if data:
                return CostBreakdown(
                    scope=scope,
                    scope_id=scope_id,
                    total_cost_usd=float(data.get("cost_usd", 0)),
                    total_tokens_input=int(data.get("tokens_input", 0)),
                    total_tokens_output=int(data.get("tokens_output", 0)),
                    record_count=int(data.get("count", 0)),
                )
        except Exception as e:
            logger.error(f"Failed to get cost breakdown from Redis: {e}")

        # Fallback: query PostgreSQL for task scope
        if scope == "task":
            try:
                async with db.get_session() as session:
                    result = await session.execute(
                        select(
                            func.sum(TokenUsageModel.cost_usd),
                            func.sum(TokenUsageModel.input_tokens),
                            func.sum(TokenUsageModel.output_tokens),
                            func.count(TokenUsageModel.id),
                        ).where(TokenUsageModel.task_id == scope_id)
                    )
                    row = result.one_or_none()
                    if row:
                        return CostBreakdown(
                            scope=scope,
                            scope_id=scope_id,
                            total_cost_usd=row[0] or 0.0,
                            total_tokens_input=row[1] or 0,
                            total_tokens_output=row[2] or 0,
                            record_count=row[3] or 0,
                        )
            except Exception as e:
                logger.error(f"Failed to get cost breakdown from DB: {e}")

        return CostBreakdown(scope=scope, scope_id=scope_id, total_cost_usd=0.0)

    async def get_multi_breakdown(
        self,
        scope: str,
        scope_ids: List[str],
    ) -> List[CostBreakdown]:
        """Get cost breakdown for multiple scopes.

        Args:
            scope: Scope type.
            scope_ids: List of scope identifiers.

        Returns:
            List of CostBreakdown.
        """
        breakdowns = []
        for sid in scope_ids:
            bd = await self.get_cost_breakdown(scope, sid)
            breakdowns.append(bd)
        return breakdowns

    async def get_top_costs(
        self,
        scope: str,
        limit: int = 10,
    ) -> List[CostBreakdown]:
        """Get top costs for a scope type.

        Args:
            scope: Scope type.
            limit: Maximum results.

        Returns:
            List of CostBreakdown sorted by cost descending.
        """
        try:
            pattern = f"{self.redis_prefix}{scope}:*"
            keys = []
            async for key in redis_client.client.scan_iter(match=pattern):
                keys.append(key)

            breakdowns = []
            for key in keys[:limit]:
                data = await redis_client.client.hgetall(key)
                if data:
                    # Extract scope_id from key
                    parts = key.decode().split(":")
                    if len(parts) >= 3:
                        scope_id = parts[2]
                        breakdowns.append(
                            CostBreakdown(
                                scope=scope,
                                scope_id=scope_id,
                                total_cost_usd=float(data.get("cost_usd", 0)),
                                total_tokens_input=int(data.get("tokens_input", 0)),
                                total_tokens_output=int(data.get("tokens_output", 0)),
                                record_count=int(data.get("count", 0)),
                            )
                        )

            breakdowns.sort(key=lambda x: x.total_cost_usd, reverse=True)
            return breakdowns[:limit]
        except Exception as e:
            logger.error(f"Failed to get top costs: {e}")
            return []

    async def cleanup(self, scope: str, scope_id: str) -> bool:
        """Clean up cost records for a scope.

        Args:
            scope: Scope type.
            scope_id: Scope identifier.

        Returns:
            True if cleaned up.
        """
        try:
            key = self._cost_key(scope, scope_id)
            await redis_client.client.delete(key)
            return True
        except Exception as e:
            logger.error(f"Failed to cleanup cost records: {e}")
            return False


# Module-level singleton
cost_tracker = CostTracker()
