import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.environments.browser_env import BrowserSession, BrowserSessionManager, DOMAIN_SELECTORS, browser_session_manager


@pytest.mark.asyncio
async def test_browser_session_launch():
    session = BrowserSession("task-1")
    mock_page = AsyncMock()
    mock_page.is_closed = MagicMock(return_value=False)
    mock_page.url = "https://example.com"
    mock_page.evaluate = AsyncMock(return_value=100)
    mock_page.bring_to_front = AsyncMock(return_value=None)
    mock_browser = AsyncMock()
    mock_browser.is_connected = MagicMock(return_value=True)
    mock_context = AsyncMock()
    mock_context.new_page = AsyncMock(return_value=mock_page)
    mock_browser.new_context = AsyncMock(return_value=mock_context)

    # Set up manager with mocked browser so launch() can bind
    browser_session_manager._browser = mock_browser

    result = await session.launch()
    assert result.success
    assert await session.is_alive()

    # Cleanup singleton
    await browser_session_manager.close_all()
    browser_session_manager._playwright = None
    browser_session_manager._browser = None
    browser_session_manager._sessions.clear()


def test_detect_domain_google():
    session = BrowserSession("t1")
    session._page = MagicMock()
    session._page.url = "https://www.google.com/search?q=test"
    assert session._detect_domain() == "google.com"


def test_detect_domain_youtube():
    session = BrowserSession("t1")
    session._page = MagicMock()
    session._page.url = "https://youtube.com/results?search_query=test"
    assert session._detect_domain() == "youtube.com"


def test_domain_selectors_coverage():
    assert "google.com" in DOMAIN_SELECTORS
    assert "youtube.com" in DOMAIN_SELECTORS
    assert "amazon.com" in DOMAIN_SELECTORS
    assert len(DOMAIN_SELECTORS["youtube.com"]) > 0


@pytest.mark.asyncio
async def test_browser_session_manager_reuse():
    mgr = BrowserSessionManager()
    # Patch _ensure_browser to avoid real playwright
    with patch.object(mgr, "_ensure_browser", new_callable=AsyncMock) as mock_ensure:
        mock_page = AsyncMock()
        mock_page.is_closed = MagicMock(return_value=False)
        mock_page.url = "https://example.com"
        mock_page.evaluate = AsyncMock(return_value=100)
        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_browser.is_connected = MagicMock(return_value=True)
        mgr._browser = mock_browser

        session1 = await mgr.get_or_create_session("task-a")
        # Simulate an alive page so the manager reuses the session
        session1._page = mock_page
        session2 = await mgr.get_or_create_session("task-a")
        assert session1 is session2
        mock_ensure.assert_awaited_once()


@pytest.mark.asyncio
async def test_browser_session_manager_persistent_browser():
    mgr = BrowserSessionManager()
    mock_page = AsyncMock()
    mock_page.is_closed = MagicMock(return_value=False)
    mock_page.url = "https://example.com"
    mock_page.evaluate = AsyncMock(return_value=100)
    mock_browser = AsyncMock()
    mock_browser.is_connected = MagicMock(return_value=True)
    mock_context = AsyncMock()
    mock_context.new_page = AsyncMock(return_value=mock_page)
    mock_browser.new_context = AsyncMock(return_value=mock_context)

    mock_pw = MagicMock()
    mock_pw.chromium = MagicMock(launch=AsyncMock(return_value=mock_browser))
    mock_pw.stop = AsyncMock()

    async_mock_pw = AsyncMock()
    async_mock_pw.start = AsyncMock(return_value=mock_pw)

    with patch("app.environments.browser_env.async_playwright", return_value=async_mock_pw):
        s1 = await mgr.get_or_create_session("task-a")
        assert s1._browser is not None
        s2 = await mgr.get_or_create_session("task-b")
        assert s2._browser is s1._browser
    await mgr.close_all()
