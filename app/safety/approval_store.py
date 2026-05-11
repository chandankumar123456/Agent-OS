from dataclasses import dataclass, field
from typing import Dict, List, Optional
from enum import Enum
from datetime import datetime, timezone


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
    """Per-session approval state store (in-memory)."""

    def __init__(self):
        self._sessions: Dict[str, ApprovalSession] = {}

    def set_mode(self, task_id: str, mode: str) -> ApprovalSession:
        """Set approval mode for a session. Creates session if needed."""
        mode_enum = ApprovalMode(mode) if mode in {m.value for m in ApprovalMode} else ApprovalMode.STANDARD
        session = self._sessions.get(task_id)
        if session is None:
            session = ApprovalSession(task_id=task_id, mode=mode_enum)
            self._sessions[task_id] = session
        else:
            session.mode = mode_enum
            session.updated_at = datetime.now(timezone.utc).isoformat()
        return session

    def get_mode(self, task_id: str) -> ApprovalMode:
        session = self._sessions.get(task_id)
        return session.mode if session else ApprovalMode.STANDARD

    def get_session(self, task_id: str) -> Optional[ApprovalSession]:
        return self._sessions.get(task_id)

    def should_auto_approve(self, task_id: str, tool_name: str, severity: str) -> bool:
        """Determine if an action should be auto-approved without interrupt.

        Returns True if:
        - mode is FULL_TRUST AND
        - tool is NOT in forbidden list

        Forbidden tools are ALWAYS blocked regardless of mode:
        filesystem__delete_file, filesystem__delete_directory, database__drop_table,
        database__drop_schema, database__delete_rows, user__delete_account,
        payment__*, crypto__*, purchase__*, buy__*, email__send*, slack__send*,
        discord__send*, sms__send*, github__delete*, github__force_push,
        aws__terminate*, aws__delete*, docker__remove*, kubernetes__delete*
        """
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

        mode = self.get_mode(task_id)
        return mode == ApprovalMode.FULL_TRUST

    def log_auto_approval(self, task_id: str, tool_name: str, params: dict, reason: str):
        session = self._sessions.get(task_id)
        if session:
            session.log_action(tool_name, params, auto_approved=True, reason=reason)


# Module-level singleton
approval_store = ApprovalStore()
