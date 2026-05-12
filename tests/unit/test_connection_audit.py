"""Tests verifying the connection audit fixture blocks external DB connections in gRPC mode."""
import os
import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("AGENTOS_RUNTIME_MODE", "").lower() != "grpc",
    reason="Only relevant in gRPC mode",
)


@pytest.mark.asyncio
async def test_redis_connection_blocked():
    """redis.asyncio.Redis instantiation must raise in gRPC mode."""
    import redis.asyncio as redis_async

    with pytest.raises(RuntimeError, match="REDIS CONNECTION BLOCKED"):
        redis_async.Redis(host="localhost", port=6379)


@pytest.mark.asyncio
async def test_asyncpg_connection_blocked():
    """asyncpg.connect must raise in gRPC mode."""
    import asyncpg

    with pytest.raises(RuntimeError, match="ASYNCPG CONNECTION BLOCKED"):
        await asyncpg.connect("postgresql://user:pass@localhost/db")


def test_postgresql_engine_creation_blocked():
    """SQLAlchemy PostgreSQL engine creation must raise in gRPC mode."""
    from sqlalchemy.ext.asyncio import create_async_engine

    with pytest.raises(RuntimeError, match="POSTGRESQL ENGINE CREATION BLOCKED"):
        create_async_engine("postgresql+asyncpg://user:pass@localhost/db")


def test_sqlite_engine_creation_allowed():
    """SQLite engines must NOT be blocked."""
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    assert engine is not None
