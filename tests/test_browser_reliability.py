"""Tests for browser automation reliability improvements."""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.environments.browser_env import BrowserSession, _retry, _is_transient_playwright_error
from playwright.async_api import TimeoutError as PlaywrightTimeoutError, Error as PlaywrightError


# ---------------------------------------------------------------------------
# _is_transient_playwright_error
# ---------------------------------------------------------------------------
def test_is_transient_timeout_error():
    assert _is_transient_playwright_error(PlaywrightTimeoutError("timeout")) is True


def test_is_transient_network_error():
    assert _is_transient_playwright_error(PlaywrightError("net::ERR_NETWORK_CHANGED")) is True


def test_is_transient_other_error():
    assert _is_transient_playwright_error(ValueError("boom")) is False


# ---------------------------------------------------------------------------
# _retry decorator
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_retry_succeeds_on_first_attempt():
    call_count = 0

    @_retry(max_retries=3, base_delay=0.1)
    async def flaky():
        nonlocal call_count
        call_count += 1
        return "ok"

    result = await flaky()
    assert result == "ok"
    assert call_count == 1


@pytest.mark.asyncio
async def test_retry_succeeds_after_transient_failures():
    call_count = 0

    @_retry(max_retries=3, base_delay=0.1)
    async def flaky():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise PlaywrightTimeoutError(f"timeout {call_count}")
        return "ok"

    result = await flaky()
    assert result == "ok"
    assert call_count == 3


@pytest.mark.asyncio
async def test_retry_exhausts_and_raises():
    call_count = 0

    @_retry(max_retries=2, base_delay=0.1)
    async def flaky():
        nonlocal call_count
        call_count += 1
        raise PlaywrightTimeoutError("always fails")

    with pytest.raises(PlaywrightTimeoutError):
        await flaky()
    assert call_count == 2


@pytest.mark.asyncio
async def test_retry_does_not_retry_non_transient():
    call_count = 0

    @_retry(max_retries=3, base_delay=0.1)
    async def flaky():
        nonlocal call_count
        call_count += 1
        raise ValueError("not transient")

    with pytest.raises(ValueError):
        await flaky()
    assert call_count == 1


# ---------------------------------------------------------------------------
# BrowserSession navigate fallback load states
# ---------------------------------------------------------------------------
@pytest.fixture
def mock_session():
    session = BrowserSession(task_id="test-task")
    session._browser = MagicMock()
    session._context = MagicMock()
    session._page = MagicMock()
    session._page.is_closed.return_value = False
    session._page.evaluate = AsyncMock(return_value=500)
    session._page.bring_to_front = AsyncMock(return_value=None)
    session._browser.is_connected.return_value = True
    return session


@pytest.mark.asyncio
async def test_navigate_fallback_load_states(mock_session):
    """networkidle -> domcontentloaded -> load fallback."""
    page = mock_session._page
    page.url = "https://example.com"
    page.title = AsyncMock(return_value="Example")

    side_effects = [
        PlaywrightTimeoutError("networkidle timeout"),  # first goto fails
        PlaywrightTimeoutError("domcontentloaded timeout"),  # second goto fails
        None,  # third goto succeeds
    ]
    page.goto = AsyncMock(side_effect=side_effects)

    result = await mock_session.navigate("https://example.com")

    assert result.success is True
    assert result.result["url"] == "https://example.com"
    assert result.result["title"] == "Example"
    assert page.goto.await_count == 3
    page.goto.assert_any_await("https://example.com", wait_until="networkidle", timeout=30000)
    page.goto.assert_any_await("https://example.com", wait_until="domcontentloaded", timeout=30000)
    page.goto.assert_any_await("https://example.com", wait_until="load", timeout=30000)


@pytest.mark.asyncio
async def test_navigate_succeeds_on_networkidle(mock_session):
    page = mock_session._page
    page.url = "https://example.com"
    page.title = AsyncMock(return_value="Example")
    page.goto = AsyncMock(return_value=None)

    result = await mock_session.navigate("https://example.com")

    assert result.success is True
    page.goto.assert_awaited_once_with("https://example.com", wait_until="networkidle", timeout=30000)


