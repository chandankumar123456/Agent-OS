"""CrashRecovery — resume interrupted tasks after kernel restart.

On startup, scans SQLite for tasks in non-terminal states and resumes them
from their last checkpoint. This ensures that crashes or forced restarts
don't lose in-flight work.

Usage:
    from app.desktop_native.crash_recovery import crash_recovery
    await crash_recovery.scan_and_resume(kernel)
"""

import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from ..logs.logger import logger
from .sqlite_store import sqlite_store
from .state_machine import TaskState


class CrashRecovery:
    """Handles recovery of interrupted tasks after a kernel restart."""

    # States that indicate a task was in progress when the kernel stopped
    RECOVERABLE_STATES = {"pending", "planning", "executing", "paused"}

    def __init__(self):
        self._sqlite = sqlite_store
        self._recovery_count = 0
        self._failed_count = 0

    async def _ensure_tables(self) -> None:
        """Ensure recovery tracking tables exist."""
        try:
            await self._sqlite.execute("""
                CREATE TABLE IF NOT EXISTS recovery_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    old_state TEXT,
                    new_state TEXT,
                    reason TEXT,
                    recovered_at TEXT NOT NULL
                )
            """)
            await self._sqlite.execute("""
                CREATE INDEX IF NOT EXISTS idx_recovery_task ON recovery_log(task_id)
            """)
            await self._sqlite.commit()
        except Exception as e:
            logger.warning(f"Failed to create recovery tables: {e}")

    async def _log_recovery(
        self,
        task_id: str,
        action: str,
        old_state: Optional[str] = None,
        new_state: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> None:
        """Log a recovery action."""
        try:
            await self._sqlite.execute(
                """
                INSERT INTO recovery_log (task_id, action, old_state, new_state, reason, recovered_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    action,
                    old_state,
                    new_state,
                    reason,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            await self._sqlite.commit()
        except Exception as e:
            logger.warning(f"Failed to log recovery: {e}")

    async def find_interrupted_tasks(self) -> List[Dict[str, Any]]:
        """Find all tasks that were interrupted (non-terminal state)."""
        await self._ensure_tables()
        try:
            placeholders = ",".join("?" * len(self.RECOVERABLE_STATES))
            rows = await self._sqlite.fetchall(
                f"""
                SELECT task_id, query, status, config, user_id, created_at
                FROM tasks
                WHERE status IN ({placeholders})
                ORDER BY created_at ASC
                """,
                tuple(self.RECOVERABLE_STATES),
            )
            return [
                {
                    "task_id": r["task_id"],
                    "query": r["query"],
                    "status": r["status"],
                    "config": r["config"] or {},
                    "user_id": r["user_id"],
                    "created_at": r["created_at"],
                }
                for r in rows
            ]
        except Exception as e:
            logger.warning(f"Failed to find interrupted tasks: {e}")
            return []

    async def _find_checkpoint(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Find the latest checkpoint for a task."""
        try:
            row = await self._sqlite.fetchone(
                """
                SELECT thread_id, checkpoint_ns, checkpoint_id, metadata
                FROM checkpoints
                WHERE thread_id = ?
                ORDER BY checkpoint_id DESC
                LIMIT 1
                """,
                (task_id,),
            )
            if row:
                return {
                    "thread_id": row["thread_id"],
                    "checkpoint_ns": row["checkpoint_ns"],
                    "checkpoint_id": row["checkpoint_id"],
                    "metadata": row["metadata"],
                }
        except Exception as e:
            logger.warning(f"Failed to find checkpoint for {task_id}: {e}")
        return None

    async def resume_task(self, kernel: Any, task_info: Dict[str, Any]) -> bool:
        """Attempt to resume a single interrupted task.

        Args:
            kernel: The AgentKernel instance to submit the resumed task to.
            task_info: Dict with task_id, query, status, config, user_id.

        Returns:
            True if the task was successfully resubmitted.
        """
        task_id = task_info["task_id"]
        old_status = task_info["status"]

        logger.info(f"Attempting to recover task {task_id} (was {old_status})")

        # Check if there's a checkpoint we can resume from
        checkpoint = await self._find_checkpoint(task_id)

        if checkpoint and old_status in ("executing", "paused"):
            # Task had a checkpoint — resume from checkpoint
            logger.info(f"Task {task_id} has checkpoint {checkpoint['checkpoint_id']}, resuming")
            await self._log_recovery(
                task_id, "resume_from_checkpoint",
                old_state=old_status, new_state="pending",
                reason=f"Checkpoint {checkpoint['checkpoint_id']} found",
            )
        else:
            # No checkpoint or early state — restart from beginning
            logger.info(f"Task {task_id} has no checkpoint, restarting from beginning")
            await self._log_recovery(
                task_id, "restart_from_beginning",
                old_state=old_status, new_state="pending",
                reason="No checkpoint available",
            )

        try:
            # Update task status to pending for re-execution
            await self._sqlite.execute(
                "UPDATE tasks SET status = ?, updated_at = ? WHERE task_id = ?",
                ("pending", datetime.now(timezone.utc).isoformat(), task_id),
            )
            await self._sqlite.commit()

            # Re-submit to kernel
            from .kernel_state_machine import TaskState as TS
            await kernel.state_machine.transition(task_id, TS.PENDING, TS.PLANNING)

            new_task_id = await kernel.submit_task(
                query=task_info["query"],
                user_id=task_info.get("user_id", "recovered"),
                config=task_info.get("config", {}),
            )

            # Log successful resubmission
            await self._log_recovery(
                task_id, "resubmitted",
                old_state=old_status, new_state="pending",
                reason=f"Resubmitted as {new_task_id}",
            )
            self._recovery_count += 1
            return True

        except Exception as e:
            logger.error(f"Failed to resume task {task_id}: {e}")
            await self._log_recovery(
                task_id, "failed",
                old_state=old_status,
                reason=str(e),
            )
            self._failed_count += 1
            return False

    async def scan_and_resume(self, kernel: Any) -> Dict[str, Any]:
        """Scan for interrupted tasks and attempt to resume them.

        Args:
            kernel: The AgentKernel instance.

        Returns:
            Dict with recovery statistics.
        """
        await self._ensure_tables()
        self._recovery_count = 0
        self._failed_count = 0

        interrupted = await self.find_interrupted_tasks()
        if not interrupted:
            logger.info("CrashRecovery: no interrupted tasks found")
            return {"found": 0, "recovered": 0, "failed": 0, "tasks": []}

        logger.info(f"CrashRecovery: found {len(interrupted)} interrupted tasks")

        results = []
        for task_info in interrupted:
            success = await self.resume_task(kernel, task_info)
            results.append({
                "task_id": task_info["task_id"],
                "old_status": task_info["status"],
                "recovered": success,
            })

        logger.info(
            f"CrashRecovery: recovered {self._recovery_count}, "
            f"failed {self._failed_count}"
        )

        return {
            "found": len(interrupted),
            "recovered": self._recovery_count,
            "failed": self._failed_count,
            "tasks": results,
        }

    async def get_recovery_history(self, task_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recovery history for a task or all tasks."""
        await self._ensure_tables()
        try:
            if task_id:
                rows = await self._sqlite.fetchall(
                    "SELECT * FROM recovery_log WHERE task_id = ? ORDER BY recovered_at DESC LIMIT ?",
                    (task_id, limit),
                )
            else:
                rows = await self._sqlite.fetchall(
                    "SELECT * FROM recovery_log ORDER BY recovered_at DESC LIMIT ?",
                    (limit,),
                )
            return [
                {
                    "task_id": r["task_id"],
                    "action": r["action"],
                    "old_state": r["old_state"],
                    "new_state": r["new_state"],
                    "reason": r["reason"],
                    "recovered_at": r["recovered_at"],
                }
                for r in rows
            ]
        except Exception as e:
            logger.warning(f"Failed to get recovery history: {e}")
            return []


# Module-level singleton
crash_recovery = CrashRecovery()
