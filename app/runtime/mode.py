"""Runtime mode detection for AgentOS.

Detects whether to use HTTP API (cloud mode) or gRPC (local-native mode)
for supervisor communication.

Usage:
    from app.runtime.mode import get_runtime_mode, get_grpc_client_config, RuntimeMode
    
    # Get current mode
    mode = get_runtime_mode()  # Returns RuntimeMode.HTTP or RuntimeMode.GRPC
    
    # Get gRPC config when in grpc mode
    if mode == RuntimeMode.GRPC:
        config = get_grpc_client_config()
        # Use config for gRPC client initialization
"""

import os
from enum import Enum
from typing import Optional
from ..config.settings import settings
from ..logs.logger import logger


class RuntimeMode(str, Enum):
    """Runtime communication modes."""
    HTTP = "http"
    GRPC = "grpc"


def get_runtime_mode() -> RuntimeMode:
    """Get the current runtime communication mode.
    
    Returns:
        RuntimeMode.HTTP for FastAPI HTTP API (cloud mode)
        RuntimeMode.GRPC for gRPC to supervisor (local-native mode)
    """
    # Environment variable takes precedence
    env_mode = os.environ.get("AGENTOS_RUNTIME_MODE")
    if env_mode:
        if env_mode not in ("http", "grpc"):
            logger.warning(
                f"Invalid AGENTOS_RUNTIME_MODE '{env_mode}', "
                f"expected 'http' or 'grpc'. Defaulting to 'http'."
            )
            return RuntimeMode.HTTP
        logger.info(f"Runtime mode from environment: {env_mode}")
        return RuntimeMode(env_mode)
    
    # Fall back to settings
    mode = settings.RUNTIME_MODE
    if mode not in ("http", "grpc"):
        logger.warning(
            f"Invalid RUNTIME_MODE '{mode}' in settings, "
            f"expected 'http' or 'grpc'. Defaulting to 'http'."
        )
        mode = "http"
    
    logger.info(f"Runtime mode from settings: {mode}")
    return RuntimeMode(mode)


def is_grpc_mode() -> bool:
    """Check if runtime is in gRPC mode."""
    return get_runtime_mode() == RuntimeMode.GRPC


def is_http_mode() -> bool:
    """Check if runtime is in HTTP mode."""
    return get_runtime_mode() == RuntimeMode.HTTP


def get_grpc_client_config():
    """Get gRPC client configuration for current mode."""
    from ..proto.grpc_client import GRPCClientConfig
    
    return GRPCClientConfig(
        host=settings.GRPC_HOST,
        port=settings.GRPC_PORT,
    )


def get_grpc_target() -> str:
    """Get gRPC target string for current mode."""
    return f"{settings.GRPC_HOST}:{settings.GRPC_PORT}"


def get_supervisor_address() -> str:
    """Get supervisor communication address based on mode.
    
    Returns:
        HTTP URL for http mode: "http://localhost:8000"
        gRPC target for grpc mode: "localhost:50051"
    """
    mode = get_runtime_mode()
    
    if mode == RuntimeMode.GRPC:
        return get_grpc_target()
    else:
        # Default HTTP API address
        return "http://localhost:8000"
