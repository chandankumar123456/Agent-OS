import hashlib
import json
from typing import Optional, Dict, Any
from ..memory.short_term import redis_client
from ..logs.logger import logger


class CacheOptimizer:
    """Caches tool results and LLM responses to reduce redundant calls.

    Uses Redis for distributed caching with TTL-based invalidation.
    Keys are SHA-256 hashes of the tool name + normalized arguments.
    """

    def __init__(self, default_ttl: int = 3600, redis=None):
        self.default_ttl = default_ttl
        self._redis = redis
        self._local_cache: Dict[str, Any] = {}
        self._hits = 0
        self._misses = 0

    def _cache_key(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Generate a deterministic cache key."""
        normalized = json.dumps(arguments, sort_keys=True, default=str)
        raw = f"{tool_name}:{normalized}"
        return f"agentos:cache:{hashlib.sha256(raw.encode()).hexdigest()}"

    def _llm_cache_key(self, messages: list, provider: str, model: str) -> str:
        """Generate a cache key for LLM responses."""
        normalized = json.dumps(messages, sort_keys=True, default=str)
        raw = f"llm:{provider}:{model}:{normalized}"
        return f"agentos:cache:{hashlib.sha256(raw.encode()).hexdigest()}"

    async def get_tool_result(self, tool_name: str, arguments: Dict[str, Any]) -> Optional[Any]:
        """Retrieve a cached tool result if available."""
        key = self._cache_key(tool_name, arguments)

        # Check local cache first
        if key in self._local_cache:
            self._hits += 1
            return self._local_cache[key]

        # Check Redis if available
        if self._redis and self._redis.client:
            try:
                data = await self._redis.client.get(key)
                if data:
                    self._hits += 1
                    result = json.loads(data)
                    self._local_cache[key] = result
                    return result
            except Exception as e:
                logger.warning(f"Cache read error for {tool_name}: {e}")

        self._misses += 1
        return None

    async def set_tool_result(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        result: Any,
        ttl: Optional[int] = None
    ) -> bool:
        """Cache a tool result."""
        key = self._cache_key(tool_name, arguments)
        self._local_cache[key] = result

        if self._redis and self._redis.client:
            try:
                serialized = json.dumps(result, default=str)
                await self._redis.client.set(key, serialized, ex=(ttl or self.default_ttl))
                return True
            except Exception as e:
                logger.warning(f"Cache write error for {tool_name}: {e}")
        return False

    async def get_llm_result(self, messages: list, provider: str, model: str) -> Optional[Any]:
        """Retrieve a cached LLM response if available."""
        key = self._llm_cache_key(messages, provider, model)

        if key in self._local_cache:
            self._hits += 1
            return self._local_cache[key]

        if self._redis and self._redis.client:
            try:
                data = await self._redis.client.get(key)
                if data:
                    self._hits += 1
                    result = json.loads(data)
                    self._local_cache[key] = result
                    return result
            except Exception as e:
                logger.warning(f"LLM cache read error: {e}")

        self._misses += 1
        return None

    async def set_llm_result(
        self,
        messages: list,
        provider: str,
        model: str,
        result: Any,
        ttl: Optional[int] = None
    ) -> bool:
        """Cache an LLM response."""
        key = self._llm_cache_key(messages, provider, model)
        self._local_cache[key] = result

        if self._redis and self._redis.client:
            try:
                serialized = json.dumps(result, default=str)
                await self._redis.client.set(key, serialized, ex=(ttl or self.default_ttl))
                return True
            except Exception as e:
                logger.warning(f"LLM cache write error: {e}")
        return False

    async def invalidate_tool(self, tool_name: str) -> int:
        """Invalidate all cached entries for a tool."""
        count = 0
        pattern = "agentos:cache:*"

        # Clear local entries for this tool
        keys_to_remove = [k for k in self._local_cache if k.startswith("agentos:cache:")]
        for k in keys_to_remove:
            del self._local_cache[k]
            count += 1

        if self._redis and self._redis.client:
            try:
                async for key in self._redis.client.scan_iter(match="agentos:cache:*"):
                    await self._redis.client.delete(key)
                    count += 1
            except Exception as e:
                logger.warning(f"Cache invalidation error: {e}")

        return count

    def get_stats(self) -> Dict[str, Any]:
        """Return cache hit/miss statistics."""
        total = self._hits + self._misses
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self._hits / total if total > 0 else 0.0,
            "local_entries": len(self._local_cache),
        }

    def reset_stats(self):
        self._hits = 0
        self._misses = 0


# Module-level singleton
cache_optimizer = CacheOptimizer(redis=redis_client)
