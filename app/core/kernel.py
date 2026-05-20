"""Unified kernel - the single public entry point for the AgentOS runtime.

Wraps the existing AgentKernel from app.desktop_native.kernel and provides
convenience methods for full lifecycle initialization.

Usage:
    from app.core.kernel import UnifiedKernel

    kernel = UnifiedKernel()
    await kernel.initialize_runtime()  # Starts kernel + orchestrator + tools
    task_id = await kernel.submit_task("Hello world")
    result = await kernel.wait_for_task(task_id)
    await kernel.stop()
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from ..desktop_native.kernel import AgentKernel, get_kernel


class UnifiedKernel(AgentKernel):
    """Unified execution kernel extending AgentKernel with lifecycle helpers.

    This class extends AgentKernel to provide a single initialize_runtime()
    method that handles the complete startup sequence: kernel start,
    orchestrator initialization, tool registration, and observability setup.
    """

    def __init__(
        self,
        max_concurrent_tasks: int = 5,
        task_timeout_seconds: int = 600,
    ):
        super().__init__(
            max_concurrent_tasks=max_concurrent_tasks,
            task_timeout_seconds=task_timeout_seconds,
        )
        self._observability_initialized = False

    async def initialize_runtime(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Full lifecycle initialization of the runtime.

        This is a convenience method that performs:
        1. Initializes desktop-native observability (logger, metrics, tracer, alerts)
        2. Initializes the memory hierarchy
        3. Starts the kernel (which starts workers, orchestrator, tools, etc.)

        Args:
            config: Optional configuration overrides.
        """
        config = config or {}

        # Initialize observability subsystems
        if not self._observability_initialized:
            from ..desktop_native.local_logger import local_logger
            local_logger.initialize()

            from ..desktop_native.local_metrics import local_metrics
            await local_metrics._ensure_table()

            from ..desktop_native.local_tracer import local_tracer
            await local_tracer._ensure_table()

            from ..desktop_native.local_alerts import local_alerts
            await local_alerts.initialize()

            from ..desktop_native.memory_hierarchy import memory_hierarchy
            await memory_hierarchy.initialize()

            self._observability_initialized = True

        # Start the kernel (initializes AgentRuntime, Orchestrator, workers, etc.)
        await self.start()


__all__ = [
    "UnifiedKernel",
    "AgentKernel",
    "get_kernel",
]
