import asyncio
from uuid import uuid4

from app.orchestrator.core import Orchestrator
from app.api.routes.tasks import use_celery


def test_use_celery_defaults_to_enabled():
    assert use_celery() is True


def test_execute_task_preserves_provided_task_id():
    orchestrator = Orchestrator()
    provided_task_id = uuid4()

    async def run():
        result = await orchestrator.execute_task("test query", {}, task_id=provided_task_id)
        return result

    result = asyncio.run(run())

    assert result.task_id == provided_task_id
