"""MemoryHierarchy — local-first memory system for desktop-native mode.

Implements a four-tier memory system:
1. Working Memory: In-process dict for active task context
2. Short-Term Memory: SQLite with TTL-based pruning
3. Long-Term Memory: SQLite + optional sqlite-vec for embeddings
4. Episodic Memory: Task history and outcomes

Usage:
    from app.desktop_native.memory_hierarchy import memory_hierarchy
    await memory_hierarchy.initialize()
    await memory_hierarchy.working.set("task-123", {"query": "hello"})
    await memory_hierarchy.short_term.store("user_pref", {"theme": "dark"}, ttl=3600)
    await memory_hierarchy.long_term.store("knowledge", "AgentOS is a desktop AI runtime")
    episodes = await memory_hierarchy.episodic.list_recent(limit=10)
"""

import json
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

from ..logs.logger import logger
from .sqlite_store import sqlite_store


class WorkingMemory:
    """In-process working memory for active tasks."""

    def __init__(self):
        self._data: Dict[str, Any] = {}

    async def set(self, key: str, value: Any):
        self._data[key] = {
            "value": value,
            "set_at": datetime.now(timezone.utc).isoformat(),
        }

    async def get(self, key: str) -> Optional[Any]:
        entry = self._data.get(key)
        return entry["value"] if entry else None

    async def delete(self, key: str):
        self._data.pop(key, None)

    async def clear(self):
        self._data.clear()

    async def keys(self) -> List[str]:
        return list(self._data.keys())


class ShortTermMemory:
    """SQLite-backed short-term memory with TTL pruning."""

    def __init__(self):
        self._sqlite = sqlite_store

    async def _ensure_table(self):
        try:
            await self._sqlite.execute("""
                CREATE TABLE IF NOT EXISTS short_term_memory (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                )
            """)
            await self._sqlite.execute("""
                CREATE INDEX IF NOT EXISTS idx_stm_expires ON short_term_memory(expires_at)
            """)
            await self._sqlite.commit()
        except Exception as e:
            logger.warning(f"Failed to create short_term_memory table: {e}")

    async def store(self, key: str, value: Any, ttl_seconds: int = 3600):
        """Store a value with TTL."""
        await self._ensure_table()
        now = datetime.now(timezone.utc)
        expires = now + timedelta(seconds=ttl_seconds)
        await self._sqlite.execute(
            "INSERT OR REPLACE INTO short_term_memory (key, value, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (key, json.dumps(value), now.isoformat(), expires.isoformat()),
        )
        await self._sqlite.commit()

    async def retrieve(self, key: str) -> Optional[Any]:
        """Retrieve a value if not expired."""
        await self._ensure_table()
        now = datetime.now(timezone.utc).isoformat()
        row = await self._sqlite.fetchone(
            "SELECT value FROM short_term_memory WHERE key = ? AND expires_at > ?",
            (key, now),
        )
        if row:
            return json.loads(row["value"])
        return None

    async def delete(self, key: str):
        await self._ensure_table()
        await self._sqlite.execute("DELETE FROM short_term_memory WHERE key = ?", (key,))
        await self._sqlite.commit()

    async def prune_expired(self) -> int:
        """Remove expired entries. Returns count deleted."""
        await self._ensure_table()
        now = datetime.now(timezone.utc).isoformat()
        cursor = await self._sqlite.execute(
            "DELETE FROM short_term_memory WHERE expires_at < ?",
            (now,),
        )
        await self._sqlite.commit()
        count = cursor.rowcount if hasattr(cursor, "rowcount") else 0
        if count > 0:
            logger.info(f"Pruned {count} expired short-term memory entries")
        return count

    async def list_keys(self, limit: int = 100) -> List[str]:
        await self._ensure_table()
        now = datetime.now(timezone.utc).isoformat()
        rows = await self._sqlite.fetchall(
            "SELECT key FROM short_term_memory WHERE expires_at > ? ORDER BY created_at DESC LIMIT ?",
            (now, limit),
        )
        return [r["key"] for r in rows]


