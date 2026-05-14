import redis.asyncio as redis
from typing import Optional, Dict, Any
import json
from ..config.settings import settings
from ..logs.logger import logger


def _is_grpc_mode() -> bool:
    """Check if running in gRPC mode without importing runtime.mode (avoids circular deps)."""
    mode = settings.RUNTIME_MODE or "http"
    return mode.lower() == "grpc"


REDIS_URL = settings.REDIS_URL


class RedisClient:
    def __init__(self):
        self.client: Optional[redis.Redis] = None

    async def connect(self):
        # In gRPC mode, skip Redis entirely — in-memory fallbacks are used
        if _is_grpc_mode():
            logger.debug("Skipping Redis connect in gRPC mode (using in-memory fallbacks)")
            return

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
        if _is_grpc_mode():
            return
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
        # gRPC mode: silently skip Redis operations (in-memory fallbacks are primary)
        if _is_grpc_mode() or not self.client:
            logger.debug(f"Redis set skipped (gRPC/unavailable): {key}")
            return False

        try:
            serialized = json.dumps(value)
            await self.client.set(key, serialized, ex=expire)
            return True
        except Exception as e:
            logger.error(f"Redis set error: {e}")
            raise

    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        # gRPC mode: silently skip Redis operations (in-memory fallbacks are primary)
        if _is_grpc_mode() or not self.client:
            logger.debug(f"Redis get skipped (gRPC/unavailable): {key}")
            return None

        try:
            value = await self.client.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.error(f"Redis get error: {e}")
            raise

    async def delete(self, key: str) -> bool:
        # gRPC mode: silently skip Redis operations (in-memory fallbacks are primary)
        if _is_grpc_mode() or not self.client:
            logger.debug(f"Redis delete skipped (gRPC/unavailable): {key}")
            return False

        try:
            await self.client.delete(key)
            return True
        except Exception as e:
            logger.error(f"Redis delete error: {e}")
            raise

    async def exists(self, key: str) -> bool:
        # gRPC mode: silently skip Redis operations (in-memory fallbacks are primary)
        if _is_grpc_mode() or not self.client:
            logger.debug(f"Redis exists skipped (gRPC/unavailable): {key}")
            return False

        try:
            return await self.client.exists(key) > 0
        except Exception as e:
            logger.error(f"Redis exists error: {e}")
            raise


redis_client = RedisClient()


class ShortTermMemory:
    def __init__(self):
        self.prefix = "agentos:context:"
        # In gRPC mode, delegate to in-memory store
        if _is_grpc_mode():
            from .in_memory import InMemoryShortTermMemory
            self._backend = InMemoryShortTermMemory()
            logger.info("ShortTermMemory using in-memory backend (gRPC mode)")
        else:
            self._backend = None

    async def save_context(
        self,
        task_id: str,
        context: Dict[str, Any],
        expire: int = 3600
    ) -> bool:
        if self._backend:
            return await self._backend.save_context(task_id, context, expire)
        key = f"{self.prefix}{task_id}"
        return await redis_client.set(key, context, expire)

    async def get_context(self, task_id: str) -> Optional[Dict[str, Any]]:
        if self._backend:
            return await self._backend.get_context(task_id)
        key = f"{self.prefix}{task_id}"
        return await redis_client.get(key)

    async def delete_context(self, task_id: str) -> bool:
        if self._backend:
            return await self._backend.delete_context(task_id)
        key = f"{self.prefix}{task_id}"
        return await redis_client.delete(key)


short_term_memory = ShortTermMemory()
