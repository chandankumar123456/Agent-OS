import redis.asyncio as redis
from typing import Optional, Dict, Any
import json
from ..config.settings import settings
from ..logs.logger import logger

REDIS_URL = settings.REDIS_URL


class RedisClient:
    def __init__(self):
        self.client: Optional[redis.Redis] = None

    async def connect(self):
        if self.client is not None:
            try:
                await self.client.ping()
                logger.debug("Redis already connected")
                return
            except Exception:
                logger.warning("Existing Redis connection dead, reconnecting")
                await self.client.aclose()
                self.client = None
        if not REDIS_URL:
            raise RuntimeError("REDIS_URL is not configured")
        self.client = redis.from_url(
            REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            max_connections=50,
            socket_connect_timeout=10,
            socket_timeout=30,
            health_check_interval=30,
        )
        await self.client.ping()
        logger.info("Redis connected")

    async def disconnect(self):
        if self.client:
            await self.client.aclose()
            self.client = None
            logger.info("Redis disconnected")

    async def set(
        self,
        key: str,
        value: Dict[str, Any],
        expire: Optional[int] = 3600
    ) -> bool:
        if not self.client:
            raise RuntimeError("Redis client is unavailable")

        try:
            serialized = json.dumps(value)
            await self.client.set(key, serialized, ex=expire)
            return True
        except Exception as e:
            logger.error(f"Redis set error: {e}")
            raise

    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        if not self.client:
            raise RuntimeError("Redis client is unavailable")

        try:
            value = await self.client.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.error(f"Redis get error: {e}")
            raise

    async def delete(self, key: str) -> bool:
        if not self.client:
            raise RuntimeError("Redis client is unavailable")

        try:
            await self.client.delete(key)
            return True
        except Exception as e:
            logger.error(f"Redis delete error: {e}")
            raise

    async def exists(self, key: str) -> bool:
        if not self.client:
            raise RuntimeError("Redis client is unavailable")

        try:
            return await self.client.exists(key) > 0
        except Exception as e:
            logger.error(f"Redis exists error: {e}")
            raise


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
