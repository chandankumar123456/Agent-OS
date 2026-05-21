"""AgentKernel - unified desktop-native runtime kernel.

Merges AgentKernel (scheduler/execution), AgentRuntime (agent registry),
and Orchestrator (task fan-out) into a single execution entry point.

Design:
- Single process, single event loop
- SQLite as the single source of truth
- asyncio.PriorityQueue for task scheduling
- Direct LangGraph invocation (no Celery hop)
- Cooperative cancellation via asyncio.Task.cancel()
- Agent lifecycle managed internally (no separate AgentRuntime needed)
"""

# Re-export the canonical AgentKernel from its implementation module.
# The actual kernel logic lives in core/desktop_native/kernel.py with the
# terminal-transition bug fix applied.
from .desktop_native.kernel import AgentKernel, get_kernel

__all__ = ["AgentKernel", "get_kernel"]
