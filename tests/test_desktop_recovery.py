"""FR6.1: Desktop recovery strategy tests — RecoveryStrategy.DESKTOP enum and tool alternatives."""
import pytest
from unittest.mock import patch
from core.capabilities.recovery import RecoveryEngine, RecoveryStrategy, RecoveryAction
from core.capabilities.models import ExecutionEnvironment


def test_recovery_strategy_has_desktop_enum():
    """FR6.1: RecoveryStrategy.DESKTOP must exist."""
    assert hasattr(RecoveryStrategy, "DESKTOP")
    assert RecoveryStrategy.DESKTOP.name == "DESKTOP"
    # Verify all expected enum members exist
    assert hasattr(RecoveryStrategy, "GENERIC")
    assert hasattr(RecoveryStrategy, "BROWSER")
    assert hasattr(RecoveryStrategy, "SHELL")


def test_tool_alternatives_no_browser_shell_for_desktop():
    """FR6.1: Desktop tools must not fallback to browser or shell."""
    engine = RecoveryEngine()
    for tool, alts in engine._tool_alternatives.items():
        if tool.startswith("desktop__") or tool.startswith("desktop_env__"):
            for alt in alts:
                assert not alt.startswith("browser__"), f"{tool} -> {alt} forbidden"
                assert not alt.startswith("shell__"), f"{tool} -> {alt} forbidden"


def test_tool_alternatives_desktop_to_desktop():
    """FR6.1: Desktop tool alternatives should map to other desktop tools."""
    engine = RecoveryEngine()
    desktop_tools = {t for t in engine._tool_alternatives if t.startswith(("desktop__", "desktop_env__"))}
    assert len(desktop_tools) > 0, "Expected at least one desktop tool with alternatives"
    for tool in desktop_tools:
        for alt in engine._tool_alternatives[tool]:
            assert alt.startswith(("desktop__", "desktop_env__")), (
                f"Desktop tool {tool} should have desktop alternatives, got {alt}"
            )


@patch("core.capabilities.recovery.redis_client")
class TestRecoveryStrategyDesktop:
    """FR6.1: RecoveryStrategy.DESKTOP affects recovery decisions."""

    @pytest.mark.asyncio
    async def test_decide_desktop_strategy_prevents_browser_environment_fallback(self, mock_rc):
        """With DESKTOP strategy, desktop environment failures should NOT fall back to browser."""
        mock_rc.client = None  # Force in-memory retry counting

        engine = RecoveryEngine(max_retries=3)
        decision = await engine.decide(
            task_id="task-ds1",
            step_id="step-1",
            error="pyautogui_fail: could not locate element",
            current_environment=ExecutionEnvironment.DESKTOP,
            recovery_strategy=RecoveryStrategy.DESKTOP,
        )
        # Should NOT be SWITCH_ENVIRONMENT to browser
        if decision.action == "switch_environment":
            assert decision.next_environment != ExecutionEnvironment.BROWSER_UI, (
                "DESKTOP strategy must not fall back to BROWSER_UI"
            )

    @pytest.mark.asyncio
    async def test_decide_desktop_strategy_prevents_shell_environment_fallback(self, mock_rc):
        """With DESKTOP strategy, desktop environment failures should NOT fall back to shell."""
        mock_rc.client = None

        engine = RecoveryEngine(max_retries=3)
        decision = await engine.decide(
            task_id="task-ds2",
            step_id="step-1",
            error="display_not_found: cannot access display",
            current_environment=ExecutionEnvironment.DESKTOP,
            recovery_strategy=RecoveryStrategy.DESKTOP,
        )
        # Should NOT be SWITCH_ENVIRONMENT to shell
        if decision.action == "switch_environment":
            assert decision.next_environment != ExecutionEnvironment.SHELL, (
                "DESKTOP strategy must not fall back to SHELL"
            )
            assert decision.next_environment != ExecutionEnvironment.CLOUD_API, (
                "DESKTOP strategy must not fall back to CLOUD_API"
            )

    @pytest.mark.asyncio
    async def test_decide_desktop_strategy_tries_tool_alternative(self, mock_rc):
        """With DESKTOP strategy, try a desktop tool alternative before escalating."""
        mock_rc.client = None

        engine = RecoveryEngine(max_retries=3)
        decision = await engine.decide(
            task_id="task-ds3",
            step_id="step-1",
            error="desktop screenshot failed",
            current_tool="desktop__screenshot",
            current_environment=ExecutionEnvironment.DESKTOP,
            recovery_strategy=RecoveryStrategy.DESKTOP,
        )
        # Should try switching to another desktop tool, not browser
        if decision.action == "switch_tool":
            assert decision.next_tool.startswith(("desktop__", "desktop_env__")), (
                f"DESKTOP strategy tool alternative should be a desktop tool, got {decision.next_tool}"
            )


class TestRecoveryStrategyExecute:
    """FR6.1: execute() method handles RecoveryStrategy.DESKTOP."""

    def test_execute_exists(self):
        """execute() method must exist on RecoveryEngine."""
        engine = RecoveryEngine()
        assert hasattr(engine, "execute")
        assert callable(engine.execute)

    @pytest.mark.asyncio
    async def test_execute_desktop_strategy_rejects_browser_env_switch(self):
        """execute() with DESKTOP strategy must reject SWITCH_ENVIRONMENT to browser."""
        from core.capabilities.models import RecoveryDecision

        engine = RecoveryEngine()
        decision = RecoveryDecision(
            task_id="task-ex1",
            step_id="step-1",
            action=RecoveryAction.SWITCH_ENVIRONMENT,
            reason="Desktop failed, fall back to browser",
            next_environment=ExecutionEnvironment.BROWSER_UI,
        )
        result = await engine.execute(decision, recovery_strategy=RecoveryStrategy.DESKTOP)
        # The execute should modify the decision for DESKTOP strategy
        # It should either escalate or keep retrying with desktop tools
        assert result.action != "switch_environment" or result.next_environment != ExecutionEnvironment.BROWSER_UI, (
            "DESKTOP strategy must not allow switching to browser environment"
        )

    @pytest.mark.asyncio
    async def test_execute_desktop_strategy_rejects_non_desktop_tool_switch(self):
        """execute() with DESKTOP strategy must reject SWITCH_TOOL to non-desktop tool."""
        from core.capabilities.models import RecoveryDecision

        engine = RecoveryEngine()
        decision = RecoveryDecision(
            task_id="task-ex2",
            step_id="step-1",
            action=RecoveryAction.SWITCH_TOOL,
            reason="Desktop tool failed, try browser",
            next_tool="browser__screenshot",
        )
        result = await engine.execute(decision, recovery_strategy=RecoveryStrategy.DESKTOP)
        # The execute should modify the decision for DESKTOP strategy
        if result.action == "switch_tool":
            assert result.next_tool is None or result.next_tool.startswith(("desktop__", "desktop_env__")), (
                f"DESKTOP strategy must not allow switching to non-desktop tool: {result.next_tool}"
            )

    @pytest.mark.asyncio
    async def test_execute_passes_through_non_desktop_strategy(self):
        """execute() without DESKTOP strategy should pass decisions through unchanged."""
        from core.capabilities.models import RecoveryDecision

        engine = RecoveryEngine()
        decision = RecoveryDecision(
            task_id="task-ex3",
            step_id="step-1",
            action=RecoveryAction.RETRY,
            reason="Transient error",
        )
        result = await engine.execute(decision, recovery_strategy=RecoveryStrategy.GENERIC)
        assert result.action == RecoveryAction.RETRY
        assert result.reason == "Transient error"
