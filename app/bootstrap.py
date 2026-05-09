"""AgentOS Bootstrap Module — Shared initialization for all runtime modes.

This module provides the canonical initialization sequence for AgentOS,
used by both the FastAPI web server (app.main) and the desktop-native
entry point (app.desktop_entry).

Design Principles:
- No FastAPI dependencies in core bootstrapping
- Idempotent initialization (safe to call multiple times)
- Clear separation between core runtime and web layer
- Support for both HTTP (cloud) and gRPC (local-native) modes
"""

import asyncio
import os
import signal
import sys
from contextlib import asynccontextmanager
from typing import Dict, Any, List, Optional, Callable

# Core runtime imports (no FastAPI)
from .config.settings import settings
from .logs.logger import logger
from .runtime.runtime import AgentRuntime
from .runtime.mode import RuntimeMode, get_runtime_mode, is_grpc_mode
from .migrations.runner import run_pending_migrations
from .mcp.monitor import mcp_health_monitor

# Optional imports for gRPC mode
try:
    from .proto.grpc_client import GRPCClient, GRPCClientConfig
    GRPC_AVAILABLE = True
except ImportError:
    GRPC_AVAILABLE = False


class BootstrapContext:
    """Context object holding all initialized runtime components.
    
    This is the canonical container for runtime state, passed between
    bootstrap phases and available throughout the application lifecycle.
    """
    
    def __init__(self):
        self.runtime: Optional[AgentRuntime] = None
        self.grpc_client: Optional[Any] = None
        self.initialized: List[str] = []
        self._shutdown_hooks: List[Callable] = []
        self._is_shutting_down = False
        
    def add_shutdown_hook(self, hook: Callable, name: str = None):
        """Register a shutdown hook to be called during cleanup."""
        self._shutdown_hooks.append((hook, name))
        
    async def shutdown(self):
        """Execute all shutdown hooks in reverse order."""
        if self._is_shutting_down:
            return
        self._is_shutting_down = True
        
        logger.info("AgentOS shutting down...")
        errors = []
        
        # Execute hooks in reverse order (LIFO)
        for hook, name in reversed(self._shutdown_hooks):
            try:
                if asyncio.iscoroutinefunction(hook):
                    await hook()
                else:
                    hook()
                if name:
                    logger.info(f"Shutdown hook completed: {name}")
            except Exception as e:
                error_msg = f"Shutdown hook failed{f' ({name})' if name else ''}: {e}"
                logger.error(error_msg)
                errors.append(error_msg)
        
        if errors:
            logger.warning(f"Shutdown completed with {len(errors)} errors")
        else:
            logger.info("AgentOS shutdown complete")


async def _check_dependencies() -> None:
    """Validate required environment configuration."""
    if not settings.DATABASE_URL:
        raise RuntimeError("DATABASE_URL is required but not set")
    
    # Skip Redis check in gRPC mode (supervisor handles Redis)
    if not is_grpc_mode() and not settings.REDIS_URL:
        raise RuntimeError("REDIS_URL is required but not set")
    
    if not settings.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is required but not set")


async def _init_database(ctx: BootstrapContext) -> None:
    """Initialize database connections and run migrations."""
    from .memory.long_term import db
    
    try:
        await db.connect()
        logger.info("Database connected successfully")
        ctx.initialized.append("db")
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        raise RuntimeError(f"Database connection failed: {e}") from e
    
    try:
        await run_pending_migrations()
        logger.info("Database migrations applied")
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise RuntimeError(f"Migration failed: {e}") from e
    
    # Register shutdown hook
    async def shutdown_db():
        try:
            await db.disconnect()
            logger.info("Database disconnected")
        except Exception as e:
            logger.error(f"Database disconnect failed: {e}")
    
    ctx.add_shutdown_hook(shutdown_db, "database")


async def _init_redis(ctx: BootstrapContext) -> None:
    """Initialize Redis connections (only in HTTP mode)."""
    if is_grpc_mode():
        logger.info("Skipping Redis initialization in gRPC mode")
        return
    
    from .memory.short_term import redis_client
    
    try:
        await redis_client.connect()
        logger.info("Redis connected successfully")
        ctx.initialized.append("redis")
    except Exception as e:
        logger.error(f"Redis connection failed: {e}")
        raise RuntimeError(f"Redis connection failed: {e}") from e
    
    # Initialize Redis PubSub
    try:
        from .memory.redis_pubsub import redis_pubsub_client
        await redis_pubsub_client.connect()
        logger.info("Redis PubSub client connected")
        ctx.initialized.append("redis_pubsub")
    except Exception as e:
        logger.error(f"Redis PubSub client connection failed: {e}")
    
    # Register shutdown hooks
    async def shutdown_redis():
        try:
            await redis_client.disconnect()
            logger.info("Redis disconnected")
        except Exception as e:
            logger.error(f"Redis disconnect failed: {e}")
    
    async def shutdown_pubsub():
        if "redis_pubsub" in ctx.initialized:
            try:
                from .memory.redis_pubsub import redis_pubsub_client
                await redis_pubsub_client.disconnect()
                logger.info("Redis PubSub disconnected")
            except Exception as e:
                logger.error(f"Redis PubSub disconnect failed: {e}")
    
    ctx.add_shutdown_hook(shutdown_pubsub, "redis_pubsub")
    ctx.add_shutdown_hook(shutdown_redis, "redis")


