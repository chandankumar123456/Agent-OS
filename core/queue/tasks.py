import asyncio
import os
import sys
from celery import Celery
from celery.signals import worker_process_init
from ..config.settings import settings
from ..logs.logger import logger
from ..agents.types import TaskStatus
from ..runtime.runtime import AgentRuntime
from ..orchestrator.errors import ErrorType, ErrorCode, UnrecoverableError, AgentOSError


def _is_desktop_mode() -> bool:
    """Check if running in desktop-native gRPC mode."""
    mode = os.environ.get("AGENTOS_RUNTIME_MODE", os.environ.get("RUNTIME_MODE", "http"))
    return mode.lower() == "grpc"


redis_url = settings.REDIS_URL

# In desktop mode, Celery is completely disabled — no broker, no backend, no workers.
# Tasks run directly in the AgentKernel's asyncio event loop.
celery_app = None
if not _is_desktop_mode() and redis_url:
    celery_app = Celery(
        "agent_os",
        broker=redis_url,
        backend=redis_url
    )
    logger.info("Celery app initialized (HTTP mode)")
elif _is_desktop_mode():
    logger.info("Celery disabled in desktop-native mode")

# Guard against non-positive soft time limit
task_soft_time_limit = max(1, settings.TIMEOUT_DEFAULT - 30)

if celery_app:
    celery_app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        worker_prefetch_multiplier=1,
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        result_expires=3600,
        task_soft_time_limit=task_soft_time_limit,
        task_time_limit=settings.TIMEOUT_DEFAULT,
    )
    logger.info("Celery configuration applied")
else:
    logger.info("Celery not configured (desktop mode or REDIS_URL missing)")

_worker_event_loop = None


@worker_process_init.connect
def on_worker_process_init(**kwargs):
    """Initialize event loop policy in each Celery worker child process.

    worker_process_init fires inside every forked child process,
    ensuring proper event loop configuration. Actual connections
    and runtime initialization happen lazily when execute_task() runs.
    """
    global _worker_event_loop

    # Windows: Force ProactorEventLoop to support asyncio subprocess (required by Playwright)
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    try:
        # Use the existing loop if available (e.g. solo pool), otherwise create one
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        _worker_event_loop = loop
        # Don't eagerly connect — let execute_task() do it lazily
        logger.info("Celery worker: event loop policy set")
    except Exception as e:
        logger.error(f"Celery worker init failed: {e}")


async def _ensure_runtime_initialized() -> AgentRuntime:
    """Ensure AgentRuntime singleton is initialized with core agents.

    This is safe to call multiple times (idempotent). Must be invoked
    in every process boundary that uses the runtime (FastAPI lifespan,
    Celery worker, standalone scripts, tests).
    """
    runtime = AgentRuntime()
    if not runtime._initialized:
        logger.info("AgentRuntime not initialized in this process; initializing now")
        await runtime.initialize()
        active = runtime.list_active()
        logger.info(f"AgentRuntime initialized in Celery worker with agents: {[a['agent_id'] for a in active]}")
    else:
        logger.debug("AgentRuntime already initialized; skipping redundant initialization")
    return runtime


def _celery_task(*args, **kwargs):
    """Decorator that wraps celery_app.task when available, otherwise no-op."""
    def decorator(func):
        if celery_app:
            return celery_app.task(*args, **kwargs)(func)
        # In desktop mode, return the function as-is (no Celery wrapping)
        return func
    return decorator


