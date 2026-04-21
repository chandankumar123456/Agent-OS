from celery import Celery
from ..config.settings import settings
from ..logs.logger import logger
from ..agents.types import TaskStatus

redis_url = settings.REDIS_URL or "redis://localhost:6379/0"

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
)

logger.info("Celery app initialized")


@celery_app.task(name="agent_os.execute_task", bind=True)
def execute_task(self, task_id: str, query: str, config: dict, user_id: str = "system"):
    logger.info(f"Executing task {task_id}: {query}")
    
    try:
        from ..orchestrator.core import orchestrator
        import asyncio
        
        from uuid import UUID
        from ..memory.long_term import task_repo

        async def run():
            await task_repo.update(task_id, status=TaskStatus.RUNNING.value)
            try:
                try:
                    result = await orchestrator.execute_task(query, config, task_id=UUID(task_id), user_id=user_id)
                except TypeError:
                    result = await orchestrator.execute_task(query, config, task_id=UUID(task_id))
                if result.status.value == "success":
                    await task_repo.update(task_id, status=TaskStatus.COMPLETED.value, result=result.output_data)
                else:
                    await task_repo.update(task_id, status=TaskStatus.FAILED.value, error=result.error_message)
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
        return {
            "task_id": task_id,
            "status": "failed",
            "error": str(e)
        }
