import asyncio
import os
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
    _lock = asyncio.Lock()

    def __new__(cls, max_agents: int = 100):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._workers: Dict[str, AgentWorker] = {}
            cls._instance._factory = AgentFactory()
            cls._instance._pool = AgentPool(max_agents)
            cls._instance._initialized = False
            cls._instance._init_lock = asyncio.Lock()
            cls._instance._register_locks: Dict[str, asyncio.Lock] = {}
            cls._instance._init_mutex_value = None
        return cls._instance

    async def initialize(self):
        """Eagerly register core system agents. Called once at app startup.

        Idempotent: safe to call multiple times. Subsequent calls are no-ops.
        Uses a Redis mutex to avoid duplicate DB writes across processes.
        """
        async with self._init_lock:
            if self._initialized:
                logger.debug("AgentRuntime.initialize() called but already initialized; skipping")
                return
            logger.info("AgentRuntime initializing core agents...")

            # Try to acquire a cross-process Redis mutex for DB writes
            acquired_mutex = False
            try:
                from ..memory.short_term import redis_client
                if redis_client.client:
                    mutex_value = f"{os.getpid()}:{asyncio.get_running_loop().time()}"
                    acquired = await redis_client.client.set(
                        "agentos:runtime:init_mutex", mutex_value, nx=True, ex=3600
                    )
                    if acquired:
                        self._init_mutex_value = mutex_value
                        acquired_mutex = True
                        logger.info("Acquired runtime initialization mutex")
                    else:
                        logger.info("Runtime initialization mutex held by another process; skipping DB writes")
                else:
                    # Redis unavailable (e.g., tests) — proceed locally
                    acquired_mutex = True
            except Exception as e:
                logger.warning(f"Redis mutex check failed, proceeding with local init: {e}")
                acquired_mutex = True

            if acquired_mutex:
                for core_type in ("planner", "executor", "verifier"):
                    agent_id = f"core_{core_type}"
                    if agent_id not in self._workers:
                        try:
                            await self.register(agent_id, {"role": core_type})
                            logger.info(f"Registered core agent: {agent_id}")
                        except Exception as e:
                            logger.error(f"Failed to register core agent {agent_id}: {e}")
                    else:
                        logger.debug(f"Core agent already registered: {agent_id}")

                # Persist core agents to database so they appear in API listings
                try:
                    from ..memory.long_term import agent_repo
                    for core_type in ("planner", "executor", "verifier"):
                        agent_id = f"core_{core_type}"
                        await agent_repo.upsert(
                            agent_key=agent_id,
                            name=agent_id,
                            role=core_type,
                            status="active",
                        )
                    logger.info("Core agents persisted to database")
                except Exception as e:
                    logger.warning(f"Failed to persist core agents to database: {e}")

            # Load any additional agents from database into runtime (always do this)
            try:
                await self.load_from_db()
                logger.info("Agents loaded from database into runtime")
            except Exception as e:
                logger.warning(f"Failed to load agents from database: {e}")

            self._initialized = True
            logger.info("AgentRuntime initialized with core agents")

    async def ensure_initialized(self) -> "AgentRuntime":
        """Convenience wrapper around initialize(). Returns self."""
        await self.initialize()
        return self

    def reset(self):
        """Clear all workers. Used ONLY for test isolation."""
        for worker in list(self._workers.values()):
            if worker._task and not worker._task.done():
                worker._task.cancel()
        for agent_id in list(self._workers.keys()):
            try:
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(mcp_protocol.router.unregister(agent_id))
                except RuntimeError:
                    pass
            except Exception as e:
                logger.warning(f"Failed to unregister {agent_id} during reset: {e}")
        self._workers.clear()
        self._register_locks.clear()
        self._initialized = False
        # Best-effort release of Redis mutex so next test/process can acquire it
        if self._init_mutex_value:
            try:
                loop = asyncio.get_running_loop()
                from ..memory.short_term import redis_client
                if redis_client.client:
                    loop.create_task(redis_client.client.delete("agentos:runtime:init_mutex"))
            except Exception:
                pass
            self._init_mutex_value = None
        logger.info("AgentRuntime reset")

    async def register(self, agent_id: str, config: Dict[str, Any]) -> AgentWorker:
        """Register and start a new agent worker."""
        # Per-ID lock prevents duplicate registration races
        if agent_id not in self._register_locks:
            self._register_locks[agent_id] = asyncio.Lock()
        async with self._register_locks[agent_id]:
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
                # Remove worker if it was partially inserted
                self._workers.pop(agent_id, None)
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
        errors = []
        for agent_id, worker in list(self._workers.items()):
            try:
                await mcp_protocol.router.unregister(agent_id)
            except Exception as e:
                errors.append((agent_id, f"unregister: {e}"))
            try:
                await worker.stop()
            except Exception as e:
                errors.append((agent_id, f"stop: {e}"))
            try:
                self._pool.release(agent_id)
            except Exception as e:
                errors.append((agent_id, f"release: {e}"))
        self._workers.clear()
        self._initialized = False
        if errors:
            logger.warning(f"Shutdown errors: {errors}")
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
                "version": agent.version or "1.0.0",
            }
            try:
                await self.register(agent.agent_key, config)
            except Exception as e:
                logger.warning(f"Failed to load agent {agent.agent_key} from DB: {e}")
