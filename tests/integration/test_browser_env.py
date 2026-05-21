import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from core.environments.browser_env import BrowserSession, browser_session_manager


@pytest.mark.asyncio
async def test_browser_session_manager_lifecycle():
    """Integration-style test using mocked browser to verify manager lifecycle."""
    with patch.object(browser_session_manager, "_ensure_browser", new_callable=AsyncMock):
        with patch.object(BrowserSession, "bind_to_browser", new_callable=AsyncMock) as mock_bind:
            # Create session
            session = await browser_session_manager.get_or_create_session("test-task")
            assert session is not None
            mock_bind.assert_awaited_once()

            # Set up mock page so is_alive() passes
            session._page = MagicMock()
            session._page.is_closed.return_value = False
            session._page.evaluate = AsyncMock(return_value=500)
            session._page.bring_to_front = AsyncMock(return_value=None)
            session._browser = MagicMock()
            session._browser.is_connected.return_value = True

            # Reuse same session
            session2 = await browser_session_manager.get_or_create_session("test-task")
            assert session2 is session

            # Close session
            result = await browser_session_manager.close_session("test-task")
            assert result.success is True

            # Verify removed from manager
            assert browser_session_manager.get_session("test-task") is None


@pytest.mark.asyncio
async def test_browser_navigate_with_mock_page():
    """Verify navigate works when page is properly mocked."""
    session = BrowserSession("test-task")
    session._browser = MagicMock()
    session._context = MagicMock()
    session._page = MagicMock()
    session._page.is_closed.return_value = False
    session._page.evaluate = AsyncMock(return_value=500)
    session._page.bring_to_front = AsyncMock(return_value=None)
    session._page.goto = AsyncMock(return_value=None)
    session._page.url = "https://example.com"
    session._page.title = AsyncMock(return_value="Example Domain")
    session._browser.is_connected.return_value = True

    result = await session.navigate("https://example.com")
    assert result.success is True
    assert "example.com" in result.result.get("url", "")
    assert result.visibility.get("type") == "browser_navigated"
