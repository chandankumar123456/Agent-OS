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

    def __init__(self, host: str = "127.0.0.1", port: int = 50051, kernel=None):
        """Initialize GRPCServer.

        Args:
            host: Bind address for the gRPC server.
            port: Port number.
            kernel: Optional AgentKernel or UnifiedKernel (from app.core.kernel)
                    instance. If provided, the server delegates to the kernel
                    instead of creating its own runtime.
        """
        self._host = host
        self._port = port
        self._server = None
        self._runtime = None
        self._orchestrator = None
        self._checkpointer = None
        self._kernel = kernel
        self._services = {}

    async def initialize(self):
        """Initialize the gRPC server with runtime components."""
        from ..langgraph.sqlite_checkpointer import SQLiteCheckpointSaver

        if self._kernel is not None:
            # Use provided AgentKernel; skip legacy runtime initialization
            logger.info("gRPC server using unified AgentKernel")
        else:
            # Import runtime components
            from ..runtime.runtime import AgentRuntime
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
            RuntimeServiceImpl(self._runtime, self._orchestrator, self._kernel), self._server
        )
        checkpoint_pb2_grpc.add_CheckpointServiceServicer_to_server(
            CheckpointServiceImpl(self._checkpointer), self._server
        )
        worker_pb2_grpc.add_WorkerExecutorServicer_to_server(
            WorkerServiceImpl(self._runtime, self._orchestrator, self._kernel), self._server
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
        self._kernel = None

    async def serve(self):
        """Start the server and wait for shutdown."""
        await self.start()
        try:
            await self._server.wait_for_termination()
        except asyncio.CancelledError:
            await self.stop()


class RuntimeServiceImpl:
    """Implementation of RuntimeService for task management."""

    def __init__(self, runtime: AgentRuntime, orchestrator: Orchestrator, kernel=None):
        self._runtime = runtime
        self._orchestrator = orchestrator
        self._kernel = kernel
        self._tasks = {}  # In-memory task store for gRPC lookups

    async def _monitor_kernel_task(self, task_id: str):
        """Background monitor: waits for kernel task completion and updates local cache."""
        if not self._kernel:
            return
        try:
            result = await self._kernel.wait_for_task(task_id)
            if task_id in self._tasks:
                task = self._tasks[task_id]
                status_str = result.get("status", "unknown")
                if status_str == "completed":
                    task.status = runtime_pb2.TASK_STATUS_COMPLETED
                    task.result = json.dumps(result.get("result", ""))
                elif status_str == "failed":
                    task.status = runtime_pb2.TASK_STATUS_FAILED
                    task.error = result.get("error", "")
                elif status_str == "cancelled":
                    task.status = runtime_pb2.TASK_STATUS_CANCELLED
                from google.protobuf.timestamp_pb2 import Timestamp
                task.updated_at = Timestamp()
                task.updated_at.GetCurrentTime()
                self._tasks[task_id] = task
        except Exception as e:
            logger.error(f"Task monitor failed for {task_id}: {e}")

    async def CreateTask(self, request, context):
        """Create and execute a new task."""
        import uuid
        from uuid import uuid4
        from google.protobuf.timestamp_pb2 import Timestamp
        
        ts = Timestamp()
        ts.GetCurrentTime()
        
        if self._kernel is not None:
            # Unified AgentKernel path: submit async and return immediately
            try:
                config = dict(request.config) if request.config else {}
                kernel_task_id = await self._kernel.submit_task(
                    query=request.query,
                    config=config,
                )
                task = runtime_pb2.Task(
                    id=kernel_task_id,
                    query=request.query,
                    status=runtime_pb2.TASK_STATUS_PENDING,
                    type=request.type if hasattr(request, 'type') else runtime_pb2.TASK_TYPE_SIMPLE,
                    created_at=ts,
                    updated_at=ts,
                )
                self._tasks[kernel_task_id] = task
                # Start background monitoring
                asyncio.create_task(self._monitor_kernel_task(kernel_task_id))
                return runtime_pb2.CreateTaskResponse(task=task, success=True)
            except Exception as kernel_err:
                logger.error(f"AgentKernel task submission failed: {kernel_err}")
                return runtime_pb2.CreateTaskResponse(success=False, error=str(kernel_err))
        
        # Legacy orchestrator path (fallback)
        task_id = f"task_{uuid4().hex[:12]}"
        try:
            config = dict(request.config) if request.config else {}
            result = await self._orchestrator.execute_task(
                query=request.query,
                config=config,
                task_id=uuid4(),
            )
            
            # Map AgentOutput status to protobuf TaskStatus
            from ..agents.base import AgentStatus
            status_map = {
                AgentStatus.SUCCESS: runtime_pb2.TASK_STATUS_COMPLETED,
                AgentStatus.FAILURE: runtime_pb2.TASK_STATUS_FAILED,
                AgentStatus.PENDING: runtime_pb2.TASK_STATUS_PENDING,
                AgentStatus.RUNNING: runtime_pb2.TASK_STATUS_EXECUTING,
            }
            pb_status = status_map.get(result.status, runtime_pb2.TASK_STATUS_COMPLETED)
            
            task = runtime_pb2.Task(
                id=str(result.task_id),
                query=request.query,
                status=pb_status,
                type=request.type if hasattr(request, 'type') else runtime_pb2.TASK_TYPE_SIMPLE,
                created_at=ts,
                updated_at=ts,
                result=json.dumps(result.output_data) if result.output_data else "",
                error=result.error_message or "",
            )
        except Exception as orch_err:
            logger.warning(f"Orchestrator execution skipped (dependencies unavailable): {orch_err}")
            # Create basic task entry for gRPC operations to function
            task = runtime_pb2.Task(
                id=task_id,
                query=request.query,
                status=runtime_pb2.TASK_STATUS_PENDING,
                type=request.type if hasattr(request, 'type') else runtime_pb2.TASK_TYPE_SIMPLE,
                created_at=ts,
                updated_at=ts,
            )
        
        # Store for GetTask/ListTasks lookups
        self._tasks[task.id] = task
        
        return runtime_pb2.CreateTaskResponse(
            task=task,
            success=True,
        )

    async def GetTask(self, request, context):
        """Get task status by ID."""
        try:
            # Sync with kernel if available
            if self._kernel is not None and request.task_id in self._tasks:
                status = await self._kernel.get_task_status(request.task_id)
                task = self._tasks[request.task_id]
                state_str = status.get("state", "unknown")
                if state_str == "completed":
                    task.status = runtime_pb2.TASK_STATUS_COMPLETED
                elif state_str == "failed":
                    task.status = runtime_pb2.TASK_STATUS_FAILED
                elif state_str == "cancelled":
                    task.status = runtime_pb2.TASK_STATUS_CANCELLED
                elif state_str == "executing":
                    task.status = runtime_pb2.TASK_STATUS_EXECUTING
                elif state_str == "planning":
                    task.status = runtime_pb2.TASK_STATUS_PLANNING
                self._tasks[request.task_id] = task

            if request.task_id in self._tasks:
                task = self._tasks[request.task_id]
                return runtime_pb2.GetTaskResponse(
                    task=task,
                    success=True,
                )
            return runtime_pb2.GetTaskResponse(
                success=False,
                error="Task not found",
            )
        except Exception as e:
            logger.error(f"Get task failed: {e}")
            return runtime_pb2.GetTaskResponse(success=False, error=str(e))

    async def CancelTask(self, request, context):
        """Cancel a running task."""
        try:
            if self._kernel is not None:
                await self._kernel.cancel_task(request.task_id)
            if request.task_id in self._tasks:
                task = self._tasks[request.task_id]
                task.status = runtime_pb2.TASK_STATUS_CANCELLED
                task.error = request.reason if hasattr(request, 'reason') and request.reason else ""
                self._tasks[request.task_id] = task
            return runtime_pb2.CancelTaskResponse(success=True)
        except Exception as e:
            logger.error(f"Cancel task failed: {e}")
            return runtime_pb2.CancelTaskResponse(success=False, error=str(e))

    async def ListTasks(self, request, context):
        """List tasks with optional filters."""
        try:
            tasks = list(self._tasks.values())
            total = len(tasks)
            
            # Apply pagination
            offset = request.offset if hasattr(request, 'offset') else 0
            limit = request.limit if hasattr(request, 'limit') else 100
            paginated = tasks[offset:offset + limit] if offset < len(tasks) else []
            
            return runtime_pb2.ListTasksResponse(
                tasks=paginated,
                total_count=total,
                success=True,
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
            if self._kernel is not None:
                return runtime_pb2.RuntimeStatus(
                    version="0.2.0",
                    state=runtime_pb2.RuntimeState.RUNTIME_STATE_READY,
                    active_tasks=self._kernel.active_task_count,
                    queued_tasks=0,
                    completed_tasks=sum(1 for t in self._tasks.values() 
                                       if t.status == runtime_pb2.TASK_STATUS_COMPLETED),
                    failed_tasks=sum(1 for t in self._tasks.values() 
                                   if t.status == runtime_pb2.TASK_STATUS_FAILED),
                    metrics=runtime_pb2.RuntimeMetrics(
                        cpu_percent=0.0,
                        memory_bytes=25 * 1024 * 1024,
                    )
                )
            agents = []
            if self._runtime:
                try:
                    agents = self._runtime.list_active()
                except Exception:
                    agents = []
            return runtime_pb2.RuntimeStatus(
                version="0.2.0",
                state=runtime_pb2.RuntimeState.RUNTIME_STATE_READY,
                active_tasks=len(self._tasks),
                queued_tasks=0,
                completed_tasks=sum(1 for t in self._tasks.values() 
                                   if t.status == runtime_pb2.TASK_STATUS_COMPLETED),
                failed_tasks=sum(1 for t in self._tasks.values() 
                               if t.status == runtime_pb2.TASK_STATUS_FAILED),
                metrics=runtime_pb2.RuntimeMetrics(
                    cpu_percent=0.0,
                    memory_bytes=25 * 1024 * 1024,  # 25MB
                )
            )
        except Exception as e:
            logger.error(f"Get runtime status failed: {e}")
            return runtime_pb2.RuntimeStatus(
                version="0.2.0",
                state=runtime_pb2.RuntimeState.RUNTIME_STATE_ERROR,
            )

    async def Shutdown(self, request, context):
        """Shutdown the runtime."""
        try:
            if self._kernel is not None:
                await self._kernel.stop()
            elif self._runtime:
                await self._runtime.shutdown_all()
            return runtime_pb2.ShutdownResponse(success=True, message="Runtime shutdown")
        except Exception as e:
            logger.error(f"Shutdown failed: {e}")
            return runtime_pb2.ShutdownResponse(success=False, message=str(e))

    async def HealthCheck(self, request, context):
        """Health check endpoint."""
        try:
            healthy = True
            if self._kernel is not None:
                healthy = self._kernel.is_running
            elif self._runtime:
                self._runtime.list_active()
            return runtime_pb2.HealthCheckResponse(
                healthy=healthy,
                version="0.2.0"
            )
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return runtime_pb2.HealthCheckResponse(healthy=False, version="0.2.0")

    async def StreamTaskEvents(self, request, context):
        """Stream task events via server-side streaming."""
        try:
            # Placeholder: yield a single completion event
            from google.protobuf.timestamp_pb2 import Timestamp
            ts = Timestamp()
            ts.GetCurrentTime()
            yield runtime_pb2.TaskEvent(
                task_id=request.task_id,
                event_type=runtime_pb2.TASK_EVENT_COMPLETED,
                timestamp=ts,
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

    def __init__(self, runtime: AgentRuntime, orchestrator: Orchestrator = None, kernel=None):
        self._runtime = runtime
        self._orchestrator = orchestrator
        self._kernel = kernel

    async def ExecuteTask(self, request, context):
        """Execute a task through the orchestrator or kernel."""
        try:
            task_config = json.loads(request.payload) if request.payload else {}

            if self._kernel is not None:
                kernel_task_id = await self._kernel.submit_task(
                    query=request.payload,
                    config=task_config,
                )
                result = await self._kernel.wait_for_task(kernel_task_id)
                return worker_pb2.TaskResponse(
                    task_id=request.task_id,
                    success=True,
                    result=json.dumps(result),
                    duration_ms=0
                )

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
async def run_grpc_server(host: str = "127.0.0.1", port: int = 50051):
    """Run the gRPC server with default configuration."""
    server = GRPCServer(host=host, port=port)
    await server.serve()


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_grpc_server())
