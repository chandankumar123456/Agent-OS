import asyncio
import os
from typing import Dict, Any, List, Optional
from ..logs.logger import logger
from ..orchestrator.errors import AgentOSError, UnrecoverableError, ErrorCode, ErrorType
from .worker import AgentWorker
from .factory import AgentFactory
from .pool import AgentPool
from ..runtime.mode import get_runtime_mode, RuntimeMode


class AgentRuntime:
    """Singleton registry mapping agent_id -> AgentWorker. Manages lifecycle.

    This is the ONLY execution entry point for all agent operations.
    No other module may instantiate agents directly.

    AgentRuntime is a pure agent registry: register(), get(), list_active(),
    shutdown_all(). It does NOT own gRPC or execution -- the kernel handles that.
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
            from ..orchestrator.errors import UnrecoverableError, ErrorCode, ErrorType
            cls._UnrecoverableError = UnrecoverableError
            cls._ErrorCode = ErrorCode
            cls._ErrorType = ErrorType
        return cls._instance

    async def initialize(self):
        """Eagerly register core system agents. Called once at app startup.

        Idempotent: safe to call multiple times. Subsequent calls are no-ops.
        """
        async with self._init_lock:
            if self._initialized:
                logger.debug("AgentRuntime.initialize() called but already initialized; skipping")
                return

            mode = get_runtime_mode()
            logger.info(f"AgentRuntime initializing core agents... (mode={mode})")

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

            # Load additional agents from DB
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
        self._workers.clear()
        self._register_locks.clear()
        self._initialized = False
        logger.info("AgentRuntime reset")

    def is_grpc_mode(self) -> bool:
        """Check if runtime is in gRPC mode.

        Returns:
            bool: True if gRPC mode, False if HTTP mode
        """
        try:
            mode = get_runtime_mode()
            return mode == RuntimeMode.GRPC
        except Exception:
            return False

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
        """Load agents from database and register them.

        If an agent has a specific version configured, load that version's
        parameters (system_prompt, model, etc.) from the agent_versions table.
        """
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
                "agent_key": agent.agent_key,
            }
            # If a non-default version is specified, resolve versioned config
            version = agent.version
            if version and version != "1.0.0":
                try:
                    versioned = await agent_repo.get_version(agent.agent_key, version)
                    if versioned:
                        config["system_prompt"] = versioned.system_prompt
                        config["model"] = versioned.model
                        config["temperature"] = versioned.temperature
                        config["max_tokens"] = versioned.max_tokens
                        config["tools"] = versioned.tools or []
                        logger.info(
                            f"Loaded agent {agent.agent_key} version {version} from DB"
                        )
                except Exception as e:
                    logger.warning(
                        f"Failed to load version {version} for agent {agent.agent_key}: {e}"
                    )
            try:
                await self.register(agent.agent_key, config)
            except Exception as e:
                logger.warning(f"Failed to load agent {agent.agent_key} from DB: {e}")

    async def load_agent_version(self, agent_key: str, version: str):
        """Explicitly load a specific agent version into the runtime.

        Creates or updates the worker for the given agent_key using the
        versioned configuration from the database.
        """
        from ..memory.long_term import agent_repo
        versioned = await agent_repo.get_version(agent_key, version)
        if not versioned:
            raise UnrecoverableError(
                f"Version {version} not found for agent {agent_key}",
                error_type=ErrorType.VALIDATION_ERROR,
                code=ErrorCode.AGENT_NOT_FOUND
            )
        config = {
            "name": versioned.name,
            "role": versioned.role,
            "system_prompt": versioned.system_prompt,
            "model": versioned.model,
            "temperature": versioned.temperature,
            "max_tokens": versioned.max_tokens,
            "tools": versioned.tools or [],
            "version": versioned.version,
            "agent_key": agent_key,
        }
        # Reset worker so the new version is picked up on next resolve
        worker = self.get(agent_key)
        if worker:
            await worker.stop()
            self._workers.pop(agent_key, None)
        await self.register(agent_key, config)
        logger.info(f"Runtime loaded agent {agent_key} version {version}")
