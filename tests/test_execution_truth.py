"""Test canonical execution state propagation across layers.

Validates the systemic fix: tool success must become canonical truth
that prevents re-verification, recovery, and fallback loops.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.execution_state import (
    ExecutionState,
    ToolExecutionRecord,
    StepExecutionRecord,
    ExecutionVerdict,
)
from app.langgraph.nodes import verifier_node
from app.capabilities.recovery import RecoveryEngine, RecoveryAction


class TestCanonicalExecutionState:
    """Tests for unified execution state schema."""

    def test_tool_record_from_open_application_success(self):
        """Terminal success detected for open_application with PID."""
        record = ToolExecutionRecord.from_tool_result(
            "desktop_env__open_application",
            {
                "success": True,
                "data": {
                    "pid": 1234,
                    "window": "Untitled - Notepad",
                    "process_path": "C:\\Windows\\notepad.exe",
                    "method": "shell",
                },
                "error": None,
            },
        )
        assert record.terminal is True
        assert record.success is True
        assert record.evidence["pid"] == 1234
        assert record.evidence["window"] == "Untitled - Notepad"

    def test_tool_record_from_open_application_no_pid(self):
        """Non-terminal when no PID/window evidence."""
        record = ToolExecutionRecord.from_tool_result(
            "desktop_env__open_application",
            {
                "success": True,
                "data": {"method": "shell"},
                "error": None,
            },
        )
        assert record.terminal is False
        assert record.success is True

    def test_tool_record_from_filesystem_write(self):
        """Terminal success for filesystem write with path."""
        record = ToolExecutionRecord.from_tool_result(
            "filesystem__write_file",
            {
                "success": True,
                "data": {"path": "/tmp/test.txt", "bytes_written": 100},
                "error": None,
            },
        )
        assert record.terminal is True
        assert record.evidence["path"] == "/tmp/test.txt"

    def test_tool_record_from_browser_navigate(self):
        """Terminal success for browser navigate with URL."""
        record = ToolExecutionRecord.from_tool_result(
            "browser_env__navigate",
            {
                "success": True,
                "data": {"url": "https://example.com", "title": "Example"},
                "error": None,
            },
        )
        assert record.terminal is True
        assert record.evidence["url"] == "https://example.com"

    def test_execution_state_record_tool_updates_verdict(self):
        """Recording a terminal success tool updates step verdict."""
        state = ExecutionState(task_id="test-task")
        tool_record = ToolExecutionRecord.from_tool_result(
            "desktop_env__open_application",
            {
                "success": True,
                "data": {"pid": 1234, "window": "Notepad"},
                "error": None,
            },
        )
        state.record_tool(1, "Open Notepad", tool_record)

        step = state.get_step(1)
        assert step.verdict == ExecutionVerdict.TERMINAL
        assert step.has_terminal_success is True
        assert "Terminal success" in step.notes

    def test_execution_state_serialization_roundtrip(self):
        """ExecutionState serializes and deserializes correctly."""
        state = ExecutionState(task_id="test-task")
        state.record_tool(
            1,
            "Open Notepad",
            ToolExecutionRecord.from_tool_result(
                "desktop_env__open_application",
                {
                    "success": True,
                    "data": {"pid": 1234},
                    "error": None,
                },
            ),
        )

        data = state.to_dict()
        restored = ExecutionState.from_dict(data)

        assert restored.task_id == "test-task"
        assert restored.has_terminal_success(1) is True
        step = restored.get_step(1)
        assert step.verdict == ExecutionVerdict.TERMINAL


class TestVerifierRespectsExecutionState:
    """Tests that verifier_node skips re-verification on terminal success."""

    @pytest.mark.asyncio
    async def test_verifier_skips_on_terminal_success(self):
        """verifier_node skips verify_plan when execution_state has terminal success."""
        state = {
            "task_id": "test-task",
            "query": "Open Notepad",
            "steps": [{"step_number": 1, "description": "Open Notepad", "output": "Done"}],
            "plan": [{"step": "Open Notepad", "id": "1"}],
            "tool_calls": [],
            "verification_reports": [],
            "environment_config": {"environment": "desktop"},
            "execution_state": ExecutionState(task_id="test-task").to_dict(),
        }

        # Add terminal success to execution_state
        exec_state = ExecutionState.from_dict(state["execution_state"])
        exec_state.record_tool(
            1,
            "Open Notepad",
            ToolExecutionRecord.from_tool_result(
                "desktop_env__open_application",
                {
                    "success": True,
                    "data": {"pid": 1234, "window": "Notepad"},
                    "error": None,
                },
            ),
        )
        state["execution_state"] = exec_state.to_dict()

        with patch("app.langgraph.nodes.verification_engine.verify_plan", new_callable=AsyncMock) as mock_verify:
            mock_verify.return_value = []
            result = await verifier_node(state)

            # verify_plan should NOT be called because terminal success exists
            mock_verify.assert_not_called()
            assert result["verified"] is True

    @pytest.mark.asyncio
    async def test_verifier_fallback_to_tool_calls(self):
        """verifier_node checks tool_calls when no execution_state."""
        state = {
            "task_id": "test-task",
            "query": "Open Notepad",
            "steps": [{"step_number": 1, "description": "Open Notepad", "output": "Done"}],
            "plan": [{"step": "Open Notepad", "id": "1"}],
            "tool_calls": [
                {
                    "step": 1,
                    "tool": "desktop_env__open_application",
                    "result": {
                        "success": True,
                        "data": {"pid": 1234, "window": "Notepad"},
                        "error": None,
                    },
                }
            ],
            "verification_reports": [],
            "environment_config": {"environment": "desktop"},
            "execution_state": None,
        }

        with patch("app.langgraph.nodes.get_llm_client") as mock_get_llm, \
             patch("app.langgraph.nodes.verification_engine.verify_plan", new_callable=AsyncMock) as mock_verify:
            mock_llm = AsyncMock()
            mock_llm.complete_json = AsyncMock(return_value={"verified": True, "reason": "Tool succeeded"})
            mock_get_llm.return_value = mock_llm
            mock_verify.return_value = []
            result = await verifier_node(state)

            mock_verify.assert_not_called()
            assert result["verified"] is True

    @pytest.mark.asyncio
    async def test_verifier_falls_back_to_verify_plan(self):
        """verifier_node falls back to verify_plan when no terminal success."""
        state = {
            "task_id": "test-task",
            "query": "Open Notepad",
            "steps": [{"step_number": 1, "description": "Open Notepad", "output": "Done"}],
            "plan": [{"step": "Open Notepad", "id": "1"}],
            "tool_calls": [],
            "verification_reports": [],
            "environment_config": {"environment": "local"},  # local env doesn't require specific tools
            "execution_state": None,
        }

        with patch("app.langgraph.nodes.get_llm_client") as mock_get_llm, \
             patch("app.langgraph.nodes.verification_engine.verify_plan", new_callable=AsyncMock) as mock_verify:
            mock_llm = AsyncMock()
            mock_llm.complete_json = AsyncMock(return_value={"verified": True, "reason": "Plan verified"})
            mock_get_llm.return_value = mock_llm
            from app.capabilities.models import VerificationReport, VerificationResult
            mock_verify.return_value = [
                VerificationReport(
                    task_id="test-task",
                    step_id="1",
                    result=VerificationResult.PASS,
                    evidence={"window": "Notepad"},
                    verifier_type="desktop_app",
                )
            ]
            result = await verifier_node(state)

            mock_verify.assert_called_once()
            assert result["verified"] is True


class TestRecoveryRespectsExecutionState:
    """Tests that recovery_engine skips when terminal success exists."""

    @pytest.mark.asyncio
    async def test_recovery_skips_on_terminal_success(self):
        """Recovery returns SKIP when execution_state has terminal success."""
        engine = RecoveryEngine(max_retries=3)
        execution_state = ExecutionState(task_id="test-task")
        execution_state.record_tool(
            1,
            "Open Notepad",
            ToolExecutionRecord.from_tool_result(
                "desktop_env__open_application",
                {
                    "success": True,
                    "data": {"pid": 1234, "window": "Notepad"},
                    "error": None,
                },
            ),
        )

        decision = await engine.decide(
            task_id="test-task",
            step_id="1",
            error="Some error",
            execution_state=execution_state.to_dict(),
        )

        assert decision.action == RecoveryAction.SKIP
        assert "terminal success" in decision.reason.lower()

    @pytest.mark.asyncio
    async def test_recovery_proceeds_without_execution_state(self):
        """Recovery proceeds normally when no execution_state."""
        engine = RecoveryEngine(max_retries=3)

        decision = await engine.decide(
            task_id="test-task",
            step_id="1",
            error="timeout",
            execution_state=None,
        )

        assert decision.action == RecoveryAction.RETRY

    @pytest.mark.asyncio
    async def test_recovery_proceeds_with_non_terminal_state(self):
        """Recovery proceeds when execution_state has no terminal success."""
        engine = RecoveryEngine(max_retries=3)
        execution_state = ExecutionState(task_id="test-task")
        execution_state.record_tool(
            1,
            "Take screenshot",
            ToolExecutionRecord.from_tool_result(
                "desktop_env__screenshot",
                {
                    "success": True,
                    "data": {"image": "base64..."},
                    "error": None,
                },
            ),
        )

        decision = await engine.decide(
            task_id="test-task",
            step_id="1",
            error="timeout",
            execution_state=execution_state.to_dict(),
        )

        # Screenshot is not terminal, so recovery should proceed
        assert decision.action == RecoveryAction.RETRY


class TestNoFallbackLoop:
    """End-to-end: verify that terminal success prevents fallback actions."""

    @pytest.mark.asyncio
    async def test_terminal_success_prevents_press_key_fallback(self):
        """The infamous bug: open_application succeeds, but verifier fails,
        causing recovery to trigger press_key(win) fallback. This test ensures
        that with canonical execution state, no fallback occurs."""
        
        # Simulate the exact state after open_application succeeds
        execution_state = ExecutionState(task_id="test-task")
        execution_state.record_tool(
            1,
            "Open Notepad",
            ToolExecutionRecord.from_tool_result(
                "desktop_env__open_application",
                {
                    "success": True,
                    "data": {
                        "pid": 1234,
                        "window": "Untitled - Notepad",
                        "process_path": "C:\\Windows\\notepad.exe",
                    },
                    "error": None,
                },
            ),
        )

        # Verifier should skip re-verification on terminal success
        state = {
            "task_id": "test-task",
            "query": "Open Notepad",
            "steps": [{"step_number": 1, "description": "Open Notepad", "output": "Done"}],
            "plan": [{"step": "Open Notepad", "id": "1"}],
            "tool_calls": [],
            "verification_reports": [],
            "environment_config": {"environment": "desktop"},
            "execution_state": execution_state.to_dict(),
        }

        with patch("app.langgraph.nodes.verification_engine.verify_plan", new_callable=AsyncMock) as mock_verify:
            mock_verify.return_value = []
            result = await verifier_node(state)
            mock_verify.assert_not_called()
            assert result["verified"] is True

        # Recovery should return SKIP, not RETRY or SWITCH_TOOL
        engine = RecoveryEngine(max_retries=3)
        decision = await engine.decide(
            task_id="test-task",
            step_id="1",
            error="Window not found by title",  # This would have triggered fallback before
            execution_state=execution_state.to_dict(),
        )
        assert decision.action == RecoveryAction.SKIP
