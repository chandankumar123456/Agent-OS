from typing import Any, Dict, Optional

from .short_term import redis_client


def _is_grpc_mode() -> bool:
    """Check if running in gRPC mode without importing runtime.mode (avoids circular deps)."""
    from ..config.settings import settings
    mode = settings.RUNTIME_MODE or "http"
    return mode.lower() == "grpc"


class SessionMemory:
    prefix = "agentos:memory:session:"

    def __init__(self):
        # In gRPC mode, delegate to in-memory store
        if _is_grpc_mode():
            from .in_memory import InMemorySessionStore
            self._backend = InMemorySessionStore()
        else:
            self._backend = None

    def _browser_key(self, task_id: str) -> str:
        return f"{self.prefix}{task_id}:browser"

    def _envs_key(self, task_id: str) -> str:
        return f"{self.prefix}{task_id}:envs"

    async def get_browser_session(self, task_id: str) -> Optional[Dict[str, Any]]:
        if self._backend:
            return await self._backend.get_browser_session(task_id)
        return await redis_client.get(self._browser_key(task_id))

    async def set_browser_session(
        self,
        task_id: str,
        data: Dict[str, Any],
        expire: int = 7200,
    ) -> bool:
        if self._backend:
            return await self._backend.set_browser_session(task_id, data, expire)
        return await redis_client.set(self._browser_key(task_id), data, expire)

    async def get_active_envs(self, task_id: str) -> Optional[Dict[str, Any]]:
        if self._backend:
            return await self._backend.get_active_envs(task_id)
        return await redis_client.get(self._envs_key(task_id))

    async def set_active_envs(
        self,
        task_id: str,
        data: Dict[str, Any],
        expire: int = 7200,
    ) -> bool:
        if self._backend:
            return await self._backend.set_active_envs(task_id, data, expire)
        return await redis_client.set(self._envs_key(task_id), data, expire)


session_memory = SessionMemory()
