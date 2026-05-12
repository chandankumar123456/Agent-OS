"""Test configuration with isolated database and async support."""
import os
import sys
from pathlib import Path

# Set test environment variables BEFORE any app imports
os.environ.setdefault("AGENTOS_ENV", "test")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "")
os.environ.setdefault("OPENAI_API_KEY", "test-key-placeholder")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-env-32chars!!")
os.environ.setdefault("RUNTIME_MODE", "http")
os.environ.setdefault("ENABLED_PROVIDERS", "openai")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


import pytest
from typing import AsyncGenerator


@pytest.fixture(scope="session")
def event_loop_policy():
    """Use default event loop policy for tests."""
    import asyncio
    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture(autouse=True)
def _test_env():
    """Ensure test environment variables are always set."""
    assert os.environ.get("DATABASE_URL") == "sqlite+aiosqlite:///:memory:"
    assert os.environ.get("SECRET_KEY", "").startswith("test-")
    yield


@pytest.fixture(autouse=True)
def block_external_connections_in_grpc_mode(monkeypatch):
    """Block Redis and PostgreSQL connections when running in gRPC/desktop mode."""
    runtime_mode = os.environ.get("AGENTOS_RUNTIME_MODE", "").lower()
    if runtime_mode != "grpc":
        yield
        return

    # Block redis.asyncio.Redis
    try:
        import redis.asyncio as redis_async

        original_redis_init = redis_async.Redis.__init__

        def blocked_redis_init(*args, **kwargs):
            import traceback
            raise RuntimeError(
                "REDIS CONNECTION BLOCKED IN GRPC MODE.\n"
                "Stack trace:\n" + "".join(traceback.format_stack())
            )

        monkeypatch.setattr(redis_async.Redis, "__init__", blocked_redis_init)
    except ImportError:
        pass

    # Block asyncpg.connect
    try:
        import asyncpg

        original_asyncpg_connect = asyncpg.connect

        async def blocked_asyncpg_connect(*args, **kwargs):
            import traceback
            raise RuntimeError(
                "ASYNCPG CONNECTION BLOCKED IN GRPC MODE.\n"
                "Stack trace:\n" + "".join(traceback.format_stack())
            )

        monkeypatch.setattr(asyncpg, "connect", blocked_asyncpg_connect)
    except ImportError:
        pass

    # Block sqlalchemy async engine creation for postgresql dialects
    try:
        from sqlalchemy.ext.asyncio import create_async_engine

        original_create_async_engine = create_async_engine

        def blocked_create_async_engine(url, **kwargs):
            url_str = str(url)
            if "postgresql" in url_str.lower() or "postgres" in url_str.lower():
                import traceback
                raise RuntimeError(
                    "POSTGRESQL ENGINE CREATION BLOCKED IN GRPC MODE.\n"
                    f"URL: {url_str}\n"
                    "Stack trace:\n" + "".join(traceback.format_stack())
                )
            return original_create_async_engine(url, **kwargs)

        monkeypatch.setattr(
            "sqlalchemy.ext.asyncio.create_async_engine",
            blocked_create_async_engine,
        )
    except ImportError:
        pass

    yield
