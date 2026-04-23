from typing import Dict, Any
from uuid import UUID
from ...agents.base import AgentOutput
from .base import ModeStrategy


class TaskMode(ModeStrategy):
    """Standard task mode: plan → execute → verify.

    Delegates to the Orchestrator's pipeline which in turn
    uses AgentRuntime for all agent execution.
    """

    async def execute(self, runtime, orchestrator, query, config, task_id, user_id):
        return await orchestrator._execute_pipeline(query, config, task_id, user_id)
