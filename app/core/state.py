"""Unified state management facade.

Re-exports all state subsystems from app.desktop_native and provides a
StateManager class that gives unified access to state, task queue, locks,
timeouts, and the state machine.

Usage:
    from app.core.state import StateManager, state_manager

    # Access subsystems:
    await state_manager.store.execute("SELECT 1")
    await state_manager.task_queue.enqueue(...)
    await state_manager.state_machine.get_current_state(task_id)
"""
from __future__ import annotations

from ..desktop_native.sqlite_store import sqlite_store
from ..desktop_native.task_queue import local_task_queue
from ..desktop_native.state_machine import local_task_state_machine
from ..desktop_native.locks import local_execution_lock
from ..desktop_native.timeouts import local_timeout_enforcer


class StateManager:
    """Unified access to all state subsystems.

    Provides a single object through which all state-related operations
    can be accessed, rather than importing individual singletons.
    """

    def __init__(self):
        self.store = sqlite_store
        self.task_queue = local_task_queue
        self.state_machine = local_task_state_machine
        self.execution_lock = local_execution_lock
        self.timeout_enforcer = local_timeout_enforcer

    async def initialize(self) -> None:
        """Initialize all state subsystems (schema creation, etc.)."""
        await self.store.initialize_schema()


# Module-level singleton
state_manager = StateManager()

__all__ = [
    "StateManager",
    "state_manager",
    "sqlite_store",
    "local_task_queue",
    "local_task_state_machine",
    "local_execution_lock",
    "local_timeout_enforcer",
]
