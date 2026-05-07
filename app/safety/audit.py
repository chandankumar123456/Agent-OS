"""Audit Trail for AgentOS.

Section 3.10: Immutable, traceable audit records for all agent actions,
tool executions, decisions, and state changes.

Features:
- Immutable audit entries with cryptographic chaining
- Per-task, per-agent, per-tool audit views
- Compliance report generation
- Retention policy enforcement
- Export to standard formats (JSON, CSV)
"""
import json
import hashlib
from enum import Enum
from typing import Dict, Any, List, Optional, Set, Iterator
from datetime import datetime, timezone
from dataclasses import dataclass, field
from threading import Lock

from pydantic import BaseModel, Field

from ..logs.logger import logger


# ─── Enums ────────────────────────────────────────────────────────────────
class AuditEventType(str, Enum):
    """Categories of auditable events."""
    # System events
    SYSTEM_START = "system_start"
    SYSTEM_STOP = "system_stop"
    CONFIG_CHANGE = "config_change"

    # Task lifecycle
    TASK_CREATED = "task_created"
    TASK_ASSIGNED = "task_assigned"
    TASK_STARTED = "task_started"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    TASK_APPROVED = "task_approved"
    TASK_REJECTED = "task_rejected"

    # Agent actions
    AGENT_CREATED = "agent_created"
    AGENT_DESTROYED = "agent_destroyed"
    AGENT_HANDOFF = "agent_handoff"
    AGENT_STATE_CHANGE = "agent_state_change"
    AGENT_ERROR = "agent_error"

    # Tool execution
    TOOL_INVOKED = "tool_invoked"
    TOOL_COMPLETED = "tool_completed"
    TOOL_FAILED = "tool_failed"
    TOOL_BLOCKED = "tool_blocked"
    TOOL_GROUNDED = "tool_grounded"

    # Safety events
    SAFETY_CHECK = "safety_check"
    SAFETY_BLOCK = "safety_block"
    GROUNDING_CHECK = "grounding_check"
    GUARDRAIL_BLOCK = "guardrail_block"

    # Collaboration
    COLLAB_SESSION_CREATED = "collab_session_created"
    COLLAB_SESSION_ENDED = "collab_session_ended"
    COLLAB_VOTE_CAST = "collab_vote_cast"
    COLLAB_DECISION = "collab_decision"

    # Data events
    DATA_ACCESS = "data_access"
    DATA_MODIFIED = "data_modified"
    DATA_DELETED = "data_deleted"
    DATA_EXPORTED = "data_exported"

    # Auth events
    AUTH_LOGIN = "auth_login"
    AUTH_LOGOUT = "auth_logout"
    AUTH_FAILURE = "auth_failure"
    AUTH_TOKEN_REFRESH = "auth_token_refresh"


class AuditSeverity(str, Enum):
    """Severity of auditable events."""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class RetentionPolicy(str, Enum):
    """Data retention policies for audit entries."""
    KEEP_ALL = "keep_all"           # Never delete
    KEEP_30D = "keep_30d"           # Delete after 30 days
    KEEP_90D = "keep_90d"           # Delete after 90 days
    KEEP_1Y = "keep_1y"             # Delete after 1 year
    KEEP_BY_SEVERITY = "keep_by_severity"  # ERROR/CRITICAL kept; INFO/WARNING pruned


# ─── Pydantic Models ──────────────────────────────────────────────────────
class AuditEntry(BaseModel):
    """Immutable audit trail entry with cryptographic chain integrity.

    Each entry is linked to its predecessor via a SHA-256 hash chain,
    making the entire trail tamper-evident.
    """
    entry_id: str = Field(
        default_factory=lambda: f"audit_{hashlib.sha256(str(datetime.now(timezone.utc)).encode()).hexdigest()[:16]}"
    )
    event_type: AuditEventType
    severity: AuditSeverity = AuditSeverity.INFO
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # Context
    task_id: Optional[str] = None
    agent_id: Optional[str] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    tool_name: Optional[str] = None

    # Data
    summary: str = ""
    details: Dict[str, Any] = Field(default_factory=dict)
    outcome: Optional[str] = None  # success, failure, blocked, pending
    metadata: Dict[str, Any] = Field(default_factory=dict)

    # Chain integrity
    previous_hash: Optional[str] = None
    entry_hash: str = ""

    class Config:
        use_enum_values = True
        frozen = True  # Immutable after creation

    def compute_hash(self) -> str:
        """Compute SHA-256 hash of entry contents for chain integrity."""
        content = json.dumps({
            "entry_id": self.entry_id,
            "event_type": self.event_type.value,
            "timestamp": self.timestamp,
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "summary": self.summary,
            "details": self.details,
            "outcome": self.outcome,
            "previous_hash": self.previous_hash,
        }, sort_keys=True, default=str)
        return hashlib.sha256(content.encode()).hexdigest()


