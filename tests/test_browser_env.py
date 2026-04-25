import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.environments.browser_env import BrowserEnvironment


@pytest.mark.asyncio
async def test_browser_launch():
    env = BrowserEnvironment()
    mock_page = AsyncMock()
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
        result = await env.launch(url="https://example.com")
        assert result.success
        assert "example.com" in result.result["message"]
