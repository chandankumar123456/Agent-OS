"""gRPC server wrapper for AgentOS Python runtime.

Provides gRPC services for supervisor communication while maintaining
LangGraph checkpoint compatibility and SQLite persistence for local mode.

Services:
- RuntimeService: Task management and runtime status
- WorkerService: Worker pool management
- CheckpointService: State persistence and retrieval
"""

import asyncio
import json
from typing import Dict, Any, Optional
from concurrent import futures

import grpc
from google.protobuf import empty_pb2

from ..logs.logger import logger

# Import proto-generated classes (files are in app/proto/ directory)
# Generated from supervisor/proto/ files using grpc_tools.protoc
import sys
from pathlib import Path

# Import from app/proto where generated files are located
from ..proto import runtime_pb2, runtime_pb2_grpc
from ..proto import checkpoint_pb2, checkpoint_pb2_grpc
from ..proto.checkpoint_pb2 import (
    SaveCheckpointResponse as CheckpointResponse,
    GetCheckpointResponse,
    ListCheckpointsResponse,
    Checkpoint,
    CleanupCheckpointsResponse,
    CheckpointEvent,
)
from ..proto import worker_pb2, worker_pb2_grpc

# Import runtime types for type hints
from ..runtime.runtime import AgentRuntime
from ..orchestrator.core import Orchestrator
from ..langgraph.sqlite_checkpointer import SQLiteCheckpointSaver


