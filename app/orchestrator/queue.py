"""Priority task queue with scheduling and worker assignment.

Uses Redis sorted sets for priority ordering and hash maps for task metadata.
Integrates with TaskStateMachine, IdempotencyEnforcement, and ExecutionLock.
"""
import json
import time
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from ..memory.short_term import redis_client
from ..logs.logger import logger
from .errors import AgentOSError, ErrorCode, ErrorType
from .state_machine import TaskState, TaskStateMachine
from .locks import ExecutionLock


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


class TaskQueue:
    """Priority task queue with Redis-backed scheduling.

    Usage:
        queue = TaskQueue()
        position = await queue.enqueue(task, priority=TaskPriority.HIGH)
        task = await queue.dequeue(worker_id="worker-1")
        await queue.complete(task_id)
    """

    def __init__(
        self,
        redis_prefix: str = "agentos:queue:",
        default_worker_ttl: int = 30,
        state_machine: Optional[TaskStateMachine] = None,
        execution_lock: Optional[ExecutionLock] = None,
    ):
        self.redis_prefix = redis_prefix
        self.default_worker_ttl = default_worker_ttl
        self.state_machine = state_machine or TaskStateMachine()
        self.execution_lock = execution_lock or ExecutionLock()

    def _queue_key(self) -> str:
        return f"{self.redis_prefix}tasks"

    def _task_key(self, task_id: str) -> str:
        return f"{self.redis_prefix}task:{task_id}"

    def _worker_key(self, worker_id: str) -> str:
        return f"{self.redis_prefix}worker:{worker_id}"

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
        """Enqueue a task with priority.

        Args:
            task_id: Unique task identifier.
            user_id: User who submitted the task.
            query: Task query string.
            priority: Task priority level.
            config: Execution configuration.
            idempotency_key: Optional idempotency key.
            scheduled_for: Optional scheduled execution time.

        Returns:
            QueuePosition with position and estimated wait.
        """
        config = config or {}
        now = datetime.now(timezone.utc)

        # Compute score: priority * 1_000_000_000 + timestamp
        # This ensures priority is dominant but FIFO within same priority
        timestamp_factor = int(time.time() * 1000)
        score = (priority.value * 1_000_000_000_000) + timestamp_factor

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

        try:
            # Add to sorted set (queue)
            await redis_client.client.zadd(
                self._queue_key(),
                {task_id: score},
            )

            # Store task metadata
            await redis_client.client.hset(
                self._task_key(task_id),
                mapping={
                    "data": queued_task.model_dump_json(),
                    "status": "queued",
                    "enqueued_at": now.isoformat(),
                },
            )

            # Set TTL on task metadata to prevent orphaned data
            await redis_client.client.expire(
                self._task_key(task_id),
                86400,  # 24 hours
            )

            # Update state machine
            try:
                await self.state_machine.transition(
                    task_id=task_id,
                    from_state=TaskState.PENDING,
                    to_state=TaskState.PLANNING,
                    triggered_by="task_queue",
                    context={"priority": priority.name, "scheduled": scheduled_for is not None},
                )
            except Exception as e:
                logger.warning(f"State machine transition failed for {task_id}: {e}")

            position = await self.get_position(task_id)
            queue_length = await self.length()
            estimated_wait = await self._estimate_wait(position)

            logger.info(
                f"Task enqueued",
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

        except Exception as e:
            logger.error(f"Failed to enqueue task {task_id}: {e}")
            raise AgentOSError(
                message=f"Failed to enqueue task: {e}",
                error_type=ErrorType.EXECUTION_ERROR,
                code=ErrorCode.TASK_QUEUE_UNAVAILABLE,
                context={"task_id": task_id, "priority": priority.name},
            )

    async def dequeue(
        self,
        worker_id: str,
        max_priority: Optional[TaskPriority] = None,
    ) -> Optional[QueuedTask]:
        """Dequeue the highest-priority available task.

        Args:
            worker_id: Worker identifier taking the task.
            max_priority: Only dequeue tasks at or above this priority.

        Returns:
            QueuedTask if available, None if queue is empty.
        """
        try:
            # Get the highest priority task (lowest score)
            # Score filter: max_priority.value * 1_000_000_000_000 gives max score for that priority
            max_score = None
            if max_priority is not None:
                max_score = (max_priority.value + 1) * 1_000_000_000_000 - 1

            if max_score is not None:
                results = await redis_client.client.zrangebyscore(
                    self._queue_key(),
                    "-inf",
                    max_score,
                    start=0,
                    num=1,
                )
            else:
                results = await redis_client.client.zrange(
                    self._queue_key(),
                    start=0,
                    end=0,
                )

            if not results:
                return None

            task_id = results[0]

            # Remove from queue atomically using pipeline
            pipe = redis_client.client.pipeline()
            pipe.zrem(self._queue_key(), task_id)
            pipe.hgetall(self._task_key(task_id))
            results = await pipe.execute()
            removed = results[0]
            task_data = results[1]

            if not removed:
                # Another worker took it
                return None

            if not task_data or "data" not in task_data:
                logger.warning(f"Task {task_id} dequeued but metadata missing")
                return None

            task = QueuedTask.model_validate_json(task_data["data"])
            task.worker_id = worker_id
            task.status = "assigned"

            # Update metadata with worker assignment
            await redis_client.client.hset(
                self._task_key(task_id),
                mapping={
                    "data": task.model_dump_json(),
                    "status": "assigned",
                    "worker_id": worker_id,
                    "assigned_at": datetime.now(timezone.utc).isoformat(),
                },
            )

            # Acquire execution lock
            lock_record = await self.execution_lock.acquire(
                task_id=task_id,
                owner=worker_id,
                ttl_seconds=self.default_worker_ttl,
            )
            if not lock_record:
                logger.warning(f"Could not acquire execution lock for {task_id}")

            logger.info(
                f"Task dequeued",
                extra={
                    "task_id": task_id,
                    "worker_id": worker_id,
                    "priority": task.priority.name,
                },
            )

            return task

        except Exception as e:
            logger.error(f"Failed to dequeue task: {e}")
            return None

    async def complete(self, task_id: str) -> bool:
        """Mark a task as completed and clean up queue data.

        Args:
            task_id: The task identifier.

        Returns:
            True if cleaned up, False otherwise.
        """
        try:
            # Remove from queue (in case it was still there)
            await redis_client.client.zrem(self._queue_key(), task_id)

            # Update task metadata
            await redis_client.client.hset(
                self._task_key(task_id),
                mapping={"status": "completed", "completed_at": datetime.now(timezone.utc).isoformat()},
            )

            # Release execution lock
            lock_info = await self.execution_lock.get_lock_info(task_id)
            if lock_info:
                await self.execution_lock.release(task_id, lock_info.lock_id)

            # Set short TTL for cleanup
            await redis_client.client.expire(self._task_key(task_id), 3600)

            logger.info(f"Task marked complete in queue", extra={"task_id": task_id})
            return True
        except Exception as e:
            logger.error(f"Failed to complete task {task_id} in queue: {e}")
            return False

    async def fail(self, task_id: str, error: str) -> bool:
        """Mark a task as failed in the queue.

        Args:
            task_id: The task identifier.
            error: Error message.

        Returns:
            True if updated, False otherwise.
        """
        try:
            await redis_client.client.zrem(self._queue_key(), task_id)
            await redis_client.client.hset(
                self._task_key(task_id),
                mapping={
                    "status": "failed",
                    "error": error,
                    "failed_at": datetime.now(timezone.utc).isoformat(),
                },
            )

            lock_info = await self.execution_lock.get_lock_info(task_id)
            if lock_info:
                await self.execution_lock.release(task_id, lock_info.lock_id)

            await redis_client.client.expire(self._task_key(task_id), 3600)
            logger.info(f"Task marked failed in queue", extra={"task_id": task_id, "error": error})
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
        """Re-queue a failed or retried task.

        Args:
            task_id: The task identifier.
            priority: Optional new priority (defaults to current).
            delay_seconds: Delay before requeue.

        Returns:
            True if requeued, False otherwise.
        """
        try:
            task_data = await redis_client.client.hgetall(self._task_key(task_id))
            if not task_data or "data" not in task_data:
                return False

            task = QueuedTask.model_validate_json(task_data["data"])
            task.retry_count += 1
            task.status = "queued"
            task.worker_id = None
            task.enqueued_at = datetime.now(timezone.utc)
            if priority is not None:
                task.priority = priority

            # Compute new score with delay
            timestamp_factor = int((time.time() + delay_seconds) * 1000)
            score = (task.priority.value * 1_000_000_000_000) + timestamp_factor

            await redis_client.client.zadd(self._queue_key(), {task_id: score})
            await redis_client.client.hset(
                self._task_key(task_id),
                mapping={
                    "data": task.model_dump_json(),
                    "status": "queued",
                    "requeued_at": datetime.now(timezone.utc).isoformat(),
                },
            )

            logger.info(
                f"Task requeued",
                extra={"task_id": task_id, "retry_count": task.retry_count, "delay": delay_seconds},
            )
            return True
        except Exception as e:
            logger.error(f"Failed to requeue task {task_id}: {e}")
            return False

    async def get_position(self, task_id: str) -> int:
        """Get the current queue position of a task (0-indexed).

        Args:
            task_id: The task identifier.

        Returns:
            Position in queue, or -1 if not in queue.
        """
        try:
            rank = await redis_client.client.zrank(self._queue_key(), task_id)
            return rank if rank is not None else -1
        except Exception as e:
            logger.error(f"Failed to get position for {task_id}: {e}")
            return -1

    async def length(self) -> int:
        """Get the total number of tasks in the queue.

        Returns:
            Queue length.
        """
        try:
            return await redis_client.client.zcard(self._queue_key())
        except Exception as e:
            logger.error(f"Failed to get queue length: {e}")
            return 0

    async def list_tasks(
        self,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[QueuedTask]:
        """List tasks in the queue.

        Args:
            status: Filter by status (queued, assigned, completed, failed).
            limit: Maximum number of tasks to return.

        Returns:
            List of QueuedTask objects.
        """
        try:
            task_ids = await redis_client.client.zrange(
                self._queue_key(),
                start=0,
                end=limit - 1,
            )

            tasks = []
            for task_id in task_ids:
                task_data = await redis_client.client.hgetall(self._task_key(task_id))
                if task_data and "data" in task_data:
                    task = QueuedTask.model_validate_json(task_data["data"])
                    if status is None or task.status == status:
                        tasks.append(task)

            return tasks
        except Exception as e:
            logger.error(f"Failed to list queue tasks: {e}")
            return []

    async def _estimate_wait(self, position: int) -> float:
        """Estimate wait time based on queue position.

        Args:
            position: Queue position (0-indexed).

        Returns:
            Estimated wait in seconds.
        """
        if position < 0:
            return 0.0
        # Rough heuristic: 5 seconds per task ahead in queue
        return position * 5.0

    async def clear(self) -> int:
        """Clear all tasks from the queue. Use with caution.

        Returns:
            Number of tasks removed.
        """
        try:
            count = await self.length()
            task_ids = await redis_client.client.zrange(
                self._queue_key(), start=0, end=-1
            )
            for task_id in task_ids:
                await redis_client.client.delete(self._task_key(task_id))
            await redis_client.client.delete(self._queue_key())
            logger.warning(f"Queue cleared, removed {count} tasks")
            return count
        except Exception as e:
            logger.error(f"Failed to clear queue: {e}")
            return 0


# Module-level singleton
task_queue = TaskQueue()
