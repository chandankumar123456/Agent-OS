"""Worker pool manager with health checks, scaling, and load balancing.

Manages a pool of worker processes across instances, tracks health,
and scales based on queue depth and load factor.
"""
import asyncio
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from ..memory.short_term import redis_client
from ..logs.logger import logger
from ..orchestrator.queue import TaskQueue
from ..config.settings import settings


def _is_desktop_mode() -> bool:
    """Check if running in desktop-native gRPC mode."""
    mode = settings.RUNTIME_MODE or "http"
    return mode.lower() == "grpc"


class WorkerStatus(str, Enum):
    """Status of a worker."""
    ACTIVE = "active"
    IDLE = "idle"
    BUSY = "busy"
    UNHEALTHY = "unhealthy"
    STOPPING = "stopping"
    STOPPED = "stopped"


class WorkerInfo(BaseModel):
    """Information about a worker."""
    worker_id: str
    status: WorkerStatus
    registered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_heartbeat: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    tasks_completed: int = 0
    tasks_failed: int = 0
    current_task_id: Optional[str] = None
    capabilities: List[str] = Field(default_factory=list)
    load_factor: float = 0.0


class PoolStatus(BaseModel):
    """Status of the worker pool."""
    active_workers: int = 0
    healthy_workers: int = 0
    pending_tasks: int = 0
    load_factor: float = 0.0
    target_count: int = 0
    workers: List[WorkerInfo] = Field(default_factory=list)


