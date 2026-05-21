from typing import Any, Dict, Optional

from .short_term import redis_client


class TaskMemory:
    prefix = "agentos:memory:task:"

    def _key(self, task_id: str) -> str:
        return f"{self.prefix}{task_id}"

    async def get(self, task_id: str) -> Optional[Dict[str, Any]]:
        return await redis_client.get(self._key(task_id))

    async def set(self, task_id: str, data: Dict[str, Any], expire: int = 3600) -> bool:
        return await redis_client.set(self._key(task_id), data, expire)

    async def update_progress(
        self,
        task_id: str,
        step_index: int,
        step_state: Dict[str, Any],
        expire: int = 3600,
    ) -> bool:
        key = self._key(task_id)
        data = await redis_client.get(key) or {}
        if "progress" not in data:
            data["progress"] = {}
        data["progress"][str(step_index)] = step_state
        return await redis_client.set(key, data, expire)

    async def clear(self, task_id: str) -> bool:
        return await redis_client.delete(self._key(task_id))


task_memory = TaskMemory()
