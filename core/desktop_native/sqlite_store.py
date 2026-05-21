"""Shared SQLite connection manager for desktop-native mode.

Provides a singleton aiosqlite connection with WAL mode enabled.
All desktop-native subsystems should use this for persistence.
"""

import asyncio
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

import aiosqlite

from . import get_desktop_db_path
from ..logs.logger import logger


class DesktopSQLiteStore:
    """Singleton SQLite store for desktop-native mode.

    Uses WAL mode for better concurrency. Single writer, multiple readers.
    All operations are async via aiosqlite.
    """

    _instance: Optional["DesktopSQLiteStore"] = None
    _lock = asyncio.Lock()

    def __new__(cls) -> "DesktopSQLiteStore":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._db_path = get_desktop_db_path()
        self._connection: Optional[aiosqlite.Connection] = None
        self._initialized = True

    async def _ensure_connection(self) -> aiosqlite.Connection:
        if self._connection is None:
            os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
            self._connection = await aiosqlite.connect(self._db_path)
            self._connection.row_factory = aiosqlite.Row
            # WAL mode for better concurrency
            await self._connection.execute("PRAGMA journal_mode=WAL")
            await self._connection.execute("PRAGMA synchronous=NORMAL")
            await self._connection.commit()
            logger.debug(f"DesktopSQLiteStore initialized at {self._db_path}")
        return self._connection

    async def initialize_schema(self) -> None:
        """Create all tables needed by desktop-native subsystems."""
        conn = await self._ensure_connection()

        # Task queue persistence
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS task_queue (
                task_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                query TEXT NOT NULL,
                priority INTEGER NOT NULL DEFAULT 2,
                config TEXT DEFAULT '{}',
                idempotency_key TEXT,
                enqueued_at TEXT NOT NULL,
                scheduled_for TEXT,
                worker_id TEXT,
                status TEXT NOT NULL DEFAULT 'queued',
                retry_count INTEGER NOT NULL DEFAULT 0,
                score REAL NOT NULL DEFAULT 0
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_task_queue_status ON task_queue(status)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_task_queue_score ON task_queue(score)
        """)

        # Task state machine
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS task_state (
                task_id TEXT PRIMARY KEY,
                state TEXT NOT NULL DEFAULT 'pending',
                updated_at TEXT NOT NULL
            )
        """)

        # State transitions history
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS state_transitions (
                transition_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                from_state TEXT NOT NULL,
                to_state TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                triggered_by TEXT NOT NULL DEFAULT 'system',
                context TEXT DEFAULT '{}',
                validation_errors TEXT DEFAULT '[]'
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_transitions_task_id ON state_transitions(task_id)
        """)

        # Execution locks
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS execution_locks (
                task_id TEXT PRIMARY KEY,
                lock_id TEXT NOT NULL,
                owner TEXT NOT NULL DEFAULT 'system',
                acquired_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                ttl_seconds INTEGER NOT NULL DEFAULT 300
            )
        """)

        # Timeout configs and deadlines
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS timeout_configs (
                task_id TEXT PRIMARY KEY,
                agent_timeout_seconds INTEGER NOT NULL DEFAULT 60,
                tool_timeout_seconds INTEGER NOT NULL DEFAULT 30,
                workflow_timeout_seconds INTEGER NOT NULL DEFAULT 300,
                step_timeout_seconds INTEGER NOT NULL DEFAULT 60,
                max_total_seconds INTEGER NOT NULL DEFAULT 600
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS timeout_deadlines (
                task_id TEXT NOT NULL,
                scope TEXT NOT NULL,
                deadline_timestamp REAL NOT NULL,
                configured_seconds INTEGER NOT NULL,
                started_at TEXT NOT NULL,
                triggered INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (task_id, scope)
            )
        """)

        # Cost tracking
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS cost_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                scope TEXT NOT NULL,
                scope_id TEXT NOT NULL,
                cost_usd REAL NOT NULL DEFAULT 0,
                tokens_input INTEGER NOT NULL DEFAULT 0,
                tokens_output INTEGER NOT NULL DEFAULT 0,
                model TEXT,
                timestamp TEXT NOT NULL,
                metadata TEXT DEFAULT '{}'
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_cost_task ON cost_records(task_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_cost_scope ON cost_records(scope, scope_id)
        """)

        # Event bus persistence (for recovery)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS event_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel TEXT NOT NULL,
                event_type TEXT NOT NULL,
                payload TEXT NOT NULL DEFAULT '{}',
                source TEXT NOT NULL DEFAULT '',
                timestamp TEXT NOT NULL
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_event_channel ON event_log(channel, timestamp)
        """)

        # Worker pool (local tracking)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS local_workers (
                worker_id TEXT PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'idle',
                registered_at TEXT NOT NULL,
                last_heartbeat TEXT NOT NULL,
                tasks_completed INTEGER NOT NULL DEFAULT 0,
                tasks_failed INTEGER NOT NULL DEFAULT 0,
                current_task_id TEXT,
                capabilities TEXT DEFAULT '[]',
                load_factor REAL NOT NULL DEFAULT 0.0
            )
        """)

        await conn.commit()
        logger.info("Desktop SQLite schema initialized")

    async def execute(self, sql: str, parameters: tuple = ()) -> aiosqlite.Cursor:
        conn = await self._ensure_connection()
        return await conn.execute(sql, parameters)

    async def executemany(self, sql: str, parameters: list) -> aiosqlite.Cursor:
        conn = await self._ensure_connection()
        return await conn.executemany(sql, parameters)

    async def fetchone(self, sql: str, parameters: tuple = ()) -> Optional[aiosqlite.Row]:
        conn = await self._ensure_connection()
        async with conn.execute(sql, parameters) as cursor:
            return await cursor.fetchone()

    async def fetchall(self, sql: str, parameters: tuple = ()) -> list:
        conn = await self._ensure_connection()
        async with conn.execute(sql, parameters) as cursor:
            return await cursor.fetchall()

    async def commit(self) -> None:
        if self._connection:
            await self._connection.commit()

    async def close(self) -> None:
        if self._connection:
            await self._connection.close()
            self._connection = None
            logger.info("DesktopSQLiteStore closed")

    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[aiosqlite.Connection, None]:
        conn = await self._ensure_connection()
        try:
            yield conn
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise


# Global singleton
sqlite_store = DesktopSQLiteStore()
