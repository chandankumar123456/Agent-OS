"""Canonical Execution State — unified truth schema for all execution layers.

Problem: tool layer, executor, goal loop, verifier, and recovery each maintain
separate success/failure opinions. This causes:
    - Tool succeeds → verifier re-checks and fails → recovery triggers → loops

Solution: ToolOutput becomes the canonical record. All downstream layers read
from ExecutionState instead of re-inferring.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from enum import Enum


class ExecutionVerdict(str, Enum):
    PENDING = "pending"
    PASS = "pass"
    FAIL = "fail"
    TERMINAL = "terminal"  # deterministic success, no further checks needed


@dataclass
class ToolExecutionRecord:
    """Canonical record of a single tool invocation.

    Written by: executor (after tool_registry.execute returns)
    Read by:    goal loop, verifier, recovery
    """
    tool_name: str
    params: Dict[str, Any]
    success: bool
    result: Optional[Any] = None
    error: Optional[str] = None
    timestamp: Optional[str] = None
    # Deterministic evidence that proves success
    evidence: Dict[str, Any] = field(default_factory=dict)
    # If True, no downstream layer should second-guess this result
    terminal: bool = False

    @classmethod
    def from_tool_result(cls, tool_name: str, tool_result: Dict[str, Any]) -> ToolExecutionRecord:
        """Build a canonical record from the executor's tool_result dict."""
        success = bool(tool_result.get("success"))
        data = tool_result.get("data", {})
        error = tool_result.get("error")
        evidence: Dict[str, Any] = {}
        terminal = False

        # Terminal success detection for deterministic actions
        if success and isinstance(data, dict):
            # open_application with PID/window = terminal
            if tool_name == "desktop_env__open_application" and (data.get("pid") or data.get("window")):
                terminal = True
                evidence = {
                    "pid": data.get("pid"),
                    "window": data.get("window"),
                    "process_path": data.get("process_path"),
                    "method": data.get("method"),
                }
            # launch_app_and_open_file with window = terminal
            elif tool_name == "desktop_env__launch_app_and_open_file" and data.get("window"):
                terminal = True
                evidence = {"window": data.get("window")}
            # filesystem write with path = terminal
            elif tool_name.startswith("filesystem__") and data.get("path"):
                terminal = True
                evidence = {"path": data.get("path")}
            # browser navigate with URL = terminal
            elif tool_name.startswith("browser_env__") and data.get("url"):
                terminal = True
                evidence = {"url": data.get("url")}

        return cls(
            tool_name=tool_name,
            params=tool_result.get("params", {}),
            success=success,
            result=data,
            error=error,
            evidence=evidence,
            terminal=terminal,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "params": self.params,
            "success": self.success,
            "result": self.result,
            "error": self.error,
            "timestamp": self.timestamp,
            "evidence": self.evidence,
            "terminal": self.terminal,
        }


@dataclass
class StepExecutionRecord:
    """Canonical record for a plan step.

    Aggregates all tool records within one step.
    """
    step_number: int
    description: str
    tools: List[ToolExecutionRecord] = field(default_factory=list)
    verdict: ExecutionVerdict = ExecutionVerdict.PENDING
    notes: Optional[str] = None

    @property
    def has_terminal_success(self) -> bool:
        return any(t.terminal and t.success for t in self.tools)

    @property
    def last_tool(self) -> Optional[ToolExecutionRecord]:
        return self.tools[-1] if self.tools else None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_number": self.step_number,
            "description": self.description,
            "tools": [t.to_dict() for t in self.tools],
            "verdict": self.verdict.value,
            "notes": self.notes,
        }


@dataclass
class ExecutionState:
    """Global canonical execution state for a task.

    Written by: executor_node
    Read by:    verifier_node, recovery_engine, goal loop, task_runner
    """
    task_id: str
    steps: Dict[int, StepExecutionRecord] = field(default_factory=dict)
    current_step: int = 0

    def record_tool(self, step_number: int, description: str, tool_record: ToolExecutionRecord) -> None:
        """Record a tool execution against a step."""
        if step_number not in self.steps:
            self.steps[step_number] = StepExecutionRecord(
                step_number=step_number,
                description=description,
            )
        self.steps[step_number].tools.append(tool_record)

        # Auto-update verdict
        if tool_record.terminal and tool_record.success:
            self.steps[step_number].verdict = ExecutionVerdict.TERMINAL
            self.steps[step_number].notes = (
                f"Terminal success via {tool_record.tool_name}: {tool_record.evidence}"
            )
        elif tool_record.success:
            self.steps[step_number].verdict = ExecutionVerdict.PASS
        else:
            self.steps[step_number].verdict = ExecutionVerdict.FAIL
            self.steps[step_number].notes = tool_record.error

    def get_step(self, step_number: int) -> Optional[StepExecutionRecord]:
        return self.steps.get(step_number)

    def has_terminal_success(self, step_number: int) -> bool:
        step = self.steps.get(step_number)
        return step.has_terminal_success if step else False

    def has_any_terminal_success(self) -> bool:
        return any(s.has_terminal_success for s in self.steps.values())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "current_step": self.current_step,
            "steps": {k: v.to_dict() for k, v in self.steps.items()},
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ExecutionState:
        state = cls(task_id=data.get("task_id", ""), current_step=data.get("current_step", 0))
        for step_num, step_data in data.get("steps", {}).items():
            record = StepExecutionRecord(
                step_number=step_data["step_number"],
                description=step_data["description"],
                verdict=ExecutionVerdict(step_data.get("verdict", "pending")),
                notes=step_data.get("notes"),
            )
            for tool_data in step_data.get("tools", []):
                record.tools.append(ToolExecutionRecord(
                    tool_name=tool_data["tool_name"],
                    params=tool_data.get("params", {}),
                    success=tool_data.get("success", False),
                    result=tool_data.get("result"),
                    error=tool_data.get("error"),
                    timestamp=tool_data.get("timestamp"),
                    evidence=tool_data.get("evidence", {}),
                    terminal=tool_data.get("terminal", False),
                ))
            state.steps[int(step_num)] = record
        return state
