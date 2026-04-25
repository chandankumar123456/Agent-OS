"""Dedicated Redis client for Pub/Sub operations to avoid connection pool exhaustion.

The main `redis_client` (in `short_term.py`) uses a connection pool optimized for
key-value operations.  Pub/Sub connections are long-lived and blocking; sharing the
same pool causes starvation under load.  This module provides a completely isolated
Redis instance with its own connection pool.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import AsyncIterator, Optional

import redis.asyncio as redis

from ..config.settings import settings
from ..logs.logger import logger

REDIS_URL = settings.REDIS_URL


class RedisPubSubClient:
    """Redis client exclusively for pub/sub. Uses its own connection pool."""

    def __init__(self) -> None:
        self._client: Optional[redis.Redis] = None
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        async with self._lock:
            if self._client is not None:
                try:
                    await self._client.ping()
                    logger.debug("PubSub Redis already connected")
                    return
                except Exception:
                    logger.warning("PubSub Redis connection dead, reconnecting")
                    await self._client.close()
                    self._client = None

            if not REDIS_URL:
                raise RuntimeError("REDIS_URL is not configured")

            # Dedicated pool: high max_connections, keepalive enabled.
            # No socket_timeout here because `listen()` is intentionally blocking.
            self._client = redis.from_url(
                REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
                max_connections=200,
                socket_connect_timeout=10,
                socket_keepalive=True,
                health_check_interval=30,
            )
            await self._client.ping()
            logger.info("Redis PubSub client connected (dedicated pool)")

    async def disconnect(self) -> None:
        async with self._lock:
            if self._client:
                try:
                    await self._client.aclose()
                except Exception:
                    pass
                self._client = None
                logger.info("Redis PubSub client disconnected")

    def get_client(self) -> redis.Redis:
        if not self._client:
            raise RuntimeError("PubSub client is not connected")
        return self._client

    async def publish(self, channel: str, message: str) -> None:
        """Publish a message to a Redis channel."""
        client = self.get_client()
        await client.publish(channel, message)

    async def subscribe(self, channel: str) -> AsyncIterator[str]:
        """Yield string messages from a Redis channel with graceful cleanup."""
        client = self.get_client()
        pubsub: Optional[redis.client.PubSub] = None
        try:
            pubsub = client.pubsub()
            await pubsub.subscribe(channel)
            logger.info(f"Subscribed to Redis channel: {channel}")
            async for message in pubsub.listen():
                if message["type"] == "message":
                    data = message.get("data")
                    if isinstance(data, str):
                        yield data
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"PubSub listen error on {channel}: {e}")
            raise
        finally:
            if pubsub is not None:
                try:
                    await pubsub.unsubscribe(channel)
                except Exception:
                    pass
                try:
                    await pubsub.aclose()
                except Exception:
                    pass


# Module-level singleton
redis_pubsub_client = RedisPubSubClient()
