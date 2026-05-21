from typing import Any, Dict, Optional

from .short_term import redis_client
from .long_term import config_repo


class UserMemory:
    prefix = "agentos:memory:user:"

    def _prefs_key(self, user_id: str) -> str:
        return f"{self.prefix}{user_id}:prefs"

    async def get_preferences(self, user_id: str) -> Optional[Dict[str, Any]]:
        cached = await redis_client.get(self._prefs_key(user_id))
        if cached is not None:
            return cached
        db_val = await config_repo.get(f"user_prefs_{user_id}")
        if db_val is not None:
            await redis_client.set(self._prefs_key(user_id), db_val, expire=3600)
            return db_val
        return None

    async def set_preference(self, user_id: str, key: str, value: Any) -> bool:
        prefs = await self.get_preferences(user_id) or {}
        prefs[key] = value
        await config_repo.upsert(f"user_prefs_{user_id}", prefs)
        await redis_client.set(self._prefs_key(user_id), prefs, expire=3600)
        return True


user_memory = UserMemory()
