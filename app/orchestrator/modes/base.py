from abc import ABC, abstractmethod
from typing import Dict, Any
from uuid import UUID
from ...agents.base import AgentOutput
from ...runtime.runtime import AgentRuntime


class ModeStrategy(ABC):
    """Abstract base for execution mode strategies.

    Each mode receives the AgentRuntime (sole execution entry point)
    and the Orchestrator (for helper methods like tracing, context,
    persistence). Modes MUST delegate agent execution to Runtime.
    """

    @abstractmethod
    async def execute(
        self,
        runtime: AgentRuntime,
        orchestrator,
        query: str,
        config: Dict[str, Any],
        task_id: UUID,
        user_id: str,
    ) -> AgentOutput:
        """Execute the mode strategy and return the result."""
        pass
