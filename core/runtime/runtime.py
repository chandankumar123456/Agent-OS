import asyncio
import os
from typing import Dict, Any, List, Optional
from ..logs.logger import logger
from ..orchestrator.errors import UnrecoverableError, ErrorCode, ErrorType
from .worker import AgentWorker
from .factory import AgentFactory
from .pool import AgentPool

# gRPC client imports (core dependency, always available)
from ..proto.grpc_client import GRPCClient, GRPCClientConfig
from ..runtime.mode import get_runtime_mode, get_grpc_client_config, RuntimeMode
from ..config.mode import get_grpc_address
GRPC_AVAILABLE = True


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
            # gRPC client (optional, only when in GRPC mode)
            cls._instance._grpc_client: Optional[GRPCClient] = None
            cls._instance._grpc_mode = False
            from ..orchestrator.errors import UnrecoverableError, ErrorCode, ErrorType
            cls._UnrecoverableError = UnrecoverableError
            cls._ErrorCode = ErrorCode
            cls._ErrorType = ErrorType
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

            # Initialize gRPC client if in grpc mode
            if GRPC_AVAILABLE:
                try:
                    mode = get_runtime_mode()
                    self._grpc_mode = (mode == RuntimeMode.GRPC)
                    if self._grpc_mode:
                        logger.info("AgentRuntime initializing in gRPC mode")
                        config = get_grpc_client_config()
                        self._grpc_client = GRPCClient(config)
                        await self._grpc_client.connect()
                        logger.info(f"gRPC client connected in mode: {mode}")
                    else:
                        logger.info(f"AgentRuntime initializing in HTTP mode (mode={mode})")
                except Exception as e:
                    logger.warning(f"Failed to initialize gRPC client: {e}")
                    self._grpc_mode = False
            else:
                logger.info("AgentRuntime initializing without gRPC support")

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

                # Load additional agents from DB (inside mutex to prevent duplicate registration)
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

    async def initialize_grpc_client(self) -> bool:
        """Initialize gRPC client when in GRPC mode.
        
        Returns:
            bool: True if gRPC client initialized successfully, False otherwise
        """
        if not GRPC_AVAILABLE:
            logger.warning("gRPC not available (import error)")
            return False

        try:
            mode = get_runtime_mode()
            # mode is a RuntimeMode enum from config.mode
            self._grpc_mode = (mode == RuntimeMode.GRPC)

            if not self._grpc_mode:
                logger.info("Runtime mode is HTTP, skipping gRPC client initialization")
                return False

            # Initialize gRPC client
            grpc_address = get_grpc_address()
            host, port_str = grpc_address.rsplit(":", 1)
            port = int(port_str)

            config = GRPCClientConfig(
                host=host,
                port=port,
                connection_timeout=5.0,
                keepalive_timeout=60
            )

            self._grpc_client = GRPCClient(config)
            await self._grpc_client.connect()

            logger.info(f"gRPC client initialized for mode={mode}, address={grpc_address}")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize gRPC client: {e}")
            self._grpc_client = None
            self._grpc_mode = False
            return False

    async def shutdown_grpc_client(self):
        """Shutdown gRPC client if initialized."""
        if self._grpc_client and self._grpc_client.is_connected:
            try:
                await self._grpc_client.close()
                logger.info("gRPC client shutdown")
            except Exception as e:
                logger.error(f"Failed to shutdown gRPC client: {e}")

    def is_grpc_mode(self) -> bool:
        """Check if runtime is in gRPC mode.
        
        Returns:
            bool: True if gRPC mode, False if HTTP mode
        """
        return self._grpc_mode

    async def execute_task_via_grpc(
        self,
        task_id: str,
        task_type: str = "mcp_tool_call",
        payload: str = "",
        timeout_seconds: int = 300,
        metadata: Optional[Dict[str, str]] = None
    ):
        """Execute a task via gRPC.
        
        Args:
            task_id: Task identifier
            task_type: Type of task (default: "mcp_tool_call")
            payload: Task payload (JSON string)
            timeout_seconds: Task timeout in seconds
            metadata: Optional task metadata
            
        Returns:
            Task execution response
            
        Raises:
            RuntimeError: If gRPC client not initialized
        """
        if not self._grpc_client:
            raise RuntimeError("gRPC client not initialized. Call initialize_grpc_client() first.")

        if not self._grpc_client.is_connected:
            raise RuntimeError("gRPC client not connected.")

        return await self._grpc_client.worker.execute_task(
            task_id=task_id,
            task_type=task_type,
            payload=payload,
            timeout_seconds=timeout_seconds,
            metadata=metadata or {}
        )

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
        """Stop all workers and gRPC client."""
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

        # Close gRPC client if connected
        if self._grpc_client:
            try:
                await self._grpc_client.close()
                logger.info("gRPC client closed")
            except Exception as e:
                errors.append(("grpc", f"close: {e}"))

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

    def get_grpc_client(self) -> Optional[Any]:
        """Get gRPC client if available."""
        return self._grpc_client if self._grpc_client is not None else None
