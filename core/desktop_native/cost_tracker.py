"""Local cost tracker for desktop-native mode.

Replaces Redis aggregates with SQLite aggregates.
All cost records are persisted to SQLite.
"""

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from ..logs.logger import logger
from .sqlite_store import sqlite_store


class CostRecord(BaseModel):
    """A single cost record."""
    task_id: str
    scope: str
    scope_id: str
    cost_usd: float
    tokens_input: int = 0
    tokens_output: int = 0
    model: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
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


class LocalCostTracker:
    """Tracks costs using SQLite aggregates.

    Replaces Redis hash increments with SQL aggregate queries.
    All records are persisted to the cost_records table.
    """

    MODEL_COSTS: Dict[str, Dict[str, float]] = {
        "gpt-4o": {"input": 0.005, "output": 0.015},
        "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
        "gpt-4": {"input": 0.03, "output": 0.06},
        "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},
    }

    def _estimate_llm_cost(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> float:
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
        """Record LLM API cost."""
        cost_usd = self._estimate_llm_cost(model, input_tokens, output_tokens)
        total_tokens = input_tokens + output_tokens

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
        await self._persist_record(record_obj)

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
            await self._persist_record(agent_record)

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
            await self._persist_record(user_record)

        logger.debug(
            "LLM cost recorded (local)",
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
        """Record tool invocation cost."""
        record = CostRecord(
            task_id=task_id,
            scope="tool",
            scope_id=tool_name,
            cost_usd=cost_usd,
            metadata={"user_id": user_id},
        )
        await self._persist_record(record)

        task_record = CostRecord(
            task_id=task_id,
            scope="task",
            scope_id=task_id,
            cost_usd=cost_usd,
            metadata={"tool": tool_name},
        )
        await self._persist_record(task_record)

        if user_id:
            user_record = CostRecord(
                task_id=task_id,
                scope="user",
                scope_id=user_id,
                cost_usd=cost_usd,
                metadata={"tool": tool_name},
            )
            await self._persist_record(user_record)

        logger.debug(
            "Tool cost recorded (local)",
            extra={"task_id": task_id, "tool": tool_name, "cost_usd": cost_usd},
        )
        return record

    async def _persist_record(self, record: CostRecord) -> bool:
        """Persist a cost record to SQLite."""
        try:
            await sqlite_store.execute(
                """
                INSERT INTO cost_records
                (task_id, scope, scope_id, cost_usd, tokens_input, tokens_output,
                 model, timestamp, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (record.task_id, record.scope, record.scope_id,
                 record.cost_usd, record.tokens_input, record.tokens_output,
                 record.model, record.timestamp.isoformat(),
                 json.dumps(record.metadata, default=str)),
            )
            await sqlite_store.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to persist cost record: {e}")
            return False

    async def get_cost_breakdown(
        self,
        scope: str,
        scope_id: str,
        period: str = "24h",
    ) -> CostBreakdown:
        """Get cost breakdown for a scope using SQLite aggregates."""
        # Parse period
        hours = 24
        if period == "7d":
            hours = 24 * 7
        elif period == "30d":
            hours = 24 * 30

        try:
            row = await sqlite_store.fetchone(
                """
                SELECT
                    SUM(cost_usd) as total_cost,
                    SUM(tokens_input) as total_input,
                    SUM(tokens_output) as total_output,
                    COUNT(*) as record_count,
                    MIN(timestamp) as period_start,
                    MAX(timestamp) as period_end
                FROM cost_records
                WHERE scope = ? AND scope_id = ?
                AND timestamp > datetime('now', '-' || ? || ' hours')
                """,
                (scope, scope_id, hours),
            )
            if row:
                return CostBreakdown(
                    scope=scope,
                    scope_id=scope_id,
                    total_cost_usd=row["total_cost"] or 0.0,
                    total_tokens_input=row["total_input"] or 0,
                    total_tokens_output=row["total_output"] or 0,
                    record_count=row["record_count"] or 0,
                    period_start=datetime.fromisoformat(row["period_start"]) if row["period_start"] else None,
                    period_end=datetime.fromisoformat(row["period_end"]) if row["period_end"] else None,
                )
        except Exception as e:
            logger.error(f"Failed to get cost breakdown from SQLite: {e}")

        return CostBreakdown(scope=scope, scope_id=scope_id, total_cost_usd=0.0)

    async def get_multi_breakdown(
        self,
        scope: str,
        scope_ids: List[str],
    ) -> List[CostBreakdown]:
        """Get cost breakdown for multiple scopes."""
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
        """Get top costs for a scope type."""
        try:
            rows = await sqlite_store.fetchall(
                """
                SELECT
                    scope_id,
                    SUM(cost_usd) as total_cost,
                    SUM(tokens_input) as total_input,
                    SUM(tokens_output) as total_output,
                    COUNT(*) as record_count
                FROM cost_records
                WHERE scope = ?
                GROUP BY scope_id
                ORDER BY total_cost DESC
                LIMIT ?
                """,
                (scope, limit),
            )
            breakdowns = []
            for row in rows:
                breakdowns.append(CostBreakdown(
                    scope=scope,
                    scope_id=row["scope_id"],
                    total_cost_usd=row["total_cost"] or 0.0,
                    total_tokens_input=row["total_input"] or 0,
                    total_tokens_output=row["total_output"] or 0,
                    record_count=row["record_count"] or 0,
                ))
            return breakdowns
        except Exception as e:
            logger.error(f"Failed to get top costs: {e}")
            return []

    async def cleanup(self, scope: str, scope_id: str) -> bool:
        """Clean up cost records for a scope."""
        try:
            await sqlite_store.execute(
                "DELETE FROM cost_records WHERE scope = ? AND scope_id = ?",
                (scope, scope_id),
            )
            await sqlite_store.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to cleanup cost records: {e}")
            return False


# Module-level singleton
local_cost_tracker = LocalCostTracker()
