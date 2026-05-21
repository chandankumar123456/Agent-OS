import asyncio
from typing import Dict, Any, Optional
from ..agents.base import AgentInput, AgentOutput
from ..logs.logger import logger


class AgentWorker:
    """Async worker that wraps an agent instance."""

    def __init__(self, agent_id: str, config: Dict[str, Any], agent_instance):
        self.agent_id = agent_id
        self.config = config
        self.agent_instance = agent_instance
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._health = {"status": "healthy", "last_heartbeat": None}

    async def start(self):
        if self._running:
            return
        self._running = True
        logger.info(f"AgentWorker {self.agent_id} started")

    async def stop(self):
        if not self._running:
            return
        self._running = False
        logger.info(f"AgentWorker {self.agent_id} stopped")

    async def execute(self, input_data: AgentInput) -> AgentOutput:
        """Execute agent directly."""
        try:
            result = await self.agent_instance.execute(input_data)
            self._health["last_heartbeat"] = asyncio.get_event_loop().time()
            return result
        except Exception as e:
            logger.error(f"AgentWorker {self.agent_id} execution error: {e}")
            from ..agents.base import AgentStatus
            return AgentOutput(
                task_id=input_data.task_id,
                step_id=input_data.step_id,
                status=AgentStatus.FAILURE,
                error_type="execution_error",
                error_message=str(e),
                recoverable=True,
            )

    async def health(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "status": self._health["status"],
            "running": self._running,
            "config": self.config,
        }
