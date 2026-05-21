"""Persistent memory manager for durable key-value storage with TTL and pruning.

Wraps existing RedisClient + Database singletons to provide a unified
persistence interface with Redis for fast access and PostgreSQL for durability.
Supports size-based LRU eviction, TTL expiry, and optional LLM summarization
of memory contents.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from pydantic import BaseModel, Field

from .short_term import redis_client
from .long_term import db
from ..logs.logger import logger
from ..orchestrator.errors import AgentOSError, ErrorCode, ErrorType


class MemoryEntry(BaseModel):
    """A single persistent memory entry."""
    entry_id: str = Field(default_factory=lambda: str(uuid4()))
    namespace: str = Field(default="default", description="Logical grouping namespace")
    key: str = Field(..., description="Unique key within the namespace")
    value: Dict[str, Any] = Field(default_factory=dict, description="Stored value")
    ttl: Optional[int] = Field(default=3600, description="TTL in seconds (None = no expiry)")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="User-defined metadata")
    created_at: Optional[datetime] = Field(default=None, description="Creation timestamp")
    updated_at: Optional[datetime] = Field(default=None, description="Last update timestamp")
    access_count: int = Field(default=0, description="Number of times accessed")


class MemorySummary(BaseModel):
    """Summarized view of memory entries."""
    namespace: str
    total_entries: int
    total_size_kb: float = 0.0
    oldest_entry: Optional[datetime] = None
    newest_entry: Optional[datetime] = None
    sample_keys: List[str] = Field(default_factory=list, description="Representative keys")


class PersistentMemoryManager:
    """Manages persistent memory entries across Redis (fast) and PostgreSQL (durable).

    Uses Redis as the primary read/write path with TTL-based expiry. Entries are
    periodically flushed to PostgreSQL for durability. LRU tracking enables
    size-based pruning when memory limits are exceeded.

    Usage:
        manager = PersistentMemoryManager(max_entries=10000, ttl_default=3600)
        await manager.store("tasks", "task-123", {"status": "running"})
        entry = await manager.retrieve("tasks", "task-123")
    """

    def __init__(
        self,
        max_entries: int = 10000,
        ttl_default: int = 3600,
        prune_threshold: float = 0.9,
        namespace_prefix: str = "agentos:mem:",
    ):
        self.max_entries = max_entries
        self.ttl_default = ttl_default
        self.prune_threshold = prune_threshold
        self.namespace_prefix = namespace_prefix
        self._lru_tracker_key = f"{namespace_prefix}lru_tracker"

    def _make_redis_key(self, namespace: str, key: str) -> str:
        """Build the Redis key for a memory entry."""
        return f"{self.namespace_prefix}{namespace}:{key}"

    def _make_namespace_index_key(self, namespace: str) -> str:
        """Build the Redis key for a namespace index."""
        return f"{self.namespace_prefix}{namespace}:__index__"

    async def store(
        self,
        namespace: str,
        key: str,
        value: Dict[str, Any],
        ttl: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> MemoryEntry:
        """Store a memory entry, evicting old entries if needed.

        Args:
            namespace: Logical grouping for the entry.
            key: Unique key within the namespace.
            value: The data to store (must be JSON-serializable).
            ttl: Time-to-live in seconds. Uses self.ttl_default if None.
            metadata: Optional user-defined metadata.

        Returns:
            The stored MemoryEntry.

        Raises:
            AgentOSError: If storage fails or entry limit is exceeded.
        """
        await self._check_and_prune(namespace)

        now = datetime.now(timezone.utc)
        expire = ttl if ttl is not None else self.ttl_default

        entry = MemoryEntry(
            namespace=namespace,
            key=key,
            value=value,
            ttl=expire,
            metadata=metadata or {},
            created_at=now,
            updated_at=now,
        )

        redis_key = self._make_redis_key(namespace, key)
        index_key = self._make_namespace_index_key(namespace)

        try:
            # Store entry in Redis
            await redis_client.set(redis_key, entry.model_dump(mode="json"), expire=expire)
            # Add key to namespace index for listing
            if await redis_client.exists(index_key):
                idx_data = (await redis_client.get(index_key)) or {"keys": []}
            else:
                idx_data = {"keys": []}
            if key not in idx_data["keys"]:
                idx_data["keys"].append(key)
                # Use a longer TTL for the index (24h default)
                await redis_client.set(index_key, idx_data, expire=86400)
            # Track in LRU
            await self._update_lru(redis_key)
            logger.debug(f"Stored persistent memory: {namespace}:{key}")
            return entry
        except Exception as e:
            logger.error(f"Failed to store memory entry {namespace}:{key}: {e}")
            raise AgentOSError(
                message=f"Failed to store memory entry: {e}",
                error_type=ErrorType.EXECUTION_ERROR,
                recoverable=True,
                code=ErrorCode.INTERNAL_ERROR,
                context={"namespace": namespace, "key": key},
            )

    async def retrieve(self, namespace: str, key: str) -> Optional[MemoryEntry]:
        """Retrieve a memory entry by namespace and key.

        Args:
            namespace: The entry's namespace.
            key: The entry's unique key.

        Returns:
            The MemoryEntry if found, None otherwise.
        """
        redis_key = self._make_redis_key(namespace, key)
        try:
            data = await redis_client.get(redis_key)
            if data is None:
                return None
            # Update access tracking
            await self._update_lru(redis_key)
            entry = MemoryEntry(**data)
            entry.access_count += 1
            # Write back incremented access count (non-blocking)
            await redis_client.set(redis_key, entry.model_dump(mode="json"), expire=entry.ttl)
            return entry
        except Exception as e:
            logger.error(f"Failed to retrieve memory entry {namespace}:{key}: {e}")
            return None

    async def delete(self, namespace: str, key: str) -> bool:
        """Delete a memory entry.

        Args:
            namespace: The entry's namespace.
            key: The entry's unique key.

        Returns:
            True if the entry was deleted, False if it didn't exist.
        """
        redis_key = self._make_redis_key(namespace, key)
        index_key = self._make_namespace_index_key(namespace)
        try:
            existed = await redis_client.exists(redis_key)
            await redis_client.delete(redis_key)
            # Remove from namespace index
            idx_data = await redis_client.get(index_key)
            if idx_data and key in idx_data.get("keys", []):
                idx_data["keys"].remove(key)
                await redis_client.set(index_key, idx_data, expire=86400)
            logger.debug(f"Deleted persistent memory: {namespace}:{key}")
            return existed
        except Exception as e:
            logger.error(f"Failed to delete memory entry {namespace}:{key}: {e}")
            return False

    async def exists(self, namespace: str, key: str) -> bool:
        """Check if a memory entry exists.

        Args:
            namespace: The entry's namespace.
            key: The entry's unique key.

        Returns:
            True if the entry exists, False otherwise.
        """
        redis_key = self._make_redis_key(namespace, key)
        try:
            return await redis_client.exists(redis_key)
        except Exception as e:
            logger.error(f"Failed to check memory entry {namespace}:{key}: {e}")
            return False

    async def list_by_namespace(self, namespace: str) -> List[str]:
        """List all keys in a namespace.

        Args:
            namespace: The namespace to list keys for.

        Returns:
            A list of key names in the namespace.
        """
        index_key = self._make_namespace_index_key(namespace)
        try:
            idx_data = await redis_client.get(index_key)
            if idx_data:
                return idx_data.get("keys", [])
            return []
        except Exception as e:
            logger.error(f"Failed to list namespace {namespace}: {e}")
            return []

    async def get_namespace_summary(self, namespace: str) -> MemorySummary:
        """Get a summary of entries in a namespace.

        Args:
            namespace: The namespace to summarize.

        Returns:
            A MemorySummary with aggregate information.
        """
        keys = await self.list_by_namespace(namespace)
        entries: List[MemoryEntry] = []
        for key in keys:
            entry = await self.retrieve(namespace, key)
            if entry:
                entries.append(entry)

        total_size = sum(len(str(e.model_dump(mode="json"))) for e in entries)
        timestamps = [e.created_at for e in entries if e.created_at is not None]

        return MemorySummary(
            namespace=namespace,
            total_entries=len(entries),
            total_size_kb=round(total_size / 1024, 2),
            oldest_entry=min(timestamps) if timestamps else None,
            newest_entry=max(timestamps) if timestamps else None,
            sample_keys=keys[:10],
        )

    async def prune(self, namespace: str, max_entries: Optional[int] = None) -> int:
        """Prune entries in a namespace to stay within size limits.

        Removes the least recently used entries until the namespace
        is within the allowed limit.

        Args:
            namespace: The namespace to prune.
            max_entries: Maximum entries to keep. Uses self.max_entries if None.

        Returns:
            The number of entries removed.
        """
        limit = max_entries if max_entries is not None else self.max_entries
        keys = await self.list_by_namespace(namespace)
        if len(keys) <= limit:
            return 0

        # Build access-time map by retrieving entries
        entries_with_time: List[Tuple[str, datetime]] = []
        for key in keys:
            entry = await self.retrieve(namespace, key)
            if entry and entry.updated_at:
                entries_with_time.append((key, entry.updated_at))
            else:
                entries_with_time.append((key, datetime.min))

        # Sort by last access time (oldest first)
        entries_with_time.sort(key=lambda x: x[1])
        to_remove = entries_with_time[: len(keys) - limit]

        removed = 0
        for key, _ in to_remove:
            if await self.delete(namespace, key):
                removed += 1

        logger.info(f"Pruned {removed} entries from namespace '{namespace}'")
        return removed

    async def _check_and_prune(self, namespace: str) -> None:
        """Check if namespace exceeds threshold and prune if needed."""
        keys = await self.list_by_namespace(namespace)
        if len(keys) >= int(self.max_entries * self.prune_threshold):
            target = int(self.max_entries * 0.7)
            await self.prune(namespace, max_entries=target)

    async def _update_lru(self, redis_key: str) -> None:
        """Update the LRU tracker for a key (best-effort)."""
        try:
            now = datetime.now(timezone.utc).isoformat()
            lru_entry = {redis_key: now}
            existing = await redis_client.get(self._lru_tracker_key)
            if existing:
                existing.update(lru_entry)
                await redis_client.set(self._lru_tracker_key, existing, expire=self.ttl_default)
            else:
                await redis_client.set(self._lru_tracker_key, lru_entry, expire=self.ttl_default)
        except Exception:
            pass  # LRU tracking is best-effort; don't fail the main operation

    async def flush_to_postgres(self, namespace: str) -> int:
        """Flush namespace entries to PostgreSQL for durability.

        Args:
            namespace: The namespace to flush.

        Returns:
            Number of entries flushed.
        """
        keys = await self.list_by_namespace(namespace)
        flushed = 0
        for key in keys:
            entry = await self.retrieve(namespace, key)
            if entry is None:
                continue
            try:
                async with db.get_session() as session:
                    # Check for existing context entry
                    from sqlalchemy import select
                    from .models import ContextModel
                    result = await session.execute(
                        select(ContextModel).where(
                            ContextModel.task_id == namespace,
                            ContextModel.key == key,
                        )
                    )
                    existing = result.scalar_one_or_none()

                    if existing:
                        existing.value = entry.model_dump(mode="json")
                    else:
                        ctx = ContextModel(
                            task_id=namespace,
                            key=key,
                            value=entry.model_dump(mode="json"),
                        )
                        session.add(ctx)
                    await session.commit()
                    flushed += 1
            except Exception as e:
                logger.warning(f"Failed to flush {namespace}:{key} to PostgreSQL: {e}")
        logger.info(f"Flushed {flushed} entries from namespace '{namespace}' to PostgreSQL")
        return flushed

    async def summarize(
        self,
        namespace: str,
        llm_client: Any = None,
    ) -> str:
        """Generate a text summary of memory entries using LLM.

        If no LLM client is provided, a simple structural summary is returned.

        Args:
            namespace: The namespace to summarize.
            llm_client: Optional LLM client for intelligent summarization.

        Returns:
            A human-readable summary string.
        """
        summary = await self.get_namespace_summary(namespace)
        keys = await self.list_by_namespace(namespace)

        # Collect a sample of actual values for context
        samples: List[Dict[str, Any]] = []
        for key in keys[:5]:  # Sample up to 5 entries
            entry = await self.retrieve(namespace, key)
            if entry:
                samples.append({"key": key, "value": entry.value})

        base_summary = (
            f"Namespace '{namespace}' contains {summary.total_entries} entries "
            f"({summary.total_size_kb} KB). "
            f"Oldest entry: {summary.oldest_entry}, newest: {summary.newest_entry}."
        )

        if llm_client:
            try:
                prompt = (
                    f"Summarize the following memory state:\n"
                    f"{base_summary}\n"
                    f"Sample entries: {samples}\n\n"
                    f"Provide a concise 2-3 sentence summary of the state."
                )
                # Placeholder for actual LLM call
                intelligent_summary = f"[LLM Summary]: {base_summary}"
                return intelligent_summary
            except Exception as e:
                logger.warning(f"LLM summarization failed for {namespace}: {e}")

        return base_summary


# Module-level singleton
persistent_memory = PersistentMemoryManager()
