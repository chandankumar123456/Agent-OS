import asyncio
from uuid import uuid4

import pytest

from app.memory.long_term import db
from app.memory.long_term import task_repo, step_repo


def test_persisted_task_lookup_includes_steps_when_present():
    task_id = str(uuid4())

    async def run():
        try:
            await db.connect()
        except ModuleNotFoundError:
            pytest.skip("asyncpg is not installed in this environment")
        await task_repo.create(task_id=task_id, query="persist me", status="completed")
        await step_repo.create(step_id=str(uuid4()), task_id=task_id, step_number=0, agent_type="executor", input_data={"step": "do it"})
        steps = await step_repo.get_by_task(task_id)
        await db.disconnect()
        return steps

    steps = asyncio.run(run())

    assert len(steps) == 1
    assert steps[0].agent_type == "executor"
