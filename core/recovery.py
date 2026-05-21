"""core.recovery - Crash recovery and checkpointing.

Merges:
- CrashRecovery (resume interrupted tasks)
- SQLiteCheckpointSaver (LangGraph checkpointer)
- Replay logic

SQLiteCheckpointSaver is the only registered LangGraph checkpointer in
the default path. Postgres checkpointer requires the [postgres] extra.
"""

from .desktop_native.crash_recovery import CrashRecovery, crash_recovery
from .langgraph.sqlite_checkpointer import SQLiteCheckpointSaver

__all__ = ["CrashRecovery", "crash_recovery", "SQLiteCheckpointSaver"]