async def _init_runtime(ctx: BootstrapContext) -> None:
    """Initialize AgentRuntime singleton."""
    try:
        runtime = AgentRuntime()
        await runtime.initialize()
        ctx.runtime = runtime
        
        # Log runtime mode
        if runtime.is_grpc_mode():
            logger.info("AgentRuntime initialized in gRPC mode")
        else:
            logger.info("AgentRuntime initialized in HTTP mode")
        
        ctx.initialized.append("runtime")
    except Exception as e:
        logger.error(f"AgentRuntime initialization failed: {e}")
        raise RuntimeError(f"AgentRuntime initialization failed: {e}") from e
    
    # Register shutdown hook
    async def shutdown_runtime():
        if ctx.runtime:
            try:
                await ctx.runtime.shutdown_all()
                logger.info("AgentRuntime shutdown")
            except Exception as e:
                logger.error(f"AgentRuntime shutdown failed: {e}")
    
    ctx.add_shutdown_hook(shutdown_runtime, "runtime")


async def _init_mcp_system(ctx: BootstrapContext) -> None:
    """Initialize MCP system servers and tool discovery."""
    # Start MCP health monitor
    try:
        mcp_health_monitor.start()
        logger.info("MCP health monitor started")
        ctx.initialized.append("mcp_monitor")
    except Exception as e:
        logger.error(f"MCP health monitor start failed: {e}")
    
    # Register built-in tools
    try:
        from .tools.builtin import register_builtin_tools
        from .tools.registry import tool_registry
        register_builtin_tools(tool_registry)
        logger.info("Built-in tools registered")
        ctx.initialized.append("builtin_tools")
    except Exception as e:
        logger.error(f"Built-in tools registration failed: {e}")
    
    # Start MCP system servers
    try:
        from .mcp.client_manager import mcp_client_manager
        await mcp_client_manager.start_system_servers()
        logger.info("MCP system servers started")
        ctx.initialized.append("mcp_servers")
    except BaseException as e:
        logger.error(f"MCP system servers start failed: {e}")
    
    # Discover MCP tools
    try:
        from .tools.registry import tool_registry
        await tool_registry.discover_mcp_tools()
        logger.info("MCP tools discovered at startup")
        ctx.initialized.append("mcp_tools_discovered")
    except Exception as e:
        logger.error(f"MCP tool discovery failed at startup: {e}")
    
    # Register shutdown hooks
    async def shutdown_mcp_servers():
        if "mcp_servers" in ctx.initialized:
            try:
                from .mcp.client_manager import mcp_client_manager
                await mcp_client_manager.disconnect_all()
                logger.info("MCP system servers stopped")
            except Exception as e:
                logger.error(f"MCP system servers stop failed: {e}")
    
    async def shutdown_mcp_monitor():
        if "mcp_monitor" in ctx.initialized:
            try:
                mcp_health_monitor.stop()
            except Exception as e:
                logger.error(f"MCP health monitor stop failed: {e}")
    
    async def shutdown_desktop_sessions():
        try:
            from .environments.desktop_env import DesktopSessionManager
            await DesktopSessionManager().close_all()
            logger.info("Desktop sessions closed")
        except Exception as e:
            logger.error(f"Desktop session close_all failed: {e}")
    
    ctx.add_shutdown_hook(shutdown_mcp_servers, "mcp_servers")
    ctx.add_shutdown_hook(shutdown_mcp_monitor, "mcp_monitor")
    ctx.add_shutdown_hook(shutdown_desktop_sessions, "desktop_sessions")


