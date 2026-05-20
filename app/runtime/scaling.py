"""Horizontal scaling coordinator stub.

The distributed Redis-based scaling coordinator has been removed from the
desktop-native runtime. This module provides a minimal stub that returns
standalone/single-instance state for backward compatibility with the cloud
API routes.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


class _ScalingResult:
    """Result of instance registration."""
    def __init__(self, accepted: bool = True, cluster_state: Optional[Dict[str, Any]] = None):
        self.accepted = accepted
        self.cluster_state = cluster_state or {"standalone": True}


class HorizontalScalingCoordinator:
    """Stub scaling coordinator for single-process desktop runtime.

    All methods return standalone/local-only results since horizontal
    scaling is not applicable in desktop mode.
    """

    def __init__(self, redis=None):
        self._instances: Dict[str, Dict[str, Any]] = {}
        self._task_locks: Dict[str, str] = {}

    async def register_instance(
        self, instance_id: str, capabilities: Optional[List[str]] = None
    ) -> _ScalingResult:
        """Register an instance (local-only, always succeeds)."""
        self._instances[instance_id] = {
            "instance_id": instance_id,
            "capabilities": capabilities or [],
            "active_tasks": 0,
        }
        return _ScalingResult(accepted=True, cluster_state={"standalone": True})

    async def deregister_instance(self, instance_id: str) -> None:
        """Remove instance registration."""
        self._instances.pop(instance_id, None)

    async def heartbeat(self) -> None:
        """No-op heartbeat for standalone mode."""
        pass

    async def get_cluster_state(self) -> Dict[str, Any]:
        """Return cluster state (standalone single-instance)."""
        return {
            "instance_count": len(self._instances),
            "instances": self._instances,
            "standalone": True,
        }

    async def assign_task(
        self, task_id: str, required_capabilities: Optional[List[str]] = None
    ) -> Optional[str]:
        """Assign task to an instance (returns first registered or None)."""
        if not self._instances:
            return None
        # Return least-loaded instance
        sorted_instances = sorted(
            self._instances.values(),
            key=lambda x: x.get("active_tasks", 0),
        )
        return sorted_instances[0]["instance_id"]

    async def acquire_task_lock(self, task_id: str, instance_id: str) -> bool:
        """Acquire a task lock (always succeeds in standalone)."""
        self._task_locks[task_id] = instance_id
        return True

    async def release_task_lock(self, task_id: str) -> None:
        """Release a task lock."""
        self._task_locks.pop(task_id, None)


# Module-level singleton
scaling_coordinator = HorizontalScalingCoordinator()
