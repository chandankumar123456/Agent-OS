"""Distributed execution locks using Redis.

Prevents duplicate task execution across processes and instances
using Redis-backed distributed locks with configurable TTL.

In gRPC mode (AGENTOS_RUNTIME_MODE=grpc), transparently delegates to
in-memory fallback to avoid Redis dependency.
"""
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field

from ..config.settings import settings
from ..logs.logger import logger


def _is_grpc_mode() -> bool:
    """Check if running in gRPC mode without importing runtime.mode (avoids circular deps)."""
    mode = settings.RUNTIME_MODE or "http"
    return mode.lower() == "grpc"


class LockRecord(BaseModel):
    """Record of a distributed lock acquisition."""
    lock_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str
    owner: str = Field(default="system")
    acquired_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    ttl_seconds: int = 300


class ExecutionLock:
    """Distributed execution lock backed by Redis.

    In gRPC mode, delegates to InMemoryDistributedLock for local-native operation.

    Usage:
        lock = ExecutionLock()
        record = await lock.acquire(task_id, ttl=60)
        if record:
            try:
                # Execute task
                pass
            finally:
                await lock.release(task_id, record.lock_id)
        else:
            # Lock already held
            pass
    """

    def __init__(
        self,
        redis_prefix: str = "agentos:execution_lock:",
        default_ttl_seconds: int = 300,
    ):
        self.redis_prefix = redis_prefix
        self.default_ttl = default_ttl_seconds

        # In gRPC/desktop mode, use local delegate
        if _is_grpc_mode():
            from ..desktop_native.locks import local_execution_lock
            self._delegate: Optional[object] = local_execution_lock
            logger.debug("ExecutionLock using desktop-native backend (gRPC mode)")
        else:
            self._delegate = None

    def _lock_key(self, task_id: str) -> str:
        return f"{self.redis_prefix}{task_id}"

    async def acquire(
        self,
        task_id: str,
        owner: str = "system",
        ttl_seconds: Optional[int] = None,
    ) -> Optional[LockRecord]:
        """Acquire a distributed lock for a task.

        Args:
            task_id: The task identifier to lock.
            owner: Identifier of the lock owner (process name, worker id, etc.).
            ttl_seconds: Lock TTL in seconds. Defaults to 300.

        Returns:
            LockRecord if acquired, None if lock is already held.
        """
        if self._delegate is not None:
            return await self._delegate.acquire(  # type: ignore[return-value]
                task_id=task_id, owner=owner, ttl_seconds=ttl_seconds
            )

        ttl = ttl_seconds or self.default_ttl
        key = self._lock_key(task_id)
        lock_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        record = LockRecord(
            lock_id=lock_id,
            task_id=task_id,
            owner=owner,
            acquired_at=now,
            expires_at=datetime.utcfromtimestamp(time.time() + ttl),
            ttl_seconds=ttl,
        )

        try:
            from ..memory.short_term import redis_client
            # Use NX (only if not exists) and EX (expiry) for atomic lock acquisition
            acquired = await redis_client.client.set(
                key,
                record.model_dump_json(),
                nx=True,
                ex=ttl,
            )
            if acquired:
                logger.info(
                    "Execution lock acquired",
                    extra={"task_id": task_id, "lock_id": lock_id, "owner": owner, "ttl": ttl},
                )
                return record
            else:
                logger.warning(
                    f"Execution lock already held for task {task_id}",
                    extra={"task_id": task_id, "owner": owner},
                )
                return None
        except Exception as e:
            logger.error(f"Failed to acquire execution lock for {task_id}: {e}")
            # Fail open: if Redis is unavailable, allow execution to proceed
            # This prioritizes availability over strict deduplication
            logger.warning(f"Redis lock failed, allowing execution for {task_id}")
            return record

    async def release(self, task_id: str, lock_id: str) -> bool:
        """Release a distributed lock.

        Args:
            task_id: The task identifier.
            lock_id: The lock_id from the LockRecord returned by acquire().

        Returns:
            True if released, False if lock was not held or owned by different lock_id.
        """
        if self._delegate is not None:
            return await self._delegate.release(task_id=task_id, lock_id=lock_id)  # type: ignore[return-value]

        key = self._lock_key(task_id)
        try:
            from ..memory.short_term import redis_client
            # Get current lock value
            value = await redis_client.client.get(key)
            if not value:
                logger.debug(f"No lock found for task {task_id}")
                return True

            # Verify ownership before releasing
            try:
                import json
                record_data = json.loads(value)
                if record_data.get("lock_id") != lock_id:
                    logger.warning(
                        f"Lock ownership mismatch for task {task_id}: "
                        f"expected {lock_id}, got {record_data.get('lock_id')}"
                    )
                    return False
            except Exception as e:
                logger.warning(f"Could not parse lock record for {task_id}: {e}")
                # If we can't parse, still delete to avoid deadlocks
                pass

            await redis_client.client.delete(key)
            logger.info(
                "Execution lock released",
                extra={"task_id": task_id, "lock_id": lock_id},
            )
            return True
        except Exception as e:
            logger.error(f"Failed to release execution lock for {task_id}: {e}")
            return False

    async def extend(
        self,
        task_id: str,
        lock_id: str,
        additional_seconds: int = 60,
    ) -> bool:
        """Extend the TTL of an existing lock.

        Args:
            task_id: The task identifier.
            lock_id: The lock_id from acquire().
            additional_seconds: Additional TTL to add.

        Returns:
            True if extended, False if lock not found or ownership mismatch.
        """
        if self._delegate is not None:
            return await self._delegate.extend(  # type: ignore[return-value]
                task_id=task_id, lock_id=lock_id, additional_seconds=additional_seconds
            )

        key = self._lock_key(task_id)
        try:
            from ..memory.short_term import redis_client
            value = await redis_client.client.get(key)
            if not value:
                return False

            import json
            record_data = json.loads(value)
            if record_data.get("lock_id") != lock_id:
                logger.warning(
                    f"Lock extend ownership mismatch for task {task_id}"
                )
                return False

            # Update TTL
            new_ttl = record_data.get("ttl_seconds", self.default_ttl) + additional_seconds
            record_data["ttl_seconds"] = new_ttl
            record_data["expires_at"] = datetime.utcfromtimestamp(
                time.time() + new_ttl
            ).isoformat()

            await redis_client.client.set(
                key,
                json.dumps(record_data),
                ex=new_ttl,
            )
            logger.info(
                "Execution lock extended",
                extra={"task_id": task_id, "lock_id": lock_id, "new_ttl": new_ttl},
            )
            return True
        except Exception as e:
            logger.error(f"Failed to extend execution lock for {task_id}: {e}")
            return False

    async def is_locked(self, task_id: str) -> bool:
        """Check if a task is currently locked.

        Args:
            task_id: The task identifier.

        Returns:
            True if locked, False otherwise.
        """
        if self._delegate is not None:
            return await self._delegate.is_locked(task_id=task_id)  # type: ignore[return-value]

        key = self._lock_key(task_id)
        try:
            from ..memory.short_term import redis_client
            exists = await redis_client.client.exists(key)
            return exists > 0
        except Exception as e:
            logger.error(f"Failed to check lock status for {task_id}: {e}")
            return False

    async def get_lock_info(self, task_id: str) -> Optional[LockRecord]:
        """Get information about the current lock for a task.

        Args:
            task_id: The task identifier.

        Returns:
            LockRecord if locked, None otherwise.
        """
        if self._delegate is not None:
            return await self._delegate.get_lock_info(task_id=task_id)  # type: ignore[return-value]

        key = self._lock_key(task_id)
        try:
            from ..memory.short_term import redis_client
            value = await redis_client.client.get(key)
            if not value:
                return None
            import json
            data = json.loads(value)
            return LockRecord(**data)
        except Exception as e:
            logger.error(f"Failed to get lock info for {task_id}: {e}")
            return None

    async def force_release(self, task_id: str) -> bool:
        """Forcefully release a lock regardless of ownership.

        Use with caution — intended for admin/recovery operations only.

        Args:
            task_id: The task identifier.

        Returns:
            True if released or no lock existed.
        """
        if self._delegate is not None:
            return await self._delegate.force_release(task_id=task_id)  # type: ignore[return-value]

        key = self._lock_key(task_id)
        try:
            from ..memory.short_term import redis_client
            await redis_client.client.delete(key)
            logger.warning(
                "Execution lock forcefully released",
                extra={"task_id": task_id},
            )
            return True
        except Exception as e:
            logger.error(f"Failed to force release lock for {task_id}: {e}")
            return False


# Module-level singleton
execution_lock = ExecutionLock()
