"""Runtime mode detection - delegates to canonical config.mode module."""
from ..config.mode import get_runtime_mode as _config_get_mode
from ..config.mode import is_grpc_mode as _config_is_grpc
from ..config.mode import is_http_mode as _config_is_http
from ..config.mode import RuntimeMode
from ..config.settings import settings

# Re-export
RuntimeMode = RuntimeMode


def get_runtime_mode() -> RuntimeMode:
    """Get the current runtime mode (delegates to config.mode)."""
    return _config_get_mode()


def is_grpc_mode() -> bool:
    """Check if runtime is in gRPC mode (delegates to config.mode)."""
    return _config_is_grpc()


def is_http_mode() -> bool:
    """Check if runtime is in HTTP mode (delegates to config.mode)."""
    return _config_is_http()


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
    return "http://localhost:8000"
