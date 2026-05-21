import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from enum import Enum
from datetime import datetime, timezone

from ..logs.logger import logger


class ApprovalMode(str, Enum):
    STANDARD = "standard"      # Current behavior: interrupt for sensitive actions
    FULL_TRUST = "full_trust"  # Auto-approve, still block forbidden


@dataclass
class ApprovalSession:
    task_id: str
    mode: ApprovalMode = ApprovalMode.STANDARD
    audit_log: List[Dict] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def log_action(self, tool_name: str, params: dict, auto_approved: bool, reason: str):
        self.audit_log.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tool_name": tool_name,
            "params": {k: v for k, v in params.items() if not k.startswith("_")},
            "auto_approved": auto_approved,
            "reason": reason,
        })


class ApprovalStore:
    """Per-session approval state store backed by SQLite for persistence."""

    def __init__(self):
        self._sessions: Dict[str, ApprovalSession] = {}
        self._using_sqlite = False
        try:
            from ..desktop_native.sqlite_store import sqlite_store
            self._sqlite = sqlite_store
            self._using_sqlite = True
        except Exception:
            self._sqlite = None

    async def _ensure_table(self):
        if not self._using_sqlite:
            return
        try:
            await self._sqlite.execute("""
                CREATE TABLE IF NOT EXISTS approval_sessions (
                    task_id TEXT PRIMARY KEY,
                    mode TEXT NOT NULL DEFAULT 'standard',
                    audit_log TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            await self._sqlite.commit()
        except Exception as e:
            logger.warning(f"Failed to create approval_sessions table: {e}")

    async def set_mode(self, task_id: str, mode: str) -> ApprovalSession:
        """Set approval mode for a session. Creates session if needed."""
        mode_enum = ApprovalMode(mode) if mode in {m.value for m in ApprovalMode} else ApprovalMode.STANDARD
        session = self._sessions.get(task_id)
        if session is None:
            session = ApprovalSession(task_id=task_id, mode=mode_enum)
            self._sessions[task_id] = session
        else:
            session.mode = mode_enum
            session.updated_at = datetime.now(timezone.utc).isoformat()

        # Persist to SQLite
        if self._using_sqlite:
            await self._ensure_table()
            try:
                await self._sqlite.execute(
                    """
                    INSERT OR REPLACE INTO approval_sessions (task_id, mode, audit_log, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (task_id, session.mode.value, json.dumps(session.audit_log), session.created_at, session.updated_at),
                )
                await self._sqlite.commit()
            except Exception as e:
                logger.warning(f"Failed to persist approval session: {e}")

        return session

    async def get_mode(self, task_id: str) -> ApprovalMode:
        # Check in-memory first
        session = self._sessions.get(task_id)
        if session:
            return session.mode

        # Fallback to SQLite
        if self._using_sqlite:
            try:
                await self._ensure_table()
                row = await self._sqlite.fetchone(
                    "SELECT mode FROM approval_sessions WHERE task_id = ?",
                    (task_id,),
                )
                if row:
                    return ApprovalMode(row["mode"]) if row["mode"] in {m.value for m in ApprovalMode} else ApprovalMode.STANDARD
            except Exception as e:
                logger.warning(f"Failed to load approval mode from SQLite: {e}")

        return ApprovalMode.STANDARD

    async def get_session(self, task_id: str) -> Optional[ApprovalSession]:
        # Check in-memory first
        if task_id in self._sessions:
            return self._sessions[task_id]

        # Fallback to SQLite
        if self._using_sqlite:
            try:
                await self._ensure_table()
                row = await self._sqlite.fetchone(
                    "SELECT * FROM approval_sessions WHERE task_id = ?",
                    (task_id,),
                )
                if row:
                    session = ApprovalSession(
                        task_id=row["task_id"],
                        mode=ApprovalMode(row["mode"]) if row["mode"] in {m.value for m in ApprovalMode} else ApprovalMode.STANDARD,
                        audit_log=json.loads(row["audit_log"]),
                        created_at=row["created_at"],
                        updated_at=row["updated_at"],
                    )
                    self._sessions[task_id] = session
                    return session
            except Exception as e:
                logger.warning(f"Failed to load approval session from SQLite: {e}")

        return None

    def should_auto_approve(self, task_id: str, tool_name: str, severity: str) -> bool:
        """Determine if an action should be auto-approved without interrupt.

        Note: This is a synchronous check (fast path). For desktop mode,
        approval state should be loaded beforehand via get_session().
        """
        session = self._sessions.get(task_id)
        mode = session.mode if session else ApprovalMode.STANDARD

        # Forbidden prefix/pattern check
        forbidden_prefixes = (
            "filesystem__delete", "database__drop", "database__delete",
            "user__delete", "github__delete", "github__force",
            "aws__terminate", "aws__delete",
            "docker__remove", "kubernetes__delete",
        )
        forbidden_tools = (
            "database__delete_rows", "user__delete_account",
        )
        if tool_name in forbidden_tools or any(tool_name.startswith(p) for p in forbidden_prefixes):
            return False
        if tool_name.startswith(("payment__", "crypto__", "purchase__", "buy__")):
            return False
        if tool_name.startswith(("email__send", "slack__send", "slack__post", "discord__send", "sms__send")):
            return False

        return mode == ApprovalMode.FULL_TRUST

    async def log_auto_approval(self, task_id: str, tool_name: str, params: dict, reason: str):
        session = self._sessions.get(task_id)
        if session:
            session.log_action(tool_name, params, auto_approved=True, reason=reason)

            # Persist updated audit log
            if self._using_sqlite:
                try:
                    await self._ensure_table()
                    await self._sqlite.execute(
                        "UPDATE approval_sessions SET audit_log = ?, updated_at = ? WHERE task_id = ?",
                        (json.dumps(session.audit_log), datetime.now(timezone.utc).isoformat(), task_id),
                    )
                    await self._sqlite.commit()
                except Exception as e:
                    logger.warning(f"Failed to persist approval log: {e}")


# Module-level singleton
approval_store = ApprovalStore()
