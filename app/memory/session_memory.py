from typing import Any, Dict, Optional

from .short_term import redis_client


class SessionMemory:
    prefix = "agentos:memory:session:"

    def _browser_key(self, task_id: str) -> str:
        return f"{self.prefix}{task_id}:browser"

    def _envs_key(self, task_id: str) -> str:
        return f"{self.prefix}{task_id}:envs"

    async def get_browser_session(self, task_id: str) -> Optional[Dict[str, Any]]:
        return await redis_client.get(self._browser_key(task_id))

    async def set_browser_session(
        self,
        task_id: str,
        data: Dict[str, Any],
        expire: int = 7200,
    ) -> bool:
        return await redis_client.set(self._browser_key(task_id), data, expire)

    async def get_active_envs(self, task_id: str) -> Optional[Dict[str, Any]]:
        return await redis_client.get(self._envs_key(task_id))

    async def set_active_envs(
        self,
        task_id: str,
        data: Dict[str, Any],
        expire: int = 7200,
    ) -> bool:
        return await redis_client.set(self._envs_key(task_id), data, expire)


session_memory = SessionMemory()
