from typing import Dict, Any, Optional
from uuid import UUID
from ..agents.base import AgentOutput
from ..logs.logger import logger


class PipelineExecutor:
    """Thin compatibility wrapper — delegates to AgentLoop.

    The AgentLoop (``app/orchestrator/agent_loop.py``) is the single
    execution entry point for all task modes.  This class exists for
    backward compatibility with any code that still references
    ``PipelineExecutor.execute()`` directly.
    """

    def __init__(self, orchestrator):
        self.orchestrator = orchestrator

    async def execute(
        self,
        query: str,
        config: Optional[Dict[str, Any]] = None,
        task_id: Optional[UUID] = None,
        user_id: Optional[str] = None,
    ) -> AgentOutput:
        """Execute a task through the AgentLoop.

        All planning, DAG execution, observation, and replanning is
        handled internally by AgentLoop.run().
        """
        logger.info(
            f"[PipelineExecutor] Delegating to AgentLoop for query: {query[:80]}"
        )
        return await self.orchestrator.agent_loop.run(
            query, config, task_id, user_id,
        )