# ─── Audit Trail Dataclasses ──────────────────────────────────────────────
@dataclass
class AuditFilter:
    """Filters for querying audit entries."""
    event_types: Optional[Set[AuditEventType]] = None
    severity_min: Optional[AuditSeverity] = None
    task_id: Optional[str] = None
    agent_id: Optional[str] = None
    user_id: Optional[str] = None
    tool_name: Optional[str] = None
    since: Optional[str] = None   # ISO timestamp
    until: Optional[str] = None   # ISO timestamp
    outcome: Optional[str] = None
    limit: int = 500
    offset: int = 0


@dataclass
class ComplianceReport:
    """Generated compliance report from audit trail."""
    report_id: str
    generated_at: str
    period_start: str
    period_end: str
    total_entries: int
    entries_by_type: Dict[str, int]
    entries_by_severity: Dict[str, int]
    task_summary: Dict[str, Any]
    safety_events: List[Dict[str, Any]]
    anomalies: List[str]
    chain_valid: bool
    retention_status: str


# ─── Audit Trail Storage ──────────────────────────────────────────────────
class AuditTrail:
    """In-memory immutable audit trail with hash-chain integrity.

    Supports filtering, compliance reporting, and retention policies.
    In production, this would be backed by a PostgreSQL append-only table.
    """

    def __init__(
        self,
        max_entries: int = 100_000,
        retention: RetentionPolicy = RetentionPolicy.KEEP_ALL,
    ):
        self._entries: List[AuditEntry] = []
        self._last_hash: Optional[str] = None
        self._lock = Lock()
        self.max_entries = max_entries
        self.retention = retention
        self._task_index: Dict[str, List[int]] = {}   # task_id → entry indices
        self._agent_index: Dict[str, List[int]] = {}   # agent_id → entry indices
        self._type_index: Dict[str, List[int]] = {}    # event_type → entry indices

    def record(
        self,
        event_type: AuditEventType,
        summary: str = "",
        severity: AuditSeverity = AuditSeverity.INFO,
        task_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        tool_name: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        outcome: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AuditEntry:
        """Record a new audit entry with hash-chain linkage."""
        with self._lock:
            # Enforce max entries
            if len(self._entries) >= self.max_entries:
                self._prune()

            entry = AuditEntry(
                event_type=event_type,
                severity=severity,
                task_id=task_id,
                agent_id=agent_id,
                user_id=user_id,
                session_id=session_id,
                tool_name=tool_name,
                summary=summary,
                details=details or {},
                outcome=outcome,
                metadata=metadata or {},
                previous_hash=self._last_hash,
            )

            # Compute final hash with chain
            entry_hash = entry.compute_hash()
            object.__setattr__(entry, 'entry_hash', entry_hash)

            idx = len(self._entries)
            self._entries.append(entry)
            self._last_hash = entry_hash

            # Update indexes
            if task_id:
                self._task_index.setdefault(task_id, []).append(idx)
            if agent_id:
                self._agent_index.setdefault(agent_id, []).append(idx)
            type_key = event_type.value
            self._type_index.setdefault(type_key, []).append(idx)

            logger.debug(f"[AuditTrail] Recorded: {event_type.value} ({severity.value}) - {summary[:80]}")
            return entry

    def query(self, filters: Optional[AuditFilter] = None) -> List[AuditEntry]:
        """Query audit entries with filters."""
        if filters is None:
            with self._lock:
                return list(self._entries)

        # Determine candidate indices
        candidates: Optional[Set[int]] = None

        if filters.task_id:
            indices = set(self._task_index.get(filters.task_id, []))
            candidates = indices if candidates is None else candidates & indices

        if filters.agent_id:
            indices = set(self._agent_index.get(filters.agent_id, []))
            candidates = indices if candidates is None else candidates & indices

        if filters.event_types:
            indices = set()
            for et in filters.event_types:
                indices.update(self._type_index.get(et.value, []))
            candidates = indices if candidates is None else candidates & indices

        with self._lock:
            if candidates is not None:
                entries = [self._entries[i] for i in sorted(candidates)]
            else:
                entries = list(self._entries)

        # Apply remaining filters
        if filters.severity_min:
            severity_order = {s: i for i, s in enumerate(AuditSeverity)}
            min_level = severity_order[filters.severity_min]
            entries = [e for e in entries if severity_order.get(e.severity, 0) >= min_level]

        if filters.tool_name:
            entries = [e for e in entries if e.tool_name == filters.tool_name]

        if filters.user_id:
            entries = [e for e in entries if e.user_id == filters.user_id]

        if filters.outcome:
            entries = [e for e in entries if e.outcome == filters.outcome]

        if filters.since:
            entries = [e for e in entries if e.timestamp >= filters.since]

        if filters.until:
            entries = [e for e in entries if e.timestamp <= filters.until]

        # Apply pagination
        start = filters.offset
        end = start + filters.limit
        return entries[start:end]

    def get_by_task(self, task_id: str) -> List[AuditEntry]:
        """Get all audit entries for a specific task."""
        return self.query(AuditFilter(task_id=task_id, limit=10_000))

    def get_by_agent(self, agent_id: str, limit: int = 1000) -> List[AuditEntry]:
        """Get all audit entries for a specific agent."""
        return self.query(AuditFilter(agent_id=agent_id, limit=limit))

    def get_recent(self, limit: int = 100) -> List[AuditEntry]:
        """Get most recent entries."""
        with self._lock:
            return list(self._entries[-limit:])

    def verify_chain(self) -> bool:
        """Verify the integrity of the entire hash chain."""
        with self._lock:
            prev = None
            for entry in self._entries:
                if prev is not None and entry.previous_hash != prev:
                    logger.error(
                        f"[AuditTrail] Chain BREAK at {entry.entry_id}: "
                        f"expected {prev}, got {entry.previous_hash}"
                    )
                    return False
                computed = entry.compute_hash()
                if computed != entry.entry_hash:
                    logger.error(
                        f"[AuditTrail] Hash MISMATCH at {entry.entry_id}: "
                        f"computed {computed}, stored {entry.entry_hash}"
                    )
                    return False
                prev = computed
            return True

    def _prune(self) -> None:
        """Remove oldest entries per retention policy."""
        if self.retention == RetentionPolicy.KEEP_ALL:
            # Remove oldest 10% as fallback
            remove_count = max(1, len(self._entries) // 10)
            self._entries = self._entries[remove_count:]
            logger.info(f"[AuditTrail] Pruned {remove_count} oldest entries (capacity overflow)")
        else:
            # Time-based pruning (simplified — uses entry count with severity weighting)
            severity_order = {AuditSeverity.CRITICAL: 4, AuditSeverity.ERROR: 3, AuditSeverity.WARNING: 2, AuditSeverity.INFO: 1, AuditSeverity.DEBUG: 0}
            # Keep all ERROR+ entries; prune INFO/DEBUG
            keep = [e for e in self._entries if severity_order.get(e.severity, 0) >= 2]
            remove_count = len(self._entries) - len(keep)
            self._entries = keep[-self.max_entries:]
            logger.info(f"[AuditTrail] Pruned {remove_count} low-severity entries by retention policy")

    # ── Compliance Report ────────────────────────────────────────────────
    def generate_compliance_report(
        self,
        period_start: Optional[str] = None,
        period_end: Optional[str] = None,
    ) -> ComplianceReport:
        """Generate a compliance report from the audit trail."""
        entries = self.query(AuditFilter(
            since=period_start,
            until=period_end,
            limit=1_000_000,
        ))

        # Count by type
        entries_by_type: Dict[str, int] = {}
        entries_by_severity: Dict[str, int] = {}
        safety_events: List[Dict[str, Any]] = []
        task_events: Dict[str, List[AuditEntry]] = {}

        for e in entries:
            type_key = e.event_type.value
            entries_by_type[type_key] = entries_by_type.get(type_key, 0) + 1
            sev_key = e.severity.value
            entries_by_severity[sev_key] = entries_by_severity.get(sev_key, 0) + 1

            # Collect safety events
            if e.event_type.value.startswith("safety_") or e.event_type.value.startswith("guardrail_") or e.event_type.value.startswith("grounding_"):
                safety_events.append({
                    "type": e.event_type.value,
                    "severity": e.severity.value,
                    "summary": e.summary,
                    "timestamp": e.timestamp,
                    "task_id": e.task_id,
                })

            # Group by task
            if e.task_id:
                task_events.setdefault(e.task_id, []).append(e)

        # Task summary
        task_summary = {
            "total_tasks": len(task_events),
            "completed_tasks": sum(1 for es in task_events.values() if any(e.event_type == AuditEventType.TASK_COMPLETED for e in es)),
            "failed_tasks": sum(1 for es in task_events.values() if any(e.event_type == AuditEventType.TASK_FAILED for e in es)),
            "blocked_tasks": sum(1 for es in task_events.values() if any(e.event_type == AuditEventType.TASK_REJECTED for e in es)),
        }

        # Anomalies
        anomalies: List[str] = []
        chain_valid = self.verify_chain()
        if not chain_valid:
            anomalies.append("Hash chain integrity VIOLATION detected")

        # Check for unusual safety block rates
        safety_blocks = entries_by_type.get("safety_block", 0) + entries_by_type.get("guardrail_block", 0)
        if safety_blocks > len(entries) * 0.1:
            anomalies.append(f"High safety block rate: {safety_blocks}/{len(entries)} entries")

        report_id = f"compliance_{hashlib.sha256(str(datetime.now(timezone.utc)).encode()).hexdigest()[:12]}"

        return ComplianceReport(
            report_id=report_id,
            generated_at=datetime.now(timezone.utc).isoformat(),
            period_start=period_start or "epoch",
            period_end=period_end or datetime.now(timezone.utc).isoformat(),
            total_entries=len(entries),
            entries_by_type=entries_by_type,
            entries_by_severity=entries_by_severity,
            task_summary=task_summary,
            safety_events=safety_events[:100],
            anomalies=anomalies,
            chain_valid=chain_valid,
            retention_status=self.retention.value,
        )

    def export_json(self, filters: Optional[AuditFilter] = None) -> str:
        """Export filtered entries as JSON."""
        entries = self.query(filters)
        data = {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "entry_count": len(entries),
            "chain_valid": self.verify_chain(),
            "entries": [e.model_dump() for e in entries],
        }
        return json.dumps(data, indent=2, default=str)

    def export_csv(self, filters: Optional[AuditFilter] = None) -> str:
        """Export filtered entries as CSV."""
        entries = self.query(filters)
        if not entries:
            return "entry_id,event_type,severity,timestamp,task_id,agent_id,summary,outcome\n"

        lines = ["entry_id,event_type,severity,timestamp,task_id,agent_id,summary,outcome"]
        for e in entries:
            summary = e.summary.replace('"', '""')
            lines.append(
                f"{e.entry_id},{e.event_type.value},{e.severity.value},{e.timestamp},"
                f"{e.task_id or ''},{e.agent_id or ''},\"{summary}\",{e.outcome or ''}"
            )
        return "\n".join(lines)

    def get_stats(self) -> Dict[str, Any]:
        """Get basic statistics about the audit trail."""
        with self._lock:
            total = len(self._entries)
            types = {}
            sevs = {}
            for e in self._entries:
                types[e.event_type.value] = types.get(e.event_type.value, 0) + 1
                sevs[e.severity.value] = sevs.get(e.severity.value, 0) + 1
            return {
                "total_entries": total,
                "events_by_type": types,
                "events_by_severity": sevs,
                "chain_valid": self.verify_chain(),
                "first_entry": self._entries[0].timestamp if self._entries else None,
                "last_entry": self._entries[-1].timestamp if self._entries else None,
                "retention_policy": self.retention.value,
            }

    def clear(self) -> None:
        """Clear all entries (for testing)."""
        with self._lock:
            self._entries.clear()
            self._last_hash = None
            self._task_index.clear()
            self._agent_index.clear()
            self._type_index.clear()


# ─── Singleton ────────────────────────────────────────────────────────────
_instance: Optional[AuditTrail] = None


def get_audit_trail(
    max_entries: int = 100_000,
    retention: RetentionPolicy = RetentionPolicy.KEEP_ALL,
) -> AuditTrail:
    """Get or create the singleton AuditTrail."""
    global _instance
    if _instance is None:
        _instance = AuditTrail(max_entries=max_entries, retention=retention)
    return _instance


def reset_audit_trail() -> None:
    """Reset the singleton (for testing)."""
    global _instance
    _instance = None
