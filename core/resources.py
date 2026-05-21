"""core.resources - Resource management layer.

Merges:
- Execution locks (asyncio-based, SQLite-persisted)
- Timeout enforcement (asyncio.wait_for + SQLite tracking)
- Resource monitor (per-task CPU/memory budgets)
- Crash recovery coordinator
- Retry policies
"""

from .desktop_native.locks import LocalExecutionLock, LockRecord, local_execution_lock
from .desktop_native.timeouts import (
    LocalTimeoutEnforcer,
    TimeoutConfig,
    TimeoutRecord,
    local_timeout_enforcer,
)
from .desktop_native.resource_monitor import (
    ResourceBudget,
    ResourceMonitor,
    ResourceSnapshot,
    resource_monitor,
)

__all__ = [
    "LocalExecutionLock",
    "LockRecord",
    "local_execution_lock",
    "LocalTimeoutEnforcer",
    "TimeoutConfig",
    "TimeoutRecord",
    "local_timeout_enforcer",
    "ResourceBudget",
    "ResourceMonitor",
    "ResourceSnapshot",
    "resource_monitor",
]
