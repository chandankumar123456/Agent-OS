"""Unit tests for DesktopRecoveryPlanner positive recovery strategies."""
import pytest

from app.capabilities.recovery import (
    DesktopRecoveryAction,
    DesktopRecoveryPlanner,
    RecoveryAction,
)
from app.capabilities.models import RecoveryDecision


class TestDesktopRecoveryAction:
    """Verify the DesktopRecoveryAction enum has all expected members."""

    def test_enum_members_exist(self):
        assert DesktopRecoveryAction.REFOCUS is not None
        assert DesktopRecoveryAction.REBUILD_TREE is not None
        assert DesktopRecoveryAction.DISMISS_POPUP is not None
        assert DesktopRecoveryAction.VISION_ESCALATE is not None
        assert DesktopRecoveryAction.ESCALATE is not None

    def test_enum_values_are_distinct(self):
        values = {m.value for m in DesktopRecoveryAction}
        assert len(values) == 5, f"Expected 5 distinct values, got {len(values)}"


class TestDesktopRecoveryPlanner:
    """Verify the planner maps error patterns to correct recovery actions."""

    def setup_method(self):
        self.planner = DesktopRecoveryPlanner()

    def _assert_switch_tool(self, decision: RecoveryDecision, expected_tool: str):
        assert decision.action == RecoveryAction.SWITCH_TOOL, (
            f"Expected SWITCH_TOOL, got {decision.action.value}: {decision.reason}"
        )
        assert decision.next_tool == expected_tool, (
            f"Expected next_tool={expected_tool}, got {decision.next_tool}"
        )

    # ── error-pattern → action mapping ──────────────────────────────────

    def test_refocus_on_focus_errors(self):
        """Focus/foreground/hwnd errors → SWITCH_TOOL to ensure_focus."""
        for error in [
            "Window focus error: hwnd 12345 not found",
            "Application not in foreground",
            "Target window is not active",
            "Failed to focus: hwnd=0x0A1B2C",
        ]:
            decision = self.planner.plan(error=error, current_tool="desktop_env__click", task_id="task-1")
            self._assert_switch_tool(decision, "desktop_env__ensure_focus")

    def test_rebuild_tree_on_stale_elements(self):
        """Stale / element-not-found / tree-changed → SWITCH_TOOL to get_ui_tree."""
        for error in [
            "element not found: button id=42",
            "UI tree changed during operation",
            "stale element reference: list_item_7",
            "invalid element handle: id=0",
        ]:
            decision = self.planner.plan(error=error, current_tool="desktop__click_element", task_id="task-2")
            self._assert_switch_tool(decision, "desktop__get_ui_tree")

    def test_dismiss_popup_on_dialog_errors(self):
        """Popup/dialog/modal/blocking → SWITCH_TOOL to press_key(esc)."""
        for error in [
            "A popup is blocking interaction",
            "Modal dialog detected",
            "Blocking dialog window appeared",
            "Popup window prevents click",
        ]:
            decision = self.planner.plan(error=error, current_tool="desktop_env__click", task_id="task-3")
            self._assert_switch_tool(decision, "desktop_env__press_key")

    def test_vision_escalate_on_coordinate_failures(self):
        """Pyautogui/coordinate/click-failed/type-failed/vision → SWITCH_TOOL to screenshot."""
        for error in [
            "pyautogui coordinate out of bounds",
            "click failed at coordinates (500, 300)",
            "type failed: target lost",
            "vision match confidence too low",
        ]:
            decision = self.planner.plan(error=error, current_tool="desktop_env__type_text", task_id="task-4")
            self._assert_switch_tool(decision, "desktop_env__screenshot")

    def test_escalate_on_no_match(self):
        """Unrecognised errors → ESCALATE."""
        err = "some completely unknown error that has no desktop-specific pattern"
        decision = self.planner.plan(error=err, current_tool="desktop_env__click", task_id="task-5")
        assert decision.action == RecoveryAction.ESCALATE, (
            f"Expected ESCALATE for unknown error, got {decision.action.value}"
        )

    def test_escalate_on_empty_error(self):
        """Empty / None error → ESCALATE (no recovery possible)."""
        decision = self.planner.plan(error=None, current_tool="desktop_env__click", task_id="task-6")
        assert decision.action == RecoveryAction.ESCALATE, (
            f"Expected ESCALATE for None error, got {decision.action.value}"
        )

        decision2 = self.planner.plan(error="", current_tool="desktop_env__click", task_id="task-7")
        assert decision2.action == RecoveryAction.ESCALATE, (
            f"Expected ESCALATE for empty error, got {decision2.action.value}"
        )