async def _init_grpc_client(ctx: BootstrapContext) -> None:
    """Initialize gRPC client for supervisor communication (gRPC mode only)."""
    if not is_grpc_mode():
        logger.info("Running in HTTP mode, skipping gRPC client initialization")
        return
    
    if not GRPC_AVAILABLE:
        logger.warning("gRPC not available (import error), skipping gRPC client")
        return
    
    try:
        grpc_config = GRPCClientConfig(
            host=settings.GRPC_HOST,
            port=settings.GRPC_PORT,
            connection_timeout=settings.GRPC_CONNECTION_TIMEOUT,
            keepalive_timeout=settings.GRPC_KEEPALIVE_TIMEOUT,
            max_send_message_length=settings.GRPC_MAX_MESSAGE_LENGTH_MB * 1024 * 1024,
            max_receive_message_length=settings.GRPC_MAX_MESSAGE_LENGTH_MB * 1024 * 1024,
        )
        grpc_client = GRPCClient(config=grpc_config)
        await grpc_client.connect()
        ctx.grpc_client = grpc_client
        ctx.initialized.append("grpc_client")
        logger.info(f"gRPC client initialized in {get_runtime_mode()} mode")
    except Exception as e:
        logger.error(f"gRPC client initialization failed: {e}")
        raise RuntimeError(f"gRPC client initialization failed: {e}") from e
    
    # Register shutdown hook
    async def shutdown_grpc():
        if ctx.grpc_client:
            try:
                await ctx.grpc_client.close()
                logger.info("gRPC client closed")
            except Exception as e:
                logger.error(f"gRPC client close failed: {e}")
    
    ctx.add_shutdown_hook(shutdown_grpc, "grpc_client")


async def bootstrap(
    skip_dependencies_check: bool = False,
    skip_database: bool = False,
    skip_redis: bool = False,
    skip_runtime: bool = False,
    skip_mcp: bool = False,
    skip_grpc: bool = False,
) -> BootstrapContext:
    """Bootstrap AgentOS runtime with all core components.
    
    This is the canonical initialization sequence for AgentOS,
    used by both HTTP (FastAPI) and gRPC (desktop-native) modes.
    
    Args:
        skip_dependencies_check: Skip environment validation
        skip_database: Skip database initialization
        skip_redis: Skip Redis initialization (auto-skipped in gRPC mode)
        skip_runtime: Skip AgentRuntime initialization
        skip_mcp: Skip MCP system initialization
        skip_grpc: Skip gRPC client initialization (auto-skipped in HTTP mode)
    
    Returns:
        BootstrapContext containing all initialized components
    
    Raises:
        RuntimeError: If any required component fails to initialize
    """
    ctx = BootstrapContext()
    
    logger.info("=" * 60)
    logger.info("AgentOS Bootstrap Starting")
    logger.info(f"Runtime Mode: {get_runtime_mode()}")
    logger.info(f"Version: {settings.VERSION}")
    logger.info("=" * 60)
    
    # Phase 1: Validate dependencies
    if not skip_dependencies_check:
        await _check_dependencies()
        logger.info("Dependencies validated")
    
    # Phase 2: Initialize persistence layer
    if not skip_database:
        await _init_database(ctx)
    
    if not skip_redis:
        await _init_redis(ctx)
    
    # Phase 3: Initialize core runtime
    if not skip_runtime:
        await _init_runtime(ctx)
    
    # Phase 4: Initialize MCP/tool systems
    if not skip_mcp:
        await _init_mcp_system(ctx)
    
    # Phase 5: Initialize gRPC client (gRPC mode only)
    if not skip_grpc:
        await _init_grpc_client(ctx)
    
    logger.info("=" * 60)
    logger.info(f"AgentOS Bootstrap Complete")
    logger.info(f"Initialized: {', '.join(ctx.initialized)}")
    logger.info("=" * 60)
    
    return ctx


@asynccontextmanager
async def bootstrap_lifespan():
    """Async context manager for bootstrap lifecycle management.
    
    Usage:
        async with bootstrap_lifespan() as ctx:
            # Runtime is initialized and available
            await ctx.runtime.execute_task(...)
        # Automatic cleanup on exit
    """
    ctx = await bootstrap()
    try:
        yield ctx
    finally:
        await ctx.shutdown()


def setup_signal_handlers(ctx: BootstrapContext):
    """Setup graceful shutdown signal handlers.
    
    Handles SIGINT (Ctrl+C) and SIGTERM for graceful shutdown.
    """
    def signal_handler(signum, frame):
        signame = signal.Signals(signum).name
        logger.info(f"Received {signame}, initiating graceful shutdown...")
        # Create task for async shutdown
        asyncio.create_task(ctx.shutdown())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    if sys.platform == "win32":
        # Windows-specific signal handling
        signal.signal(signal.SIGBREAK, signal_handler)


# Convenience exports
__all__ = [
    "bootstrap",
    "bootstrap_lifespan",
    "BootstrapContext",
    "setup_signal_handlers",
]
