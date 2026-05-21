"""core.ipc.schema - Re-exports generated proto stubs from core/proto/.

This module provides a stable import path for proto-generated types
used in IPC communication.
"""

from ..proto import runtime_pb2, runtime_pb2_grpc
from ..proto import checkpoint_pb2, checkpoint_pb2_grpc
from ..proto import worker_pb2, worker_pb2_grpc

__all__ = [
    "runtime_pb2",
    "runtime_pb2_grpc",
    "checkpoint_pb2",
    "checkpoint_pb2_grpc",
    "worker_pb2",
    "worker_pb2_grpc",
]
