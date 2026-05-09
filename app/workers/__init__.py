"""
Workers package for AgentOS.

This package contains worker-related components including:
- Executor server for gRPC task execution
- Worker pool management
- Task routing and handling
"""

from app.workers.executor_server import WorkerExecutorServicer, serve

__all__ = [
    "WorkerExecutorServicer",
    "serve",
]