# ---------------------------------------------------------------------------
# click / type_text auto-wait visibility
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_click_waits_for_visibility(mock_session):
    page = mock_session._page
    page.wait_for_selector = AsyncMock(return_value=MagicMock())
    page.click = AsyncMock(return_value=None)
    page.url = "https://example.com"

    result = await mock_session.click("#btn")

    assert result.success is True
    page.wait_for_selector.assert_awaited_once_with("#btn", state="visible", timeout=10000)
    page.click.assert_awaited_once_with("#btn", timeout=10000)


@pytest.mark.asyncio
async def test_type_text_waits_for_visibility(mock_session):
    page = mock_session._page
    page.wait_for_selector = AsyncMock(return_value=MagicMock())
    page.fill = AsyncMock(return_value=None)

    result = await mock_session.type_text("#input", "hello")

    assert result.success is True
    page.wait_for_selector.assert_awaited_once_with("#input", state="visible", timeout=10000)
    page.fill.assert_awaited_once_with("#input", "hello")


# ---------------------------------------------------------------------------
# get_url / get_title
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_url(mock_session):
    mock_session._page.url = "https://example.com"
    result = await mock_session.get_url()
    assert result.success is True
    assert result.result["url"] == "https://example.com"


@pytest.mark.asyncio
async def test_get_title(mock_session):
    mock_session._page.title = AsyncMock(return_value="Hello World")
    result = await mock_session.get_title()
    assert result.success is True
    assert result.result["title"] == "Hello World"


# ---------------------------------------------------------------------------
# Session recovery when page closes
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_session_recovery_on_closed_page():
    session = BrowserSession(task_id="recovery-task")
    session._browser = MagicMock()
    session._context = MagicMock()
    session._page = MagicMock()

    # Page is closed but browser/context still alive
    session._page.is_closed.return_value = True
    session._browser.is_connected.return_value = True

    new_page = MagicMock()
    new_page.goto = AsyncMock(return_value=None)
    new_page.bring_to_front = AsyncMock(return_value=None)
    new_page.evaluate = AsyncMock(return_value=500)
    new_page.url = "https://prev.example.com"
    session._context.new_page = AsyncMock(return_value=new_page)

    session._current_url = "https://prev.example.com"

    page = await session._ensure_page()

    assert page is new_page
    session._context.new_page.assert_awaited_once()
    new_page.goto.assert_awaited_once_with("https://prev.example.com", wait_until="domcontentloaded")


@pytest.mark.asyncio
async def test_session_manager_reuses_connected_session():
    from core.environments.browser_env import BrowserSessionManager

    manager = BrowserSessionManager()
    session = BrowserSession(task_id="reuse")
    session._browser = MagicMock()
    session._page = MagicMock()
    session._page.is_closed.return_value = False
    session._page.evaluate = AsyncMock(return_value=500)
    session._browser.is_connected.return_value = True

    manager._sessions["reuse"] = session
    retrieved = await manager.get_or_create_session("reuse")
    assert retrieved is session


@pytest.mark.asyncio
async def test_session_manager_recreate_dead_session():
    from core.environments.browser_env import BrowserSessionManager

    manager = BrowserSessionManager()
    dead_session = BrowserSession(task_id="dead")
    dead_session._browser = MagicMock()
    dead_session._page = MagicMock()
    dead_session._page.is_closed.return_value = True
    dead_session.close_context_only = AsyncMock(return_value=None)

    manager._sessions["dead"] = dead_session

    with patch.object(manager, "_ensure_browser", new_callable=AsyncMock) as mock_ensure_browser:
        with patch.object(BrowserSession, "bind_to_browser", new_callable=AsyncMock) as mock_bind:
            new_session = await manager.get_or_create_session("dead")
            dead_session.close_context_only.assert_awaited_once()
            mock_ensure_browser.assert_awaited_once()
            mock_bind.assert_awaited_once()
            assert new_session is not dead_session
