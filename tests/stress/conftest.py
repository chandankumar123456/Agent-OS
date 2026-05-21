"""Fixtures for stress tests."""
from __future__ import annotations

import logging

import httpx
import pytest
import pytest_asyncio

from core.auth.utils import create_access_token
from core.main import app
from .runner import StressTestRunner

logger = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def stress_test_token():
    """Generate a valid JWT for stress test authentication."""
    token = create_access_token({"sub": "stress-test-user", "role": "admin"})
    return token


@pytest_asyncio.fixture
async def stress_async_client():
    """Provide an async HTTP client wired directly to the FastAPI ASGI app.

    Function-scoped so each stress test gets a fresh app lifespan (and fresh DB/Redis connections).
    """
    from core.memory.long_term import db
    from core.memory.short_term import redis_client
    from core.memory.redis_pubsub import redis_pubsub_client
    from core.runtime.runtime import AgentRuntime

    try:
        await db.connect()
    except Exception as e:
        logger.error(f"Database connection failed in stress_async_client: {e}")
        raise

    try:
        from core.memory.long_term import user_repo
        existing = await user_repo.get_by_id("stress-test-user")
        if not existing:
            await user_repo.create(
                user_id="stress-test-user",
                email="stress@test.com",
                hashed_password="not-needed",
                name="Stress Test User",
                role="admin",
            )
    except Exception as e:
        logger.warning(f"Stress test user setup skipped or failed (may already exist): {e}")

    # Relax rate limits and task caps for stress testing
    from core.config.settings import settings
    settings.MAX_ACTIVE_TASKS_PER_USER = 1000
    settings.RATE_LIMIT_PER_MINUTE = 100000

    # Disable rate limiting entirely for stress tests by patching the check method
    import core.middleware.rate_limit as rl_module
    _orig_is_rate_limited = rl_module.RateLimitMiddleware._is_rate_limited
    async def _patched_is_rate_limited(self, client_id, limit):
        return False, 0, limit
    rl_module.RateLimitMiddleware._is_rate_limited = _patched_is_rate_limited

    # Clear any accumulated rate-limit state for the stress test user in Redis
    try:
        if redis_client.client:
            pattern = "agentos:ratelimit:user:stress-test-user:*"
            keys = []
            async for key in redis_client.client.scan_iter(match=pattern):
                keys.append(key)
            if keys:
                await redis_client.client.delete(*keys)
    except Exception as e:
        logger.warning(f"Failed to clear Redis rate limit keys: {e}")

    try:
        await redis_client.connect()
    except Exception as e:
        logger.error(f"Redis connection failed in stress_async_client: {e}")
        raise

    try:
        await redis_pubsub_client.connect()
    except Exception as e:
        logger.error(f"Redis PubSub connection failed in stress_async_client: {e}")
        raise

    runtime = AgentRuntime()
    try:
        await runtime.initialize()
    except Exception as e:
        logger.error(f"AgentRuntime initialization failed in stress_async_client: {e}")
        raise

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client

    try:
        await runtime.shutdown_all()
    except Exception as e:
        logger.error(f"AgentRuntime shutdown failed in stress_async_client: {e}")

    try:
        await redis_pubsub_client.disconnect()
    except Exception as e:
        logger.error(f"Redis PubSub disconnect failed in stress_async_client: {e}")

    try:
        await redis_client.disconnect()
    except Exception as e:
        logger.error(f"Redis disconnect failed in stress_async_client: {e}")

    try:
        await db.disconnect()
    except Exception as e:
        logger.error(f"Database disconnect failed in stress_async_client: {e}")

    # Restore original rate limiter
    rl_module.RateLimitMiddleware._is_rate_limited = _orig_is_rate_limited


@pytest.fixture
def stress_runner(stress_test_token, stress_async_client):
    """Provide a StressTestRunner pointing at the ASGI app."""
    return StressTestRunner(
        base_url="http://test", token=stress_test_token, client=stress_async_client
    )
