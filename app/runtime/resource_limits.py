import asyncio
from typing import Dict, Any, Optional
from dataclasses import dataclass
from ..logs.logger import logger
from ..runtime.pool import AgentPool
from ..memory.short_term import redis_client


@dataclass
class ResourceGrant:
    granted: bool
    available: int
    wait_time: float
    reason: str


class ResourceLimitEnforcer:
    """Enforces resource limits: max concurrent agents, DB connections, Redis connections, memory.

    Uses Redis for cross-process coordination when available, falling back to
    in-memory tracking for single-node deployments.
    """

    def __init__(
        self,
        max_concurrent_agents: int = 100,
        max_db_connections: int = 60,
        max_redis_connections: int = 50,
        max_memory_mb: int = 4096,
        redis=None
    ):
        self.max_concurrent_agents = max_concurrent_agents
        self.max_db_connections = max_db_connections
        self.max_redis_connections = max_redis_connections
        self.max_memory_mb = max_memory_mb
        self._redis = redis

        self._local_agents = 0
        self._local_db = 0
        self._local_redis = 0
        self._lock = asyncio.Lock()

    def _redis_key(self, resource_type: str) -> str:
        return f"agentos:resource:{resource_type}"

    async def _get_usage(self, resource_type: str) -> int:
        if self._redis and self._redis.client:
            try:
                val = await self._redis.client.get(self._redis_key(resource_type))
                return int(val) if val else 0
            except Exception:
                pass
        async with self._lock:
            if resource_type == "agent":
                return self._local_agents
            elif resource_type == "db":
                return self._local_db
            elif resource_type == "redis":
                return self._local_redis
            return 0

    async def _increment(self, resource_type: str, delta: int = 1):
        if self._redis and self._redis.client:
            try:
                key = self._redis_key(resource_type)
                await self._redis.client.incrby(key, delta)
                return
            except Exception:
                pass
        async with self._lock:
            if resource_type == "agent":
                self._local_agents += delta
            elif resource_type == "db":
                self._local_db += delta
            elif resource_type == "redis":
                self._local_redis += delta

    async def check_resource_availability(
        self,
        resource_type: str,
        requested: int = 1
    ) -> ResourceGrant:
        """Check if requested resources are available."""
        limits = {
            "agent": self.max_concurrent_agents,
            "db": self.max_db_connections,
            "redis": self.max_redis_connections,
        }

        if resource_type not in limits:
            return ResourceGrant(
                granted=False,
                available=0,
                wait_time=0.0,
                reason=f"Unknown resource type: {resource_type}"
            )

        current = await self._get_usage(resource_type)
        limit = limits[resource_type]
        available = max(0, limit - current)

        if available >= requested:
            return ResourceGrant(
                granted=True,
                available=available,
                wait_time=0.0,
                reason="Resources available"
            )

        estimated_wait = (requested - available) * 2.0
        return ResourceGrant(
            granted=False,
            available=available,
            wait_time=estimated_wait,
            reason=f"{resource_type} limit reached: {current}/{limit}"
        )

    async def acquire(self, resource_type: str, amount: int = 1) -> bool:
        """Acquire resources. Returns True on success."""
        grant = await self.check_resource_availability(resource_type, amount)
        if not grant.granted:
            logger.warning(f"Resource acquisition failed: {grant.reason}")
            return False
        await self._increment(resource_type, amount)
        return True

    async def release(self, resource_type: str, amount: int = 1):
        """Release previously acquired resources."""
        await self._increment(resource_type, -amount)

    async def get_usage_summary(self) -> Dict[str, Any]:
        """Get current resource usage across all types."""
        agents = await self._get_usage("agent")
        db = await self._get_usage("db")
        red = await self._get_usage("redis")

        return {
            "agents": {"used": agents, "limit": self.max_concurrent_agents, "available": max(0, self.max_concurrent_agents - agents)},
            "db_connections": {"used": db, "limit": self.max_db_connections, "available": max(0, self.max_db_connections - db)},
            "redis_connections": {"used": red, "limit": self.max_redis_connections, "available": max(0, self.max_redis_connections - red)},
            "memory_limit_mb": self.max_memory_mb,
        }


# Module-level singleton
resource_limit_enforcer = ResourceLimitEnforcer(redis=redis_client)
