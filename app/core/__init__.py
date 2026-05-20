"""app.core - Unified public API for the AgentOS runtime.

This package provides the clean, unified entry point for the AgentOS
desktop-native runtime. It is a FACADE layer - the existing implementations
remain in their original locations (desktop_native, orchestrator, agents,
tools, memory), but app.core provides the single coherent public API.

Usage:
    from app.core.kernel import UnifiedKernel
    from app.core.orchestration import AgentLoop, Orchestrator
    from app.core.state import StateManager
    from app.core.execution import execute_task
"""
from __future__ import annotations

from .kernel import UnifiedKernel, AgentKernel

__all__ = [
    "UnifiedKernel",
    "AgentKernel",
]
