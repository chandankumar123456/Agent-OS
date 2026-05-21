import pytest

from core.safety.gate import SafetyGate, safety_gate
from core.safety.models import ActionSeverity


class TestSafetyGate:
    def test_check_tool_call_irreversible(self):
        gate = SafetyGate()
        result = gate.check_tool_call("filesystem__delete_file", {}, "delete file")
        assert result == ActionSeverity.IRREVERSIBLE

    def test_check_tool_call_warning(self):
        gate = SafetyGate()
        result = gate.check_tool_call(
            "shell__execute_command", {"command": "rm -rf /"}, "run command"
        )
        assert result == ActionSeverity.WARNING

    def test_check_tool_call_safe(self):
        gate = SafetyGate()
        result = gate.check_tool_call(
            "filesystem__read_file", {"path": "/tmp/foo"}, "read file"
        )
        assert result == ActionSeverity.SAFE

    def test_singleton(self):
        assert safety_gate is not None
        assert isinstance(safety_gate, SafetyGate)

    def test_check_plan(self):
        gate = SafetyGate()
        plan = [
            {"step_number": 1, "description": "read file", "tool": "filesystem__read_file", "expected_output": "contents"},
            {"step_number": 2, "description": "delete file", "tool": "filesystem__delete_file", "expected_output": "deleted"},
            {"step_number": 3, "description": "run command", "tool": "shell__execute_command", "expected_output": "output"},
        ]
        results = gate.check_plan(plan, "do some work")
        assert results == [
            ActionSeverity.SAFE,
            ActionSeverity.IRREVERSIBLE,
            ActionSeverity.SAFE,
        ]


def test_safety_gate_blocks_credentials_in_desktop_params():
    """SR4: Must block credential-like strings in desktop tool parameters."""
    gate = SafetyGate()
    result = gate.validate_desktop_params(
        {"text": "password=SuperSecret123!"}
    )
    assert result.blocked is True
    assert "credential" in result.reason.lower()
