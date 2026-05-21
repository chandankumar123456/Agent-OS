"""Base classes and data structures for desktop benchmarks."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional



logger = logging.getLogger(__name__)


@dataclass
class BenchmarkResult:
    """Structured outcome of a single benchmark run."""

    success: bool
    action_count: int
    task_name: str
    error: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)


class DesktopBenchmarkBase(ABC):
    """Base class for desktop automation benchmarks.

    Subclasses must implement :meth:`_execute` which performs the actual
    desktop goal loop and sets ``self.result``.

    Usage::

        class NotepadBenchmark(DesktopBenchmarkBase):
            def __init__(self):
                super().__init__("notepad_type_save")

            async def _execute(self):
                loop = DesktopGoalLoop(task_id="bench-notepad")
                result = await loop.execute(query="...")
                self.result.success = result.success
                self.result.action_count = len(result.actions_performed)
    """

    def __init__(self, task_name: str) -> None:
        self.task_name = task_name
        self.result: BenchmarkResult = BenchmarkResult(
            success=False,
            action_count=0,
            task_name=task_name,
        )

    async def run(self) -> BenchmarkResult:
        """Execute the benchmark and return the result."""
        logger.info("Starting benchmark [%s]", self.task_name)
        try:
            await self._execute()
        except Exception as exc:
            logger.exception("Benchmark [%s] failed with exception", self.task_name)
            self.result.success = False
            self.result.error = str(exc)
        logger.info(
            "Benchmark [%s] complete: success=%s, actions=%d",
            self.task_name,
            self.result.success,
            self.result.action_count,
        )
        return self.result

    @abstractmethod
    async def _execute(self) -> None:
        """Subclass hook — perform the desktop goal loop via DesktopGoalLoop and populate self.result."""
