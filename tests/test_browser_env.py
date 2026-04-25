import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.environments.browser_env import BrowserSession, BrowserSessionManager, DOMAIN_SELECTORS


@pytest.mark.asyncio
async def test_browser_session_launch():
    session = BrowserSession("task-1")
    mock_page = AsyncMock()
    mock_page.is_closed = MagicMock(return_value=False)
    mock_browser = AsyncMock()
    mock_context = AsyncMock()
    mock_context.new_page = AsyncMock(return_value=mock_page)
    mock_browser.new_context = AsyncMock(return_value=mock_context)

    mock_pw = MagicMock()
    mock_pw.chromium = MagicMock(launch=AsyncMock(return_value=mock_browser))
    mock_pw.stop = AsyncMock()

    async_mock_pw = AsyncMock()
    async_mock_pw.start = AsyncMock(return_value=mock_pw)

    with patch("app.environments.browser_env.async_playwright", return_value=async_mock_pw):
        result = await session.launch()
        assert result.success
        assert session.is_alive()


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
    # Patch BrowserSession.launch to avoid real playwright
    with patch.object(BrowserSession, "launch", new_callable=AsyncMock) as mock_launch:
        mock_launch.return_value = MagicMock(success=True)
        session1 = await mgr.get_or_create_session("task-a")
        # Simulate an alive page so the manager reuses the session
        session1._page = MagicMock()
        session1._page.is_closed = MagicMock(return_value=False)
        session2 = await mgr.get_or_create_session("task-a")
        assert session1 is session2
        mock_launch.assert_awaited_once()
