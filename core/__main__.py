"""AgentOS unified entry point.

Boot the AgentKernel and gRPC IPC server with a single command::

    python -m core --socket-path /tmp/agentos.sock
    python -m core --http --http-port 8000

Flags:
    --socket-path   Unix socket (or named pipe on Windows) for gRPC IPC.
    --http          Also start the optional FastAPI HTTP adapter.
    --http-port     Port for the HTTP adapter (default 8000).
    --log-level     Logging verbosity (default INFO).
    --data-dir      Base directory for SQLite and other local state.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import sys


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m core",
        description="AgentOS unified runtime - desktop-native kernel with optional HTTP adapter.",
    )
    parser.add_argument(
        "--socket-path",
        default=None,
        help="Unix socket path for gRPC IPC (default: $XDG_RUNTIME_DIR/agentos.sock or /tmp/agentos.sock).",
    )
    parser.add_argument(
        "--http",
        action="store_true",
        default=False,
        help="Start the optional FastAPI HTTP adapter alongside the kernel.",
    )
    parser.add_argument(
        "--http-port",
        type=int,
        default=8000,
        help="Port for the HTTP adapter (default: 8000).",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging verbosity (default: INFO).",
    )
    parser.add_argument(
        "--data-dir",
        default=None,
        help="Base directory for local state (default: ~/.agentos).",
    )
    return parser.parse_args(argv)


async def _run(args: argparse.Namespace) -> None:
    """Main async entrypoint that owns the single event loop."""

    # --- Environment setup ------------------------------------------------
    os.environ.setdefault("AGENTOS_RUNTIME_MODE", "grpc")
    os.environ.setdefault("RUNTIME_MODE", "grpc")

    data_dir = args.data_dir or os.environ.get(
        "AGENTOS_DATA_DIR", os.path.expanduser("~/.agentos")
    )
    os.makedirs(data_dir, exist_ok=True)
    os.environ["AGENTOS_DATA_DIR"] = data_dir

    # SQLite path (unless already set to something valid)
    if not os.environ.get("DATABASE_URL") or "postgresql" in os.environ.get("DATABASE_URL", ""):
        db_path = os.path.join(data_dir, "agentos.db")
        os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"

    # --- Logging ----------------------------------------------------------
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    log = logging.getLogger("core")
    log.info("AgentOS kernel starting (data_dir=%s)", data_dir)

    # --- Boot kernel ------------------------------------------------------
    from core.desktop_native.kernel import AgentKernel
    from core.desktop_native.sqlite_store import sqlite_store
    from core.desktop_native.sqlite_tuning import sqlite_tuning

    await sqlite_store.initialize_schema()
    await sqlite_tuning.apply_optimizations()

    kernel = AgentKernel()
    await kernel.start()
    log.info("AgentKernel started")

    # --- gRPC IPC server --------------------------------------------------
    from core.ipc.grpc_server import GRPCServer

    socket_path = args.socket_path or os.environ.get(
        "AGENTOS_SOCKET_PATH",
        os.path.join(
            os.environ.get("XDG_RUNTIME_DIR", "/tmp"),
            "agentos.sock",
        ),
    )

    grpc_server = GRPCServer(kernel=kernel)
    # Bind to unix socket if the path looks like a file path, otherwise TCP
    if socket_path.startswith("/") or socket_path.startswith("."):
        grpc_server._host = f"unix:{socket_path}"
        grpc_server._port = 0  # not used for UDS
    else:
        grpc_server._host = "0.0.0.0"
        grpc_server._port = 50051
    await grpc_server.start()
    log.info("gRPC IPC server listening on %s", socket_path)

    # --- Optional HTTP adapter --------------------------------------------
    http_server = None
    if args.http:
        try:
            from core.adapters.http import build_http_app
        except ImportError as exc:
            log.error("Cannot start HTTP adapter: %s", exc)
            raise SystemExit(1) from exc

        import uvicorn

        http_app = build_http_app(kernel=kernel)
        config = uvicorn.Config(
            app=http_app,
            host="0.0.0.0",
            port=args.http_port,
            log_level=args.log_level.lower(),
            access_log=False,
        )
        http_server = uvicorn.Server(config)
        # Run uvicorn in a background task so we don't block the loop
        asyncio.create_task(http_server.serve())
        log.info("HTTP adapter listening on port %d", args.http_port)

    # --- Shutdown machinery -----------------------------------------------
    shutdown_event = asyncio.Event()

    def _signal_handler() -> None:
        log.info("Received shutdown signal, draining...")
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            # Windows does not support add_signal_handler; fall back
            signal.signal(sig, lambda *_: _signal_handler())

    # --- Block until shutdown signal --------------------------------------
    await shutdown_event.wait()

    # --- Graceful teardown ------------------------------------------------
    log.info("Shutting down...")
    if http_server is not None:
        http_server.should_exit = True
        # Give uvicorn a moment to finish in-flight requests
        await asyncio.sleep(0.5)
    await grpc_server.stop(grace=5.0)
    await kernel.stop(timeout=5.0)
    log.info("AgentOS kernel stopped. Goodbye.")


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    try:
        asyncio.run(_run(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
