import pytest
from unittest.mock import AsyncMock, patch
from app.capabilities.recovery import RecoveryEngine, RecoveryAction
from app.capabilities.models import ExecutionEnvironment


@pytest.fixture
def mock_redis():
    """Provide a mock Redis client for recovery tests."""
    client = AsyncMock()
    stored = {}

    async def _get(key):
        return stored.get(key)

    async def _incr(key):
        stored[key] = stored.get(key, 0) + 1
        return stored[key]

    async def _scan_iter(match):
        prefix = match.replace("*", "")
        for k in list(stored.keys()):
            if k.startswith(prefix):
                yield k

    client.get = AsyncMock(side_effect=_get)
    client.incr = AsyncMock(side_effect=_incr)
    client.expire = AsyncMock(return_value=True)
    client.scan_iter = _scan_iter
    client.delete = AsyncMock(return_value=0)
    with patch("app.capabilities.recovery.redis_client") as mock_rc:
        mock_rc.client = client
        yield client


@pytest.mark.asyncio
async def test_recovery_suggests_environment_fallback_for_desktop(mock_redis):
    engine = RecoveryEngine(max_retries=3)
    decision = await engine.decide(
        "task-d1",
        "step-1",
        error="pyautogui_fail: could not locate element",
        current_environment=ExecutionEnvironment.DESKTOP,
    )
    assert decision.action == RecoveryAction.SWITCH_ENVIRONMENT
    assert decision.next_environment == ExecutionEnvironment.BROWSER_UI
    assert "desktop environment failure" in decision.reason.lower()


@pytest.mark.asyncio
async def test_recovery_suggests_environment_fallback_for_browser(mock_redis):
    engine = RecoveryEngine(max_retries=3)
    decision = await engine.decide(
        "task-b1",
        "step-1",
        error="playwright_timeout while waiting for selector",
        current_environment=ExecutionEnvironment.BROWSER_UI,
    )
    assert decision.action == RecoveryAction.SWITCH_ENVIRONMENT
    assert decision.next_environment == ExecutionEnvironment.CLOUD_API
    assert "browser_ui environment failure" in decision.reason.lower()


@pytest.mark.asyncio
async def test_recovery_escalates_permission_denied_without_env(mock_redis):
    engine = RecoveryEngine(max_retries=3)
    # No current_environment provided → should escalate as before
    decision = await engine.decide(
        "task-p1",
        "step-1",
        error="permission_denied",
    )
    assert decision.action == RecoveryAction.ESCALATE
    assert "permission denied" in decision.reason.lower()


@pytest.mark.asyncio
async def test_recovery_environment_fallback_for_shell_permission(mock_redis):
    engine = RecoveryEngine(max_retries=3)
    decision = await engine.decide(
        "task-s1",
        "step-1",
        error="permission_denied",
        current_environment=ExecutionEnvironment.SHELL,
    )
    assert decision.action == RecoveryAction.SWITCH_ENVIRONMENT
    assert decision.next_environment == ExecutionEnvironment.LOCAL


@pytest.mark.asyncio
async def test_recovery_environment_fallback_for_cloud_api(mock_redis):
    engine = RecoveryEngine(max_retries=3)
    decision = await engine.decide(
        "task-c1",
        "step-1",
        error="network_unreachable to cloud endpoint",
        current_environment=ExecutionEnvironment.CLOUD_API,
    )
    assert decision.action == RecoveryAction.SWITCH_ENVIRONMENT
    assert decision.next_environment == ExecutionEnvironment.SHELL


@pytest.mark.asyncio
async def test_recovery_tool_alternative_browser_to_cloud(mock_redis):
    engine = RecoveryEngine(max_retries=3)
    decision = await engine.decide(
        "task-t1",
        "step-1",
        error="browser search returned 500",
        current_tool="browser__search",
    )
    assert decision.action == RecoveryAction.SWITCH_TOOL
    assert decision.next_tool == "cloud_api__search"


@pytest.mark.asyncio
async def test_recovery_tool_alternative_desktop_to_browser(mock_redis):
    engine = RecoveryEngine(max_retries=3)
    decision = await engine.decide(
        "task-t2",
        "step-1",
        error="desktop screenshot failed",
        current_tool="desktop__screenshot",
    )
    assert decision.action == RecoveryAction.SWITCH_TOOL
    assert decision.next_tool == "browser__screenshot"


@pytest.mark.asyncio
async def test_recovery_no_fallback_for_unknown_environment_error(mock_redis):
    engine = RecoveryEngine(max_retries=3)
    # Error does not match any environment-specific pattern
    decision = await engine.decide(
        "task-u1",
        "step-1",
        error="something weird happened",
        current_environment=ExecutionEnvironment.DESKTOP,
    )
    # Should default to retry since retries < max_retries
    assert decision.action == RecoveryAction.RETRY


@pytest.mark.asyncio
async def test_recovery_transient_pattern_includes_playwright_timeout(mock_redis):
    engine = RecoveryEngine(max_retries=3)
    decision = await engine.decide(
        "task-tr1",
        "step-1",
        error="playwright_timeout",
    )
    # Without environment, the transient pattern matches first
    assert decision.action == RecoveryAction.RETRY
    assert "Transient" in decision.reason
