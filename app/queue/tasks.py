import asyncio
from celery import Celery
from ..config.settings import settings
from ..logs.logger import logger
from ..agents.types import TaskStatus

redis_url = settings.REDIS_URL
if not redis_url:
    raise RuntimeError("REDIS_URL is required for Celery")

celery_app = Celery(
    "agent_os",
    broker=redis_url,
    backend=redis_url
)

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
    task_soft_time_limit=settings.TIMEOUT_DEFAULT - 30,
    task_time_limit=settings.TIMEOUT_DEFAULT,
)

logger.info("Celery app initialized")


@celery_app.task(
    name="agent_os.execute_task",
    bind=True,
    max_retries=settings.MAX_RETRIES,
    default_retry_delay=60
)
def execute_task(self, task_id: str, query: str, config: dict, user_id: str = "system"):
    logger.info(f"Executing task {task_id}: {query}")

    try:
        from ..orchestrator.core import orchestrator
        from uuid import UUID
        from ..memory.long_term import task_repo, db

        async def run():
            await db.connect()
            logger.info("Database session available for task execution")

            from ..memory.short_term import redis_client
            await redis_client.connect()
            logger.info("Redis connected for task execution")

            await task_repo.update(task_id, status=TaskStatus.RUNNING.value)
            try:
                result = await orchestrator.execute_task(
                    query, config, task_id=UUID(task_id), user_id=user_id
                )
                if result.status.value == "success":
                    await task_repo.update(
                        task_id, status=TaskStatus.COMPLETED.value, result=result.output_data
                    )
                else:
                    await task_repo.update(
                        task_id, status=TaskStatus.FAILED.value, error=result.error_message
                    )
                return result
            except Exception as exc:
                await task_repo.update(task_id, status=TaskStatus.FAILED.value, error=str(exc))
                raise

        result = asyncio.run(run())

        return {
            "task_id": task_id,
            "status": result.status.value,
            "result": result.output_data
        }
    except Exception as e:
        logger.error(f"Task execution failed: {e}")
        retries = getattr(self.request, 'retries', 0)
        max_retries = getattr(self, 'max_retries', settings.MAX_RETRIES)

        if retries < max_retries:
            logger.info(f"Retrying task {task_id}, attempt {retries + 1}")
            raise self.retry(exc=e, countdown=60 * (2 ** retries))

        return {
            "task_id": task_id,
            "status": "failed",
            "error": str(e)
        }
