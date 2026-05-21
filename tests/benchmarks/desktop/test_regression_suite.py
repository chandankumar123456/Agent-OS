"""Desktop regression benchmark suite — 5 real-world desktop tasks.

Each benchmark class wraps a :class:`DesktopGoalLoop` call and records
success / action count.  Tests are automatically skipped when the target
executable is not installed on the system.

NOTE: DesktopGoalLoop is imported lazily inside _execute() to avoid a
pre-existing circular import between app.agents.executor and
app.desktop.goal_loop (see tests/test_desktop_loop.py for the same pattern).
"""

from __future__ import annotations

from typing import Callable

import pytest

from .base import BenchmarkResult, DesktopBenchmarkBase


# ── Benchmark 1: Notepad ──────────────────────────────────────────────


class NotepadBenchmark(DesktopBenchmarkBase):
    """Open Notepad, type 'Hello AgentOS', save as C:\\temp\\bench.txt."""

    def __init__(self) -> None:
        super().__init__("notepad_type_save")

    async def _execute(self) -> None:
        from core.desktop.goal_loop import DesktopGoalLoop  # lazy: avoid circular import

        loop = DesktopGoalLoop(task_id="bench-notepad")
        result = await loop.execute(
            query="Open Notepad, type 'Hello AgentOS', and save the file as C:\\temp\\bench.txt",
        )
        self.result.success = result.success
        self.result.action_count = len(result.actions_performed)


@pytest.mark.win32
@pytest.mark.asyncio
async def test_notepad_type_save(skip_if_not_installed: Callable[[str], None]) -> None:
    """Regression benchmark: Notepad type-and-save workflow."""
    skip_if_not_installed("notepad.exe")
    bench = NotepadBenchmark()
    result: BenchmarkResult = await bench.run()
    assert result.success, f"Notepad benchmark failed: {result.error}"
    assert result.action_count > 0, "Notepad benchmark recorded zero actions"


# ── Benchmark 2: Calculator ───────────────────────────────────────────


class CalculatorBenchmark(DesktopBenchmarkBase):
    """Open Calculator and compute 7 × 8."""

    def __init__(self) -> None:
        super().__init__("calculator_multiply")

    async def _execute(self) -> None:
        from core.desktop.goal_loop import DesktopGoalLoop  # lazy: avoid circular import

        loop = DesktopGoalLoop(task_id="bench-calculator")
        result = await loop.execute(
            query="Open Calculator and compute 7 times 8",
        )
        self.result.success = result.success
        self.result.action_count = len(result.actions_performed)


@pytest.mark.uwp
@pytest.mark.asyncio
async def test_calculator_multiply(skip_if_not_installed: Callable[[str], None]) -> None:
    """Regression benchmark: Calculator multiplication."""
    skip_if_not_installed("calculator.exe")
    bench = CalculatorBenchmark()
    result: BenchmarkResult = await bench.run()
    assert result.success, f"Calculator benchmark failed: {result.error}"
    assert result.action_count > 0, "Calculator benchmark recorded zero actions"


# ── Benchmark 3: Paint ────────────────────────────────────────────────


class PaintBenchmark(DesktopBenchmarkBase):
    """Open Paint and draw a horizontal line."""

    def __init__(self) -> None:
        super().__init__("paint_draw_line")

    async def _execute(self) -> None:
        from core.desktop.goal_loop import DesktopGoalLoop  # lazy: avoid circular import

        loop = DesktopGoalLoop(task_id="bench-paint")
        result = await loop.execute(
            query="Open Paint and draw a horizontal line across the canvas",
        )
        self.result.success = result.success
        self.result.action_count = len(result.actions_performed)


@pytest.mark.canvas
@pytest.mark.asyncio
async def test_paint_draw_line(skip_if_not_installed: Callable[[str], None]) -> None:
    """Regression benchmark: Paint line-drawing workflow."""
    skip_if_not_installed("mspaint.exe")
    bench = PaintBenchmark()
    result: BenchmarkResult = await bench.run()
    assert result.success, f"Paint benchmark failed: {result.error}"
    assert result.action_count > 0, "Paint benchmark recorded zero actions"


# ── Benchmark 4: VS Code ──────────────────────────────────────────────


class VSCodeBenchmark(DesktopBenchmarkBase):
    """Open VS Code and create a new untitled file."""

    def __init__(self) -> None:
        super().__init__("vscode_new_file")

    async def _execute(self) -> None:
        from core.desktop.goal_loop import DesktopGoalLoop  # lazy: avoid circular import

        loop = DesktopGoalLoop(task_id="bench-vscode")
        result = await loop.execute(
            query="Open Visual Studio Code and create a new untitled file",
        )
        self.result.success = result.success
        self.result.action_count = len(result.actions_performed)


@pytest.mark.electron
@pytest.mark.asyncio
async def test_vscode_new_file(skip_if_not_installed: Callable[[str], None]) -> None:
    """Regression benchmark: VS Code new-file workflow."""
    skip_if_not_installed("code.exe")
    bench = VSCodeBenchmark()
    result: BenchmarkResult = await bench.run()
    assert result.success, f"VS Code benchmark failed: {result.error}"
    assert result.action_count > 0, "VS Code benchmark recorded zero actions"


# ── Benchmark 5: File Explorer ────────────────────────────────────────


class ExplorerBenchmark(DesktopBenchmarkBase):
    """Open File Explorer and navigate to the Desktop folder."""

    def __init__(self) -> None:
        super().__init__("explorer_navigate_desktop")

    async def _execute(self) -> None:
        from core.desktop.goal_loop import DesktopGoalLoop  # lazy: avoid circular import

        loop = DesktopGoalLoop(task_id="bench-explorer")
        result = await loop.execute(
            query="Open File Explorer and navigate to the Desktop folder",
        )
        self.result.success = result.success
        self.result.action_count = len(result.actions_performed)


@pytest.mark.win32
@pytest.mark.asyncio
async def test_explorer_navigate_desktop(skip_if_not_installed: Callable[[str], None]) -> None:
    """Regression benchmark: File Explorer desktop-navigation workflow."""
    skip_if_not_installed("explorer.exe")
    bench = ExplorerBenchmark()
    result: BenchmarkResult = await bench.run()
    assert result.success, f"Explorer benchmark failed: {result.error}"
    assert result.action_count > 0, "Explorer benchmark recorded zero actions"
