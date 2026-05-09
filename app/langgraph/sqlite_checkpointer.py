"""SQLite checkpointer for LangGraph state persistence in local-native mode.

Replaces PostgreSQL with SQLite for local-first operation, maintaining
full LangGraph checkpoint compatibility while using a file-based database.
"""

import base64
import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

from langgraph.checkpoint.base import BaseCheckpointSaver, Checkpoint, CheckpointMetadata, CheckpointTuple

try:
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
except ImportError:
    # Fallback for different langgraph versions
    from langgraph.checkpoint.serde.base import SerializerProtocol
    class JsonPlusSerializer:
        def dumps_typed(self, obj):
            return json.loads(json.dumps(obj, default=str))
        def loads_typed(self, data):
            return data


_serde = JsonPlusSerializer()


class _AgentOSJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, bytes):
            return {"__type__": "bytes", "data": base64.b64encode(obj).decode("utf-8")}
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, set):
            return list(obj)
        return super().default(obj)


def _agentos_object_hook(obj):
    if obj.get("__type__") == "bytes":
        return base64.b64decode(obj["data"])
    return obj


def _encode(data: Any) -> str:
    return json.dumps(_serde.dumps_typed(data), cls=_AgentOSJSONEncoder)


def _decode(text: str) -> Any:
    return _serde.loads_typed(json.loads(text, object_hook=_agentos_object_hook))


