import asyncio
from typing import Dict, Any, List, Optional
from ..logs.logger import logger
from ..mcp.protocol import mcp_protocol
from .worker import AgentWorker
from .factory import AgentFactory
from .pool import AgentPool


class AgentRuntime:
    """Singleton registry mapping agent_id → AgentWorker. Manages lifecycle.

    This is the ONLY execution entry point for all agent operations.
    No other module may instantiate agents directly.
    """

    _instance = None

    def __new__(cls, max_agents: int = 100):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._workers: Dict[str, AgentWorker] = {}
            cls._instance._factory = AgentFactory()
            cls._instance._pool = AgentPool(max_agents)
            cls._instance._initialized = False
        return cls._instance

    async def initialize(self):
        """Eagerly register core system agents. Called once at app startup."""
        if self._initialized:
            return
        for core_type in ("planner", "executor", "verifier"):
            agent_id = f"core_{core_type}"
            if agent_id not in self._workers:
                await self.register(agent_id, {"role": core_type})
        self._initialized = True
        logger.info("AgentRuntime initialized with core agents")

    def reset(self):
        """Clear all workers. Used ONLY for test isolation."""
        for worker in list(self._workers.values()):
            if worker._task and not worker._task.done():
                worker._task.cancel()
        self._workers.clear()
        self._initialized = False
        logger.info("AgentRuntime reset")

    async def register(self, agent_id: str, config: Dict[str, Any]) -> AgentWorker:
        """Register and start a new agent worker."""
        if agent_id in self._workers:
            logger.warning(f"Agent {agent_id} already registered, returning existing")
            return self._workers[agent_id]

        await self._pool.acquire(agent_id)

        try:
            agent_type = config.get("role", "custom")
            agent_instance = self._factory.create_agent(agent_type, config)
            worker = AgentWorker(agent_id, config, agent_instance)
            await worker.start()
            self._workers[agent_id] = worker

            # Register worker with MCP protocol so it can receive messages
            await mcp_protocol.router.register(agent_id, worker.on_message)

            logger.info(f"Registered agent {agent_id} of type {agent_type}")
            return worker
        except Exception:
            self._pool.release(agent_id)
            raise

    def get(self, agent_id: str) -> Optional[AgentWorker]:
        """Get an agent worker by ID. Returns None if not registered."""
        return self._workers.get(agent_id)

    def list_active(self) -> List[Dict[str, Any]]:
        """List all active workers."""
        return [
            {
                "agent_id": wid,
                "config": worker.config,
                "running": worker._running,
            }
            for wid, worker in self._workers.items()
        ]

    async def shutdown_all(self):
        """Stop all workers."""
        for agent_id, worker in list(self._workers.items()):
            await mcp_protocol.router.unregister(agent_id)
            await worker.stop()
            self._pool.release(agent_id)
        self._workers.clear()
        self._initialized = False
        logger.info("All agent workers shutdown")

    async def load_from_db(self):
        """Load agents from database and register them."""
        from ..memory.long_term import agent_repo
        agents = await agent_repo.list_all()
        for agent in agents:
            config = {
                "name": agent.name,
                "role": agent.role,
                "system_prompt": agent.system_prompt,
                "model": agent.model,
                "temperature": agent.temperature,
                "max_tokens": agent.max_tokens,
                "tools": agent.tools or [],
            }
            await self.register(agent.agent_key, config)
