import redis.asyncio as redis
from typing import Optional, Dict, Any
import json
from ..config.settings import settings
from ..logs.logger import logger

REDIS_URL = settings.REDIS_URL or "redis://localhost:6379/0"


class RedisClient:
    def __init__(self):
        self.client: Optional[redis.Redis] = None
    
    async def connect(self):
        try:
            self.client = redis.from_url(
                REDIS_URL,
                encoding="utf-8",
                decode_responses=True
            )
            await self.client.ping()
            logger.info("Redis connected")
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}. Using mock mode.")
            self.client = None
    
    async def disconnect(self):
        if self.client:
            await self.client.close()
            logger.info("Redis disconnected")
    
    async def set(
        self,
        key: str,
        value: Dict[str, Any],
        expire: Optional[int] = 3600
    ) -> bool:
        if not self.client:
            return True
        
        try:
            serialized = json.dumps(value)
            await self.client.set(key, serialized, ex=expire)
            return True
        except Exception as e:
            logger.error(f"Redis set error: {e}")
            return False
    
    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        if not self.client:
            return None
        
        try:
            value = await self.client.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.error(f"Redis get error: {e}")
            return None
    
    async def delete(self, key: str) -> bool:
        if not self.client:
            return True
        
        try:
            await self.client.delete(key)
            return True
        except Exception as e:
            logger.error(f"Redis delete error: {e}")
            return False
    
    async def exists(self, key: str) -> bool:
        if not self.client:
            return False
        
        try:
            return await self.client.exists(key) > 0
        except Exception as e:
            logger.error(f"Redis exists error: {e}")
            return False


redis_client = RedisClient()


class ShortTermMemory:
    def __init__(self):
        self.prefix = "agentos:context:"
    
    async def save_context(
        self,
        task_id: str,
        context: Dict[str, Any],
        expire: int = 3600
    ) -> bool:
        key = f"{self.prefix}{task_id}"
        return await redis_client.set(key, context, expire)
    
    async def get_context(self, task_id: str) -> Optional[Dict[str, Any]]:
        key = f"{self.prefix}{task_id}"
        return await redis_client.get(key)
    
    async def delete_context(self, task_id: str) -> bool:
        key = f"{self.prefix}{task_id}"
        return await redis_client.delete(key)


short_term_memory = ShortTermMemory()