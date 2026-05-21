"""Desktop-native local-first implementations for AgentOS.

This package provides drop-in replacements for Redis and PostgreSQL
dependencies when running in desktop-native mode (RUNTIME_MODE=grpc).

All implementations use:
- asyncio for concurrency (no distributed locks/queues)
- SQLite for persistence (no PostgreSQL server required)
- In-memory structures for ephemeral state (no Redis required)
"""

import os


def is_desktop_mode() -> bool:
    """Check if running in desktop-native mode."""
    mode = os.environ.get("AGENTOS_RUNTIME_MODE", os.environ.get("RUNTIME_MODE", "http"))
    return mode.lower() == "grpc"


def get_desktop_db_path() -> str:
    """Get the path to the desktop-native SQLite database."""
    home = os.path.expanduser("~")
    agentos_dir = os.path.join(home, ".agentos")
    os.makedirs(agentos_dir, exist_ok=True)
    return os.path.join(agentos_dir, "agentos.db")
