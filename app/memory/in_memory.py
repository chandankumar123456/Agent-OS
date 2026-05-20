"""In-memory fallback implementations for gRPC/desktop-native mode.

When running in gRPC mode (AGENTOS_RUNTIME_MODE=grpc), Redis is not available.
These classes provide drop-in replacements that use in-memory data structures
with TTL expiry simulation.

Design:
- Same public API as Redis-backed classes
- TTL expiry checked on access (lazy eviction)
- asyncio.Lock for thread-safety within single process
- Pub/sub via asyncio.Queue + broadcast pattern
"""

import asyncio
import json
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, List, Optional, Set


class _ExpiringDict:
    """Dict-like structure with per-key TTL expiry (lazy eviction)."""

    def __init__(self):
        self._data: Dict[str, Any] = {}
        self._expiry: Dict[str, float] = {}  # key -> absolute expiry time
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        async with self._lock:
            self._evict_expired()
            if key in self._data:
                return self._data[key]
            return None

    async def set(self, key: str, value: Any, ex: Optional[int] = None, nx: bool = False) -> bool:
        async with self._lock:
            self._evict_expired()
            if nx and key in self._data:
                return False
            self._data[key] = value
            if ex is not None:
                self._expiry[key] = time.time() + ex
            elif key in self._expiry:
                del self._expiry[key]
            return True

    async def delete(self, key: str) -> int:
        async with self._lock:
            if key in self._data:
                del self._data[key]
                self._expiry.pop(key, None)
                return 1
            return 0

    async def exists(self, key: str) -> bool:
        async with self._lock:
            self._evict_expired()
            return key in self._data

    def _evict_expired(self):
        now = time.time()
        expired = [k for k, exp in self._expiry.items() if exp <= now]
        for k in expired:
            self._data.pop(k, None)
            del self._expiry[k]


class _InMemorySortedSet:
    """Sorted set implementation for priority queue (mimics Redis ZADD/ZRANGE/ZPOPMIN)."""

    def __init__(self):
        self._scores: Dict[str, float] = {}  # member -> score
        self._lock = asyncio.Lock()

    async def zadd(self, mapping: Dict[str, float]) -> int:
        async with self._lock:
            count = 0
            for member, score in mapping.items():
                if member not in self._scores:
                    count += 1
                self._scores[member] = score
            return count

    async def zrange(self, start: int = 0, end: int = -1) -> List[str]:
        async with self._lock:
            sorted_members = sorted(self._scores.items(), key=lambda x: x[1])
            if end == -1:
                end = len(sorted_members)
            else:
                end = end + 1  # inclusive in Redis
            return [m for m, _ in sorted_members[start:end]]

    async def zrangebyscore(self, min_score: float = float("-inf"), max_score: float = float("inf"),
                            start: int = 0, num: int = -1) -> List[str]:
        async with self._lock:
            filtered = [(m, s) for m, s in self._scores.items() if min_score <= s <= max_score]
            filtered.sort(key=lambda x: x[1])
            if num == -1:
                num = len(filtered)
            return [m for m, _ in filtered[start:start + num]]

    async def zrem(self, *members: str) -> int:
        async with self._lock:
            count = 0
            for m in members:
                if m in self._scores:
                    del self._scores[m]
                    count += 1
            return count

    async def zrank(self, member: str) -> Optional[int]:
        async with self._lock:
            if member not in self._scores:
                return None
            sorted_members = sorted(self._scores.items(), key=lambda x: x[1])
            for i, (m, _) in enumerate(sorted_members):
                if m == member:
                    return i
            return None

    async def zcard(self) -> int:
        async with self._lock:
            return len(self._scores)

    async def zpopmin(self, count: int = 1) -> List[tuple]:
        async with self._lock:
            sorted_members = sorted(self._scores.items(), key=lambda x: x[1])
            result = sorted_members[:count]
            for m, _ in result:
                del self._scores[m]
            return result


