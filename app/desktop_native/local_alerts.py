"""LocalAlertManager — desktop-native alerting with local notifications.

Replaces webhook/Slack-based alerting with local-first alerts:
- Desktop notifications via Tauri hooks (placeholder for now)
- Log file alerts
- SQLite alert history
- Alert rules engine with cooldown

Usage:
    from app.desktop_native.local_alerts import local_alerts
    await local_alerts.initialize()
    await local_alerts.fire("high_memory", "Memory usage above 80%", severity="warning")
"""

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Callable, Any

from ..logs.logger import logger
from .sqlite_store import sqlite_store
from .local_logger import local_logger


@dataclass
class AlertRule:
    name: str
    condition: str
    cooldown_seconds: int = 300
    severity: str = "warning"


class LocalAlertManager:
    """Desktop-native alert manager with local notifications and SQLite history."""

    def __init__(self):
        self._rules: Dict[str, AlertRule] = {}
        self._last_fired: Dict[str, datetime] = {}
        self._handlers: List[Callable] = []
        self._sqlite = sqlite_store
        self._initialized = False

    async def initialize(self):
        """Initialize alert manager and create tables."""
        if self._initialized:
            return
        await self._ensure_table()
        self._initialized = True
        logger.info("LocalAlertManager initialized")

    async def _ensure_table(self):
        try:
            await self._sqlite.execute("""
                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    rule_name TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    message TEXT NOT NULL,
                    details TEXT,
                    fired_at TEXT NOT NULL,
                    acknowledged_at TEXT
                )
            """)
            await self._sqlite.execute("""
                CREATE INDEX IF NOT EXISTS idx_alerts_rule ON alerts(rule_name, fired_at)
            """)
            await self._sqlite.commit()
        except Exception as e:
            logger.warning(f"Failed to create alerts table: {e}")

    def register_rule(self, rule: AlertRule):
        """Register an alert rule."""
        self._rules[rule.name] = rule
        logger.info(f"Alert rule registered: {rule.name}")

    def add_handler(self, handler: Callable):
        """Add a handler for alert events.

        Handlers receive: (rule_name, severity, message, details)
        """
        self._handlers.append(handler)

    async def fire(
        self,
        rule_name: str,
        message: str,
        severity: str = "warning",
        details: Optional[Dict[str, Any]] = None,
        force: bool = False,
    ) -> bool:
        """Fire an alert.

        Args:
            rule_name: Name of the alert rule
            message: Human-readable alert message
            severity: info, warning, error, critical
            details: Additional structured data
            force: Bypass cooldown

        Returns:
            True if alert was fired (not suppressed by cooldown)
        """
        if not self._initialized:
            await self.initialize()

        now = datetime.now(timezone.utc)

        # Check cooldown
        rule = self._rules.get(rule_name)
        if rule and not force:
            last = self._last_fired.get(rule_name)
            if last and (now - last).total_seconds() < rule.cooldown_seconds:
                logger.debug(f"Alert {rule_name} suppressed by cooldown")
                return False

        self._last_fired[rule_name] = now

        # Persist to SQLite
        try:
            await self._sqlite.execute(
                "INSERT INTO alerts (rule_name, severity, message, details, fired_at) VALUES (?, ?, ?, ?, ?)",
                (rule_name, severity, message, json.dumps(details or {}), now.isoformat()),
            )
            await self._sqlite.commit()
        except Exception as e:
            logger.warning(f"Failed to persist alert: {e}")

        # Log the alert
        log_method = {
            "critical": local_logger.critical,
            "error": local_logger.error,
            "warning": local_logger.warning,
            "info": local_logger.info,
        }.get(severity, local_logger.warning)
        log_method(f"ALERT: {message}", extra={"rule": rule_name, "severity": severity, **(details or {})})

        # Notify handlers
        for handler in self._handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(rule_name, severity, message, details)
                else:
                    handler(rule_name, severity, message, details)
            except Exception as e:
                logger.warning(f"Alert handler failed: {e}")

        # TODO: Tauri native notification via gRPC -> Go Supervisor
        # This will be implemented when Tauri integration is complete

        return True

    async def acknowledge(self, alert_id: int):
        """Acknowledge an alert."""
        try:
            now = datetime.now(timezone.utc).isoformat()
            await self._sqlite.execute(
                "UPDATE alerts SET acknowledged_at = ? WHERE id = ?",
                (now, alert_id),
            )
            await self._sqlite.commit()
        except Exception as e:
            logger.warning(f"Failed to acknowledge alert {alert_id}: {e}")

    async def list_active(self, limit: int = 100) -> List[Dict[str, Any]]:
        """List unacknowledged alerts."""
        try:
            await self._ensure_table()
            rows = await self._sqlite.fetchall(
                "SELECT * FROM alerts WHERE acknowledged_at IS NULL ORDER BY fired_at DESC LIMIT ?",
                (limit,),
            )
            return [self._row_to_dict(r) for r in rows]
        except Exception as e:
            logger.warning(f"Failed to list active alerts: {e}")
            return []

    async def list_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """List all alert history."""
        try:
            await self._ensure_table()
            rows = await self._sqlite.fetchall(
                "SELECT * FROM alerts ORDER BY fired_at DESC LIMIT ?",
                (limit,),
            )
            return [self._row_to_dict(r) for r in rows]
        except Exception as e:
            logger.warning(f"Failed to list alert history: {e}")
            return []

    async def cleanup_old(self, max_age_days: int = 30) -> int:
        """Remove old acknowledged alerts."""
        try:
            await self._ensure_table()
            cutoff = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).isoformat()
            cursor = await self._sqlite.execute(
                "DELETE FROM alerts WHERE fired_at < ? AND acknowledged_at IS NOT NULL",
                (cutoff,),
            )
            await self._sqlite.commit()
            count = cursor.rowcount if hasattr(cursor, "rowcount") else 0
            if count > 0:
                logger.info(f"Cleaned up {count} old alerts")
            return count
        except Exception as e:
            logger.warning(f"Failed to cleanup old alerts: {e}")
            return 0

    def _row_to_dict(self, row) -> Dict[str, Any]:
        return {
            "id": row["id"],
            "rule_name": row["rule_name"],
            "severity": row["severity"],
            "message": row["message"],
            "details": json.loads(row["details"]) if row["details"] else {},
            "fired_at": row["fired_at"],
            "acknowledged_at": row["acknowledged_at"],
        }


# Module-level singleton
local_alerts = LocalAlertManager()
