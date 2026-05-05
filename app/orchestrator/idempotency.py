"""Idempotency enforcement with Redis locks.

Prevents duplicate task execution using idempotency keys and
distributed locks with configurable TTL.
"""
import hashlib
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from ..memory.short_term import redis_client
from ..memory.long_term import db
from ..logs.logger import logger
from .errors import AgentOSError, ErrorCode, ErrorType


class IdempotencyRecord(BaseModel):
    """Record of an idempotency key usage."""
    record_id: str = Field(default_factory=lambda: str(uuid4()))
    idempotency_key: str
    task_id: str
    status: str = Field(default="pending")  # pending, completed, failed
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result_ref: Optional[str] = None


class IdempotencyEnforcement:
    """Enforces idempotency using Redis locks and deduplication.

    Usage:
        enforcement = IdempotencyEnforcement()
        if await enforcement.acquire_lock("key-123", task_id):
            # Execute task
            await enforcement.mark_completed("key-123", task_id)
        else:
            # Duplicate detected
            existing = await enforcement.get_record("key-123")
    """

    def __init__(
        self,
        lock_ttl_seconds: int = 300,
        record_ttl_hours: int = 24,
        redis_prefix: str = "agentos:idempotency:",
    ):
        self.lock_ttl = lock_ttl_seconds
        self.record_ttl = record_ttl_hours * 3600
        self.redis_prefix = redis_prefix

    def _lock_key(self, idempotency_key: str) -> str:
        return f"{self.redis_prefix}lock:{idempotency_key}"

    def _record_key(self, idempotency_key: str) -> str:
        return f"{self.redis_prefix}record:{idempotency_key}"

    def generate_key(
        self,
        user_id: str,
        query: str,
        config: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Generate a deterministic idempotency key.

        Args:
            user_id: User identifier.
            query: Task query string.
            config: Optional config dict.

        Returns:
            SHA-256 hash as idempotency key.
        """
        content = f"{user_id}:{query}"
        if config:
            import json
            # Sort keys for determinism
            content += f":{json.dumps(config, sort_keys=True)}"
        return hashlib.sha256(content.encode()).hexdigest()

    async def acquire_lock(
        self,
        idempotency_key: str,
        task_id: str,
    ) -> bool:
        """Acquire an idempotency lock.

        Args:
            idempotency_key: The idempotency key.
            task_id: Current task ID attempting to acquire.

        Returns:
            True if lock acquired, False if already locked by another task.

        Raises:
            AgentOSError: If lock is held by another active task (idempotency conflict).
        """
        lock_key = self._lock_key(idempotency_key)
        record_key = self._record_key(idempotency_key)

        try:
            # Check for existing record
            existing = await redis_client.get(record_key)
            if existing:
                existing_task_id = existing.get("task_id")
                existing_status = existing.get("status", "pending")

                if existing_task_id != task_id:
                    # Another task holds this key
                    if existing_status == "pending":
                        # Check if lock is expired
                        lock = await redis_client.get(lock_key)
                        if lock:
                            raise AgentOSError(
                                message=f"Idempotency conflict: key '{idempotency_key}' is already in use by task {existing_task_id}",
                                error_type=ErrorType.EXECUTION_ERROR,
                                recoverable=False,
                                code=ErrorCode.TASK_IDEMPOTENCY_CONFLICT,
                                context={
                                    "idempotency_key": idempotency_key,
                                    "existing_task_id": existing_task_id,
                                    "requested_task_id": task_id,
                                },
                                http_status=409,
                            )
                        else:
                            # Lock expired, steal it
                            logger.info(f"Stealing expired idempotency lock for {idempotency_key}")
                    elif existing_status in ("completed", "failed"):
                        # Already processed - return the result reference
                        return False

            # Try to acquire lock with NX (only if not exists)
            lock_data = {
                "task_id": task_id,
                "acquired_at": datetime.utcnow().isoformat(),
            }
            # Use SET NX EX via redis_client's set method
            # Since redis_client.set doesn't support NX, we check get first
            current_lock = await redis_client.get(lock_key)
            if current_lock is not None:
                # Lock exists, check who holds it
                if current_lock and current_lock.get("task_id") != task_id:
                    raise AgentOSError(
                        message=f"Idempotency lock held by another task",
                        error_type=ErrorType.EXECUTION_ERROR,
                        recoverable=False,
                        code=ErrorCode.TASK_IDEMPOTENCY_CONFLICT,
                        context={
                            "idempotency_key": idempotency_key,
                            "holder_task_id": current_lock.get("task_id"),
                            "requested_task_id": task_id,
                        },
                        http_status=409,
                    )

            await redis_client.set(lock_key, lock_data, expire=self.lock_ttl)

            # Create or update record
            record = {
                "idempotency_key": idempotency_key,
                "task_id": task_id,
                "status": "pending",
                "created_at": datetime.utcnow().isoformat(),
            }
            await redis_client.set(record_key, record, expire=self.record_ttl)

            # Persist to DB for durability
            await self._save_record_to_db(idempotency_key, task_id, "pending")

            logger.debug(f"Acquired idempotency lock: {idempotency_key} -> {task_id}")
            return True

        except AgentOSError:
            raise
        except Exception as e:
            logger.error(f"Idempotency lock acquisition failed: {e}")
            # Fail open - allow execution if lock mechanism is broken
            return True

    async def release_lock(self, idempotency_key: str, task_id: str) -> bool:
        """Release an idempotency lock.

        Args:
            idempotency_key: The idempotency key.
            task_id: Task ID that holds the lock.

        Returns:
            True if released, False if not held by this task.
        """
        lock_key = self._lock_key(idempotency_key)
        try:
            lock = await redis_client.get(lock_key)
            if lock and lock.get("task_id") == task_id:
                await redis_client.delete(lock_key)
                logger.debug(f"Released idempotency lock: {idempotency_key}")
                return True
            return False
        except Exception as e:
            logger.warning(f"Idempotency lock release failed: {e}")
            return False

    async def mark_completed(
        self,
        idempotency_key: str,
        task_id: str,
        result_ref: Optional[str] = None,
    ) -> None:
        """Mark an idempotent task as completed.

        Args:
            idempotency_key: The idempotency key.
            task_id: The task identifier.
            result_ref: Optional reference to the result.
        """
        record_key = self._record_key(idempotency_key)
        try:
            record = await redis_client.get(record_key) or {}
            if record.get("task_id") == task_id:
                record["status"] = "completed"
                record["completed_at"] = datetime.utcnow().isoformat()
                if result_ref:
                    record["result_ref"] = result_ref
                await redis_client.set(record_key, record, expire=self.record_ttl)
                await self._save_record_to_db(idempotency_key, task_id, "completed", result_ref)
                logger.debug(f"Marked idempotency complete: {idempotency_key}")
        except Exception as e:
            logger.warning(f"Mark completed failed for {idempotency_key}: {e}")

    async def mark_failed(self, idempotency_key: str, task_id: str) -> None:
        """Mark an idempotent task as failed.

        Args:
            idempotency_key: The idempotency key.
            task_id: The task identifier.
        """
        record_key = self._record_key(idempotency_key)
        try:
            record = await redis_client.get(record_key) or {}
            if record.get("task_id") == task_id:
                record["status"] = "failed"
                record["completed_at"] = datetime.utcnow().isoformat()
                await redis_client.set(record_key, record, expire=self.record_ttl)
                await self._save_record_to_db(idempotency_key, task_id, "failed")
                logger.debug(f"Marked idempotency failed: {idempotency_key}")
        except Exception as e:
            logger.warning(f"Mark failed failed for {idempotency_key}: {e}")

    async def get_record(self, idempotency_key: str) -> Optional[Dict[str, Any]]:
        """Get the idempotency record for a key.

        Args:
            idempotency_key: The idempotency key.

        Returns:
            Record dict if found, None otherwise.
        """
        record_key = self._record_key(idempotency_key)
        try:
            return await redis_client.get(record_key)
        except Exception as e:
            logger.warning(f"Redis record read failed for {idempotency_key}: {e}")
        return None

    async def is_duplicate(self, idempotency_key: str) -> bool:
        """Check if a key represents a completed duplicate.

        Args:
            idempotency_key: The idempotency key.

        Returns:
            True if already completed, False otherwise.
        """
        record = await self.get_record(idempotency_key)
        if record and record.get("status") == "completed":
            return True
        return False

    async def _save_record_to_db(
        self,
        idempotency_key: str,
        task_id: str,
        status: str,
        result_ref: Optional[str] = None,
    ) -> None:
        """Persist idempotency record to PostgreSQL."""
        try:
            async with db.get_session() as session:
                from sqlalchemy import select
                from ..memory.models import ContextModel
                result = await session.execute(
                    select(ContextModel).where(
                        ContextModel.task_id == f"idempotency:{idempotency_key}"
                    )
                )
                existing = result.scalar_one_or_none()
                value = {
                    "idempotency_key": idempotency_key,
                    "task_id": task_id,
                    "status": status,
                    "result_ref": result_ref,
                    "updated_at": datetime.utcnow().isoformat(),
                }
                if existing:
                    existing.value = value
                else:
                    ctx = ContextModel(
                        task_id=f"idempotency:{idempotency_key}",
                        key="record",
                        value=value,
                    )
                    session.add(ctx)
                await session.commit()
        except Exception as e:
            logger.warning(f"DB idempotency record save failed: {e}")


# Module-level singleton
idempotency_enforcement = IdempotencyEnforcement()
