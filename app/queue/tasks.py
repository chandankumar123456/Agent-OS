import asyncio
from celery import Celery
from celery.signals import worker_process_init
from ..config.settings import settings
from ..logs.logger import logger
from ..agents.types import TaskStatus
from ..runtime.runtime import AgentRuntime

redis_url = settings.REDIS_URL
if not redis_url:
    raise RuntimeError("REDIS_URL is required for Celery")

celery_app = Celery(
    "agent_os",
    broker=redis_url,
    backend=redis_url
)

# Guard against non-positive soft time limit
task_soft_time_limit = max(1, settings.TIMEOUT_DEFAULT - 30)

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

logger.info("Celery app initialized")

_worker_event_loop = None


@worker_process_init.connect
def on_worker_process_init(**kwargs):
    """Initialize AgentRuntime in each Celery worker child process.

    worker_process_init fires inside every forked child process,
    ensuring the runtime is available in the correct event loop.
    """
    global _worker_event_loop
    try:
        # Use the existing loop if available (e.g. solo pool), otherwise create one
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        _worker_event_loop = loop

        # Connect DB and Redis so runtime.load_from_db() can work
        from ..memory.long_term import db
        from ..memory.short_term import redis_client
        loop.run_until_complete(db.connect())
        loop.run_until_complete(redis_client.connect())

        loop.run_until_complete(_ensure_runtime_initialized())

        # NOTE: MCP system servers are started lazily on-demand by mcp_client_manager
        # to avoid spawning duplicate subprocesses in every Celery worker process.
        logger.info("AgentRuntime eagerly initialized in Celery worker process")
    except Exception as e:
        logger.error(f"Celery worker eager initialization failed: {e}")


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


@celery_app.task(
    name="agent_os.execute_task",
    bind=True,
    max_retries=settings.MAX_RETRIES,
    default_retry_delay=60
)
def execute_task(self, task_id: str, query: str, config: dict, user_id: str = "system"):
    logger.info(f"Executing task {task_id}: {query}")

    from ..orchestrator.core import orchestrator
    from ..orchestrator.v2.event_bus import event_bus, Event
    from uuid import UUID
    from ..memory.long_term import task_repo, db
    from ..memory.short_term import redis_client
    from ..memory.redis_pubsub import redis_pubsub_client

    async def run():
        # Re-validate connections on the persistent worker loop; no-ops if healthy
        await db.connect()
        await redis_client.connect()
        await redis_pubsub_client.connect()

        logger.info("Database and Redis connected for task execution")

        runtime = await _ensure_runtime_initialized()
        worker = runtime.get("core_planner")
        if not worker:
            raise RuntimeError(
                "Agent core_planner not found in runtime. "
                "Ensure AgentRuntime.initialize() was called at startup."
            )
        logger.info("Runtime verified: core_planner available")

        await event_bus.publish(
            f"task:{task_id}",
            Event("task.received", {"task_id": task_id, "query": query, "user_id": user_id}, source="celery"),
        )

        await task_repo.update(task_id, status=TaskStatus.RUNNING.value)
        await event_bus.publish(
            f"task:{task_id}",
            Event("task.status_changed", {"task_id": task_id, "status": "running"}, source="celery"),
        )
        try:
            result = await orchestrator.execute_task(
                query, config, task_id=UUID(task_id), user_id=user_id
            )
            if result.status.value == "success":
                await task_repo.update(
                    task_id, status=TaskStatus.COMPLETED.value, result=result.output_data
                )
                await event_bus.publish(
                    f"task:{task_id}",
                    Event("task.completed", {"task_id": task_id, "status": "completed"}, source="celery"),
                )
            else:
                await task_repo.update(
                    task_id, status=TaskStatus.FAILED.value, error=result.error_message
                )
                await event_bus.publish(
                    f"task:{task_id}",
                    Event("task.failed", {"task_id": task_id, "error": result.error_message}, source="celery"),
                )
            return result
        except Exception as exc:
            await task_repo.update(task_id, status=TaskStatus.FAILED.value, error=str(exc))
            await event_bus.publish(
                f"task:{task_id}",
                Event("task.failed", {"task_id": task_id, "error": str(exc)}, source="celery"),
            )
            raise

    loop = _worker_event_loop
    if loop is None or loop.is_closed():
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(run())

        return {
            "task_id": task_id,
            "status": result.status.value,
            "result": result.output_data
        }
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
