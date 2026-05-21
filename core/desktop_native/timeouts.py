"""Local timeout enforcement for desktop-native mode.

Replaces Redis-backed deadline tracking with in-process asyncio timeouts.
Configurations are persisted to SQLite for inspection.
"""

import asyncio
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field

from ..logs.logger import logger
from .sqlite_store import sqlite_store


class TimeoutConfig(BaseModel):
    """Timeout configuration for a task execution scope."""
    agent_timeout_seconds: int = 60
    tool_timeout_seconds: int = 30
    workflow_timeout_seconds: int = 300
    step_timeout_seconds: int = 60
    max_total_seconds: int = 600


class TimeoutRecord(BaseModel):
    """Record of timeout enforcement for a task."""
    task_id: str
    scope: str
    deadline_timestamp: float
    configured_seconds: int
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    triggered: bool = False


class LocalTimeoutEnforcer:
    """Enforces timeouts using asyncio primitives.

    Uses asyncio.wait_for and asyncio.timeout for actual enforcement.
    Persists configurations to SQLite for inspection and recovery.
    """

    def __init__(
        self,
        prefix: str = "agentos:timeout:",
        default_config: Optional[TimeoutConfig] = None,
    ):
        self._prefix = prefix
        self._default_config = default_config or TimeoutConfig()
        self._active_deadlines: dict = {}  # (task_id, scope) -> TimeoutRecord

    async def set_config(
        self,
        task_id: str,
        config: TimeoutConfig,
    ) -> bool:
        """Set timeout configuration for a task."""
        try:
            await sqlite_store.execute(
                """
                INSERT OR REPLACE INTO timeout_configs
                (task_id, agent_timeout_seconds, tool_timeout_seconds,
                 workflow_timeout_seconds, step_timeout_seconds, max_total_seconds)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (task_id, config.agent_timeout_seconds, config.tool_timeout_seconds,
                 config.workflow_timeout_seconds, config.step_timeout_seconds,
                 config.max_total_seconds),
            )
            await sqlite_store.commit()
            logger.debug(f"Timeout config set for {task_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to set timeout config for {task_id}: {e}")
            return False

    async def get_config(self, task_id: str) -> TimeoutConfig:
        """Get timeout configuration for a task."""
        try:
            row = await sqlite_store.fetchone(
                "SELECT * FROM timeout_configs WHERE task_id = ?",
                (task_id,),
            )
            if row:
                return TimeoutConfig(
                    agent_timeout_seconds=row["agent_timeout_seconds"],
                    tool_timeout_seconds=row["tool_timeout_seconds"],
                    workflow_timeout_seconds=row["workflow_timeout_seconds"],
                    step_timeout_seconds=row["step_timeout_seconds"],
                    max_total_seconds=row["max_total_seconds"],
                )
        except Exception as e:
            logger.warning(f"Failed to get timeout config for {task_id}: {e}")
        return self._default_config

    async def set_deadline(
        self,
        task_id: str,
        scope: str,
        seconds: int,
    ) -> TimeoutRecord:
        """Set a deadline for a specific scope."""
        deadline = time.time() + seconds
        record = TimeoutRecord(
            task_id=task_id,
            scope=scope,
            deadline_timestamp=deadline,
            configured_seconds=seconds,
        )
        self._active_deadlines[(task_id, scope)] = record

        try:
            await sqlite_store.execute(
                """
                INSERT OR REPLACE INTO timeout_deadlines
                (task_id, scope, deadline_timestamp, configured_seconds, started_at, triggered)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (task_id, scope, deadline, seconds,
                 record.started_at.isoformat(), 0),
            )
            await sqlite_store.commit()
        except Exception as e:
            logger.warning(f"Failed to set deadline for {task_id}/{scope}: {e}")

        return record

    async def check_deadline(self, task_id: str, scope: str) -> bool:
        """Check if a deadline has been exceeded."""
        record = self._active_deadlines.get((task_id, scope))
        if not record:
            # Check SQLite
            try:
                row = await sqlite_store.fetchone(
                    "SELECT * FROM timeout_deadlines WHERE task_id = ? AND scope = ?",
                    (task_id, scope),
                )
                if row:
                    record = TimeoutRecord(
                        task_id=row["task_id"],
                        scope=row["scope"],
                        deadline_timestamp=row["deadline_timestamp"],
                        configured_seconds=row["configured_seconds"],
                        started_at=datetime.fromisoformat(row["started_at"]),
                        triggered=bool(row["triggered"]),
                    )
                    self._active_deadlines[(task_id, scope)] = record
                else:
                    return False
            except Exception as e:
                logger.error(f"Failed to check deadline for {task_id}/{scope}: {e}")
                return False

        exceeded = time.time() > record.deadline_timestamp
        if exceeded and not record.triggered:
            record.triggered = True
            try:
                await sqlite_store.execute(
                    "UPDATE timeout_deadlines SET triggered = 1 WHERE task_id = ? AND scope = ?",
                    (task_id, scope),
                )
                await sqlite_store.commit()
            except Exception as e:
                logger.warning(f"Failed to mark deadline triggered: {e}")
            logger.warning(
                f"Deadline exceeded for {task_id}/{scope}",
                extra={"task_id": task_id, "scope": scope},
            )
        return exceeded

    async def enforce_tool(
        self,
        task_id: str,
        tool_name: str,
        coro,
        override_seconds: Optional[int] = None,
    ) -> Any:
        """Enforce tool execution timeout."""
        config = await self.get_config(task_id)
        timeout = override_seconds or config.tool_timeout_seconds
        scope = f"tool:{tool_name}"
        await self.set_deadline(task_id, scope, timeout)

        try:
            result = await asyncio.wait_for(coro, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            from ..orchestrator.errors import AgentOSError, ErrorCode, ErrorType
            logger.error(
                f"Tool timeout exceeded: {tool_name} for task {task_id}",
                extra={"task_id": task_id, "tool": tool_name, "timeout": timeout},
            )
            raise AgentOSError(
                message=f"Tool '{tool_name}' timed out after {timeout}s",
                error_type=ErrorType.TIMEOUT_ERROR,
                code=ErrorCode.TIMEOUT_ERROR,
                context={"task_id": task_id, "tool": tool_name, "timeout_seconds": timeout},
                http_status=504,
            )
        finally:
            self._active_deadlines.pop((task_id, scope), None)
            try:
                await sqlite_store.execute(
                    "DELETE FROM timeout_deadlines WHERE task_id = ? AND scope = ?",
                    (task_id, scope),
                )
                await sqlite_store.commit()
            except Exception:
                pass

    async def enforce_agent(
        self,
        task_id: str,
        agent_name: str,
        coro,
        override_seconds: Optional[int] = None,
    ) -> Any:
        """Enforce agent execution timeout."""
        config = await self.get_config(task_id)
        timeout = override_seconds or config.agent_timeout_seconds
        scope = f"agent:{agent_name}"
        await self.set_deadline(task_id, scope, timeout)

        try:
            result = await asyncio.wait_for(coro, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            from ..orchestrator.errors import AgentOSError, ErrorCode, ErrorType
            logger.error(
                f"Agent timeout exceeded: {agent_name} for task {task_id}",
                extra={"task_id": task_id, "agent": agent_name, "timeout": timeout},
            )
            raise AgentOSError(
                message=f"Agent '{agent_name}' timed out after {timeout}s",
                error_type=ErrorType.TIMEOUT_ERROR,
                code=ErrorCode.TIMEOUT_ERROR,
                context={"task_id": task_id, "agent": agent_name, "timeout_seconds": timeout},
                http_status=504,
            )
        finally:
            self._active_deadlines.pop((task_id, scope), None)
            try:
                await sqlite_store.execute(
                    "DELETE FROM timeout_deadlines WHERE task_id = ? AND scope = ?",
                    (task_id, scope),
                )
                await sqlite_store.commit()
            except Exception:
                pass

    async def enforce_step(
        self,
        task_id: str,
        step_number: int,
        coro,
        override_seconds: Optional[int] = None,
    ) -> Any:
        """Enforce step execution timeout."""
        config = await self.get_config(task_id)
        timeout = override_seconds or config.step_timeout_seconds
        scope = f"step:{step_number}"
        await self.set_deadline(task_id, scope, timeout)

        try:
            result = await asyncio.wait_for(coro, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            from ..orchestrator.errors import AgentOSError, ErrorCode, ErrorType
            logger.error(
                f"Step timeout exceeded: step {step_number} for task {task_id}",
                extra={"task_id": task_id, "step": step_number, "timeout": timeout},
            )
            raise AgentOSError(
                message=f"Step {step_number} timed out after {timeout}s",
                error_type=ErrorType.TIMEOUT_ERROR,
                code=ErrorCode.TIMEOUT_ERROR,
                context={"task_id": task_id, "step": step_number, "timeout_seconds": timeout},
                http_status=504,
            )
        finally:
            self._active_deadlines.pop((task_id, scope), None)
            try:
                await sqlite_store.execute(
                    "DELETE FROM timeout_deadlines WHERE task_id = ? AND scope = ?",
                    (task_id, scope),
                )
                await sqlite_store.commit()
            except Exception:
                pass

    async def enforce_workflow(
        self,
        task_id: str,
        coro,
        override_seconds: Optional[int] = None,
    ) -> Any:
        """Enforce workflow execution timeout."""
        config = await self.get_config(task_id)
        timeout = override_seconds or config.workflow_timeout_seconds
        scope = "workflow"
        await self.set_deadline(task_id, scope, timeout)

        try:
            result = await asyncio.wait_for(coro, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            from ..orchestrator.errors import AgentOSError, ErrorCode, ErrorType
            logger.error(
                f"Workflow timeout exceeded for task {task_id}",
                extra={"task_id": task_id, "timeout": timeout},
            )
            raise AgentOSError(
                message=f"Workflow timed out after {timeout}s",
                error_type=ErrorType.TIMEOUT_ERROR,
                code=ErrorCode.TIMEOUT_ERROR,
                context={"task_id": task_id, "timeout_seconds": timeout},
                http_status=504,
            )
        finally:
            self._active_deadlines.pop((task_id, scope), None)
            try:
                await sqlite_store.execute(
                    "DELETE FROM timeout_deadlines WHERE task_id = ? AND scope = ?",
                    (task_id, scope),
                )
                await sqlite_store.commit()
            except Exception:
                pass

    @asynccontextmanager
    async def timeout_scope(
        self,
        task_id: str,
        scope: str,
        seconds: int,
    ):
        """Async context manager for timeout enforcement."""
        await self.set_deadline(task_id, scope, seconds)
        try:
            yield
        except asyncio.TimeoutError:
            from ..orchestrator.errors import AgentOSError, ErrorCode, ErrorType
            logger.error(
                f"Timeout in scope {scope} for task {task_id}",
                extra={"task_id": task_id, "scope": scope, "timeout": seconds},
            )
            raise AgentOSError(
                message=f"Timeout in scope '{scope}' after {seconds}s",
                error_type=ErrorType.TIMEOUT_ERROR,
                code=ErrorCode.TIMEOUT_ERROR,
                context={"task_id": task_id, "scope": scope, "timeout_seconds": seconds},
                http_status=504,
            )
        finally:
            self._active_deadlines.pop((task_id, scope), None)
            try:
                await sqlite_store.execute(
                    "DELETE FROM timeout_deadlines WHERE task_id = ? AND scope = ?",
                    (task_id, scope),
                )
                await sqlite_store.commit()
            except Exception:
                pass

    async def cleanup(self, task_id: str) -> bool:
        """Clean up all timeout records for a task."""
        # Clear from memory
        scopes_to_remove = [
            scope for (tid, scope) in self._active_deadlines if tid == task_id
        ]
        for scope in scopes_to_remove:
            self._active_deadlines.pop((task_id, scope), None)

        try:
            await sqlite_store.execute(
                "DELETE FROM timeout_deadlines WHERE task_id = ?",
                (task_id,),
            )
            await sqlite_store.execute(
                "DELETE FROM timeout_configs WHERE task_id = ?",
                (task_id,),
            )
            await sqlite_store.commit()
            logger.debug(f"Timeout records cleaned up for {task_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to cleanup timeouts for {task_id}: {e}")
            return False


# Module-level singleton
local_timeout_enforcer = LocalTimeoutEnforcer()
