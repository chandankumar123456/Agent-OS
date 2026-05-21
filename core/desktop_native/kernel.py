"""AgentKernel — unified desktop-native runtime kernel.

Replaces the fragmented runtime (AgentRuntime + Orchestrator + TaskRunner +
Celery + Redis) with a single asyncio process that owns all execution.

Design:
- Single process, single event loop
- SQLite as the single source of truth
- asyncio.PriorityQueue for task scheduling
- Direct LangGraph invocation (no Celery hop)
- Cooperative cancellation via asyncio.Task.cancel()
"""

import asyncio
import json
import os
import signal
import sys
import time
import traceback
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set

from ..logs.logger import logger
from ..config.settings import settings
from .sqlite_store import sqlite_store
from .event_bus import local_event_bus, Event
from .locks import local_execution_lock
from .timeouts import local_timeout_enforcer
from .task_queue import local_task_queue, TaskPriority
from .state_machine import local_task_state_machine, TaskState
from .resource_monitor import resource_monitor, ResourceBudget
from .crash_recovery import crash_recovery
from .sqlite_tuning import sqlite_tuning


class AgentKernel:
    """Unified execution kernel for desktop-native AgentOS.

    Responsibilities:
    - Task scheduling (asyncio.PriorityQueue + SQLite)
    - Agent lifecycle (AgentPool as semaphore)
    - Execution routing (Fast Path -> LangGraph)
    - State management (SQLite single-writer)
    - Event emission (LocalEventBus)
    - Resource GC (session reaper)
    - Crash recovery (resume from checkpoints)

    Usage:
        kernel = AgentKernel()
        await kernel.start()
        task_id = await kernel.submit_task("Open Notepad and type hello")
        result = await kernel.wait_for_task(task_id)
        await kernel.stop()
    """

    def __init__(
        self,
        max_concurrent_tasks: int = 5,
        task_timeout_seconds: int = 600,
    ):
        self.max_concurrent = max_concurrent_tasks
        self.task_timeout = task_timeout_seconds
        self._semaphore = asyncio.Semaphore(max_concurrent_tasks)
        self._running = False
        self._shutdown_event = asyncio.Event()
        self._worker_tasks: Set[asyncio.Task] = set()
        self._active_tasks: Dict[str, asyncio.Task] = {}
        self._task_results: Dict[str, Any] = {}
        self._result_events: Dict[str, asyncio.Event] = {}
        self._gc_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

        # Lazy imports to avoid circular deps
        self._orchestrator = None
        self._runtime = None
        self._checkpointer = None

    async def start(self) -> None:
        """Initialize the kernel and start the scheduler."""
        if self._running:
            return

        logger.info("=" * 60)
        logger.info("AgentKernel starting...")
        logger.info(f"Max concurrent tasks: {self.max_concurrent}")
        logger.info(f"Task timeout: {self.task_timeout}s")
        logger.info("=" * 60)

        # Initialize SQLite schema
        await sqlite_store.initialize_schema()

        # Apply SQLite performance tuning
        tuning_results = await sqlite_tuning.apply_optimizations()
        logger.info(f"SQLite tuning applied: {tuning_results}")

        # Initialize core runtime (agents, tools, checkpointer)
        from ..runtime.runtime import AgentRuntime
        self._runtime = AgentRuntime()
        await self._runtime.initialize()

        # Initialize orchestrator
        from ..orchestrator.core import Orchestrator
        self._orchestrator = Orchestrator()

        # Initialize checkpointer
        from ..langgraph.sqlite_checkpointer import SQLiteCheckpointSaver
        self._checkpointer = SQLiteCheckpointSaver()

        # Start resource monitor
        await resource_monitor.start()

        self._running = True

        # Start worker pool
        for i in range(self.max_concurrent):
            worker = asyncio.create_task(
                self._worker_loop(f"worker-{i}"),
                name=f"kernel_worker_{i}",
            )
            self._worker_tasks.add(worker)
            worker.add_done_callback(self._worker_tasks.discard)

        # Start GC task
        self._gc_task = asyncio.create_task(self._gc_loop(), name="kernel_gc")

        # Setup signal handlers
        self._setup_signal_handlers()

        # Crash recovery: resume interrupted tasks
        recovery_stats = await crash_recovery.scan_and_resume(self)
        if recovery_stats["found"] > 0:
            logger.info(
                f"Crash recovery: {recovery_stats['recovered']}/{recovery_stats['found']} "
                f"tasks recovered"
            )

        logger.info("AgentKernel started successfully")

    async def stop(self, timeout: float = 30.0) -> None:
        """Graceful shutdown with cancellation of active tasks."""
        if not self._running:
            return

        logger.info("AgentKernel shutting down...")
        self._running = False
        self._shutdown_event.set()

        # Cancel all active task coroutines
        async with self._lock:
            for task_id, task in list(self._active_tasks.items()):
                logger.info(f"Cancelling active task {task_id}")
                task.cancel()

        # Cancel workers
        for worker in list(self._worker_tasks):
            worker.cancel()

        if self._gc_task:
            self._gc_task.cancel()

        # Stop resource monitor
        await resource_monitor.stop()

        # Wait for graceful shutdown
        if self._worker_tasks:
            await asyncio.wait(
                list(self._worker_tasks),
                timeout=timeout,
                return_when=asyncio.ALL_COMPLETED,
            )

        logger.info("AgentKernel shutdown complete")

    async def submit_task(
        self,
        query: str,
        user_id: str = "system",
        config: Optional[Dict[str, Any]] = None,
        priority: TaskPriority = TaskPriority.NORMAL,
    ) -> str:
        """Submit a task to the kernel.

        Returns:
            task_id: The assigned task identifier.
        """
        task_id = str(uuid.uuid4())
        config = config or {}
        now = datetime.now(timezone.utc)

        # Persist task to SQLite
        await sqlite_store.execute(
            """
            INSERT INTO task_queue (task_id, user_id, query, priority, config, status, enqueued_at, score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (task_id, user_id, query, priority.value, json.dumps(config), "queued", now.isoformat(), 0),
        )
        await sqlite_store.commit()

        # Set initial state
        await local_task_state_machine.reset_state(task_id, TaskState.PENDING)

        # Enqueue
        await local_task_queue.enqueue(task_id, user_id, query, priority=priority, config=config)

        # Setup result event
        self._result_events[task_id] = asyncio.Event()

        # Publish event
        await local_event_bus.publish(
            "tasks",
            Event("task:submitted", {"task_id": task_id, "query": query, "priority": priority.name}),
        )

        logger.info(f"Task submitted: {task_id}")
        return task_id

    async def wait_for_task(self, task_id: str, timeout: Optional[float] = None) -> Dict[str, Any]:
        """Wait for a task to complete and return its result.

        Args:
            task_id: The task to wait for.
            timeout: Maximum seconds to wait. None means no timeout.

        Returns:
            Dict with status, result, and error.
        """
        event = self._result_events.get(task_id)
        if not event:
            return {"status": "not_found", "task_id": task_id}

        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            return {"status": "timeout", "task_id": task_id}

        return self._task_results.get(task_id, {"status": "unknown", "task_id": task_id})

    async def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """Get the current status of a task."""
        state = await local_task_state_machine.get_current_state(task_id)
        return {
            "task_id": task_id,
            "state": state.value,
            "is_terminal": await local_task_state_machine.is_terminal(task_id),
        }

    async def cancel_task(self, task_id: str) -> bool:
        """Cancel a running task."""
        async with self._lock:
            task = self._active_tasks.get(task_id)
            if task and not task.done():
                task.cancel()
                logger.info(f"Task {task_id} cancellation requested")
                return True
        return False

    async def list_tasks(
        self,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """List tasks from the queue."""
        tasks = await local_task_queue.list_tasks(status=status, limit=limit)
        return [t.model_dump(mode="json") for t in tasks]

    async def _worker_loop(self, worker_id: str) -> None:
        """Worker that consumes tasks from the queue."""
        logger.info(f"Worker {worker_id} started")

        while self._running:
            try:
                # Dequeue with timeout to allow shutdown checks
                task = await local_task_queue.dequeue(worker_id)
                if task is None:
                    await asyncio.sleep(0.1)
                    continue

                task_id = task.task_id
                logger.info(f"Worker {worker_id} picked up task {task_id}")

                # Start resource monitoring for this task
                budget = ResourceBudget(
                    memory_mb=task.config.get("memory_mb", 512.0),
                    cpu_percent=task.config.get("cpu_percent", 100.0),
                    max_runtime_seconds=min(
                        task.config.get("max_runtime_seconds", self.task_timeout),
                        self.task_timeout,
                    ),
                )
                await resource_monitor.start_monitoring(task_id, budget)

                # Execute task with semaphore + timeout
                async with self._semaphore:
                    task_coro = self._execute_task(task_id, task.query, task.config, task.user_id)
                    wrapped = asyncio.create_task(
                        asyncio.wait_for(task_coro, timeout=self.task_timeout),
                        name=f"task_{task_id}",
                    )

                    async with self._lock:
                        self._active_tasks[task_id] = wrapped

                    try:
                        # Poll for resource violations while task runs
                        while not wrapped.done():
                            await asyncio.sleep(2.0)
                            violation = resource_monitor.get_violation(task_id)
                            if violation:
                                logger.warning(f"Resource violation for {task_id}: {violation}")
                                wrapped.cancel()
                                raise RuntimeError(f"Resource limit exceeded: {violation}")

                        result = await wrapped
                        self._task_results[task_id] = {
                            "status": "completed",
                            "task_id": task_id,
                            "result": result,
                        }
                        await local_task_queue.complete(task_id)
                        # Route through VERIFYING state (fixes terminal-transition bug):
                        # EXECUTING -> VERIFYING -> COMPLETED
                        await local_task_state_machine.transition(
                            task_id, TaskState.EXECUTING, TaskState.VERIFYING
                        )
                        await local_task_state_machine.transition(
                            task_id, TaskState.VERIFYING, TaskState.COMPLETED
                        )

                        # Notify GUI
                        try:
                            from .tauri_bridge import tauri_bridge
                            await tauri_bridge.notify_task_complete(
                                task_id, task.query, success=True, result=str(result) if result else None
                            )
                            await tauri_bridge.record_task_for_gui(
                                task_id, task.query, "completed",
                                result=str(result) if result else None,
                            )
                        except Exception:
                            pass

                    except asyncio.CancelledError:
                        logger.info(f"Task {task_id} was cancelled")
                        self._task_results[task_id] = {
                            "status": "cancelled",
                            "task_id": task_id,
                        }
                        await local_task_state_machine.transition(
                            task_id, TaskState.EXECUTING, TaskState.FAILED
                        )
                        raise
                    except Exception as e:
                        logger.error(f"Task {task_id} failed: {e}")
                        self._task_results[task_id] = {
                            "status": "failed",
                            "task_id": task_id,
                            "error": str(e),
                        }
                        await local_task_queue.fail(task_id, str(e))
                        await local_task_state_machine.transition(
                            task_id, TaskState.EXECUTING, TaskState.FAILED
                        )

                        # Notify GUI of failure
                        try:
                            from .tauri_bridge import tauri_bridge
                            await tauri_bridge.notify_task_complete(
                                task_id, task.query, success=False, result=str(e)
                            )
                            await tauri_bridge.record_task_for_gui(
                                task_id, task.query, "failed",
                                error=str(e),
                            )
                        except Exception:
                            pass

                    finally:
                        async with self._lock:
                            self._active_tasks.pop(task_id, None)
                        # Signal completion
                        event = self._result_events.get(task_id)
                        if event:
                            event.set()

                        # Stop resource monitoring
                        await resource_monitor.stop_monitoring(task_id)

                        await local_event_bus.publish(
                            "tasks",
                            Event(
                                "task:updated",
                                {
                                    "task_id": task_id,
                                    "status": self._task_results[task_id]["status"],
                                },
                            ),
                        )

            except asyncio.CancelledError:
                logger.info(f"Worker {worker_id} cancelled")
                raise
            except Exception as e:
                logger.error(f"Worker {worker_id} error: {e}")
                await asyncio.sleep(1.0)

        logger.info(f"Worker {worker_id} stopped")

    async def _execute_task(
        self,
        task_id: str,
        query: str,
        config: Dict[str, Any],
        user_id: str,
    ) -> Any:
        """Execute a single task using the orchestrator."""
        # Transition from current state to EXECUTING. If still in PENDING,
        # first move to PLANNING then EXECUTING.
        current_state = await local_task_state_machine.get_current_state(task_id)
        if current_state == TaskState.PENDING:
            try:
                await local_task_state_machine.transition(
                    task_id, TaskState.PENDING, TaskState.PLANNING, triggered_by="kernel"
                )
            except ValueError:
                pass  # May already be transitioning
        try:
            await local_task_state_machine.transition(
                task_id, TaskState.PLANNING, TaskState.EXECUTING, triggered_by="kernel"
            )
        except ValueError:
            # If planning->executing fails, try pending->executing as fallback
            try:
                await local_task_state_machine.transition(
                    task_id, TaskState.PENDING, TaskState.EXECUTING, triggered_by="kernel"
                )
            except ValueError:
                pass  # Best effort

        # Acquire execution lock
        lock = await local_execution_lock.acquire(task_id, owner="kernel")
        if not lock:
            raise RuntimeError(f"Could not acquire execution lock for task {task_id}")

        try:
            # Set timeout config
            from .timeouts import TimeoutConfig
            timeout_config = TimeoutConfig(
                agent_timeout_seconds=config.get("timeout", self.task_timeout),
                tool_timeout_seconds=config.get("tool_timeout", 30),
                workflow_timeout_seconds=config.get("workflow_timeout", self.task_timeout),
            )
            await local_timeout_enforcer.set_config(task_id, timeout_config)

            # Execute via orchestrator
            from ..agents.types import TaskStatus
            from ..orchestrator.context import TaskContext

            ctx = TaskContext(
                task_id=uuid.UUID(task_id),
                user_id=user_id,
                query=query,
                config=config,
            )

            result = await self._orchestrator.execute_task(
                query=query,
                config=config,
                task_id=uuid.UUID(task_id),
                user_id=user_id,
            )

            return result.output_data if hasattr(result, "output_data") else result

        finally:
            await local_execution_lock.release(task_id, lock.lock_id)
            await local_timeout_enforcer.cleanup(task_id)

    async def _gc_loop(self) -> None:
        """Periodic garbage collection of expired locks, old events, sessions, etc."""
        gc_cycle = 0
        while self._running:
            try:
                await asyncio.sleep(60.0)
                if not self._running:
                    break

                gc_cycle += 1

                # Cleanup expired locks
                count = await local_execution_lock.cleanup_expired()
                if count > 0:
                    logger.info(f"GC: cleaned up {count} expired locks")

                # Cleanup old events
                count = await local_event_bus.cleanup_old_events(max_age_days=7)
                if count > 0:
                    logger.info(f"GC: cleaned up {count} old events")

                # Cleanup old transitions
                count = await local_task_state_machine.cleanup_old_history(max_age_days=30)
                if count > 0:
                    logger.info(f"GC: cleaned up {count} old transitions")

                # Cleanup desktop session registry (every cycle)
                try:
                    from ..environments.desktop_env import desktop_session_manager
                    closed = await desktop_session_manager.close_all()
                    if closed > 0:
                        logger.info(f"GC: closed {closed} stale desktop sessions")
                except Exception:
                    pass

                # Cleanup old GUI task history (every 5 cycles = 5 min)
                if gc_cycle % 5 == 0:
                    try:
                        from .tauri_bridge import tauri_bridge
                        count = await tauri_bridge.cleanup_old_history(max_age_days=30)
                        if count > 0:
                            logger.info(f"GC: cleaned up {count} old GUI history entries")
                    except Exception:
                        pass

                # SQLite maintenance (every 10 cycles = 10 min)
                if gc_cycle % 10 == 0:
                    try:
                        stats = await sqlite_tuning.get_performance_stats()
                        logger.info(f"GC: DB size={stats.get('size_mb', 0):.1f}MB, pages={stats.get('page_count', 0)}")
                        # Run vacuum if needed
                        await sqlite_tuning.vacuum_if_needed(threshold_mb=1024.0)
                    except Exception as e:
                        logger.warning(f"GC: SQLite maintenance error: {e}")

                # Log system stats (every 10 cycles)
                if gc_cycle % 10 == 0:
                    try:
                        stats = await resource_monitor.get_system_stats()
                        logger.info(
                            f"GC: monitored_tasks={stats.get('monitored_tasks', 0)}, "
                            f"mem={stats.get('process_memory_mb', 0):.1f}MB, "
                            f"cpu={stats.get('process_cpu_percent', 0):.1f}%"
                        )
                    except Exception:
                        pass

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"GC loop error: {e}")

    def _setup_signal_handlers(self) -> None:
        """Setup graceful shutdown on signals."""
        def _signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, initiating graceful shutdown...")
            asyncio.create_task(self.stop())

        try:
            signal.signal(signal.SIGINT, _signal_handler)
            signal.signal(signal.SIGTERM, _signal_handler)
        except Exception:
            pass  # Windows may not support all signals

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def active_task_count(self) -> int:
        return len(self._active_tasks)


# Module-level singleton
_kernel_instance: Optional[AgentKernel] = None
_kernel_lock = asyncio.Lock()


async def get_kernel() -> AgentKernel:
    """Get the global AgentKernel singleton."""
    global _kernel_instance
    if _kernel_instance is None:
        async with _kernel_lock:
            if _kernel_instance is None:
                _kernel_instance = AgentKernel()
    return _kernel_instance
