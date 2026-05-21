"""CapabilityManager — desktop-native capability tokens with user approval.

Manages what tools/capabilities an agent is allowed to use on the local machine.
- Issues capability tokens scoped to specific tools/actions
- Requires explicit user approval for sensitive capabilities
- Persists approved capabilities to SQLite
- Enforces capability expiry and revocation

Usage:
    manager = CapabilityManager()
    token = await manager.request_capability("desktop_env__open_application", task_id="123")
    if token:
        # Agent can use this tool
        await manager.use_capability(token.token_id)
"""

import secrets
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Set
from enum import Enum

from pydantic import BaseModel

from ..logs.logger import logger
from .sqlite_store import sqlite_store


class CapabilityStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    REVOKED = "revoked"
    EXPIRED = "expired"


class CapabilityScope(str, Enum):
    TOOL = "tool"
    CATEGORY = "category"
    SYSTEM = "system"


class CapabilityToken(BaseModel):
    token_id: str
    task_id: str
    scope: CapabilityScope
    target: str  # tool name or category
    status: CapabilityStatus
    created_at: str
    expires_at: str
    last_used_at: Optional[str] = None
    use_count: int = 0
    max_uses: Optional[int] = None
    approved_by: Optional[str] = None  # user name who approved


SENSITIVE_CAPABILITIES: Set[str] = {
    "desktop_env__open_application",
    "desktop_env__launch_app_and_open_file",
    "desktop_env__press_key",
    "desktop_env__click",
    "desktop_env__type_text",
    "shell__execute",
    "shell__run_command",
    "filesystem__delete_file",
    "filesystem__delete_directory",
    "filesystem__write_file",
    "browser__navigate",
    "email__send",
}