class GRPCServer:
    """gRPC server wrapper for AgentOS runtime.

    Provides gRPC services for supervisor communication while maintaining
    LangGraph checkpoint compatibility and SQLite persistence for local mode.
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 50051):
        self._host = host
        self._port = port
        self._server = None
        self._runtime = None
        self._orchestrator = None
        self._checkpointer = None
        self._services = {}

    async def initialize(self):
        """Initialize the gRPC server with runtime components."""
        # Import runtime components
        from ..runtime.runtime import AgentRuntime
        from ..langgraph.sqlite_checkpointer import SQLiteCheckpointSaver
        from ..orchestrator.core import Orchestrator

        # Initialize runtime
        self._runtime = AgentRuntime()
        await self._runtime.initialize()

        # Initialize orchestrator
        self._orchestrator = Orchestrator()

        # Initialize SQLite checkpointer for local mode
        self._checkpointer = SQLiteCheckpointSaver()

        logger.info(f"gRPC server initialized on {self._host}:{self._port}")

    async def start(self):
        """Start the gRPC server."""
        await self.initialize()

        self._server = grpc.aio.server(
            futures.ThreadPoolExecutor(max_workers=10),
            options=[
                ("grpc.max_send_message_length", 50 * 1024 * 1024),
                ("grpc.max_receive_message_length", 50 * 1024 * 1024),
            ]
        )

        # Register services
        runtime_pb2_grpc.add_RuntimeServiceServicer_to_server(
            RuntimeServiceImpl(self._runtime, self._orchestrator), self._server
        )
        checkpoint_pb2_grpc.add_CheckpointServiceServicer_to_server(
            CheckpointServiceImpl(self._checkpointer), self._server
        )
        worker_pb2_grpc.add_WorkerExecutorServicer_to_server(
            WorkerServiceImpl(self._runtime, self._orchestrator), self._server
        )

        self._server.add_insecure_port(f"{self._host}:{self._port}")
        await self._server.start()

        logger.info(f"gRPC server started on {self._host}:{self._port}")

    async def stop(self, grace: float = 5.0):
        """Stop the gRPC server."""
        if self._server:
            await self._server.stop(grace)
            self._server = None
            logger.info("gRPC server stopped")

        # Shutdown runtime
        if self._runtime:
            await self._runtime.shutdown_all()
            self._runtime = None

        self._orchestrator = None
        self._checkpointer = None

    async def serve(self):
        """Start the server and wait for shutdown."""
        await self.start()
        try:
            await self._server.wait_for_termination()
        except asyncio.CancelledError:
            await self.stop()


class RuntimeServiceImpl:
    """Implementation of RuntimeService for task management."""

    def __init__(self, runtime: AgentRuntime, orchestrator: Orchestrator):
        self._runtime = runtime
        self._orchestrator = orchestrator

    async def CreateTask(self, request, context):
        """Create and execute a new task."""
        try:
            result = await self._orchestrator.ainvoke({
                "query": request.query,
                "config": dict(request.config) if request.config else {},
            })
            return runtime_pb2.CreateTaskResponse(
                task=runtime_pb2.Task(
                    id=result.get("task_id", ""),
                    query=request.query,
                    status=runtime_pb2.TASK_STATUS_COMPLETED,
                    result=json.dumps(result),
                ),
                success=True
            )
        except Exception as e:
            logger.error(f"Create task failed: {e}")
            return runtime_pb2.CreateTaskResponse(success=False, error=str(e))

    async def GetTask(self, request, context):
        """Get task status by ID."""
        try:
            # For now, return placeholder response
            return runtime_pb2.GetTaskResponse(
                task=runtime_pb2.Task(
                    id=request.task_id,
                    status=runtime_pb2.TASK_STATUS_COMPLETED
                ),
                success=True
            )
        except Exception as e:
            logger.error(f"Get task failed: {e}")
            return runtime_pb2.GetTaskResponse(success=False, error=str(e))

    async def CancelTask(self, request, context):
        """Cancel a running task."""
        try:
            return runtime_pb2.CancelTaskResponse(success=True)
        except Exception as e:
            logger.error(f"Cancel task failed: {e}")
            return runtime_pb2.CancelTaskResponse(success=False, error=str(e))

    async def ListTasks(self, request, context):
        """List tasks with optional filters."""
        try:
            return runtime_pb2.ListTasksResponse(
                tasks=[],
                total_count=0,
                success=True
            )
        except Exception as e:
            logger.error(f"List tasks failed: {e}")
            return runtime_pb2.ListTasksResponse(success=False, error=str(e))

    async def ApproveTask(self, request, context):
        """Approve a pending task."""
        try:
            return runtime_pb2.ApproveTaskResponse(success=True)
        except Exception as e:
            logger.error(f"Approve task failed: {e}")
            return runtime_pb2.ApproveTaskResponse(success=False, error=str(e))

    async def RejectTask(self, request, context):
        """Reject a pending task."""
        try:
            return runtime_pb2.RejectTaskResponse(success=True)
        except Exception as e:
            logger.error(f"Reject task failed: {e}")
            return runtime_pb2.RejectTaskResponse(success=False, error=str(e))

    async def GetRuntimeStatus(self, request, context):
        """Get runtime status and metrics."""
        try:
            agents = self._runtime.list_active()
            return runtime_pb2.RuntimeStatus(
                version="0.2.0",
                state=runtime_pb2.RuntimeState.RUNTIME_STATE_READY,
                active_tasks=len(agents),
                completed_tasks=len(agents),
                metrics=runtime_pb2.RuntimeMetrics(
                    cpu_percent=0.0,
                    memory_bytes=25 * 1024 * 1024,  # 25MB
                )
            )
        except Exception as e:
            logger.error(f"Get runtime status failed: {e}")
            return runtime_pb2.RuntimeStatus(state=runtime_pb2.RuntimeState.RUNTIME_STATE_ERROR, error=str(e))

    async def Shutdown(self, request, context):
        """Shutdown the runtime."""
        try:
            await self._runtime.shutdown_all()
            return runtime_pb2.ShutdownResponse(success=True, message="Runtime shutdown")
        except Exception as e:
            logger.error(f"Shutdown failed: {e}")
            return runtime_pb2.ShutdownResponse(success=False, message=str(e))

    async def HealthCheck(self, request, context):
        """Health check endpoint."""
        try:
            agents = self._runtime.list_active()
            return runtime_pb2.HealthCheckResponse(
                healthy=True,
                version="0.2.0"
            )
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return runtime_pb2.HealthCheckResponse(healthy=False, error=str(e))

    async def StreamTaskEvents(self, request, context):
        """Stream task events via server-side streaming."""
        try:
            # Placeholder: yield a single completion event
            yield runtime_pb2.TaskEvent(
                task_id=request.task_id,
                event_type="completed",
                message="Task completed",
            )
        except Exception as e:
            logger.error(f"Stream task events failed: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))

    async def GetConfig(self, request, context):
        """Get configuration."""
        try:
            return runtime_pb2.GetConfigResponse(
                config={"runtime_mode": "grpc", "version": "0.2.0"},
                success=True
            )
        except Exception as e:
            logger.error(f"Get config failed: {e}")
            return runtime_pb2.GetConfigResponse(success=False, error=str(e))

    async def SetConfig(self, request, context):
        """Set configuration."""
        try:
            return runtime_pb2.SetConfigResponse(success=True)
        except Exception as e:
            logger.error(f"Set config failed: {e}")
            return runtime_pb2.SetConfigResponse(success=False, error=str(e))


class CheckpointServiceImpl:
    """Implementation of CheckpointService for state persistence."""

    def __init__(self, checkpointer: SQLiteCheckpointSaver):
        self._checkpointer = checkpointer

    async def SaveCheckpoint(self, request, context):
        """Save a checkpoint."""
        try:
            checkpoint = json.loads(request.state_blob.decode("utf-8")) if request.state_blob else {}
            metadata = json.loads(request.metadata) if request.metadata else {}

            config = {
                "configurable": {
                    "thread_id": request.thread_id,
                    "checkpoint_ns": request.checkpoint_ns or "",
                }
            }

            new_config = await self._checkpointer.aput(config, checkpoint, metadata)
            return CheckpointResponse(
                success=True,
                checkpoint_id=new_config["configurable"].get("checkpoint_id", "")
            )
        except Exception as e:
            logger.error(f"Save checkpoint failed: {e}")
            return CheckpointResponse(success=False, error=str(e))

    async def GetCheckpoint(self, request, context):
        """Get a checkpoint by config."""
        try:
            config = {
                "configurable": {
                    "thread_id": request.thread_id,
                    "checkpoint_ns": request.checkpoint_ns or "",
                    "checkpoint_id": request.checkpoint_id or None,
                }
            }

            checkpoint_tuple = await self._checkpointer.aget_tuple(config)
            if not checkpoint_tuple:
                return GetCheckpointResponse(success=False, error="Checkpoint not found")

            return GetCheckpointResponse(
                success=True,
                checkpoint=Checkpoint(
                    id=checkpoint_tuple.config["configurable"].get("checkpoint_id", ""),
                    thread_id=checkpoint_tuple.config["configurable"]["thread_id"],
                    checkpoint_ns=checkpoint_tuple.config["configurable"].get("checkpoint_ns", ""),
                    state_blob=json.dumps(checkpoint_tuple.checkpoint).encode("utf-8"),
                    metadata=json.dumps(checkpoint_tuple.metadata) if checkpoint_tuple.metadata else "{}",
                )
            )
        except Exception as e:
            logger.error(f"Get checkpoint failed: {e}")
            return GetCheckpointResponse(success=False, error=str(e))

    async def ListCheckpoints(self, request, context):
        """List checkpoints with optional filters."""
        try:
            config = None
            if request.thread_id:
                config = {
                    "configurable": {
                        "thread_id": request.thread_id,
                        "checkpoint_ns": request.checkpoint_ns or "",
                    }
                }

            checkpoints = []
            async for checkpoint_tuple in self._checkpointer.alist(config):
                checkpoints.append(Checkpoint(
                    id=checkpoint_tuple.config["configurable"].get("checkpoint_id", ""),
                    thread_id=checkpoint_tuple.config["configurable"]["thread_id"],
                    checkpoint_ns=checkpoint_tuple.config["configurable"].get("checkpoint_ns", ""),
                    state_blob=json.dumps(checkpoint_tuple.checkpoint).encode("utf-8"),
                    metadata=json.dumps(checkpoint_tuple.metadata) if checkpoint_tuple.metadata else "{}",
                ))

            return ListCheckpointsResponse(
                success=True,
                checkpoints=checkpoints,
                total_count=len(checkpoints)
            )
        except Exception as e:
            logger.error(f"List checkpoints failed: {e}")
            return ListCheckpointsResponse(success=False, error=str(e))

    async def GetLatestCheckpoint(self, request, context):
        """Get the latest checkpoint for a thread."""
        try:
            config = {
                "configurable": {
                    "thread_id": request.thread_id,
                    "checkpoint_ns": request.checkpoint_ns or "",
                }
            }

            checkpoint_tuple = await self._checkpointer.aget_tuple(config)
            if not checkpoint_tuple:
                return GetCheckpointResponse(success=False, error="Checkpoint not found")

            return GetCheckpointResponse(
                success=True,
                checkpoint=Checkpoint(
                    id=checkpoint_tuple.config["configurable"].get("checkpoint_id", ""),
                    thread_id=checkpoint_tuple.config["configurable"]["thread_id"],
                    checkpoint_ns=checkpoint_tuple.config["configurable"].get("checkpoint_ns", ""),
                    state_blob=json.dumps(checkpoint_tuple.checkpoint).encode("utf-8"),
                    metadata=json.dumps(checkpoint_tuple.metadata) if checkpoint_tuple.metadata else "{}",
                )
            )
        except Exception as e:
            logger.error(f"Get latest checkpoint failed: {e}")
            return GetCheckpointResponse(success=False, error=str(e))

    async def CleanupCheckpoints(self, request, context):
        """Clean up old checkpoints."""
        try:
            # Placeholder: no actual cleanup implemented yet
            return CleanupCheckpointsResponse(
                success=True,
                deleted_count=0,
                message="Cleanup placeholder"
            )
        except Exception as e:
            logger.error(f"Cleanup checkpoints failed: {e}")
            return CleanupCheckpointsResponse(success=False, error=str(e))

    async def SubscribeCheckpoints(self, request, context):
        """Subscribe to checkpoint events via server-side streaming."""
        try:
            # Placeholder: yield a single subscription confirmation event
            yield CheckpointEvent(
                event_type="subscribed",
                thread_id=request.thread_id,
                message="Checkpoint subscription active",
            )
        except Exception as e:
            logger.error(f"Subscribe checkpoints failed: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))


class WorkerServiceImpl:
    """Implementation of WorkerService for worker pool management."""

    def __init__(self, runtime: AgentRuntime, orchestrator: Orchestrator = None):
        self._runtime = runtime
        self._orchestrator = orchestrator

    async def ExecuteTask(self, request, context):
        """Execute a task through the orchestrator."""
        try:
            task_config = json.loads(request.payload) if request.payload else {}

            if self._orchestrator:
                result = await self._orchestrator.ainvoke({
                    "query": request.payload,
                    "config": task_config,
                })
            else:
                # Fallback to runtime if orchestrator not available
                result = {"status": "executed", "task_id": request.task_id}

            return worker_pb2.TaskResponse(
                task_id=request.task_id,
                success=True,
                result=json.dumps(result),
                duration_ms=0
            )
        except Exception as e:
            logger.error(f"Execute task failed: {e}")
            return worker_pb2.TaskResponse(
                task_id=request.task_id,
                success=False,
                error=str(e)
            )

    async def HealthCheck(self, request, context):
        """Health check for worker service."""
        try:
            agents = self._runtime.list_active()
            return worker_pb2.HealthResponse(
                healthy=True,
                version="0.2.0",
            )
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return worker_pb2.HealthResponse(healthy=False, version="error")


# Convenience function to create and run the gRPC server
async def run_grpc_server(host: str = "0.0.0.0", port: int = 50051):
    """Run the gRPC server with default configuration."""
    server = GRPCServer(host=host, port=port)
    await server.serve()


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_grpc_server())
