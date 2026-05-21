"""core.state - Unified state management layer.

Merges:
- SQLite store (single-writer, WAL mode, connection pool for readers)
- Task state machine (single TaskState enum, single transition table)
- SQLite tuning (performance pragmas)

All state reads and writes go through SQLite. No Redis, no PostgreSQL
in the default code path.
"""

# Re-export from implementation modules
from .desktop_native.sqlite_store import DesktopSQLiteStore, sqlite_store
from .desktop_native.state_machine import (
    TaskState,
    StateTransition,
    LocalTaskStateMachine,
    local_task_state_machine,
)
from .desktop_native.sqlite_tuning import SQLiteTuning, sqlite_tuning

__all__ = [
    "DesktopSQLiteStore",
    "sqlite_store",
    "TaskState",
    "StateTransition",
    "LocalTaskStateMachine",
    "local_task_state_machine",
    "SQLiteTuning",
    "sqlite_tuning",
]