class LongTermMemory:
    """SQLite-backed long-term memory with optional vector embeddings."""

    def __init__(self):
        self._sqlite = sqlite_store
        self._vec_available = False
        try:
            import sqlite_vec
            self._vec_available = True
        except ImportError:
            logger.info("sqlite-vec not available, using keyword-only long-term memory")

    async def _ensure_table(self):
        try:
            await self._sqlite.execute("""
                CREATE TABLE IF NOT EXISTS long_term_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT UNIQUE,
                    content TEXT NOT NULL,
                    embedding BLOB,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            await self._sqlite.commit()

            # Initialize sqlite-vec if available
            if self._vec_available:
                try:
                    await self._sqlite.execute("SELECT vec_version()")
                    logger.info("sqlite-vec extension loaded")
                except Exception:
                    logger.warning("sqlite-vec extension not loaded in SQLite")
        except Exception as e:
            logger.warning(f"Failed to create long_term_memory table: {e}")

    async def store(self, key: str, content: str, metadata: Optional[Dict[str, Any]] = None):
        """Store content in long-term memory."""
        await self._ensure_table()
        now = datetime.now(timezone.utc).isoformat()
        await self._sqlite.execute(
            """
            INSERT OR REPLACE INTO long_term_memory
            (key, content, metadata, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (key, content, json.dumps(metadata or {}), now, now),
        )
        await self._sqlite.commit()

    async def retrieve(self, key: str) -> Optional[Dict[str, Any]]:
        """Retrieve content by key."""
        await self._ensure_table()
        row = await self._sqlite.fetchone(
            "SELECT * FROM long_term_memory WHERE key = ?",
            (key,),
        )
        if row:
            return {
                "key": row["key"],
                "content": row["content"],
                "metadata": json.loads(row["metadata"]),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
        return None

    async def search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Simple keyword search (fallback when embeddings unavailable)."""
        await self._ensure_table()
        # Simple LIKE-based search
        pattern = f"%{query}%"
        rows = await self._sqlite.fetchall(
            "SELECT * FROM long_term_memory WHERE content LIKE ? OR key LIKE ? ORDER BY updated_at DESC LIMIT ?",
            (pattern, pattern, limit),
        )
        return [
            {
                "key": r["key"],
                "content": r["content"],
                "metadata": json.loads(r["metadata"]),
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
            }
            for r in rows
        ]

    async def delete(self, key: str):
        await self._ensure_table()
        await self._sqlite.execute("DELETE FROM long_term_memory WHERE key = ?", (key,))
        await self._sqlite.commit()


class EpisodicMemory:
    """Task history and outcomes for episodic learning."""

    def __init__(self):
        self._sqlite = sqlite_store

    async def _ensure_table(self):
        try:
            await self._sqlite.execute("""
                CREATE TABLE IF NOT EXISTS episodic_memory (
                    task_id TEXT PRIMARY KEY,
                    query TEXT NOT NULL,
                    summary TEXT,
                    outcome TEXT NOT NULL,
                    tools_used TEXT NOT NULL DEFAULT '[]',
                    duration_seconds REAL,
                    created_at TEXT NOT NULL
                )
            """)
            await self._sqlite.commit()
        except Exception as e:
            logger.warning(f"Failed to create episodic_memory table: {e}")

    async def record(
        self,
        task_id: str,
        query: str,
        outcome: str,
        summary: Optional[str] = None,
        tools_used: Optional[List[str]] = None,
        duration_seconds: Optional[float] = None,
    ):
        """Record a task episode."""
        await self._ensure_table()
        now = datetime.now(timezone.utc).isoformat()
        await self._sqlite.execute(
            """
            INSERT OR REPLACE INTO episodic_memory
            (task_id, query, summary, outcome, tools_used, duration_seconds, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                query,
                summary,
                outcome,
                json.dumps(tools_used or []),
                duration_seconds,
                now,
            ),
        )
        await self._sqlite.commit()

    async def list_recent(self, limit: int = 10) -> List[Dict[str, Any]]:
        """List recent episodes."""
        await self._ensure_table()
        rows = await self._sqlite.fetchall(
            "SELECT * FROM episodic_memory ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        return [
            {
                "task_id": r["task_id"],
                "query": r["query"],
                "summary": r["summary"],
                "outcome": r["outcome"],
                "tools_used": json.loads(r["tools_used"]),
                "duration_seconds": r["duration_seconds"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]

    async def get_similar(self, query: str, limit: int = 3) -> List[Dict[str, Any]]:
        """Find similar past episodes by query text."""
        await self._ensure_table()
        pattern = f"%{query}%"
        rows = await self._sqlite.fetchall(
            "SELECT * FROM episodic_memory WHERE query LIKE ? OR summary LIKE ? ORDER BY created_at DESC LIMIT ?",
            (pattern, pattern, limit),
        )
        return [
            {
                "task_id": r["task_id"],
                "query": r["query"],
                "summary": r["summary"],
                "outcome": r["outcome"],
                "tools_used": json.loads(r["tools_used"]),
                "duration_seconds": r["duration_seconds"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]

    async def cleanup_old(self, max_age_days: int = 90) -> int:
        """Remove old episodes."""
        await self._ensure_table()
        cutoff = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).isoformat()
        cursor = await self._sqlite.execute(
            "DELETE FROM episodic_memory WHERE created_at < ?",
            (cutoff,),
        )
        await self._sqlite.commit()
        count = cursor.rowcount if hasattr(cursor, "rowcount") else 0
        if count > 0:
            logger.info(f"Cleaned up {count} old episodic memories")
        return count


class MemoryHierarchy:
    """Unified memory hierarchy for desktop-native mode."""

    def __init__(self):
        self.working = WorkingMemory()
        self.short_term = ShortTermMemory()
        self.long_term = LongTermMemory()
        self.episodic = EpisodicMemory()

    async def initialize(self):
        """Initialize all memory tiers."""
        await self.short_term._ensure_table()
        await self.long_term._ensure_table()
        await self.episodic._ensure_table()
        logger.info("MemoryHierarchy initialized")

    async def gc(self):
        """Run garbage collection on all memory tiers."""
        await self.short_term.prune_expired()
        await self.episodic.cleanup_old(max_age_days=90)
        await self.long_term._sqlite.execute(
            "DELETE FROM long_term_memory WHERE updated_at < ?",
            ((datetime.now(timezone.utc) - timedelta(days=365)).isoformat(),),
        )
        await self.long_term._sqlite.commit()


# Module-level singleton
memory_hierarchy = MemoryHierarchy()
