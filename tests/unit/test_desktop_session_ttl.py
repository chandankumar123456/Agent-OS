"""Tests for DesktopSessionManager TTL enforcement and background reaper."""
import asyncio
import time as _time

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.environments.desktop_env import DesktopSessionManager


@pytest.fixture
def manager():
    """Create a DesktopSessionManager with a short TTL for testing."""
    return DesktopSessionManager(session_ttl_seconds=2)


@pytest.fixture(autouse=True)
def mock_desktop_session():
    """Mock DesktopSession so tests don't touch real desktop."""
    with patch(
        "core.environments.desktop_env.DesktopSession"
    ) as MockSession:
        instance = MagicMock()
        instance.close = AsyncMock(
            return_value=MagicMock(success=True, result={"message": "closed"})
        )
        MockSession.return_value = instance
        yield MockSession


@pytest.mark.asyncio
async def test_session_expires_after_ttl(manager):
    """A session older than TTL should be closed by close_expired_sessions."""
    session = await manager.get_or_create_session("task-expire")
    assert manager.get_session("task-expire") is not None

    # Simulate time passing beyond TTL by backdating both created_at and last_accessed
    manager._session_meta["task-expire"]["created_at"] = _time.time() - 3
    manager._session_meta["task-expire"]["last_accessed"] = _time.time() - 3

    closed = await manager.close_expired_sessions()
    assert closed == 1
    assert manager.get_session("task-expire") is None
    assert "task-expire" not in manager._session_meta


@pytest.mark.asyncio
async def test_close_expired_sessions_closes_old_sessions(manager):
    """close_expired_sessions should close sessions older than TTL."""
    await manager.get_or_create_session("task-reaper")
    assert manager.get_session("task-reaper") is not None

    # Backdate the session so it's already expired (both timestamps)
    manager._session_meta["task-reaper"]["created_at"] = _time.time() - 3
    manager._session_meta["task-reaper"]["last_accessed"] = _time.time() - 3

    # Wait for one cleanup cycle (TTL check interval is 60s by default,
    # but we can invoke the logic directly for a fast test)
    closed = await manager.close_expired_sessions()
    assert closed == 1
    assert manager.get_session("task-reaper") is None


@pytest.mark.asyncio
async def test_get_or_create_updates_last_accessed(manager):
    """Re-accessing an existing session should bump last_accessed."""
    await manager.get_or_create_session("task-access")
    original_last = manager._session_meta["task-access"]["last_accessed"]

    # Small delay to ensure timestamp differs
    await asyncio.sleep(0.05)

    await manager.get_or_create_session("task-access")
    updated_last = manager._session_meta["task-access"]["last_accessed"]

    assert updated_last > original_last
    # created_at should remain unchanged
    assert manager._session_meta["task-access"]["created_at"] == original_last
