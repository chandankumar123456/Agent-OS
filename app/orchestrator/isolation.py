"""Failure isolation boundaries for tasks and agents.

Ensures failures in one task or agent don't cascade to others by
providing separate execution contexts with independent error handling
and resource limits.
"""
import asyncio
import traceback
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, Field

from ..memory.short_term import redis_client
from ..logs.logger import logger
from .errors import AgentOSError, ErrorCode, ErrorType
from .state_machine import TaskState, TaskStateMachine
from .timeouts import TimeoutEnforcer, TimeoutConfig


class ResourceLimits(BaseModel):
    """Resource limits for an isolated context."""
    max_memory_mb: int = 512
    max_cpu_percent: float = 50.0
    max_concurrent_tools: int = 5
    max_llm_calls: int = 20


class IsolationContext(BaseModel):
    """Isolated execution context for a task or agent."""
    task_id: str
    isolated_state: Dict[str, Any] = Field(default_factory=dict)
    error_handler: Optional[str] = None  # Handler identifier
    resource_limits: ResourceLimits = Field(default_factory=ResourceLimits)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    active: bool = True
    failure_count: int = 0
    max_failures: int = 3


class FailureIsolator:
    """Provides failure isolation boundaries for task execution.

    Usage:
        isolator = FailureIsolator()
        context = await isolator.isolate_context(task_id)

        async with isolator.run_isolated(task_id, agent_coro):
            # If agent_coro fails, it's contained within this boundary
            pass
    """

    def __init__(
        self,
        redis_prefix: str = "agentos:isolation:",
        state_machine: Optional[TaskStateMachine] = None,
        timeout_enforcer: Optional[TimeoutEnforcer] = None,
    ):
        self.redis_prefix = redis_prefix
        self.state_machine = state_machine or TaskStateMachine()
        self.timeout_enforcer = timeout_enforcer or TimeoutEnforcer()
        # In-memory isolation contexts for test/fallback
        self._local_contexts: Dict[str, IsolationContext] = {}

    def _context_key(self, task_id: str) -> str:
        return f"{self.redis_prefix}context:{task_id}"

    def _failure_key(self, task_id: str) -> str:
        return f"{self.redis_prefix}failures:{task_id}"

    async def isolate_context(
        self,
        task_id: str,
        resource_limits: Optional[ResourceLimits] = None,
        max_failures: int = 3,
    ) -> IsolationContext:
        """Create or retrieve an isolated context for a task.

        Args:
            task_id: The task identifier.
            resource_limits: Optional resource limits.
            max_failures: Maximum failures before circuit opens.

        Returns:
            IsolationContext.
        """
        limits = resource_limits or ResourceLimits()
        context = IsolationContext(
            task_id=task_id,
            resource_limits=limits,
            max_failures=max_failures,
        )

        try:
            await redis_client.client.set(
                self._context_key(task_id),
                context.model_dump_json(),
                ex=3600,
            )
        except Exception as e:
            logger.warning(f"Redis isolation context failed for {task_id}: {e}")
            self._local_contexts[task_id] = context

        logger.info(
            f"Isolation context created",
            extra={"task_id": task_id, "max_failures": max_failures},
        )
        return context

    async def get_context(self, task_id: str) -> Optional[IsolationContext]:
        """Get the isolation context for a task.

        Args:
            task_id: The task identifier.

        Returns:
            IsolationContext if found, None otherwise.
        """
        try:
            value = await redis_client.client.get(self._context_key(task_id))
            if value:
                return IsolationContext.model_validate_json(value)
        except Exception as e:
            logger.warning(f"Failed to get isolation context for {task_id}: {e}")

        if task_id in self._local_contexts:
            return self._local_contexts[task_id]

        return None

    async def record_failure(
        self,
        task_id: str,
        error: Exception,
        context: Optional[str] = None,
    ) -> int:
        """Record a failure within an isolation boundary.

        Args:
            task_id: The task identifier.
            error: The exception that occurred.
            context: Additional context about where the failure occurred.

        Returns:
            Current failure count.
        """
        failure_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error_type": type(error).__name__,
            "error_message": str(error),
            "context": context or "unknown",
            "traceback": traceback.format_exc(),
        }

        try:
            # Push failure to list
            await redis_client.client.lpush(
                self._failure_key(task_id),
                str(failure_entry),
            )
            await redis_client.client.expire(self._failure_key(task_id), 3600)

            # Update context failure count
            iso_context = await self.get_context(task_id)
            if iso_context:
                iso_context.failure_count += 1
                iso_context.active = iso_context.failure_count < iso_context.max_failures
                try:
                    await redis_client.client.set(
                        self._context_key(task_id),
                        iso_context.model_dump_json(),
                        ex=3600,
                    )
                except Exception:
                    self._local_contexts[task_id] = iso_context

                count = iso_context.failure_count
            else:
                count = 1
        except Exception as e:
            logger.error(f"Failed to record failure for {task_id}: {e}")
            count = 1

        logger.warning(
            f"Failure recorded in isolation boundary",
            extra={
                "task_id": task_id,
                "failure_count": count,
                "error_type": type(error).__name__,
            },
        )
        return count

    async def is_circuit_open(self, task_id: str) -> bool:
        """Check if the circuit breaker is open for a task.

        Args:
            task_id: The task identifier.

        Returns:
            True if circuit is open (too many failures), False otherwise.
        """
        context = await self.get_context(task_id)
        if not context:
            return False
        return not context.active

    async def reset(self, task_id: str) -> bool:
        """Reset the isolation context and failure count for a task.

        Args:
            task_id: The task identifier.

        Returns:
            True if reset.
        """
        try:
            context = await self.get_context(task_id)
            if context:
                context.failure_count = 0
                context.active = True
                await redis_client.client.set(
                    self._context_key(task_id),
                    context.model_dump_json(),
                    ex=3600,
                )
            await redis_client.client.delete(self._failure_key(task_id))
            logger.info(f"Isolation context reset for {task_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to reset isolation for {task_id}: {e}")
            return False

    @asynccontextmanager
    async def run_isolated(
        self,
        task_id: str,
        coro_factory: Callable[[], Any],
        fallback_coro_factory: Optional[Callable[[], Any]] = None,
    ):
        """Run a coroutine within an isolated boundary.

        If the coroutine fails, the failure is contained and an optional
        fallback coroutine is executed. The failure does not propagate
        outside the boundary.

        Usage:
            async with isolator.run_isolated(task_id, main_task, fallback_task):
                result = await main_task()
        """
        context = await self.get_context(task_id)
        if not context:
            context = await self.isolate_context(task_id)

        if not context.active:
            logger.warning(
                f"Circuit breaker open for {task_id}, skipping execution",
                extra={"task_id": task_id, "failure_count": context.failure_count},
            )
            if fallback_coro_factory:
                try:
                    result = await fallback_coro_factory()
                    yield result
                    return
                except Exception as fallback_error:
                    logger.error(f"Fallback also failed for {task_id}: {fallback_error}")
            raise AgentOSError(
                message=f"Circuit breaker open for task {task_id}",
                error_type=ErrorType.EXECUTION_ERROR,
                code=ErrorCode.ISOLATION_FAILURE,
                context={"task_id": task_id, "failure_count": context.failure_count},
                http_status=503,
            )

        try:
            yield
        except Exception as e:
            count = await self.record_failure(task_id, e, context="isolated_execution")
            logger.error(
                f"Isolated execution failed for {task_id}",
                extra={"task_id": task_id, "failure_count": count, "error": str(e)},
            )

            if count >= context.max_failures:
                context.active = False
                try:
                    await redis_client.client.set(
                        self._context_key(task_id),
                        context.model_dump_json(),
                        ex=3600,
                    )
                except Exception:
                    self._local_contexts[task_id] = context

            # Try fallback
            if fallback_coro_factory:
                try:
                    logger.info(f"Executing fallback for {task_id}")
                    result = await fallback_coro_factory()
                    yield result
                    return
                except Exception as fallback_error:
                    logger.error(f"Fallback failed for {task_id}: {fallback_error}")

            # Re-raise as structured error
            raise AgentOSError(
                message=f"Isolated execution failed: {e}",
                error_type=ErrorType.EXECUTION_ERROR,
                code=ErrorCode.ISOLATION_FAILURE,
                context={"task_id": task_id, "failure_count": count, "original_error": str(e)},
                http_status=500,
            )

    async def get_failure_history(self, task_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent failure history for a task.

        Args:
            task_id: The task identifier.
            limit: Maximum number of failures to return.

        Returns:
            List of failure entries.
        """
        try:
            values = await redis_client.client.lrange(
                self._failure_key(task_id), 0, limit - 1
            )
            import ast
            history = []
            for v in values:
                try:
                    history.append(ast.literal_eval(v))
                except Exception:
                    pass
            return history
        except Exception as e:
            logger.error(f"Failed to get failure history for {task_id}: {e}")
            return []

    async def cleanup(self, task_id: str) -> bool:
        """Clean up isolation context and failure history for a task.

        Args:
            task_id: The task identifier.

        Returns:
            True if cleaned up.
        """
        try:
            await redis_client.client.delete(self._context_key(task_id))
            await redis_client.client.delete(self._failure_key(task_id))
            if task_id in self._local_contexts:
                del self._local_contexts[task_id]
            logger.debug(f"Isolation context cleaned up for {task_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to cleanup isolation for {task_id}: {e}")
            return False


# Module-level singleton
failure_isolator = FailureIsolator()
