"""TauriBridge — Python-side integration with Tauri GUI via gRPC/Supervisor.

This module provides:
- Event emission to Tauri frontend (via Supervisor WebSocket)
- Native notification triggers
- Task history queries for the GUI
- Settings sync between Python and Tauri

Usage:
    from core.desktop_native.tauri_bridge import tauri_bridge
    await tauri_bridge.emit_event("task:completed", {"task_id": "123", "result": "..."})
    await tauri_bridge.show_notification("Task Complete", "Your task has finished")
"""

from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from ..logs.logger import logger
from .sqlite_store import sqlite_store
from .local_alerts import local_alerts


class TauriBridge:
    """Bridge between Python runtime and Tauri GUI."""

    def __init__(self):
        self._sqlite = sqlite_store
        self._event_queue: List[Dict[str, Any]] = []
        self._notifications_enabled = True

    async def _ensure_tables(self):
        """Ensure GUI-related tables exist."""
        try:
            await self._sqlite.execute("""
                CREATE TABLE IF NOT EXISTS gui_task_history (
                    task_id TEXT PRIMARY KEY,
                    query TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    completed_at TEXT,
                    duration_seconds REAL
                )
            """)
            await self._sqlite.execute("""
                CREATE INDEX IF NOT EXISTS idx_gui_history_status ON gui_task_history(status)
            """)
            await self._sqlite.execute("""
                CREATE INDEX IF NOT EXISTS idx_gui_history_created ON gui_task_history(created_at DESC)
            """)
            await self._sqlite.commit()
        except Exception as e:
            logger.warning(f"Failed to create GUI tables: {e}")

    async def emit_event(self, event_type: str, payload: Dict[str, Any]) -> bool:
        """Emit an event to the Tauri frontend via Supervisor.

        In the current architecture, events flow:
        Python -> LocalEventBus -> gRPC streaming -> Supervisor -> WebSocket -> Tauri

        This method publishes to the local event bus which is picked up by
        the gRPC streaming layer.
        """
        try:
            from .event_bus import local_event_bus, Event

            event = Event(
                event_type,
                payload,
                source="python_runtime",
            )
            await local_event_bus.publish("tauri", event)

            # Also queue for batch emission
            self._event_queue.append({
                "type": event_type,
                "payload": payload,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

            return True
        except Exception as e:
            logger.warning(f"Failed to emit event to Tauri: {e}")
            return False

    async def show_notification(self, title: str, body: str, urgency: str = "normal") -> bool:
        """Trigger a native desktop notification.

        Urgency levels: low, normal, critical
        """
        if not self._notifications_enabled:
            return False

        try:
            # Log the notification
            logger.info(f"NOTIFICATION: {title} - {body}")

            # Emit as event so Tauri can display it
            await self.emit_event("notification", {
                "title": title,
                "body": body,
                "urgency": urgency,
            })

            # Also fire through alert manager
            await local_alerts.fire(
                "desktop_notification",
                f"{title}: {body}",
                severity="info" if urgency != "critical" else "critical",
            )

            return True
        except Exception as e:
            logger.warning(f"Failed to show notification: {e}")
            return False

    async def notify_task_complete(self, task_id: str, query: str, success: bool, result: Optional[str] = None) -> bool:
        """Show notification when a task completes."""
        title = "Task Complete" if success else "Task Failed"
        body = f"{'✓' if success else '✗'} {query[:50]}{'...' if len(query) > 50 else ''}"
        await self.show_notification(title, body, urgency="normal" if success else "critical")
        await self.emit_event("task:completed" if success else "task:failed", {
            "task_id": task_id,
            "query": query,
            "result": result,
        })
        return True

    async def notify_approval_required(self, task_id: str, tool_name: str, reason: str) -> bool:
        """Show notification when user approval is required."""
        await self.show_notification(
            "Approval Required",
            f"Task {task_id} wants to use {tool_name}: {reason}",
            urgency="critical",
        )
        await self.emit_event("approval:required", {
            "task_id": task_id,
            "tool_name": tool_name,
            "reason": reason,
        })
        return True

    async def record_task_for_gui(self, task_id: str, query: str, status: str, **kwargs):
        """Record task for GUI task history."""
        await self._ensure_tables()
        try:
            now = datetime.now(timezone.utc).isoformat()
            await self._sqlite.execute(
                """
                INSERT OR REPLACE INTO gui_task_history
                (task_id, query, status, result, error, created_at, completed_at, duration_seconds)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    query,
                    status,
                    kwargs.get("result"),
                    kwargs.get("error"),
                    kwargs.get("created_at", now),
                    kwargs.get("completed_at"),
                    kwargs.get("duration_seconds"),
                ),
            )
            await self._sqlite.commit()
        except Exception as e:
            logger.warning(f"Failed to record task for GUI: {e}")

    async def get_task_history(self, limit: int = 50, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get task history for GUI display."""
        await self._ensure_tables()
        try:
            if status:
                rows = await self._sqlite.fetchall(
                    "SELECT * FROM gui_task_history WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                    (status, limit),
                )
            else:
                rows = await self._sqlite.fetchall(
                    "SELECT * FROM gui_task_history ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                )
            return [
                {
                    "task_id": r["task_id"],
                    "query": r["query"],
                    "status": r["status"],
                    "result": r["result"],
                    "error": r["error"],
                    "created_at": r["created_at"],
                    "completed_at": r["completed_at"],
                    "duration_seconds": r["duration_seconds"],
                }
                for r in rows
            ]
        except Exception as e:
            logger.warning(f"Failed to get task history: {e}")
            return []

    async def get_task_stats(self) -> Dict[str, Any]:
        """Get task statistics for GUI dashboard."""
        await self._ensure_tables()
        try:
            total = await self._sqlite.fetchone("SELECT COUNT(*) as count FROM gui_task_history")
            completed = await self._sqlite.fetchone("SELECT COUNT(*) as count FROM gui_task_history WHERE status = 'completed'")
            failed = await self._sqlite.fetchone("SELECT COUNT(*) as count FROM gui_task_history WHERE status = 'failed'")
            running = await self._sqlite.fetchone("SELECT COUNT(*) as count FROM gui_task_history WHERE status = 'running'")

            return {
                "total": total["count"] if total else 0,
                "completed": completed["count"] if completed else 0,
                "failed": failed["count"] if failed else 0,
                "running": running["count"] if running else 0,
            }
        except Exception as e:
            logger.warning(f"Failed to get task stats: {e}")
            return {"total": 0, "completed": 0, "failed": 0, "running": 0}

    async def cleanup_old_history(self, max_age_days: int = 30) -> int:
        """Clean up old task history."""
        try:
            from datetime import timedelta
            cutoff = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).isoformat()
            # Count before delete
            before = await self._sqlite.fetchone(
                "SELECT COUNT(*) as count FROM gui_task_history WHERE created_at < ?",
                (cutoff,),
            )
            count = before["count"] if before else 0
            await self._sqlite.execute(
                "DELETE FROM gui_task_history WHERE created_at < ?",
                (cutoff,),
            )
            await self._sqlite.commit()
            if count > 0:
                logger.info(f"Cleaned up {count} old GUI task history entries")
            return count
        except Exception as e:
            logger.warning(f"Failed to cleanup old GUI history: {e}")
            return 0

    def set_notifications_enabled(self, enabled: bool):
        """Enable or disable notifications."""
        self._notifications_enabled = enabled


# Module-level singleton
tauri_bridge = TauriBridge()
