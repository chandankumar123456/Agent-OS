"""AgentOS Entry Point - routes to desktop or cloud mode based on runtime configuration.

In desktop-native mode (gRPC), the Go Supervisor spawns this process and
communicates via gRPC on port 50051. No HTTP server is needed because the
Supervisor provides the HTTP API on port 8080.

In cloud/HTTP mode, this launches the FastAPI application via uvicorn for
standalone web service deployment.

Usage:
    # Auto-detect mode from environment
    python -m app.main

    # Or set mode explicitly
    AGENTOS_RUNTIME_MODE=grpc python -m app.main   # Desktop mode
    AGENTOS_RUNTIME_MODE=http python -m app.main   # Cloud/HTTP mode
"""
import os
import sys
import asyncio


def _get_app():
    """Lazy import of the FastAPI app for backward compatibility.

    This allows ``uvicorn app.main:app`` to work while avoiding an
    unconditional import of FastAPI and all middleware at module level,
    which would otherwise pull the full web stack even in desktop/gRPC mode.
    """
    from app.cloud_api.main import app as _app
    return _app


# Lazy attribute access: ``app`` is resolved only when accessed (e.g. by uvicorn).
def __getattr__(name: str):
    if name == "app":
        return _get_app()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def main():
    """Detect runtime mode and launch appropriate entry point."""
    mode = os.environ.get("AGENTOS_RUNTIME_MODE", os.environ.get("RUNTIME_MODE", "http")).lower()

    if mode == "grpc":
        # Desktop-native mode: run the kernel directly via gRPC
        from app.desktop_entry import main as desktop_main
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        sys.exit(asyncio.run(desktop_main()))
    else:
        # Cloud/HTTP mode: run FastAPI via uvicorn
        import uvicorn
        from app.cloud_api.main import app
        uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
