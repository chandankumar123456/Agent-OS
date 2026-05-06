"""Timeout enforcement for agents, tools, and workflows.

Uses asyncio timeouts for execution control and Redis for tracking
timeout configurations and deadlines across distributed workers.
"""
import asyncio
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from ..memory.short_term import redis_client
from ..logs.logger import logger
from .errors import AgentOSError, ErrorCode, ErrorType


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
    scope: str  # agent, tool, workflow, step
    deadline_timestamp: float
    configured_seconds: int
    started_at: datetime = Field(default_factory=datetime.utcnow)
    triggered: bool = False


class TimeoutEnforcer:
    """Enforces timeouts at agent, tool, and workflow levels.

    Usage:
        enforcer = TimeoutEnforcer()
        # Set timeout config for task
        await enforcer.set_config(task_id, TimeoutConfig(tool_timeout_seconds=45))

        # Enforce tool timeout
        try:
            result = await enforcer.enforce_tool(task_id, tool_name, coro)
        except TimeoutError:
            # Handle timeout
            pass
    """

    def __init__(
        self,
        redis_prefix: str = "agentos:timeout:",
        default_config: Optional[TimeoutConfig] = None,
    ):
        self.redis_prefix = redis_prefix
        self.default_config = default_config or TimeoutConfig()

    def _config_key(self, task_id: str) -> str:
        return f"{self.redis_prefix}config:{task_id}"

    def _deadline_key(self, task_id: str, scope: str) -> str:
        return f"{self.redis_prefix}deadline:{task_id}:{scope}"

    async def set_config(
        self,
        task_id: str,
        config: TimeoutConfig,
        ttl_seconds: int = 3600,
    ) -> bool:
        """Set timeout configuration for a task.

        Args:
            task_id: The task identifier.
            config: Timeout configuration.
            ttl_seconds: TTL for the config in Redis.

        Returns:
            True if set successfully.
        """
        try:
            await redis_client.client.set(
                self._config_key(task_id),
                config.model_dump_json(),
                ex=ttl_seconds,
            )
            logger.debug(f"Timeout config set for {task_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to set timeout config for {task_id}: {e}")
            return False

    async def get_config(self, task_id: str) -> TimeoutConfig:
        """Get timeout configuration for a task.

        Args:
            task_id: The task identifier.

        Returns:
            TimeoutConfig (defaults if not found).
        """
        try:
            value = await redis_client.client.get(self._config_key(task_id))
            if value:
                return TimeoutConfig.model_validate_json(value)
        except Exception as e:
            logger.warning(f"Failed to get timeout config for {task_id}: {e}")
        return self.default_config

    async def set_deadline(
        self,
        task_id: str,
        scope: str,
        seconds: int,
    ) -> TimeoutRecord:
        """Set a deadline for a specific scope.

        Args:
            task_id: The task identifier.
            scope: Scope name (agent, tool, workflow, step).
            seconds: Timeout in seconds.

        Returns:
            TimeoutRecord.
        """
        deadline = time.time() + seconds
        record = TimeoutRecord(
            task_id=task_id,
            scope=scope,
            deadline_timestamp=deadline,
            configured_seconds=seconds,
        )
        try:
            await redis_client.client.set(
                self._deadline_key(task_id, scope),
                record.model_dump_json(),
                ex=seconds + 60,  # Slightly longer than deadline for cleanup
            )
        except Exception as e:
            logger.warning(f"Failed to set deadline for {task_id}/{scope}: {e}")
        return record

    async def check_deadline(self, task_id: str, scope: str) -> bool:
        """Check if a deadline has been exceeded.

        Args:
            task_id: The task identifier.
            scope: Scope name.

        Returns:
            True if deadline exceeded or not found (fail-safe), False if within deadline.
        """
        try:
            value = await redis_client.client.get(self._deadline_key(task_id, scope))
            if not value:
                return False  # No deadline set
            record = TimeoutRecord.model_validate_json(value)
            exceeded = time.time() > record.deadline_timestamp
            if exceeded and not record.triggered:
                record.triggered = True
                await redis_client.client.set(
                    self._deadline_key(task_id, scope),
                    record.model_dump_json(),
                    ex=60,
                )
                logger.warning(
                    f"Deadline exceeded for {task_id}/{scope}",
                    extra={"task_id": task_id, "scope": scope},
                )
            return exceeded
        except Exception as e:
            logger.error(f"Failed to check deadline for {task_id}/{scope}: {e}")
            return False

    async def enforce_tool(
        self,
        task_id: str,
        tool_name: str,
        coro,
        override_seconds: Optional[int] = None,
    ) -> Any:
        """Enforce tool execution timeout.

        Args:
            task_id: The task identifier.
            tool_name: Name of the tool being executed.
            coro: Coroutine to execute.
            override_seconds: Optional override timeout.

        Returns:
            Result of the coroutine.

        Raises:
            AgentOSError: If timeout is exceeded.
        """
        config = await self.get_config(task_id)
        timeout = override_seconds or config.tool_timeout_seconds
        scope = f"tool:{tool_name}"
        await self.set_deadline(task_id, scope, timeout)

        try:
            result = await asyncio.wait_for(coro, timeout=timeout)
            return result
        except asyncio.TimeoutError:
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
            await redis_client.client.delete(self._deadline_key(task_id, scope))

    async def enforce_agent(
        self,
        task_id: str,
        agent_name: str,
        coro,
        override_seconds: Optional[int] = None,
    ) -> Any:
        """Enforce agent execution timeout.

        Args:
            task_id: The task identifier.
            agent_name: Name of the agent being executed.
            coro: Coroutine to execute.
            override_seconds: Optional override timeout.

        Returns:
            Result of the coroutine.

        Raises:
            AgentOSError: If timeout is exceeded.
        """
        config = await self.get_config(task_id)
        timeout = override_seconds or config.agent_timeout_seconds
        scope = f"agent:{agent_name}"
        await self.set_deadline(task_id, scope, timeout)

        try:
            result = await asyncio.wait_for(coro, timeout=timeout)
            return result
        except asyncio.TimeoutError:
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
            await redis_client.client.delete(self._deadline_key(task_id, scope))

    async def enforce_step(
        self,
        task_id: str,
        step_number: int,
        coro,
        override_seconds: Optional[int] = None,
    ) -> Any:
        """Enforce step execution timeout.

        Args:
            task_id: The task identifier.
            step_number: Step number in the plan.
            coro: Coroutine to execute.
            override_seconds: Optional override timeout.

        Returns:
            Result of the coroutine.

        Raises:
            AgentOSError: If timeout is exceeded.
        """
        config = await self.get_config(task_id)
        timeout = override_seconds or config.step_timeout_seconds
        scope = f"step:{step_number}"
        await self.set_deadline(task_id, scope, timeout)

        try:
            result = await asyncio.wait_for(coro, timeout=timeout)
            return result
        except asyncio.TimeoutError:
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
            await redis_client.client.delete(self._deadline_key(task_id, scope))

    async def enforce_workflow(
        self,
        task_id: str,
        coro,
        override_seconds: Optional[int] = None,
    ) -> Any:
        """Enforce workflow execution timeout.

        Args:
            task_id: The task identifier.
            coro: Coroutine to execute.
            override_seconds: Optional override timeout.

        Returns:
            Result of the coroutine.

        Raises:
            AgentOSError: If timeout is exceeded.
        """
        config = await self.get_config(task_id)
        timeout = override_seconds or config.workflow_timeout_seconds
        scope = "workflow"
        await self.set_deadline(task_id, scope, timeout)

        try:
            result = await asyncio.wait_for(coro, timeout=timeout)
            return result
        except asyncio.TimeoutError:
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
            await redis_client.client.delete(self._deadline_key(task_id, scope))

    @asynccontextmanager
    async def timeout_scope(
        self,
        task_id: str,
        scope: str,
        seconds: int,
    ):
        """Async context manager for timeout enforcement.

        Usage:
            async with enforcer.timeout_scope(task_id, "my_scope", 30):
                await long_running_operation()
        """
        await self.set_deadline(task_id, scope, seconds)
        try:
            yield
        except asyncio.TimeoutError:
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
            await redis_client.client.delete(self._deadline_key(task_id, scope))

    async def cleanup(self, task_id: str) -> bool:
        """Clean up all timeout records for a task.

        Args:
            task_id: The task identifier.

        Returns:
            True if cleaned up.
        """
        try:
            pattern = f"{self.redis_prefix}deadline:{task_id}:*"
            keys = []
            async for key in redis_client.client.scan_iter(match=pattern):
                keys.append(key)
            if keys:
                await redis_client.client.delete(*keys)
            await redis_client.client.delete(self._config_key(task_id))
            logger.debug(f"Timeout records cleaned up for {task_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to cleanup timeouts for {task_id}: {e}")
            return False


# Module-level singleton
timeout_enforcer = TimeoutEnforcer()
