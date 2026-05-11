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

# Ensure project root is in path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Core imports (no FastAPI)
from app.bootstrap import bootstrap, BootstrapContext, setup_signal_handlers
from app.config.settings import settings
from app.logs.logger import logger
from app.runtime.mode import RuntimeMode, get_runtime_mode, is_grpc_mode


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
        
        # Bootstrap all components
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
