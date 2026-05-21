"""Memory leak detection for DesktopSessionManager across repeated task sessions.

Uses tracemalloc to measure memory growth after creating and closing
desktop sessions, ensuring no significant memory is retained.
"""
import pytest
import tracemalloc

from core.environments.desktop_env import DesktopSessionManager


@pytest.mark.asyncio
async def test_memory_growth_per_task():
    """Run 10 desktop sessions and assert <2MB growth.

    Creates and closes 10 DesktopSession instances, measuring the
    memory delta via tracemalloc.  Growth should stay well under 2 MB
    if cleanup (nullifying references + gc.collect) is effective.
    """
    tracemalloc.start()
    manager = DesktopSessionManager(session_ttl_seconds=3600)
    before, _ = tracemalloc.get_traced_memory()

    for i in range(10):
        session = await manager.get_or_create_session(f"task-{i}")
        await manager.close_session(f"task-{i}")

    after, _ = tracemalloc.get_traced_memory()
    growth_mb = (after - before) / (1024 * 1024)
    tracemalloc.stop()
    assert growth_mb < 2.0, f"Memory grew by {growth_mb:.2f}MB across 10 tasks"