class WorkerPoolManager:
    """Manages worker pools across processes with health checks and scaling.

    Usage:
        manager = WorkerPoolManager()
        await manager.register_worker("worker-1", capabilities=["desktop", "browser"])
        status = await manager.manage_workers(target_count=5)
    """

    def __init__(
        self,
        redis_prefix: str = "agentos:worker:",
        heartbeat_timeout_seconds: int = 60,
        task_queue: Optional[TaskQueue] = None,
    ):
        self.redis_prefix = redis_prefix
        self.heartbeat_timeout = heartbeat_timeout_seconds
        self.task_queue = task_queue or TaskQueue()

    def _worker_key(self, worker_id: str) -> str:
        return f"{self.redis_prefix}info:{worker_id}"

    def _workers_index_key(self) -> str:
        return f"{self.redis_prefix}index"

    async def register_worker(
        self,
        worker_id: str,
        capabilities: Optional[List[str]] = None,
    ) -> WorkerInfo:
        """Register a new worker.

        In desktop mode, this is a no-op as there are no distributed workers.
        """
        info = WorkerInfo(
            worker_id=worker_id,
            status=WorkerStatus.IDLE,
            capabilities=capabilities or [],
        )

        if _is_desktop_mode():
            logger.debug(f"Worker registration skipped in desktop mode")
            return info

        try:
            await redis_client.client.set(
                self._worker_key(worker_id),
                info.model_dump_json(),
                ex=self.heartbeat_timeout * 2,
            )
            await redis_client.client.sadd(self._workers_index_key(), worker_id)
            logger.info(
                f"Worker registered",
                extra={"worker_id": worker_id, "capabilities": capabilities},
            )
        except Exception as e:
            logger.error(f"Failed to register worker {worker_id}: {e}")

        return info

    async def heartbeat(self, worker_id: str, status: Optional[WorkerStatus] = None) -> bool:
        """Send a heartbeat from a worker.

        In desktop mode, this is a no-op.
        """
        if _is_desktop_mode():
            return True

        try:
            value = await redis_client.client.get(self._worker_key(worker_id))
            if not value:
                # Worker not registered, auto-register
                await self.register_worker(worker_id)
                value = await redis_client.client.get(self._worker_key(worker_id))

            import json
            info = WorkerInfo(**json.loads(value))
            info.last_heartbeat = datetime.now(timezone.utc)
            if status:
                info.status = status

            await redis_client.client.set(
                self._worker_key(worker_id),
                info.model_dump_json(),
                ex=self.heartbeat_timeout * 2,
            )
            return True
        except Exception as e:
            logger.error(f"Heartbeat failed for {worker_id}: {e}")
            return False

    async def update_task_assignment(
        self,
        worker_id: str,
        task_id: Optional[str],
    ) -> bool:
        """Update the current task assignment for a worker.

        Args:
            worker_id: Worker identifier.
            task_id: Task ID or None to clear.

        Returns:
            True if updated.
        """
        try:
            value = await redis_client.client.get(self._worker_key(worker_id))
            if not value:
                return False

            import json
            info = WorkerInfo(**json.loads(value))
            info.current_task_id = task_id
            info.status = WorkerStatus.BUSY if task_id else WorkerStatus.IDLE

            await redis_client.client.set(
                self._worker_key(worker_id),
                info.model_dump_json(),
                ex=self.heartbeat_timeout * 2,
            )
            return True
        except Exception as e:
            logger.error(f"Failed to update task assignment for {worker_id}: {e}")
            return False

    async def record_task_completion(self, worker_id: str, success: bool = True) -> bool:
        """Record task completion for a worker.

        Args:
            worker_id: Worker identifier.
            success: Whether the task succeeded.

        Returns:
            True if recorded.
        """
        try:
            value = await redis_client.client.get(self._worker_key(worker_id))
            if not value:
                return False

            import json
            info = WorkerInfo(**json.loads(value))
            if success:
                info.tasks_completed += 1
            else:
                info.tasks_failed += 1
            info.current_task_id = None
            info.status = WorkerStatus.IDLE

            await redis_client.client.set(
                self._worker_key(worker_id),
                info.model_dump_json(),
                ex=self.heartbeat_timeout * 2,
            )
            return True
        except Exception as e:
            logger.error(f"Failed to record completion for {worker_id}: {e}")
            return False

    async def get_worker(self, worker_id: str) -> Optional[WorkerInfo]:
        """Get worker information.

        Args:
            worker_id: Worker identifier.

        Returns:
            WorkerInfo if found, None otherwise.
        """
        try:
            value = await redis_client.client.get(self._worker_key(worker_id))
            if value:
                import json
                return WorkerInfo(**json.loads(value))
        except Exception as e:
            logger.error(f"Failed to get worker {worker_id}: {e}")
        return None

    async def list_workers(self) -> List[WorkerInfo]:
        """List all registered workers.

        In desktop mode, returns an empty list.
        """
        if _is_desktop_mode():
            return []

        workers = []
        try:
            worker_ids = await redis_client.client.smembers(self._workers_index_key())
            for wid in worker_ids:
                info = await self.get_worker(wid)
                if info:
                    workers.append(info)
        except Exception as e:
            logger.error(f"Failed to list workers: {e}")
        return workers

    async def health_check(self) -> List[WorkerInfo]:
        """Run health check on all workers and mark unhealthy ones.

        In desktop mode, returns an empty list.
        """
        if _is_desktop_mode():
            return []

        unhealthy = []
        try:
            workers = await self.list_workers()
            now = datetime.now(timezone.utc)
            for info in workers:
                last_heartbeat = info.last_heartbeat
                if isinstance(last_heartbeat, str):
                    last_heartbeat = datetime.fromisoformat(last_heartbeat)
                age_seconds = (now - last_heartbeat).total_seconds()

                if age_seconds > self.heartbeat_timeout:
                    info.status = WorkerStatus.UNHEALTHY
                    try:
                        await redis_client.client.set(
                            self._worker_key(info.worker_id),
                            info.model_dump_json(),
                            ex=self.heartbeat_timeout * 2,
                        )
                    except Exception:
                        pass
                    unhealthy.append(info)
                    logger.warning(
                        f"Worker unhealthy",
                        extra={"worker_id": info.worker_id, "last_heartbeat_age": age_seconds},
                    )
        except Exception as e:
            logger.error(f"Health check failed: {e}")
        return unhealthy

    async def unregister_worker(self, worker_id: str) -> bool:
        """Unregister a worker.

        Args:
            worker_id: Worker identifier.

        Returns:
            True if unregistered.
        """
        try:
            await redis_client.client.delete(self._worker_key(worker_id))
            await redis_client.client.srem(self._workers_index_key(), worker_id)
            logger.info(f"Worker unregistered", extra={"worker_id": worker_id})
            return True
        except Exception as e:
            logger.error(f"Failed to unregister worker {worker_id}: {e}")
            return False

    async def manage_workers(
        self,
        target_count: int,
        health_check_interval: int = 30,
    ) -> PoolStatus:
        """Manage worker pool health and scaling.

        In desktop mode, returns a minimal status with no workers.
        """
        if _is_desktop_mode():
            return PoolStatus(
                active_workers=0,
                healthy_workers=0,
                pending_tasks=0,
                load_factor=0.0,
                target_count=target_count,
                workers=[],
            )

        # Run health check
        await self.health_check()

        workers = await self.list_workers()
        pending_tasks = await self.task_queue.length()

        active_workers = sum(1 for w in workers if w.status in (WorkerStatus.ACTIVE, WorkerStatus.IDLE, WorkerStatus.BUSY))
        healthy_workers = sum(1 for w in workers if w.status != WorkerStatus.UNHEALTHY)

        # Calculate load factor: pending tasks / healthy workers
        if healthy_workers > 0:
            load_factor = pending_tasks / healthy_workers
        else:
            load_factor = float(pending_tasks)

        # Clean up stopped workers
        for w in workers:
            if w.status == WorkerStatus.STOPPED:
                await self.unregister_worker(w.worker_id)

        status = PoolStatus(
            active_workers=active_workers,
            healthy_workers=healthy_workers,
            pending_tasks=pending_tasks,
            load_factor=round(load_factor, 2),
            target_count=target_count,
            workers=workers,
        )

        logger.info(
            f"Pool status",
            extra={
                "active_workers": active_workers,
                "healthy_workers": healthy_workers,
                "pending_tasks": pending_tasks,
                "load_factor": load_factor,
                "target_count": target_count,
            },
        )

        return status

    async def select_worker(self) -> Optional[str]:
        """Select the best available worker for task assignment.

        Returns:
            Worker ID or None if no workers available.
        """
        workers = await self.list_workers()
        available = [
            w for w in workers
            if w.status in (WorkerStatus.IDLE, WorkerStatus.ACTIVE)
        ]

        if not available:
            return None

        # Select worker with lowest load factor / fewest completed tasks
        # Simple round-robin: select the one with fewest tasks completed
        selected = min(available, key=lambda w: w.tasks_completed)
        return selected.worker_id

    async def scale_up(self, count: int) -> List[str]:
        """Signal that more workers are needed.

        In a real deployment this would trigger process/container creation.
        Here we return placeholder worker IDs.

        Args:
            count: Number of workers to add.

        Returns:
            List of new worker IDs.
        """
        new_ids = []
        for _ in range(count):
            worker_id = f"worker-{int(time.time() * 1000000)}"
            await self.register_worker(worker_id)
            new_ids.append(worker_id)
        logger.info(f"Scale up requested", extra={"count": count, "new_workers": new_ids})
        return new_ids

    async def scale_down(self, worker_ids: List[str]) -> int:
        """Signal workers to stop.

        Args:
            worker_ids: Workers to stop.

        Returns:
            Number of workers marked for stopping.
        """
        count = 0
        for wid in worker_ids:
            try:
                value = await redis_client.client.get(self._worker_key(wid))
                if value:
                    import json
                    info = WorkerInfo(**json.loads(value))
                    info.status = WorkerStatus.STOPPING
                    await redis_client.client.set(
                        self._worker_key(wid),
                        info.model_dump_json(),
                        ex=self.heartbeat_timeout * 2,
                    )
                    count += 1
            except Exception as e:
                logger.error(f"Failed to scale down worker {wid}: {e}")
        logger.info(f"Scale down requested", extra={"count": count, "workers": worker_ids})
        return count


# Module-level singleton
worker_pool_manager = WorkerPoolManager()
