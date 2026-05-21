"""core.ipc.grpc_server - gRPC server for AgentOS runtime.

Re-exports the GRPCServer from core/runtime/grpc_server.py which is the
canonical implementation.
"""

from ..runtime.grpc_server import (
    GRPCServer,
    RuntimeServiceImpl,
    CheckpointServiceImpl,
    WorkerServiceImpl,
    run_grpc_server,
)

__all__ = [
    "GRPCServer",
    "RuntimeServiceImpl",
    "CheckpointServiceImpl",
    "WorkerServiceImpl",
    "run_grpc_server",
]
