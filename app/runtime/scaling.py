import asyncio
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone
from ..memory.short_term import redis_client
from ..logs.logger import logger


@dataclass
class InstanceRegistration:
    accepted: bool
    assigned_tasks: List[str]
    cluster_state: Dict[str, Any]


@dataclass
class ClusterInstance:
    instance_id: str
    capabilities: List[str]
    last_heartbeat: str
    active_tasks: int
    healthy: bool = True


class HorizontalScalingCoordinator:
    """Coordinates multiple AgentOS instances with shared state, distributed locks, and load balancing.

    Uses Redis for instance discovery and task distribution.
    """

    def __init__(self, redis=None, heartbeat_ttl: int = 30):
        self._redis = redis
        self.heartbeat_ttl = heartbeat_ttl
        self._local_instance_id: Optional[str] = None
        self._local_capabilities: List[str] = []

    def _instance_key(self, instance_id: str) -> str:
        return f"agentos:instance:{instance_id}"

    def _cluster_tasks_key(self) -> str:
        return "agentos:cluster:tasks"

    def _cluster_lock_key(self, task_id: str) -> str:
        return f"agentos:cluster:task_lock:{task_id}"

    async def register_instance(
        self,
        instance_id: str,
        capabilities: List[str]
    ) -> InstanceRegistration:
        """Register this instance with the cluster."""
        self._local_instance_id = instance_id
        self._local_capabilities = capabilities

        if self._redis and self._redis.client:
            try:
                data = {
                    "instance_id": instance_id,
                    "capabilities": capabilities,
                    "last_heartbeat": datetime.now(timezone.utc).isoformat(),
                    "active_tasks": 0,
                    "healthy": True
                }
                await self._redis.client.set(
                    self._instance_key(instance_id),
                    data,
                    ex=self.heartbeat_ttl
                )

                cluster_state = await self.get_cluster_state()
                return InstanceRegistration(
                    accepted=True,
                    assigned_tasks=[],
                    cluster_state=cluster_state
                )
            except Exception as e:
                logger.warning(f"Instance registration failed: {e}")

        return InstanceRegistration(
            accepted=True,
            assigned_tasks=[],
            cluster_state={"standalone": True}
        )

    async def heartbeat(self):
        """Send a heartbeat to keep the instance registered."""
        if not self._local_instance_id:
            return
        if self._redis and self._redis.client:
            try:
                data = {
                    "instance_id": self._local_instance_id,
                    "capabilities": self._local_capabilities,
                    "last_heartbeat": datetime.now(timezone.utc).isoformat(),
                    "active_tasks": 0,
                    "healthy": True
                }
                await self._redis.client.set(
                    self._instance_key(self._local_instance_id),
                    data,
                    ex=self.heartbeat_ttl
                )
            except Exception as e:
                logger.warning(f"Heartbeat failed: {e}")

    async def get_cluster_state(self) -> Dict[str, Any]:
        """Get the current state of all registered instances."""
        instances: Dict[str, Any] = {}
        if self._redis and self._redis.client:
            try:
                async for key in self._redis.client.scan_iter(match="agentos:instance:*"):
                    data = await self._redis.client.get(key)
                    if data:
                        instance_id = key.replace("agentos:instance:", "")
                        instances[instance_id] = data
            except Exception as e:
                logger.warning(f"Cluster state read failed: {e}")

        return {
            "instances": instances,
            "instance_count": len(instances),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    async def assign_task(self, task_id: str, required_capabilities: List[str] = None) -> Optional[str]:
        """Assign a task to the least-loaded capable instance. Returns instance_id or None."""
        if not self._redis or not self._redis.client:
            return self._local_instance_id

        try:
            state = await self.get_cluster_state()
            candidates = []
            for instance_id, data in state.get("instances", {}).items():
                caps = data.get("capabilities", [])
                if required_capabilities and not all(c in caps for c in required_capabilities):
                    continue
                candidates.append((instance_id, data.get("active_tasks", 0)))

            if not candidates:
                return None

            # Pick least loaded
            candidates.sort(key=lambda x: x[1])
            return candidates[0][0]
        except Exception as e:
            logger.warning(f"Task assignment failed: {e}")
            return None

    async def acquire_task_lock(self, task_id: str, instance_id: str) -> bool:
        """Acquire a distributed lock for a task."""
        if not self._redis or not self._redis.client:
            return True

        try:
            key = self._cluster_lock_key(task_id)
            result = await self._redis.client.set(key, instance_id, nx=True, ex=300)
            return result is not None
        except Exception as e:
            logger.warning(f"Task lock acquisition failed: {e}")
            return True

    async def release_task_lock(self, task_id: str):
        """Release a distributed task lock."""
        if not self._redis or not self._redis.client:
            return

        try:
            await self._redis.client.delete(self._cluster_lock_key(task_id))
        except Exception as e:
            logger.warning(f"Task lock release failed: {e}")

    async def deregister_instance(self, instance_id: str):
        """Remove an instance from the cluster."""
        if self._redis and self._redis.client:
            try:
                await self._redis.client.delete(self._instance_key(instance_id))
            except Exception as e:
                logger.warning(f"Instance deregistration failed: {e}")


# Module-level singleton
scaling_coordinator = HorizontalScalingCoordinator(redis=redis_client)
