"""Local task queue for desktop-native mode.

Replaces Redis sorted sets with SQLite-backed priority queue.
Uses asyncio.Condition for efficient dequeue waiting.
"""

import asyncio
import json
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from ..logs.logger import logger
from .sqlite_store import sqlite_store


class TaskPriority(int, Enum):
    """Priority levels for task queue. Lower value = higher priority."""
    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3


class QueuePosition(BaseModel):
    """Position of a task in the queue."""
    task_id: str
    position: int
    estimated_wait_seconds: float
    assigned_worker: Optional[str] = None
    queue_length: int


class QueuedTask(BaseModel):
    """Task metadata stored in the queue."""
    task_id: str
    user_id: str
    query: str
    priority: TaskPriority
    config: Dict[str, Any] = Field(default_factory=dict)
    idempotency_key: Optional[str] = None
    enqueued_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    scheduled_for: Optional[datetime] = None
    worker_id: Optional[str] = None
    status: str = "queued"
    retry_count: int = 0


class LocalTaskQueue:
    """SQLite-backed priority task queue for desktop-native mode.

    Uses SQLite for persistence and asyncio.Condition for coordinating
    producers and consumers. Priority ordering uses the same scoring
    algorithm as the Redis implementation for compatibility.
    """

    def __init__(
        self,
        prefix: str = "agentos:queue:",
        default_worker_ttl: int = 30,
    ):
        self._prefix = prefix
        self._default_worker_ttl = default_worker_ttl
        self._condition = asyncio.Condition()

    def _compute_score(self, priority: TaskPriority, delay_seconds: int = 0) -> float:
        timestamp_factor = int((time.time() + delay_seconds) * 1000)
        return (priority.value * 1_000_000_000_000) + timestamp_factor

    async def enqueue(
        self,
        task_id: str,
        user_id: str,
        query: str,
        priority: TaskPriority = TaskPriority.NORMAL,
        config: Optional[Dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
        scheduled_for: Optional[datetime] = None,
    ) -> QueuePosition:
        """Enqueue a task with priority."""
        config = config or {}
        now = datetime.now(timezone.utc)
        score = self._compute_score(priority)

        queued_task = QueuedTask(
            task_id=task_id,
            user_id=user_id,
            query=query,
            priority=priority,
            config=config,
            idempotency_key=idempotency_key,
            enqueued_at=now,
            scheduled_for=scheduled_for,
        )

        await sqlite_store.execute(
            """
            INSERT OR REPLACE INTO task_queue
            (task_id, user_id, query, priority, config, idempotency_key,
             enqueued_at, scheduled_for, worker_id, status, retry_count, score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (task_id, user_id, query, priority.value,
             json.dumps(config, default=str), idempotency_key,
             now.isoformat(), scheduled_for.isoformat() if scheduled_for else None,
             None, "queued", 0, score),
        )
        await sqlite_store.commit()

        position = await self.get_position(task_id)
        queue_length = await self.length()
        estimated_wait = await self._estimate_wait(position)

        async with self._condition:
            self._condition.notify()

        logger.info(
            "Task enqueued (local)",
            extra={
                "task_id": task_id,
                "priority": priority.name,
                "position": position,
                "queue_length": queue_length,
            },
        )

        return QueuePosition(
            task_id=task_id,
            position=position,
            estimated_wait_seconds=estimated_wait,
            queue_length=queue_length,
        )

    async def dequeue(
        self,
        worker_id: str,
        max_priority: Optional[TaskPriority] = None,
    ) -> Optional[QueuedTask]:
        """Dequeue the highest-priority available task."""
        max_score = None
        if max_priority is not None:
            max_score = (max_priority.value + 1) * 1_000_000_000_000 - 1

        # Try to get a task
        row = None
        if max_score is not None:
            row = await sqlite_store.fetchone(
                """
                SELECT * FROM task_queue
                WHERE status = 'queued' AND score <= ?
                ORDER BY score ASC
                LIMIT 1
                """,
                (max_score,),
            )
        else:
            row = await sqlite_store.fetchone(
                """
                SELECT * FROM task_queue
                WHERE status = 'queued'
                ORDER BY score ASC
                LIMIT 1
                """,
            )

        if not row:
            return None

        task_id = row["task_id"]
        now = datetime.now(timezone.utc)

        # Mark as assigned
        await sqlite_store.execute(
            """
            UPDATE task_queue
            SET status = 'assigned', worker_id = ?, score = ?
            WHERE task_id = ? AND status = 'queued'
            """,
            (worker_id, self._compute_score(TaskPriority(row["priority"])), task_id),
        )
        await sqlite_store.commit()

        # Check if update succeeded (row may have been taken by another worker)
        updated = await sqlite_store.fetchone(
            "SELECT * FROM task_queue WHERE task_id = ? AND status = 'assigned'",
            (task_id,),
        )
        if not updated:
            return None

        task = QueuedTask(
            task_id=updated["task_id"],
            user_id=updated["user_id"],
            query=updated["query"],
            priority=TaskPriority(updated["priority"]),
            config=json.loads(updated["config"]),
            idempotency_key=updated["idempotency_key"],
            enqueued_at=datetime.fromisoformat(updated["enqueued_at"]),
            scheduled_for=datetime.fromisoformat(updated["scheduled_for"]) if updated["scheduled_for"] else None,
            worker_id=updated["worker_id"],
            status=updated["status"],
            retry_count=updated["retry_count"],
        )

        logger.info(
            "Task dequeued (local)",
            extra={
                "task_id": task_id,
                "worker_id": worker_id,
                "priority": task.priority.name,
            },
        )
        return task

    async def complete(self, task_id: str) -> bool:
        """Mark a task as completed."""
        try:
            await sqlite_store.execute(
                """
                UPDATE task_queue
                SET status = 'completed'
                WHERE task_id = ?
                """,
                (task_id,),
            )
            await sqlite_store.commit()
            logger.info("Task marked complete in queue (local)", extra={"task_id": task_id})
            return True
        except Exception as e:
            logger.error(f"Failed to complete task {task_id} in queue: {e}")
            return False

    async def fail(self, task_id: str, error: str) -> bool:
        """Mark a task as failed."""
        try:
            await sqlite_store.execute(
                """
                UPDATE task_queue
                SET status = 'failed'
                WHERE task_id = ?
                """,
                (task_id,),
            )
            await sqlite_store.commit()
            logger.info("Task marked failed in queue (local)", extra={"task_id": task_id, "error": error})
            return True
        except Exception as e:
            logger.error(f"Failed to mark task {task_id} as failed: {e}")
            return False

    async def requeue(
        self,
        task_id: str,
        priority: Optional[TaskPriority] = None,
        delay_seconds: int = 0,
    ) -> bool:
        """Re-queue a failed or retried task."""
        row = await sqlite_store.fetchone(
            "SELECT * FROM task_queue WHERE task_id = ?",
            (task_id,),
        )
        if not row:
            return False

        current_priority = TaskPriority(row["priority"])
        new_priority = priority or current_priority
        new_score = self._compute_score(new_priority, delay_seconds)
        now = datetime.now(timezone.utc)
        retry_count = row["retry_count"] + 1

        await sqlite_store.execute(
            """
            UPDATE task_queue
            SET status = 'queued', worker_id = NULL, priority = ?, score = ?,
                retry_count = ?, enqueued_at = ?
            WHERE task_id = ?
            """,
            (new_priority.value, new_score, retry_count, now.isoformat(), task_id),
        )
        await sqlite_store.commit()

        async with self._condition:
            self._condition.notify()

        logger.info(
            "Task requeued (local)",
            extra={"task_id": task_id, "retry_count": retry_count, "delay": delay_seconds},
        )
        return True

    async def get_position(self, task_id: str) -> int:
        """Get queue position of a task."""
        row = await sqlite_store.fetchone(
            """
            SELECT COUNT(*) as position FROM task_queue
            WHERE status = 'queued' AND score < (
                SELECT score FROM task_queue WHERE task_id = ?
            )
            """,
            (task_id,),
        )
        return row["position"] if row else -1

    async def length(self) -> int:
        """Get total number of queued tasks."""
        row = await sqlite_store.fetchone(
            "SELECT COUNT(*) as count FROM task_queue WHERE status = 'queued'",
        )
        return row["count"] if row else 0

    async def list_tasks(
        self,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[QueuedTask]:
        """List tasks in the queue."""
        if status:
            rows = await sqlite_store.fetchall(
                """
                SELECT * FROM task_queue
                WHERE status = ?
                ORDER BY score ASC
                LIMIT ?
                """,
                (status, limit),
            )
        else:
            rows = await sqlite_store.fetchall(
                """
                SELECT * FROM task_queue
                ORDER BY score ASC
                LIMIT ?
                """,
                (limit,),
            )

        tasks = []
        for row in rows:
            tasks.append(QueuedTask(
                task_id=row["task_id"],
                user_id=row["user_id"],
                query=row["query"],
                priority=TaskPriority(row["priority"]),
                config=json.loads(row["config"]),
                idempotency_key=row["idempotency_key"],
                enqueued_at=datetime.fromisoformat(row["enqueued_at"]),
                scheduled_for=datetime.fromisoformat(row["scheduled_for"]) if row["scheduled_for"] else None,
                worker_id=row["worker_id"],
                status=row["status"],
                retry_count=row["retry_count"],
            ))
        return tasks

    async def _estimate_wait(self, position: int) -> float:
        if position < 0:
            return 0.0
        return position * 5.0

    async def clear(self) -> int:
        """Clear all tasks from the queue."""
        try:
            row = await sqlite_store.fetchone("SELECT COUNT(*) as count FROM task_queue")
            count = row["count"] if row else 0
            await sqlite_store.execute("DELETE FROM task_queue")
            await sqlite_store.commit()
            logger.warning(f"Queue cleared (local), removed {count} tasks")
            return count
        except Exception as e:
            logger.error(f"Failed to clear queue: {e}")
            return 0


# Module-level singleton
local_task_queue = LocalTaskQueue()