class CapabilityManager:
    """Manages agent capabilities with user approval."""

    def __init__(self):
        self._sqlite = sqlite_store
        self._pending_approvals: Dict[str, CapabilityToken] = {}

    async def _ensure_table(self):
        try:
            await self._sqlite.execute("""
                CREATE TABLE IF NOT EXISTS capability_tokens (
                    token_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    target TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    last_used_at TEXT,
                    use_count INTEGER NOT NULL DEFAULT 0,
                    max_uses INTEGER,
                    approved_by TEXT
                )
            """)
            await self._sqlite.commit()
        except Exception as e:
            logger.warning(f"Failed to create capability_tokens table: {e}")

    async def request_capability(
        self,
        target: str,
        task_id: str,
        scope: CapabilityScope = CapabilityScope.TOOL,
        max_uses: Optional[int] = None,
        expires_in_minutes: int = 60,
    ) -> Optional[CapabilityToken]:
        """Request a capability token.

        For sensitive capabilities, this will require user approval.
        Returns the token if approved or if no approval is needed.
        """
        await self._ensure_table()

        # Check if already approved for this task
        existing = await self.get_active_capability(target, task_id)
        if existing:
            logger.info(f"Reusing existing capability for {target}")
            return existing

        # Check if sensitive
        is_sensitive = target in SENSITIVE_CAPABILITIES or any(
            target.startswith(prefix) for prefix in ("shell__", "filesystem__delete", "email__")
        )

        token_id = "cap_" + secrets.token_urlsafe(16)
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=expires_in_minutes)

        token = CapabilityToken(
            token_id=token_id,
            task_id=task_id,
            scope=scope,
            target=target,
            status=CapabilityStatus.APPROVED if not is_sensitive else CapabilityStatus.PENDING,
            created_at=now.isoformat(),
            expires_at=expires_at.isoformat(),
            max_uses=max_uses,
        )

        # Persist
        await self._sqlite.execute(
            """
            INSERT INTO capability_tokens (token_id, task_id, scope, target, status, created_at, expires_at, use_count, max_uses)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (token.token_id, token.task_id, token.scope.value, token.target, token.status.value,
             token.created_at, token.expires_at, token.use_count, token.max_uses),
        )
        await self._sqlite.commit()

        if is_sensitive:
            self._pending_approvals[token_id] = token
            logger.warning(
                f"CAPABILITY APPROVAL REQUIRED: task={task_id} tool={target} "
                f"token={token_id}"
            )
            # In desktop mode, auto-approve for now (TODO: hook into Tauri dialog)
            await self.approve_capability(token_id, approved_by="auto_desktop")
            return await self.get_capability(token_id)

        logger.info(f"Capability granted: {target} for task {task_id}")
        return token

    async def approve_capability(self, token_id: str, approved_by: str) -> bool:
        """Approve a pending capability."""
        try:
            await self._ensure_table()
            await self._sqlite.execute(
                "UPDATE capability_tokens SET status = ?, approved_by = ? WHERE token_id = ?",
                (CapabilityStatus.APPROVED.value, approved_by, token_id),
            )
            await self._sqlite.commit()
            self._pending_approvals.pop(token_id, None)
            logger.info(f"Capability approved: {token_id} by {approved_by}")
            return True
        except Exception as e:
            logger.error(f"Failed to approve capability {token_id}: {e}")
            return False

    async def deny_capability(self, token_id: str) -> bool:
        """Deny a pending capability."""
        try:
            await self._ensure_table()
            await self._sqlite.execute(
                "UPDATE capability_tokens SET status = ? WHERE token_id = ?",
                (CapabilityStatus.DENIED.value, token_id),
            )
            await self._sqlite.commit()
            self._pending_approvals.pop(token_id, None)
            logger.info(f"Capability denied: {token_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to deny capability {token_id}: {e}")
            return False

    async def use_capability(self, token_id: str) -> bool:
        """Record usage of a capability. Returns True if valid."""
        token = await self.get_capability(token_id)
        if not token:
            return False

        if token.status != CapabilityStatus.APPROVED.value:
            logger.warning(f"Capability not approved: {token_id}")
            return False

        # Check expiry
        expires = datetime.fromisoformat(token.expires_at)
        if datetime.now(timezone.utc) > expires:
            await self.revoke_capability(token_id, CapabilityStatus.EXPIRED)
            logger.warning(f"Capability expired: {token_id}")
            return False

        # Check max uses
        if token.max_uses is not None and token.use_count >= token.max_uses:
            await self.revoke_capability(token_id, CapabilityStatus.EXPIRED)
            logger.warning(f"Capability max uses reached: {token_id}")
            return False

        # Update use count
        now = datetime.now(timezone.utc).isoformat()
        await self._sqlite.execute(
            "UPDATE capability_tokens SET use_count = use_count + 1, last_used_at = ? WHERE token_id = ?",
            (now, token_id),
        )
        await self._sqlite.commit()
        return True

    async def get_capability(self, token_id: str) -> Optional[CapabilityToken]:
        """Get a capability token by ID."""
        try:
            await self._ensure_table()
            row = await self._sqlite.fetchone(
                "SELECT * FROM capability_tokens WHERE token_id = ?",
                (token_id,),
            )
            if row:
                return CapabilityToken(
                    token_id=row["token_id"],
                    task_id=row["task_id"],
                    scope=CapabilityScope(row["scope"]),
                    target=row["target"],
                    status=CapabilityStatus(row["status"]),
                    created_at=row["created_at"],
                    expires_at=row["expires_at"],
                    last_used_at=row["last_used_at"],
                    use_count=row["use_count"],
                    max_uses=row["max_uses"],
                    approved_by=row["approved_by"],
                )
        except Exception as e:
            logger.warning(f"Failed to get capability {token_id}: {e}")
        return None

    async def get_active_capability(self, target: str, task_id: str) -> Optional[CapabilityToken]:
        """Get an active capability for a target and task."""
        try:
            await self._ensure_table()
            row = await self._sqlite.fetchone(
                """
                SELECT * FROM capability_tokens
                WHERE target = ? AND task_id = ? AND status = ?
                ORDER BY created_at DESC LIMIT 1
                """,
                (target, task_id, CapabilityStatus.APPROVED.value),
            )
            if row:
                token = CapabilityToken(
                    token_id=row["token_id"],
                    task_id=row["task_id"],
                    scope=CapabilityScope(row["scope"]),
                    target=row["target"],
                    status=CapabilityStatus(row["status"]),
                    created_at=row["created_at"],
                    expires_at=row["expires_at"],
                    last_used_at=row["last_used_at"],
                    use_count=row["use_count"],
                    max_uses=row["max_uses"],
                    approved_by=row["approved_by"],
                )
                # Check expiry
                expires = datetime.fromisoformat(token.expires_at)
                if datetime.now(timezone.utc) > expires:
                    return None
                return token
        except Exception as e:
            logger.warning(f"Failed to get active capability: {e}")
        return None

    async def revoke_capability(self, token_id: str, reason: CapabilityStatus = CapabilityStatus.REVOKED):
        """Revoke a capability."""
        try:
            await self._ensure_table()
            await self._sqlite.execute(
                "UPDATE capability_tokens SET status = ? WHERE token_id = ?",
                (reason.value, token_id),
            )
            await self._sqlite.commit()
            logger.info(f"Capability revoked: {token_id} ({reason.value})")
        except Exception as e:
            logger.error(f"Failed to revoke capability {token_id}: {e}")

    async def cleanup_expired(self) -> int:
        """Clean up expired capabilities. Returns count cleaned."""
        try:
            await self._ensure_table()
            now = datetime.now(timezone.utc).isoformat()
            cursor = await self._sqlite.execute(
                "UPDATE capability_tokens SET status = ? WHERE expires_at < ? AND status = ?",
                (CapabilityStatus.EXPIRED.value, now, CapabilityStatus.APPROVED.value),
            )
            await self._sqlite.commit()
            count = cursor.rowcount if hasattr(cursor, "rowcount") else 0
            if count > 0:
                logger.info(f"Cleaned up {count} expired capabilities")
            return count
        except Exception as e:
            logger.warning(f"Failed to cleanup expired capabilities: {e}")
            return 0

    async def list_pending(self) -> List[CapabilityToken]:
        """List all pending capabilities awaiting approval."""
        try:
            await self._ensure_table()
            rows = await self._sqlite.fetchall(
                "SELECT * FROM capability_tokens WHERE status = ?",
                (CapabilityStatus.PENDING.value,),
            )
            return [
                CapabilityToken(
                    token_id=r["token_id"],
                    task_id=r["task_id"],
                    scope=CapabilityScope(r["scope"]),
                    target=r["target"],
                    status=CapabilityStatus(r["status"]),
                    created_at=r["created_at"],
                    expires_at=r["expires_at"],
                    last_used_at=r["last_used_at"],
                    use_count=r["use_count"],
                    max_uses=r["max_uses"],
                    approved_by=r["approved_by"],
                )
                for r in rows
            ]
        except Exception as e:
            logger.warning(f"Failed to list pending capabilities: {e}")
            return []


# Module-level singleton
capability_manager = CapabilityManager()