class SQLiteCheckpointSaver(BaseCheckpointSaver):
    """Async SQLite-backed checkpoint saver for LangGraph.

    Persists agent state to a local SQLite database file so graphs can be resumed
    across process restarts. Designed for local-native operation where PostgreSQL
    is not available or desired.

    Thread-safe: uses connection pooling and locks for concurrent access.
    """

    def __init__(self, db_path: Optional[str] = None, session_factory=None):
        super().__init__()
        self._session_factory = session_factory
        self._db_path = db_path or str(Path(__file__).parent.parent.parent / "data" / "checkpoints.db")
        
        # Ensure the directory exists
        db_dir = Path(self._db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)
        
        self._local = threading.local()
        self._lock = threading.Lock()
        self._ensure_schema()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a thread-local database connection."""
        if not hasattr(self._local, "connection") or self._local.connection is None:
            self._local.connection = sqlite3.connect(self._db_path, check_same_thread=False)
            self._local.connection.row_factory = sqlite3.Row
            self._local.connection.execute("PRAGMA journal_mode=WAL")
        return self._local.connection

    def _ensure_schema(self):
        """Create the checkpoints schema if it doesn't exist."""
        conn = self._get_connection()
        with conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS checkpoints (
                    thread_id TEXT NOT NULL,
                    checkpoint_ns TEXT NOT NULL DEFAULT '',
                    checkpoint_id TEXT NOT NULL,
                    parent_checkpoint_id TEXT,
                    checkpoint TEXT NOT NULL,
                    checkpoint_metadata TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS checkpoint_writes (
                    id TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL,
                    checkpoint_ns TEXT NOT NULL,
                    checkpoint_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    task_path TEXT,
                    write_data TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(thread_id, checkpoint_ns, checkpoint_id, task_id, task_path)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_checkpoint_writes_thread_ns 
                ON checkpoint_writes(thread_id, checkpoint_ns)
            """)

    async def aput(
        self,
        config: Dict[str, Any],
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Save a checkpoint to the database."""
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id = checkpoint["id"]
        parent_checkpoint_id = checkpoint.get("parent_config", {}).get("configurable", {}).get("checkpoint_id") if checkpoint.get("parent_config") else None

        conn = self._get_connection()
        with self._lock:
            with conn:
                # Check if checkpoint exists
                existing = conn.execute(
                    """
                    SELECT thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id,
                           checkpoint, checkpoint_metadata, created_at
                    FROM checkpoints
                    WHERE thread_id = ? AND checkpoint_ns = ? AND checkpoint_id = ?
                    """,
                    (thread_id, checkpoint_ns, checkpoint_id),
                ).fetchone()

                if existing:
                    conn.execute(
                        """
                        UPDATE checkpoints
                        SET checkpoint = ?, checkpoint_metadata = ?, parent_checkpoint_id = ?
                        WHERE thread_id = ? AND checkpoint_ns = ? AND checkpoint_id = ?
                        """,
                        (_encode(checkpoint), _encode(metadata), parent_checkpoint_id,
                         thread_id, checkpoint_ns, checkpoint_id),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO checkpoints (thread_id, checkpoint_ns, checkpoint_id,
                                                 parent_checkpoint_id, checkpoint, checkpoint_metadata)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id,
                         _encode(checkpoint), _encode(metadata)),
                    )

        logger.debug(f"Checkpoint saved: {thread_id}/{checkpoint_ns}/{checkpoint_id}")
        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint_id,
            }
        }

    async def _load_pending_writes(self, conn, thread_id: str, checkpoint_ns: str, checkpoint_id: str) -> List[Any]:
        """Load pending writes for a checkpoint."""
        rows = conn.execute(
            """
            SELECT write_data FROM checkpoint_writes
            WHERE thread_id = ? AND checkpoint_ns = ? AND checkpoint_id = ?
            """,
            (thread_id, checkpoint_ns, checkpoint_id),
        ).fetchall()
        return [_decode(r["write_data"]) for r in rows]

    async def aget_tuple(self, config: Dict[str, Any]) -> Optional[CheckpointTuple]:
        """Get a checkpoint tuple by config."""
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id = config["configurable"].get("checkpoint_id")

        conn = self._get_connection()
        with self._lock:
            if checkpoint_id:
                row = conn.execute(
                    """
                    SELECT thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id,
                           checkpoint, checkpoint_metadata, created_at
                    FROM checkpoints
                    WHERE thread_id = ? AND checkpoint_ns = ? AND checkpoint_id = ?
                    """,
                    (thread_id, checkpoint_ns, checkpoint_id),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id,
                           checkpoint, checkpoint_metadata, created_at
                    FROM checkpoints
                    WHERE thread_id = ? AND checkpoint_ns = ?
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (thread_id, checkpoint_ns),
                ).fetchone()

            if not row:
                return None

            checkpoint = _decode(row["checkpoint"])
            metadata = _decode(row["checkpoint_metadata"]) if row["checkpoint_metadata"] else {}

            parent_config = None
            if row["parent_checkpoint_id"]:
                parent_config = {
                    "configurable": {
                        "thread_id": row["thread_id"],
                        "checkpoint_ns": row["checkpoint_ns"],
                        "checkpoint_id": row["parent_checkpoint_id"],
                    }
                }

            pending_writes = await self._load_pending_writes(
                conn, thread_id, checkpoint_ns, row["checkpoint_id"]
            )

            return CheckpointTuple(
                config={
                    "configurable": {
                        "thread_id": thread_id,
                        "checkpoint_ns": checkpoint_ns,
                        "checkpoint_id": row["checkpoint_id"],
                    }
                },
                checkpoint=checkpoint,
                metadata=metadata,
                parent_config=parent_config,
                pending_writes=pending_writes or None,
            )

    async def alist(
        self,
        config: Optional[Dict[str, Any]] = None,
        *,
        filter: Optional[Dict[str, Any]] = None,
        before: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None,
    ) -> AsyncIterator[CheckpointTuple]:
        """List checkpoints with optional filters."""
        thread_id = config["configurable"]["thread_id"] if config else None
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "") if config else ""

        conn = self._get_connection()
        with self._lock:
            query = "SELECT * FROM checkpoints WHERE checkpoint_ns = ?"
            params = [checkpoint_ns]
            if thread_id:
                query += " AND thread_id = ?"
                params.append(thread_id)
            if before:
                before_id = before["configurable"].get("checkpoint_id")
                if before_id:
                    query += " AND checkpoint_id < ?"
                    params.append(before_id)
            query += " ORDER BY created_at DESC"
            if limit:
                query += " LIMIT ?"
                params.append(limit)

            rows = conn.execute(query, params).fetchall()

            for row in rows:
                checkpoint = _decode(row["checkpoint"])
                metadata = _decode(row["checkpoint_metadata"]) if row["checkpoint_metadata"] else {}
                parent_config = None
                if row["parent_checkpoint_id"]:
                    parent_config = {
                        "configurable": {
                            "thread_id": row["thread_id"],
                            "checkpoint_ns": row["checkpoint_ns"],
                            "checkpoint_id": row["parent_checkpoint_id"],
                        }
                    }
                pending_writes = await self._load_pending_writes(
                    conn, row["thread_id"], row["checkpoint_ns"], row["checkpoint_id"]
                )
                yield CheckpointTuple(
                    config={
                        "configurable": {
                            "thread_id": row["thread_id"],
                            "checkpoint_ns": row["checkpoint_ns"],
                            "checkpoint_id": row["checkpoint_id"],
                        }
                    },
                    checkpoint=checkpoint,
                    metadata=metadata,
                    parent_config=parent_config,
                    pending_writes=pending_writes or None,
                )

    async def aput_writes(
        self,
        config: Dict[str, Any],
        writes,
        task_id: str,
        task_path: str = "",
    ) -> None:
        """Persist intermediate writes for resume/interrupt support."""
        import uuid as _uuid

        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id = config["configurable"].get("checkpoint_id", "")

        conn = self._get_connection()
        with self._lock:
            for task_id_local, channel, value in writes:
                write_id = str(_uuid.uuid4())
                conn.execute(
                    """
                    INSERT OR IGNORE INTO checkpoint_writes 
                    (id, thread_id, checkpoint_ns, checkpoint_id, task_id, task_path, write_data)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (write_id, thread_id, checkpoint_ns, checkpoint_id, task_id_local, task_path, _encode((task_id_local, channel, value))),
                )

        logger.debug(
            f"aput_writes: thread={thread_id} ns={checkpoint_ns} "
            f"checkpoint={checkpoint_id} task={task_id} writes={len(writes)}"
        )

    async def adelete(self, config: Dict[str, Any]) -> None:
        """Delete a checkpoint and its associated writes."""
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")

        conn = self._get_connection()
        with self._lock:
            with conn:
                conn.execute(
                    "DELETE FROM checkpoints WHERE thread_id = ? AND checkpoint_ns = ?",
                    (thread_id, checkpoint_ns),
                )
                conn.execute(
                    "DELETE FROM checkpoint_writes WHERE thread_id = ? AND checkpoint_ns = ?",
                    (thread_id, checkpoint_ns),
                )


# Import logger after definition to avoid circular import
from ..logs.logger import logger
