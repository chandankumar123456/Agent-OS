"""LocalTracer — SQLite-based span storage for desktop-native mode.

Replaces PostgreSQL-backed tracing with local SQLite storage:
- Span tree structure for task execution analysis
- Immediate persistence (no batching delays)
- Query API for task history and performance analysis
- No external dependencies

Usage:
    from app.desktop_native.local_tracer import local_tracer
    span_id = local_tracer.start_span("task-123", "planner", "plan_task")
    local_tracer.end_span(span_id, status="success")
    await local_tracer.persist_span(span_id)
"""

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from ..logs.logger import logger
from .sqlite_store import sqlite_store


@dataclass
class Span:
    span_id: str
    trace_id: str
    operation: str
    agent_name: str
    start_time: datetime
    end_time: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    status: str = "pending"
    error: Optional[str] = None


class LocalTracer:
    """Desktop-native trace manager with SQLite persistence."""

    def __init__(self):
        self._spans: Dict[str, Span] = {}
        self._trace_index: Dict[str, List[str]] = {}
        self._sqlite = sqlite_store

    async def _ensure_table(self):
        try:
            await self._sqlite.execute("""
                CREATE TABLE IF NOT EXISTS traces (
                    span_id TEXT PRIMARY KEY,
                    trace_id TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    agent_name TEXT NOT NULL,
                    start_time TEXT NOT NULL,
                    end_time TEXT,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL DEFAULT 'pending',
                    error TEXT
                )
            """)
            await self._sqlite.execute("""
                CREATE INDEX IF NOT EXISTS idx_traces_trace_id ON traces(trace_id)
            """)
            await self._sqlite.execute("""
                CREATE INDEX IF NOT EXISTS idx_traces_start_time ON traces(start_time)
            """)
            await self._sqlite.commit()
        except Exception as e:
            logger.warning(f"Failed to create traces table: {e}")

    def start_span(
        self,
        trace_id: str,
        agent_name: str,
        operation: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Start a new span and return its ID."""
        span_id = str(uuid.uuid4())
        span = Span(
            span_id=span_id,
            trace_id=trace_id,
            operation=operation,
            agent_name=agent_name,
            start_time=datetime.now(timezone.utc),
            metadata=metadata or {},
        )
        self._spans[span_id] = span
        if trace_id not in self._trace_index:
            self._trace_index[trace_id] = []
        self._trace_index[trace_id].append(span_id)
        return span_id

    def end_span(self, span_id: str, status: str = "success", error: Optional[str] = None):
        """End a span with the given status."""
        if span_id in self._spans:
            span = self._spans[span_id]
            span.end_time = datetime.now(timezone.utc)
            span.status = status
            span.error = error

    async def persist_span(self, span_id: str) -> bool:
        """Persist a single span to SQLite."""
        if span_id not in self._spans:
            return False
        span = self._spans[span_id]
        try:
            await self._ensure_table()
            await self._sqlite.execute(
                """
                INSERT OR REPLACE INTO traces
                (span_id, trace_id, operation, agent_name, start_time, end_time, metadata, status, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    span.span_id,
                    span.trace_id,
                    span.operation,
                    span.agent_name,
                    span.start_time.isoformat(),
                    span.end_time.isoformat() if span.end_time else None,
                    json.dumps(span.metadata),
                    span.status,
                    span.error,
                ),
            )
            await self._sqlite.commit()
            return True
        except Exception as e:
            logger.warning(f"Failed to persist span {span_id}: {e}")
            return False

    async def persist_all(self) -> int:
        """Persist all spans. Returns count persisted."""
        count = 0
        for span_id in list(self._spans.keys()):
            if await self.persist_span(span_id):
                count += 1
        return count

    async def get_trace(self, trace_id: str) -> List[Dict[str, Any]]:
        """Get all spans for a trace."""
        try:
            await self._ensure_table()
            rows = await self._sqlite.fetchall(
                "SELECT * FROM traces WHERE trace_id = ? ORDER BY start_time",
                (trace_id,),
            )
            return [self._row_to_dict(r) for r in rows]
        except Exception as e:
            logger.warning(f"Failed to get trace {trace_id}: {e}")
            return []

    async def get_span(self, span_id: str) -> Optional[Dict[str, Any]]:
        """Get a single span by ID."""
        try:
            await self._ensure_table()
            row = await self._sqlite.fetchone(
                "SELECT * FROM traces WHERE span_id = ?",
                (span_id,),
            )
            return self._row_to_dict(row) if row else None
        except Exception as e:
            logger.warning(f"Failed to get span {span_id}: {e}")
            return None

    async def list_recent(self, limit: int = 100) -> List[Dict[str, Any]]:
        """List recent spans."""
        try:
            await self._ensure_table()
            rows = await self._sqlite.fetchall(
                "SELECT * FROM traces ORDER BY start_time DESC LIMIT ?",
                (limit,),
            )
            return [self._row_to_dict(r) for r in rows]
        except Exception as e:
            logger.warning(f"Failed to list recent traces: {e}")
            return []

    async def cleanup_old(self, max_age_days: int = 90) -> int:
        """Remove old traces. Returns count deleted."""
        try:
            await self._ensure_table()
            from datetime import timedelta
            cutoff = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).isoformat()
            cursor = await self._sqlite.execute(
                "DELETE FROM traces WHERE start_time < ?",
                (cutoff,),
            )
            await self._sqlite.commit()
            count = cursor.rowcount if hasattr(cursor, "rowcount") else 0
            if count > 0:
                logger.info(f"Cleaned up {count} old traces")
            return count
        except Exception as e:
            logger.warning(f"Failed to cleanup old traces: {e}")
            return 0

    def _row_to_dict(self, row) -> Dict[str, Any]:
        return {
            "span_id": row["span_id"],
            "trace_id": row["trace_id"],
            "operation": row["operation"],
            "agent_name": row["agent_name"],
            "start_time": row["start_time"],
            "end_time": row["end_time"],
            "metadata": json.loads(row["metadata"]),
            "status": row["status"],
            "error": row["error"],
        }


# Module-level singleton
local_tracer = LocalTracer()
