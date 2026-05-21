"""Local execution locks for desktop-native mode.

Replaces Redis distributed locks with asyncio.Lock and asyncio.Semaphore.
In a single-process desktop runtime, true distributed locks are unnecessary.
"""

import asyncio
import time
import uuid
from datetime import datetime, timezone
from typing import Dict, Optional

from pydantic import BaseModel, Field

from ..logs.logger import logger
from .sqlite_store import sqlite_store


class LockRecord(BaseModel):
    """Record of a lock acquisition."""
    lock_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str
    owner: str = Field(default="system")
    acquired_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    ttl_seconds: int = 300


class LocalExecutionLock:
    """Local execution lock using asyncio primitives.

    Uses a dictionary of per-task locks for concurrency control within
    the single Python process. Also persists lock state to SQLite for
    inspection and recovery.
    """

    def __init__(
        self,
        prefix: str = "agentos:execution_lock:",
        default_ttl_seconds: int = 300,
    ):
        self._prefix = prefix
        self._default_ttl = default_ttl_seconds
        self._locks: Dict[str, asyncio.Lock] = {}
        self._lock_owners: Dict[str, LockRecord] = {}
        self._global_lock = asyncio.Lock()

    def _lock_key(self, task_id: str) -> str:
        return f"{self._prefix}{task_id}"

    async def acquire(
        self,
        task_id: str,
        owner: str = "system",
        ttl_seconds: Optional[int] = None,
    ) -> Optional[LockRecord]:
        """Acquire a lock for a task.

        In desktop mode, this uses asyncio.Lock for intra-process
        concurrency control. The lock is also recorded in SQLite.
        """
        ttl = ttl_seconds or self._default_ttl
        now = datetime.now(timezone.utc)
        lock_id = str(uuid.uuid4())
        record = LockRecord(
            lock_id=lock_id,
            task_id=task_id,
            owner=owner,
            acquired_at=now,
            expires_at=datetime.fromtimestamp(time.time() + ttl, tz=timezone.utc),
            ttl_seconds=ttl,
        )

        key = self._lock_key(task_id)

        async with self._global_lock:
            if key not in self._locks:
                self._locks[key] = asyncio.Lock()

        # Try to acquire the asyncio lock without blocking
        acquired = self._locks[key].locked()
        if acquired:
            # Already held by another task in the same process
            logger.warning(
                f"Execution lock already held for task {task_id}",
                extra={"task_id": task_id, "owner": owner},
            )
            return None

        await self._locks[key].acquire()

        async with self._global_lock:
            self._lock_owners[key] = record

        # Persist to SQLite
        try:
            await sqlite_store.execute(
                """
                INSERT OR REPLACE INTO execution_locks
                (task_id, lock_id, owner, acquired_at, expires_at, ttl_seconds)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (task_id, lock_id, owner, now.isoformat(),
                 record.expires_at.isoformat() if record.expires_at else None, ttl),
            )
            await sqlite_store.commit()
        except Exception as e:
            logger.warning(f"Failed to persist lock to SQLite: {e}")

        logger.info(
            "Execution lock acquired",
            extra={"task_id": task_id, "lock_id": lock_id, "owner": owner, "ttl": ttl},
        )
        return record

    async def release(self, task_id: str, lock_id: str) -> bool:
        """Release a lock."""
        key = self._lock_key(task_id)

        async with self._global_lock:
            current = self._lock_owners.get(key)
            if current and current.lock_id != lock_id:
                logger.warning(
                    f"Lock ownership mismatch for task {task_id}: "
                    f"expected {lock_id}, got {current.lock_id}"
                )
                return False

            self._lock_owners.pop(key, None)

        lock = self._locks.get(key)
        if lock and lock.locked():
            try:
                lock.release()
            except RuntimeError:
                pass  # Already released

        # Remove from SQLite
        try:
            await sqlite_store.execute(
                "DELETE FROM execution_locks WHERE task_id = ?",
                (task_id,),
            )
            await sqlite_store.commit()
        except Exception as e:
            logger.warning(f"Failed to remove lock from SQLite: {e}")

        logger.info(
            "Execution lock released",
            extra={"task_id": task_id, "lock_id": lock_id},
        )
        return True

    async def extend(
        self,
        task_id: str,
        lock_id: str,
        additional_seconds: int = 60,
    ) -> bool:
        """Extend the TTL of an existing lock."""
        key = self._lock_key(task_id)

        async with self._global_lock:
            current = self._lock_owners.get(key)
            if not current:
                return False
            if current.lock_id != lock_id:
                logger.warning(
                    f"Lock extend ownership mismatch for task {task_id}"
                )
                return False

            current.ttl_seconds += additional_seconds
            current.expires_at = datetime.fromtimestamp(
                time.time() + current.ttl_seconds, tz=timezone.utc
            )

        # Update SQLite
        try:
            await sqlite_store.execute(
                """
                UPDATE execution_locks
                SET ttl_seconds = ttl_seconds + ?, expires_at = ?
                WHERE task_id = ? AND lock_id = ?
                """,
                (additional_seconds,
                 datetime.fromtimestamp(time.time() + current.ttl_seconds, tz=timezone.utc).isoformat(),
                 task_id, lock_id),
            )
            await sqlite_store.commit()
        except Exception as e:
            logger.warning(f"Failed to extend lock in SQLite: {e}")

        logger.info(
            "Execution lock extended",
            extra={"task_id": task_id, "lock_id": lock_id, "new_ttl": current.ttl_seconds},
        )
        return True

    async def is_locked(self, task_id: str) -> bool:
        """Check if a task is currently locked."""
        key = self._lock_key(task_id)
        lock = self._locks.get(key)
        return lock is not None and lock.locked()

    async def get_lock_info(self, task_id: str) -> Optional[LockRecord]:
        """Get information about the current lock for a task."""
        key = self._lock_key(task_id)
        async with self._global_lock:
            return self._lock_owners.get(key)

    async def force_release(self, task_id: str) -> bool:
        """Forcefully release a lock regardless of ownership."""
        key = self._lock_key(task_id)

        async with self._global_lock:
            self._lock_owners.pop(key, None)

        lock = self._locks.get(key)
        if lock and lock.locked():
            try:
                lock.release()
            except RuntimeError:
                pass

        try:
            await sqlite_store.execute(
                "DELETE FROM execution_locks WHERE task_id = ?",
                (task_id,),
            )
            await sqlite_store.commit()
        except Exception as e:
            logger.warning(f"Failed to force release lock in SQLite: {e}")

        logger.warning(
            "Execution lock forcefully released",
            extra={"task_id": task_id},
        )
        return True

    async def cleanup_expired(self) -> int:
        """Remove expired locks from SQLite and memory."""
        now = datetime.now(timezone.utc).isoformat()
        count = 0
        try:
            rows = await sqlite_store.fetchall(
                "SELECT task_id FROM execution_locks WHERE expires_at < ?",
                (now,),
            )
            for row in rows:
                task_id = row["task_id"]
                await self.force_release(task_id)
                count += 1
        except Exception as e:
            logger.error(f"Failed to cleanup expired locks: {e}")
        return count


# Module-level singleton
local_execution_lock = LocalExecutionLock()