async def execute_task_async(task_id: str, query: str, config: dict, user_id: str = "system") -> dict:
    """Execute a task asynchronously (used by AgentKernel in desktop mode).

    This is the canonical task execution function that works both:
    - In desktop mode: called directly by AgentKernel._execute_task()
    - In HTTP mode: wrapped by Celery's execute_task()
    """
    from ..orchestrator.core import orchestrator
    from ..orchestrator.event_bus import event_bus, Event
    from uuid import UUID
    from ..memory.long_term import task_repo

    logger.info(f"Executing task {task_id}: {query}")

    await event_bus.publish(
        f"task:{task_id}",
        Event("task.received", {"task_id": task_id, "query": query, "user_id": user_id}, source="kernel"),
    )

    try:
        await task_repo.update(task_id, status=TaskStatus.RUNNING.value)
    except Exception as e:
        logger.warning(f"Task status update failed: {e}")

    await event_bus.publish(
        f"task:{task_id}",
        Event("task.status_changed", {"task_id": task_id, "status": "running"}, source="kernel"),
    )

    try:
        # Enforce hard timeout on the entire task execution
        task_timeout = config.get("timeout", settings.TIMEOUT_DEFAULT)
        result = await asyncio.wait_for(
            orchestrator.execute_task(query, config, task_id=UUID(task_id), user_id=user_id),
            timeout=task_timeout,
        )
        if result.status.value == "success":
            try:
                await task_repo.update(
                    task_id, status=TaskStatus.COMPLETED.value, result=result.output_data
                )
            except Exception as e:
                logger.warning(f"Task completion update failed: {e}")
            await event_bus.publish(
                f"task:{task_id}",
                Event("task.status_changed", {"task_id": task_id, "status": "completed"}, source="kernel"),
            )
            return {
                "task_id": task_id,
                "status": result.status.value,
                "result": result.output_data,
            }
        else:
            try:
                await task_repo.update(
                    task_id, status=TaskStatus.FAILED.value, error=result.error_message
                )
            except Exception as e:
                logger.warning(f"Task failure update failed: {e}")
            await event_bus.publish(
                f"task:{task_id}",
                Event("task.status_changed", {"task_id": task_id, "status": "failed", "error": result.error_message}, source="kernel"),
            )
            return {
                "task_id": task_id,
                "status": "failed",
                "error": result.error_message,
            }
    except asyncio.TimeoutError:
        error_msg = f"Task timed out after {task_timeout}s"
        logger.error(error_msg, task_id=task_id)
        try:
            await task_repo.update(task_id, status=TaskStatus.FAILED.value, error=error_msg)
        except Exception:
            pass
        await event_bus.publish(
            f"task:{task_id}",
            Event("task.status_changed", {"task_id": task_id, "status": "failed", "error": error_msg, "reason": "timeout"}, source="kernel"),
        )
        return {
            "task_id": task_id,
            "status": "failed",
            "error": error_msg,
        }
    except Exception as exc:
        logger.error(f"Task {task_id} failed: {exc}")
        try:
            await task_repo.update(task_id, status=TaskStatus.FAILED.value, error=str(exc))
        except Exception:
            pass
        await event_bus.publish(
            f"task:{task_id}",
            Event("task.status_changed", {"task_id": task_id, "status": "failed", "error": str(exc)}, source="kernel"),
        )
        return {
            "task_id": task_id,
            "status": "failed",
            "error": str(exc),
        }


@_celery_task(
    name="agent_os.execute_task",
    bind=True,
    max_retries=settings.MAX_RETRIES,
    default_retry_delay=60
)
def execute_task(self, task_id: str, query: str, config: dict, user_id: str = "system"):
    """Celery task wrapper for execute_task_async.

    In desktop mode, this function is NOT wrapped by Celery and can be
    called directly or via execute_task_async().
    """
    # Desktop mode: delegate to async function directly
    if _is_desktop_mode():
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # We're already in an async context (AgentKernel worker)
            raise RuntimeError(
                "execute_task() called synchronously in desktop mode. "
                "Use execute_task_async() instead."
            )
        return loop.run_until_complete(execute_task_async(task_id, query, config, user_id))

    # HTTP mode: Celery worker process
    from ..memory.long_term import db
    from ..memory.short_term import redis_client
    from ..memory.redis_pubsub import redis_pubsub_client

    async def run():
        # Re-validate connections on the persistent worker loop
        await db.connect()
        await redis_client.connect()
        await redis_pubsub_client.connect()
        return await execute_task_async(task_id, query, config, user_id)

    loop = _worker_event_loop
    if loop is None or loop.is_closed():
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(run())
        return result
    except Exception as e:
        logger.error(f"Task execution failed: {e}")
        retries = getattr(self.request, 'retries', 0)
        max_retries = getattr(self, 'max_retries', settings.MAX_RETRIES)

        # Update DB to FAILED before final return so status is never stuck
        try:
            loop.run_until_complete(task_repo.update(task_id, status=TaskStatus.FAILED.value, error=str(e)))
        except Exception as db_err:
            logger.error(f"Failed to persist final failure status: {db_err}")

        if retries < max_retries:
            logger.info(f"Retrying task {task_id}, attempt {retries + 1}")
            raise self.retry(exc=e, countdown=60 * (2 ** retries))

        return {
            "task_id": task_id,
            "status": "failed",
            "error": str(e)
        }
