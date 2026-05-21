"""Memory consistency layer ensuring read-after-write consistency.

Acts as the central state source by resolving conflicts between
Redis cache and PostgreSQL, with configurable consistency levels.
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from .short_term import redis_client
from .long_term import db
from ..logs.logger import logger


class ConsistencyLevel(str, Enum):
    """Consistency guarantee levels."""
    EVENTUAL = "eventual"      # Redis first, async DB sync
    STRONG = "strong"          # DB first, invalidate Redis
    READ_THROUGH = "read_through"  # Read from DB, cache in Redis


class ConsistentState(BaseModel):
    """Resolved consistent state."""
    task_id: str
    state: Dict[str, Any] = Field(default_factory=dict)
    source_of_truth: str = Field(default="unknown")  # "redis", "postgres", "merged"
    last_updated: Optional[datetime] = None
    conflict_detected: bool = Field(default=False)
    conflict_resolution: str = Field(default="none")


class MemoryConsistencyLayer:
    """Ensures all components see consistent task state.

    Resolves conflicts between Redis (fast, ephemeral) and PostgreSQL
    (durable, slow) by comparing timestamps and selecting the winner.

    Usage:
        layer = MemoryConsistencyLayer()
        state = await layer.get_consistent_state(task_id, ConsistencyLevel.STRONG)
        await layer.write_consistent_state(task_id, {"status": "running"}, ConsistencyLevel.STRONG)
    """

    def __init__(
        self,
        default_level: ConsistencyLevel = ConsistencyLevel.STRONG,
        redis_prefix: str = "agentos:consistent:",
    ):
        self.default_level = default_level
        self.redis_prefix = redis_prefix

    def _redis_key(self, task_id: str) -> str:
        return f"{self.redis_prefix}{task_id}"

    async def get_consistent_state(
        self,
        task_id: str,
        level: Optional[ConsistencyLevel] = None,
    ) -> ConsistentState:
        """Retrieve consistent state for a task.

        Args:
            task_id: The task identifier.
            level: Consistency level override.

        Returns:
            ConsistentState with resolved state.
        """
        level = level or self.default_level

        if level == ConsistencyLevel.READ_THROUGH:
            return await self._read_through(task_id)
        elif level == ConsistencyLevel.STRONG:
            return await self._strong_consistency(task_id)
        else:
            return await self._eventual_consistency(task_id)

    async def write_consistent_state(
        self,
        task_id: str,
        state: Dict[str, Any],
        level: Optional[ConsistencyLevel] = None,
    ) -> ConsistentState:
        """Write state with consistency guarantees.

        Args:
            task_id: The task identifier.
            state: State dictionary to write.
            level: Consistency level override.

        Returns:
            ConsistentState reflecting the written state.
        """
        level = level or self.default_level
        now = datetime.now(timezone.utc).isoformat()
        state["_last_updated"] = now

        if level == ConsistencyLevel.STRONG:
            # Write to DB first, then invalidate Redis
            await self._write_to_db(task_id, state)
            await self._invalidate_redis(task_id)
            return ConsistentState(
                task_id=task_id,
                state=state,
                source_of_truth="postgres",
                last_updated=now,
            )
        elif level == ConsistencyLevel.READ_THROUGH:
            # Write to DB, then update Redis
            await self._write_to_db(task_id, state)
            await self._write_to_redis(task_id, state)
            return ConsistentState(
                task_id=task_id,
                state=state,
                source_of_truth="postgres",
                last_updated=now,
            )
        else:
            # Eventual: write to Redis first, async to DB
            await self._write_to_redis(task_id, state)
            # Fire-and-forget DB write
            try:
                await self._write_to_db(task_id, state)
            except Exception as e:
                logger.warning(f"Async DB write failed for {task_id}: {e}")
            return ConsistentState(
                task_id=task_id,
                state=state,
                source_of_truth="redis",
                last_updated=now,
            )

    async def resolve_conflict(self, task_id: str) -> ConsistentState:
        """Explicitly resolve conflicts between Redis and DB.

        Compares timestamps and merges state, with PostgreSQL winning
        on timestamp ties.

        Args:
            task_id: The task identifier.

        Returns:
            ConsistentState with resolved conflict info.
        """
        redis_state = await self._read_from_redis(task_id)
        db_state = await self._read_from_db(task_id)

        if not redis_state and not db_state:
            return ConsistentState(task_id=task_id, source_of_truth="none")

        if not redis_state:
            return ConsistentState(
                task_id=task_id,
                state=db_state,
                source_of_truth="postgres",
                last_updated=db_state.get("_last_updated"),
            )

        if not db_state:
            return ConsistentState(
                task_id=task_id,
                state=redis_state,
                source_of_truth="redis",
                last_updated=redis_state.get("_last_updated"),
            )

        # Both exist - compare timestamps
        redis_ts = redis_state.get("_last_updated", "")
        db_ts = db_state.get("_last_updated", "")

        conflict_detected = redis_ts != db_ts

        if db_ts >= redis_ts:
            winner = db_state
            source = "postgres"
            resolution = "db_wins_by_timestamp"
        else:
            winner = redis_state
            source = "redis"
            resolution = "redis_wins_by_timestamp"

        # Sync winner to loser
        if source == "postgres":
            await self._write_to_redis(task_id, winner)
        else:
            await self._write_to_db(task_id, winner)

        return ConsistentState(
            task_id=task_id,
            state=winner,
            source_of_truth=source,
            last_updated=winner.get("_last_updated"),
            conflict_detected=conflict_detected,
            conflict_resolution=resolution,
        )

    async def _eventual_consistency(self, task_id: str) -> ConsistentState:
        """Redis-first eventual consistency."""
        redis_state = await self._read_from_redis(task_id)
        if redis_state:
            return ConsistentState(
                task_id=task_id,
                state=redis_state,
                source_of_truth="redis",
                last_updated=redis_state.get("_last_updated"),
            )
        # Fallback to DB
        db_state = await self._read_from_db(task_id)
        if db_state:
            # Backfill Redis
            await self._write_to_redis(task_id, db_state)
            return ConsistentState(
                task_id=task_id,
                state=db_state,
                source_of_truth="postgres",
                last_updated=db_state.get("_last_updated"),
            )
        return ConsistentState(task_id=task_id, source_of_truth="none")

    async def _strong_consistency(self, task_id: str) -> ConsistentState:
        """DB-first strong consistency."""
        db_state = await self._read_from_db(task_id)
        if db_state:
            # Check if Redis is stale and invalidate if so
            redis_state = await self._read_from_redis(task_id)
            if redis_state:
                redis_ts = redis_state.get("_last_updated", "")
                db_ts = db_state.get("_last_updated", "")
                if redis_ts != db_ts:
                    await self._invalidate_redis(task_id)
            return ConsistentState(
                task_id=task_id,
                state=db_state,
                source_of_truth="postgres",
                last_updated=db_state.get("_last_updated"),
            )
        # Fallback to Redis if DB has nothing
        redis_state = await self._read_from_redis(task_id)
        if redis_state:
            return ConsistentState(
                task_id=task_id,
                state=redis_state,
                source_of_truth="redis",
                last_updated=redis_state.get("_last_updated"),
            )
        return ConsistentState(task_id=task_id, source_of_truth="none")

    async def _read_through(self, task_id: str) -> ConsistentState:
        """Always read from DB, cache result."""
        db_state = await self._read_from_db(task_id)
        if db_state:
            await self._write_to_redis(task_id, db_state)
            return ConsistentState(
                task_id=task_id,
                state=db_state,
                source_of_truth="postgres",
                last_updated=db_state.get("_last_updated"),
            )
        return ConsistentState(task_id=task_id, source_of_truth="none")

    async def _read_from_redis(self, task_id: str) -> Optional[Dict[str, Any]]:
        try:
            return await redis_client.get(self._redis_key(task_id))
        except Exception as e:
            logger.warning(f"Redis read failed for {task_id}: {e}")
            return None

    async def _write_to_redis(self, task_id: str, state: Dict[str, Any]) -> None:
        try:
            await redis_client.set(
                self._redis_key(task_id),
                state,
                expire=86400,
            )
        except Exception as e:
            logger.warning(f"Redis write failed for {task_id}: {e}")

    async def _invalidate_redis(self, task_id: str) -> None:
        try:
            await redis_client.delete(self._redis_key(task_id))
        except Exception as e:
            logger.warning(f"Redis invalidation failed for {task_id}: {e}")

    async def _read_from_db(self, task_id: str) -> Optional[Dict[str, Any]]:
        try:
            async with db.get_session() as session:
                from sqlalchemy import select
                from .models import ContextModel
                result = await session.execute(
                    select(ContextModel).where(
                        ContextModel.task_id == f"consistent_state:{task_id}"
                    )
                )
                row = result.scalar_one_or_none()
                if row and row.value:
                    return row.value if isinstance(row.value, dict) else {}
        except Exception as e:
            logger.warning(f"DB read failed for {task_id}: {e}")
        return None

    async def _write_to_db(self, task_id: str, state: Dict[str, Any]) -> None:
        try:
            async with db.get_session() as session:
                from sqlalchemy import select
                from .models import ContextModel
                result = await session.execute(
                    select(ContextModel).where(
                        ContextModel.task_id == f"consistent_state:{task_id}"
                    )
                )
                existing = result.scalar_one_or_none()
                if existing:
                    existing.value = state
                else:
                    ctx = ContextModel(
                        task_id=f"consistent_state:{task_id}",
                        key="state",
                        value=state,
                    )
                    session.add(ctx)
                await session.commit()
        except Exception as e:
            logger.warning(f"DB write failed for {task_id}: {e}")


# Module-level singleton
consistency_layer = MemoryConsistencyLayer()
