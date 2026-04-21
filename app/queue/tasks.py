from celery import Celery
from ..config.settings import settings
from ..logs.logger import logger

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
def execute_task(self, task_id: str, query: str, config: dict):
    logger.info(f"Executing task {task_id}: {query}")
    
    try:
        from ..orchestrator.core import orchestrator
        import asyncio
        
        from uuid import UUID

        result = asyncio.run(orchestrator.execute_task(query, config, task_id=UUID(task_id)))
        
        return {
            "task_id": task_id,
            "status": "success",
            "result": result.output_data
        }
    except Exception as e:
        logger.error(f"Task execution failed: {e}")
        return {
            "task_id": task_id,
            "status": "failed",
            "error": str(e)
        }
