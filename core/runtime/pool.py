import asyncio
from typing import Dict, Any
from ..logs.logger import logger


class AgentPool:
    """Manages a pool of agent workers with concurrency limits.

    Uses a semaphore to ensure no more than max_agents workers
    are actively processing at any given time.
    """

    def __init__(self, max_agents: int = 100):
        self.max_agents = max_agents
        self._semaphore = asyncio.Semaphore(max_agents)
        self._workers: Dict[str, Any] = {}
        self._queue: asyncio.Queue = asyncio.Queue()

    async def acquire(self, agent_id: str) -> bool:
        """Acquire a slot in the pool for an agent."""
        if agent_id in self._workers:
            logger.debug(f"AgentPool: {agent_id} already acquired")
            return True
        await self._semaphore.acquire()
        self._workers[agent_id] = True
        logger.debug(f"AgentPool: acquired slot for {agent_id}")
        return True

    def release(self, agent_id: str):
        """Release a slot in the pool."""
        if agent_id not in self._workers:
            logger.debug(f"AgentPool: {agent_id} not in pool, ignoring release")
            return
        del self._workers[agent_id]
        self._semaphore.release()
        logger.debug(f"AgentPool: released slot for {agent_id}")

    def active_count(self) -> int:
        return len(self._workers)

    def is_full(self) -> bool:
        return self.active_count() >= self.max_agents
