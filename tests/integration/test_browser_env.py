import pytest
from app.environments.browser_env import BrowserSession


@pytest.mark.asyncio
async def test_browser_launch_idempotent():
    session = BrowserSession("test-task")
    out1 = await session.launch(headless=True)
    assert out1.success is True

    out2 = await session.launch(headless=True)
    assert out2.success is True
    assert "already" in out2.result.get("message", "").lower()

    await session.close()


@pytest.mark.asyncio
async def test_browser_navigate():
    session = BrowserSession("test-task")
    await session.launch(headless=True)
    result = await session.navigate("https://example.com")
    assert result.success is True
    assert "example.com" in result.result.get("url", "")
    await session.close()