class InMemoryPubSub:
    """In-memory pub/sub using asyncio.Queue per channel."""

    def __init__(self):
        self._channels: Dict[str, List[asyncio.Queue]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def subscribe(self, channel: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        async with self._lock:
            self._channels[channel].append(q)
        return q

    async def unsubscribe(self, channel: str, queue: asyncio.Queue):
        async with self._lock:
            if channel in self._channels:
                try:
                    self._channels[channel].remove(queue)
                except ValueError:
                    pass
                if not self._channels[channel]:
                    del self._channels[channel]

    async def publish(self, channel: str, message: str) -> int:
        async with self._lock:
            queues = list(self._channels.get(channel, []))
        for q in queues:
            await q.put(message)
        return len(queues)


# ---------------------------------------------------------------------------
# Higher-level backend wrappers
# ---------------------------------------------------------------------------

class InMemoryDistributedLock:
    """In-memory distributed lock matching ExecutionLock API.

    Uses _ExpiringDict with nx=True for atomic lock acquisition.
    """

    def __init__(
        self,
        prefix: str = "agentos:execution_lock:",
        default_ttl_seconds: int = 300,
    ):
        self._prefix = prefix
        self._default_ttl = default_ttl_seconds
        self._store = _ExpiringDict()

    def _lock_key(self, task_id: str) -> str:
        return f"{self._prefix}{task_id}"

    async def acquire(
        self,
        task_id: str,
        owner: str = "system",
        ttl_seconds: Optional[int] = None,
    ) -> Optional["LockRecord"]:
        from ..orchestrator.types import LockRecord

        ttl = ttl_seconds or self._default_ttl
        key = self._lock_key(task_id)
        lock_id = str(__import__("uuid").uuid4())
        now = datetime.now(timezone.utc)
        record = LockRecord(
            lock_id=lock_id,
            task_id=task_id,
            owner=owner,
            acquired_at=now,
            expires_at=datetime.fromtimestamp(time.time() + ttl, tz=timezone.utc),
            ttl_seconds=ttl,
        )

        try:
            acquired = await self._store.set(key, record.model_dump_json(), ex=ttl, nx=True)
            if acquired:
                from ..logs.logger import logger
                logger.info(
                    "Execution lock acquired (in-memory)",
                    extra={"task_id": task_id, "lock_id": lock_id, "owner": owner, "ttl": ttl},
                )
                return record
            else:
                from ..logs.logger import logger
                logger.warning(
                    "Execution lock already held (in-memory)",
                    extra={"task_id": task_id, "owner": owner},
                )
                return None
        except Exception as e:
            from ..logs.logger import logger
            logger.error(f"Failed to acquire in-memory lock for {task_id}: {e}")
            return record

    async def release(self, task_id: str, lock_id: str) -> bool:
        key = self._lock_key(task_id)
        try:
            value = await self._store.get(key)
            if not value:
                return True

            import json
            record_data = json.loads(value)
            if record_data.get("lock_id") != lock_id:
                from ..logs.logger import logger
                logger.warning(
                    f"Lock ownership mismatch for task {task_id}: "
                    f"expected {lock_id}, got {record_data.get('lock_id')}"
                )
                return False

            await self._store.delete(key)
            from ..logs.logger import logger
            logger.info(
                "Execution lock released (in-memory)",
                extra={"task_id": task_id, "lock_id": lock_id},
            )
            return True
        except Exception as e:
            from ..logs.logger import logger
            logger.error(f"Failed to release in-memory lock for {task_id}: {e}")
            return False

    async def extend(
        self,
        task_id: str,
        lock_id: str,
        additional_seconds: int = 60,
    ) -> bool:
        key = self._lock_key(task_id)
        try:
            import json
            value = await self._store.get(key)
            if not value:
                return False

            record_data = json.loads(value)
            if record_data.get("lock_id") != lock_id:
                from ..logs.logger import logger
                logger.warning(
                    f"Lock extend ownership mismatch for task {task_id}"
                )
                return False

            new_ttl = record_data.get("ttl_seconds", self._default_ttl) + additional_seconds
            record_data["ttl_seconds"] = new_ttl
            record_data["expires_at"] = datetime.fromtimestamp(
                time.time() + new_ttl, tz=timezone.utc
            ).isoformat()

            await self._store.set(key, json.dumps(record_data), ex=new_ttl)
            from ..logs.logger import logger
            logger.info(
                "Execution lock extended (in-memory)",
                extra={"task_id": task_id, "lock_id": lock_id, "new_ttl": new_ttl},
            )
            return True
        except Exception as e:
            from ..logs.logger import logger
            logger.error(f"Failed to extend in-memory lock for {task_id}: {e}")
            return False

    async def is_locked(self, task_id: str) -> bool:
        key = self._lock_key(task_id)
        try:
            return await self._store.exists(key)
        except Exception as e:
            from ..logs.logger import logger
            logger.error(f"Failed to check in-memory lock status for {task_id}: {e}")
            return False

    async def get_lock_info(self, task_id: str) -> Optional["LockRecord"]:
        from ..orchestrator.types import LockRecord

        key = self._lock_key(task_id)
        try:
            import json
            value = await self._store.get(key)
            if not value:
                return None
            data = json.loads(value)
            return LockRecord(**data)
        except Exception as e:
            from ..logs.logger import logger
            logger.error(f"Failed to get in-memory lock info for {task_id}: {e}")
            return None

    async def force_release(self, task_id: str) -> bool:
        key = self._lock_key(task_id)
        try:
            await self._store.delete(key)
            from ..logs.logger import logger
            logger.warning(
                "Execution lock forcefully released (in-memory)",
                extra={"task_id": task_id},
            )
            return True
        except Exception as e:
            from ..logs.logger import logger
            logger.error(f"Failed to force release in-memory lock for {task_id}: {e}")
            return False


class InMemoryTaskQueue:
    """In-memory priority task queue matching TaskQueue API.

    Uses _InMemorySortedSet for priority ordering and _ExpiringDict for metadata.
    """

    def __init__(
        self,
        prefix: str = "agentos:queue:",
        default_worker_ttl: int = 30,
        state_machine: Optional["TaskStateMachine"] = None,
        execution_lock: Optional[InMemoryDistributedLock] = None,
    ):
        self._prefix = prefix
        self._default_worker_ttl = default_worker_ttl
        self._queue = _InMemorySortedSet()
        self._metadata = _ExpiringDict()

        # Lazy-import to avoid circular deps at module load
        self._state_machine = state_machine
        self._execution_lock = execution_lock

    def _queue_key(self) -> str:
        return f"{self._prefix}tasks"

    def _task_key(self, task_id: str) -> str:
        return f"{self._prefix}task:{task_id}"

    async def enqueue(
        self,
        task_id: str,
        user_id: str,
        query: str,
        priority: "TaskPriority" = None,
        config: Optional[Dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
        scheduled_for: Optional[datetime] = None,
    ) -> "QueuePosition":
        from ..orchestrator.types import TaskPriority, QueuePosition, QueuedTask
        from ..logs.logger import logger

        if priority is None:
            priority = TaskPriority.NORMAL

        config = config or {}
        now = datetime.now(timezone.utc)

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
            await self._queue.zadd({task_id: score})
            await self._metadata.set(
                self._task_key(task_id),
                {
                    "data": queued_task.model_dump_json(),
                    "status": "queued",
                    "enqueued_at": now.isoformat(),
                },
                ex=86400,
            )

            # State machine transition (best-effort)
            if self._state_machine:
                from ..orchestrator.types import TaskState
                try:
                    await self._state_machine.transition(
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
                "Task enqueued (in-memory)",
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
            from ..orchestrator.errors import AgentOSError, ErrorCode, ErrorType
            from ..logs.logger import logger
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
        max_priority: Optional["TaskPriority"] = None,
    ) -> Optional["QueuedTask"]:
        from ..orchestrator.types import TaskPriority, QueuedTask
        from ..logs.logger import logger

        try:
            max_score = None
            if max_priority is not None:
                max_score = (max_priority.value + 1) * 1_000_000_000_000 - 1

            if max_score is not None:
                results = await self._queue.zrangebyscore(
                    min_score=float("-inf"), max_score=max_score, start=0, num=1
                )
            else:
                results = await self._queue.zrange(start=0, end=0)

            if not results:
                return None

            task_id = results[0]

            # Remove from queue
            removed = await self._queue.zrem(task_id)
            if not removed:
                return None

            # Get metadata
            meta = await self._metadata.get(self._task_key(task_id))
            if not meta or "data" not in meta:
                logger.warning(f"Task {task_id} dequeued but metadata missing")
                return None

            task = QueuedTask.model_validate_json(meta["data"])
            task.worker_id = worker_id
            task.status = "assigned"

            # Update metadata
            await self._metadata.set(
                self._task_key(task_id),
                {
                    "data": task.model_dump_json(),
                    "status": "assigned",
                    "worker_id": worker_id,
                    "assigned_at": datetime.now(timezone.utc).isoformat(),
                },
            )

            # Acquire execution lock
            lock = self._execution_lock or InMemoryDistributedLock()
            lock_record = await lock.acquire(
                task_id=task_id,
                owner=worker_id,
                ttl_seconds=self._default_worker_ttl,
            )
            if not lock_record:
                logger.warning(f"Could not acquire execution lock for {task_id}")

            logger.info(
                "Task dequeued (in-memory)",
                extra={
                    "task_id": task_id,
                    "worker_id": worker_id,
                    "priority": task.priority.name,
                },
            )

            return task
        except Exception as e:
            from ..logs.logger import logger
            logger.error(f"Failed to dequeue task: {e}")
            return None

    async def complete(self, task_id: str) -> bool:
        from ..logs.logger import logger
        from datetime import datetime, timezone

        try:
            await self._queue.zrem(task_id)

            meta = await self._metadata.get(self._task_key(task_id))
            if meta:
                meta["status"] = "completed"
                meta["completed_at"] = datetime.now(timezone.utc).isoformat()
                await self._metadata.set(self._task_key(task_id), meta)

            # Release execution lock
            lock = self._execution_lock or InMemoryDistributedLock()
            lock_info = await lock.get_lock_info(task_id)
            if lock_info:
                await lock.release(task_id, lock_info.lock_id)

            logger.info("Task marked complete in queue (in-memory)", extra={"task_id": task_id})
            return True
        except Exception as e:
            from ..logs.logger import logger
            logger.error(f"Failed to complete task {task_id} in queue: {e}")
            return False

    async def fail(self, task_id: str, error: str) -> bool:
        from ..logs.logger import logger
        from datetime import datetime, timezone

        try:
            await self._queue.zrem(task_id)

            meta = await self._metadata.get(self._task_key(task_id))
            if meta:
                meta["status"] = "failed"
                meta["error"] = error
                meta["failed_at"] = datetime.now(timezone.utc).isoformat()
                await self._metadata.set(self._task_key(task_id), meta)

            lock = self._execution_lock or InMemoryDistributedLock()
            lock_info = await lock.get_lock_info(task_id)
            if lock_info:
                await lock.release(task_id, lock_info.lock_id)

            logger.info("Task marked failed in queue (in-memory)", extra={"task_id": task_id, "error": error})
            return True
        except Exception as e:
            from ..logs.logger import logger
            logger.error(f"Failed to mark task {task_id} as failed: {e}")
            return False

    async def requeue(
        self,
        task_id: str,
        priority: Optional["TaskPriority"] = None,
        delay_seconds: int = 0,
    ) -> bool:
        from ..orchestrator.types import TaskPriority, QueuedTask
        from ..logs.logger import logger

        try:
            meta = await self._metadata.get(self._task_key(task_id))
            if not meta or "data" not in meta:
                return False

            task = QueuedTask.model_validate_json(meta["data"])
            task.retry_count += 1
            task.status = "queued"
            task.worker_id = None
            task.enqueued_at = datetime.now(timezone.utc)
            if priority is not None:
                task.priority = priority

            timestamp_factor = int((time.time() + delay_seconds) * 1000)
            score = (task.priority.value * 1_000_000_000_000) + timestamp_factor

            await self._queue.zadd({task_id: score})
            meta["data"] = task.model_dump_json()
            meta["status"] = "queued"
            meta["requeued_at"] = datetime.now(timezone.utc).isoformat()
            await self._metadata.set(self._task_key(task_id), meta)

            logger.info(
                "Task requeued (in-memory)",
                extra={"task_id": task_id, "retry_count": task.retry_count, "delay": delay_seconds},
            )
            return True
        except Exception as e:
            from ..logs.logger import logger
            logger.error(f"Failed to requeue task {task_id}: {e}")
            return False

    async def get_position(self, task_id: str) -> int:
        try:
            rank = await self._queue.zrank(task_id)
            return rank if rank is not None else -1
        except Exception as e:
            from ..logs.logger import logger
            logger.error(f"Failed to get position for {task_id}: {e}")
            return -1

    async def length(self) -> int:
        try:
            return await self._queue.zcard()
        except Exception as e:
            from ..logs.logger import logger
            logger.error(f"Failed to get queue length: {e}")
            return 0

    async def list_tasks(
        self,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List["QueuedTask"]:
        from ..orchestrator.types import QueuedTask
        from ..logs.logger import logger

        try:
            task_ids = await self._queue.zrange(start=0, end=limit - 1)

            tasks = []
            for task_id in task_ids:
                meta = await self._metadata.get(self._task_key(task_id))
                if meta and "data" in meta:
                    task = QueuedTask.model_validate_json(meta["data"])
                    if status is None or task.status == status:
                        tasks.append(task)

            return tasks
        except Exception as e:
            from ..logs.logger import logger
            logger.error(f"Failed to list queue tasks: {e}")
            return []

    async def _estimate_wait(self, position: int) -> float:
        if position < 0:
            return 0.0
        return position * 5.0

    async def clear(self) -> int:
        from ..logs.logger import logger

        try:
            count = await self.length()
            task_ids = await self._queue.zrange(start=0, end=-1)
            for task_id in task_ids:
                await self._metadata.delete(self._task_key(task_id))
            logger.warning(f"Queue cleared (in-memory), removed {count} tasks")
            return count
        except Exception as e:
            from ..logs.logger import logger
            logger.error(f"Failed to clear queue: {e}")
            return 0


# ---------------------------------------------------------------------------
# Session & Short-Term Memory fallbacks
# ---------------------------------------------------------------------------

class InMemorySessionStore:
    """In-memory session store matching SessionMemory API.

    Uses _ExpiringDict with 2-hour default TTL (7200s).
    """

    def __init__(self, default_ttl: int = 7200):
        self._prefix = "agentos:memory:session:"
        self._store = _ExpiringDict()
        self._default_ttl = default_ttl

    def _browser_key(self, task_id: str) -> str:
        return f"{self._prefix}{task_id}:browser"

    def _envs_key(self, task_id: str) -> str:
        return f"{self._prefix}{task_id}:envs"

    async def get_browser_session(self, task_id: str) -> Optional[Dict[str, Any]]:
        return await self._store.get(self._browser_key(task_id))

    async def set_browser_session(
        self,
        task_id: str,
        data: Dict[str, Any],
        expire: int = 7200,
    ) -> bool:
        return await self._store.set(self._browser_key(task_id), data, ex=expire)

    async def get_active_envs(self, task_id: str) -> Optional[Dict[str, Any]]:
        return await self._store.get(self._envs_key(task_id))

    async def set_active_envs(
        self,
        task_id: str,
        data: Dict[str, Any],
        expire: int = 7200,
    ) -> bool:
        return await self._store.set(self._envs_key(task_id), data, ex=expire)


class InMemoryShortTermMemory:
    """In-memory short-term context matching ShortTermMemory API.

    Uses _ExpiringDict with 1-hour default TTL (3600s).
    """

    def __init__(self, default_ttl: int = 3600):
        self._prefix = "agentos:context:"
        self._store = _ExpiringDict()
        self._default_ttl = default_ttl

    async def save_context(
        self,
        task_id: str,
        context: Dict[str, Any],
        expire: int = 3600,
    ) -> bool:
        key = f"{self._prefix}{task_id}"
        return await self._store.set(key, context, ex=expire)

    async def get_context(self, task_id: str) -> Optional[Dict[str, Any]]:
        key = f"{self._prefix}{task_id}"
        return await self._store.get(key)

    async def delete_context(self, task_id: str) -> bool:
        key = f"{self._prefix}{task_id}"
        return await self._store.delete(key) > 0
