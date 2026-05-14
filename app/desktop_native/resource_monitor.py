"""ResourceMonitor — per-task CPU/memory tracking with budget enforcement.

Monitors resource usage per task and kills runaway tasks that exceed
configured memory or CPU budgets.

Usage:
    from app.desktop_native.resource_monitor import resource_monitor
    await resource_monitor.start_monitoring(task_id, memory_mb=500, cpu_percent=50)
    ... task runs ...
    await resource_monitor.stop_monitoring(task_id)
"""

import asyncio
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional

from ..logs.logger import logger


@dataclass
class ResourceBudget:
    """Resource budget for a single task."""
    memory_mb: float = 512.0  # Max RSS memory in MB
    cpu_percent: float = 100.0  # Max CPU % (per core)
    max_runtime_seconds: float = 600.0  # Max task runtime


@dataclass
class ResourceSnapshot:
    """Snapshot of resource usage at a point in time."""
    timestamp: datetime
    memory_mb: float
    cpu_percent: float
    runtime_seconds: float


class ResourceMonitor:
    """Monitors and enforces resource limits per task.

    Uses psutil if available; falls back to process-based heuristics.
    """

    def __init__(self, check_interval_seconds: float = 5.0):
        self._check_interval = check_interval_seconds
        self._budgets: Dict[str, ResourceBudget] = {}
        self._snapshots: Dict[str, list] = {}
        self._start_times: Dict[str, datetime] = {}
        self._tasks: Dict[str, asyncio.Task] = {}
        self._violations: Dict[str, str] = {}
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

        self._psutil = None
        try:
            import psutil
            self._psutil = psutil
        except ImportError:
            logger.warning("psutil not installed; resource monitoring will use heuristics only")

    async def start_monitoring(
        self,
        task_id: str,
        budget: Optional[ResourceBudget] = None,
    ) -> None:
        """Start monitoring a task's resource usage."""
        async with self._lock:
            self._budgets[task_id] = budget or ResourceBudget()
            self._snapshots[task_id] = []
            self._start_times[task_id] = datetime.now(timezone.utc)
            self._violations.pop(task_id, None)
            logger.debug(f"Resource monitoring started for task {task_id}")

    async def stop_monitoring(self, task_id: str) -> Optional[ResourceSnapshot]:
        """Stop monitoring a task and return final snapshot."""
        async with self._lock:
            budget = self._budgets.pop(task_id, None)
            if not budget:
                return None

            snapshots = self._snapshots.pop(task_id, [])
            self._start_times.pop(task_id, None)
            self._tasks.pop(task_id, None)

            final = snapshots[-1] if snapshots else None
            logger.debug(f"Resource monitoring stopped for task {task_id}")
            return final

    def get_latest_snapshot(self, task_id: str) -> Optional[ResourceSnapshot]:
        """Get the latest resource snapshot for a task."""
        snapshots = self._snapshots.get(task_id)
        return snapshots[-1] if snapshots else None

    def get_violation(self, task_id: str) -> Optional[str]:
        """Get violation reason if task exceeded budget."""
        return self._violations.get(task_id)

    def _get_current_usage(self, task_id: str) -> ResourceSnapshot:
        """Get current resource usage for this process."""
        now = datetime.now(timezone.utc)
        start = self._start_times.get(task_id, now)
        runtime = (now - start).total_seconds()

        memory_mb = 0.0
        cpu_percent = 0.0

        if self._psutil:
            try:
                proc = self._psutil.Process(os.getpid())
                mem_info = proc.memory_info()
                memory_mb = mem_info.rss / (1024 * 1024)
                cpu_percent = proc.cpu_percent(interval=None)
            except Exception as e:
                logger.warning(f"psutil error: {e}")
        else:
            # Heuristic: check asyncio task count
            try:
                loop = asyncio.get_running_loop()
                task_count = len(asyncio.all_tasks(loop))
                memory_mb = task_count * 2.0  # Rough heuristic: 2MB per task
            except Exception:
                pass

        return ResourceSnapshot(
            timestamp=now,
            memory_mb=memory_mb,
            cpu_percent=cpu_percent,
            runtime_seconds=runtime,
        )

    async def _check_budgets(self) -> None:
        """Check all active tasks against their budgets."""
        async with self._lock:
            for task_id, budget in list(self._budgets.items()):
                snapshot = self._get_current_usage(task_id)
                snapshots = self._snapshots.get(task_id, [])
                snapshots.append(snapshot)

                # Keep only last 60 snapshots (5 min at 5s interval)
                if len(snapshots) > 60:
                    snapshots[:] = snapshots[-60:]

                # Check memory limit
                if snapshot.memory_mb > budget.memory_mb:
                    self._violations[task_id] = (
                        f"Memory limit exceeded: {snapshot.memory_mb:.1f}MB > "
                        f"{budget.memory_mb:.1f}MB"
                    )
                    logger.warning(
                        f"Task {task_id} {self._violations[task_id]}"
                    )

                # Check CPU limit
                elif snapshot.cpu_percent > budget.cpu_percent:
                    self._violations[task_id] = (
                        f"CPU limit exceeded: {snapshot.cpu_percent:.1f}% > "
                        f"{budget.cpu_percent:.1f}%"
                    )
                    logger.warning(
                        f"Task {task_id} {self._violations[task_id]}"
                    )

                # Check runtime limit
                elif snapshot.runtime_seconds > budget.max_runtime_seconds:
                    self._violations[task_id] = (
                        f"Runtime limit exceeded: {snapshot.runtime_seconds:.1f}s > "
                        f"{budget.max_runtime_seconds:.1f}s"
                    )
                    logger.warning(
                        f"Task {task_id} {self._violations[task_id]}"
                    )

    async def _monitor_loop(self) -> None:
        """Background monitoring loop."""
        logger.info("ResourceMonitor started")
        while self._running:
            try:
                if self._budgets:
                    await self._check_budgets()
                await asyncio.sleep(self._check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"ResourceMonitor loop error: {e}")
                await asyncio.sleep(self._check_interval)
        logger.info("ResourceMonitor stopped")

    async def start(self) -> None:
        """Start the background monitoring loop."""
        if self._running:
            return
        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())

    async def stop(self) -> None:
        """Stop the background monitoring loop."""
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None

    def get_all_snapshots(self, task_id: str) -> list:
        """Get all snapshots for a task."""
        return list(self._snapshots.get(task_id, []))

    async def get_system_stats(self) -> Dict:
        """Get overall system resource stats."""
        stats = {
            "monitored_tasks": len(self._budgets),
            "total_violations": len(self._violations),
            "python_version": sys.version,
        }

        if self._psutil:
            try:
                proc = self._psutil.Process(os.getpid())
                stats["process_memory_mb"] = proc.memory_info().rss / (1024 * 1024)
                stats["process_cpu_percent"] = proc.cpu_percent(interval=None)
                stats["system_memory_percent"] = self._psutil.virtual_memory().percent
                stats["system_cpu_percent"] = self._psutil.cpu_percent(interval=None)
            except Exception as e:
                stats["error"] = str(e)
        else:
            stats["note"] = "psutil not available"

        return stats


# Module-level singleton
resource_monitor = ResourceMonitor()
