"""Runtime mode configuration for AgentOS.

Supports two modes:
- HTTP: Traditional FastAPI HTTP API (default)
- GRPC: gRPC communication with Go supervisor (local-native mode)

Usage:
    from app.config.mode import get_runtime_mode, is_grpc_mode
    
    if is_grpc_mode():
        # Use gRPC client
        client = GRPCClient()
        await client.connect()
    else:
        # Use HTTP API
        pass
"""

import os
from enum import Enum
from typing import Final

from ..logs.logger import logger


class RuntimeMode(Enum):
    """Runtime execution mode."""
    HTTP = "http"
    GRPC = "grpc"


# Environment variable for mode selection
ENV_RUNTIME_MODE: Final[str] = "AGENTOS_RUNTIME_MODE"

# Default mode
DEFAULT_MODE: Final[str] = "http"

# gRPC default configuration
DEFAULT_GRPC_HOST: Final[str] = "localhost"
DEFAULT_GRPC_PORT: Final[int] = 50051


def get_runtime_mode() -> RuntimeMode:
    """Get the current runtime mode from environment variable.
    
    Returns:
        RuntimeMode: HTTP or GRPC mode (defaults to HTTP on invalid input)
    """
    mode_str = os.environ.get(ENV_RUNTIME_MODE, DEFAULT_MODE).lower()
    if mode_str == "http":
        return RuntimeMode.HTTP
    elif mode_str == "grpc":
        return RuntimeMode.GRPC
    else:
        if ENV_RUNTIME_MODE in os.environ:
            logger.warning(f"Invalid runtime mode '{mode_str}', defaulting to '{DEFAULT_MODE}'")
        return RuntimeMode.HTTP


def is_grpc_mode() -> bool:
    """Check if runtime is in gRPC mode.
    
    Returns:
        bool: True if gRPC mode, False if HTTP mode
    """
    return get_runtime_mode() == RuntimeMode.GRPC


def is_http_mode() -> bool:
    """Check if runtime is in HTTP mode.
    
    Returns:
        bool: True if HTTP mode, False if gRPC mode
    """
    return get_runtime_mode() == RuntimeMode.HTTP


def get_grpc_host() -> str:
    """Get gRPC server host from environment or use default."""
    return os.environ.get("AGENTOS_GRPC_HOST", DEFAULT_GRPC_HOST)


def get_grpc_port() -> int:
    """Get gRPC server port from environment or use default."""
    port_str = os.environ.get("AGENTOS_GRPC_PORT", str(DEFAULT_GRPC_PORT))
    try:
        return int(port_str)
    except ValueError:
        logger.warning(f"Invalid gRPC port '{port_str}', using default {DEFAULT_GRPC_PORT}")
        return DEFAULT_GRPC_PORT


def get_grpc_address() -> str:
    """Get full gRPC address (host:port)."""
    return f"{get_grpc_host()}:{get_grpc_port()}"


def get_grpc_client_config():
    """Get gRPC client configuration for current mode."""
    from app.proto.grpc_client import GRPCClientConfig
    from app.config.settings import settings
    
    return GRPCClientConfig(
        host=settings.GRPC_HOST,
        port=settings.GRPC_PORT,
        connection_timeout=settings.GRPC_CONNECTION_TIMEOUT,
        keepalive_timeout=settings.GRPC_KEEPALIVE_TIMEOUT,
        max_send_message_length=settings.GRPC_MAX_MESSAGE_LENGTH_MB * 1024 * 1024,
        max_receive_message_length=settings.GRPC_MAX_MESSAGE_LENGTH_MB * 1024 * 1024,
    )
