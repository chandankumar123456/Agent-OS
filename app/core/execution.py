"""Execution flow facade.

Provides a simplified interface for submitting and executing tasks through
the orchestrator. The actual execution logic lives in app/orchestrator/;
this module provides convenience wrappers.

Usage:
    from app.core.execution import execute_task

    result = await execute_task("Open Notepad and type hello")
"""
from __future__ import annotations

from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from ..orchestrator.context import TaskContext
from ..orchestrator.pipeline import PipelineExecutor
from ..orchestrator.router import AgentRouter
from ..agents.base import AgentOutput


async def execute_task(
    query: str,
    config: Optional[Dict[str, Any]] = None,
    task_id: Optional[UUID] = None,
    user_id: Optional[str] = None,
) -> AgentOutput:
    """Execute a task through the orchestrator.

    This is a convenience function that creates an Orchestrator instance
    and delegates execution to the AgentLoop.

    Args:
        query: The task query/instruction to execute.
        config: Optional configuration overrides.
        task_id: Optional pre-assigned task ID.
        user_id: Optional user ID (defaults to "system").

    Returns:
        AgentOutput with the execution result.
    """
    from ..orchestrator.core import Orchestrator

    orchestrator = Orchestrator()
    return await orchestrator.execute_task(
        query=query,
        config=config,
        task_id=task_id or uuid4(),
        user_id=user_id or "system",
    )


__all__ = [
    "TaskContext",
    "PipelineExecutor",
    "AgentRouter",
    "execute_task",
]
