"""AgentOS Desktop-Native Entry Point

This is the canonical entry point for running AgentOS in desktop-native mode.
It initializes the runtime without any FastAPI dependencies and communicates
with the Go supervisor via gRPC.

Usage:
    # Run directly
    python -m app.desktop_entry
    
    # Or import and use
    from app.desktop_entry import main
    asyncio.run(main())

Environment:
    AGENTOS_RUNTIME_MODE=grpc    # Required for desktop-native mode
    GRPC_HOST=localhost          # Supervisor gRPC host
    GRPC_PORT=50051             # Supervisor gRPC port
"""

import asyncio
import os
import sys
from typing import Optional

# Set gRPC mode BEFORE any app imports to avoid settings validation race
# where REDIS_URL is required in HTTP mode but optional in gRPC mode.
# We set BOTH env vars because:
# - AGENTOS_RUNTIME_MODE is checked by app.runtime.mode
# - RUNTIME_MODE is the Settings field name read by Pydantic BaseSettings
if os.environ.get("AGENTOS_RUNTIME_MODE") != "grpc":
    os.environ["AGENTOS_RUNTIME_MODE"] = "grpc"
if os.environ.get("RUNTIME_MODE") != "grpc":
    os.environ["RUNTIME_MODE"] = "grpc"

# Force SQLite as the database in desktop-native mode to eliminate PostgreSQL dependency
if not os.environ.get("DATABASE_URL") or "postgresql" in os.environ.get("DATABASE_URL", "").lower():
    db_path = os.path.expanduser("~/.agentos/agentos.db")
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"

# Ensure project root is in path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Core imports (no FastAPI)
from app.bootstrap import bootstrap, BootstrapContext, setup_signal_handlers
from app.config.settings import settings
from app.logs.logger import logger
from app.runtime.mode import RuntimeMode, get_runtime_mode, is_grpc_mode
from app.runtime.grpc_server import GRPCServer


class DesktopRuntime:
    """Desktop-native runtime manager.
    
    Manages the lifecycle of AgentOS in desktop-native mode,
    providing a clean interface for the supervisor to interact with.
    """
    
    def __init__(self):
        self.ctx: Optional[BootstrapContext] = None
        self._running = False
        self._shutdown_event = asyncio.Event()
    
    async def initialize(self) -> BootstrapContext:
        """Initialize the desktop runtime.
        
        Returns:
            BootstrapContext with all initialized components
        
        Raises:
            RuntimeError: If initialization fails or not in gRPC mode
        """
        # Validate we're in gRPC mode
        if not is_grpc_mode():
            logger.warning("AGENTOS_RUNTIME_MODE is not set to 'grpc'")
            logger.warning("Forcing gRPC mode for desktop-native operation")
            os.environ["AGENTOS_RUNTIME_MODE"] = "grpc"
        
        logger.info("=" * 60)
        logger.info("AgentOS Desktop-Native Runtime Starting")
        logger.info(f"Runtime Mode: {get_runtime_mode()}")
        logger.info(f"Version: {settings.VERSION}")
        logger.info("=" * 60)
        
        # Initialize desktop-native observability systems
        logger.info("Initializing desktop-native observability...")
        from app.desktop_native.local_logger import local_logger
        local_logger.initialize()

        from app.desktop_native.local_metrics import local_metrics
        await local_metrics._ensure_table()

        from app.desktop_native.local_tracer import local_tracer
        await local_tracer._ensure_table()

        from app.desktop_native.local_alerts import local_alerts
        await local_alerts.initialize()

        from app.desktop_native.memory_hierarchy import memory_hierarchy
        await memory_hierarchy.initialize()

        logger.info("Desktop-native observability initialized")

        # Initialize Tauri GUI bridge
        logger.info("Initializing Tauri GUI bridge...")
        from app.desktop_native.tauri_bridge import tauri_bridge
        await tauri_bridge._ensure_tables()
        logger.info("Tauri GUI bridge initialized")

        # Initialize SQLite performance tuning
        logger.info("Applying SQLite performance tuning...")
        from app.desktop_native.sqlite_tuning import sqlite_tuning
        tuning = await sqlite_tuning.apply_optimizations()
        logger.info(f"SQLite tuning: {tuning}")

        # Initialize AgentKernel (replaces fragmented runtime)
        from app.desktop_native.kernel import AgentKernel
        self.kernel = AgentKernel()
        await self.kernel.start()

        # Start gRPC server with the unified AgentKernel
        self.grpc_server = GRPCServer(kernel=self.kernel)
        await self.grpc_server.start()

        # Keep bootstrap for compatibility (initializes DB, runtime, etc.)
        self.ctx = await bootstrap()

        # Setup signal handlers for graceful shutdown
        setup_signal_handlers(self.ctx)

        self._running = True
        logger.info("Desktop runtime initialized successfully")

        return self.ctx
    
    async def run(self):
        """Run the desktop runtime main loop.
        
        This keeps the runtime alive and responsive to gRPC calls
        from the supervisor. The runtime will:
        - Process tasks via gRPC
        - Maintain checkpoint persistence
        - Handle graceful shutdown on signals
        """
        if not self.ctx:
            raise RuntimeError("Runtime not initialized. Call initialize() first.")
        
        logger.info("Desktop runtime entering main loop")
        logger.info("Waiting for tasks via gRPC...")
        logger.info("Press Ctrl+C to shutdown gracefully")
        
        try:
            # Wait for shutdown signal
            await self._shutdown_event.wait()
        except asyncio.CancelledError:
            logger.info("Main loop cancelled")
        finally:
            self._running = False
    
    def shutdown(self):
        """Signal the runtime to shutdown gracefully."""
        logger.info("Shutdown requested")
        self._shutdown_event.set()
    
    async def cleanup(self):
        """Cleanup all resources."""
        if hasattr(self, "grpc_server") and self.grpc_server:
            await self.grpc_server.stop()
        if hasattr(self, "kernel") and self.kernel:
            await self.kernel.stop()
        if self.ctx:
            await self.ctx.shutdown()
            self.ctx = None
        self._running = False
        logger.info("Desktop runtime cleanup complete")
    
    @property
    def is_running(self) -> bool:
        """Check if runtime is currently running."""
        return self._running
    
    @property
    def runtime(self) -> Optional[object]:
        """Get the AgentRuntime instance."""
        return self.ctx.runtime if self.ctx else None
    
    @property
    def grpc_client(self) -> Optional[object]:
        """Get the gRPC client instance."""
        return self.ctx.grpc_client if self.ctx else None


async def main():
    """Main entry point for desktop-native AgentOS.
    
    This function:
    1. Initializes all runtime components
    2. Sets up signal handlers for graceful shutdown
    3. Runs the main loop waiting for gRPC tasks
    4. Cleans up on exit
    
    Returns:
        int: Exit code (0 for success, 1 for error)
    """
    desktop = DesktopRuntime()
    exit_code = 0
    
    try:
        # Initialize
        await desktop.initialize()
        
        # Run main loop
        await desktop.run()
        
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.error(f"Fatal error in desktop runtime: {e}", exc_info=True)
        exit_code = 1
    finally:
        # Cleanup
        await desktop.cleanup()
    
    return exit_code


if __name__ == "__main__":
    # Set event loop policy for Windows
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    # Run main
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except Exception as e:
        logger.error(f"Unhandled exception: {e}", exc_info=True)
        sys.exit(1)
