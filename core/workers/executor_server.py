"""
Worker Executor Server - Python gRPC server for task execution.

Receives task execution requests from Go workers and routes them
to appropriate handlers based on task type using the real LangGraph
orchestration engine.
"""

import asyncio
import json
import time
import os
import sys
from typing import Dict, Any
from concurrent import futures
from uuid import UUID

import grpc

# Ensure project root is in path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Import generated proto files
try:
    from supervisor.proto import worker_pb2
    from supervisor.proto import worker_pb2_grpc
except ImportError:
    worker_pb2 = None
    worker_pb2_grpc = None

# Import real AgentOS components
from core.orchestrator.core import orchestrator
from core.tools.registry import tool_registry
from core.logs.logger import logger


class WorkerExecutorServicer(worker_pb2_grpc.WorkerExecutorServicer):
    """
    gRPC servicer for worker task execution.
    
    Routes task execution requests to the real LangGraph orchestration
    engine and tool registry — no mock data.
    """

    def __init__(self):
        """Initialize the executor servicer."""
        pass

    def ExecuteTask(
        self,
        request,
        context: grpc.ServicerContext
    ):
        """
        Execute a task based on its type using real AgentOS components.
        """
        start_time = time.time()
        task_id = request.task_id
        task_type = request.task_type

        try:
            # Parse JSON payload
            try:
                payload = json.loads(request.payload) if request.payload else {}
            except json.JSONDecodeError as e:
                return self._error_response(task_id, f"Invalid JSON payload: {str(e)}", start_time)

            # Route to appropriate handler
            result = self._execute_real(task_type, task_id, payload)
            duration_ms = int((time.time() - start_time) * 1000)

            result_json = json.dumps(result, default=str)

            return worker_pb2.TaskResponse(
                task_id=task_id,
                success=True,
                result=result_json,
                error="",
                duration_ms=duration_ms
            )

        except Exception as e:
            logger.error(f"Executor task failed: {e}", exc_info=True)
            return self._error_response(task_id, str(e), start_time)

    def _execute_real(self, task_type: str, task_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a task using real AgentOS components.
        
        This runs synchronously inside the gRPC handler. For LangGraph tasks,
        we use asyncio.run() to bridge the async orchestrator into this sync context.
        """
        if task_type == "mcp_tool_call":
            return self._execute_mcp_tool(task_id, payload)
        elif task_type == "langgraph_task":
            return self._execute_langgraph(task_id, payload)
        elif task_type == "agent_task":
            return self._execute_agent(task_id, payload)
        else:
            raise ValueError(f"Unknown task type: {task_type}")

    def _execute_mcp_tool(self, task_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Execute an MCP tool call through the real tool registry."""
        tool_name = payload.get("tool_name", "")
        tool_args = payload.get("arguments", {})

        if not tool_name:
            raise ValueError("tool_name is required")

        # Execute via async bridge
        async def run():
            result = await tool_registry.execute(tool_name, tool_args)
            return {
                "task_id": task_id,
                "task_type": "mcp_tool_call",
                "tool_name": tool_name,
                "result": result.result if result.success else None,
                "error": result.error if not result.success else None,
                "success": result.success,
            }

        return asyncio.run(run())

    def _execute_langgraph(self, task_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a LangGraph workflow through the real orchestrator."""
        query = payload.get("query", "")
        config = payload.get("config", {})

        if not query:
            raise ValueError("query is required for LangGraph task")

        async def run():
            output = await orchestrator.execute_task(
                query=query,
                config=config,
                task_id=UUID(task_id) if task_id else None,
                user_id=payload.get("user_id", "system"),
            )
            return {
                "task_id": str(output.task_id),
                "task_type": "langgraph_task",
                "status": output.status.value if hasattr(output.status, 'value') else str(output.status),
                "result": output.output_data if hasattr(output, 'output_data') else None,
                "error": output.error_message if hasattr(output, 'error_message') else None,
                "success": output.status.name == "SUCCESS" if hasattr(output.status, 'name') else False,
            }

        return asyncio.run(run())

    def _execute_agent(self, task_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a single agent task through the real orchestrator."""
        query = payload.get("query", "")
        agent_name = payload.get("agent_name", payload.get("agent_id", "default"))

        config = {
            "mode": "task",
            "agent_id": agent_name,
        }
        if payload.get("model"):
            config["model"] = payload["model"]

        async def run():
            output = await orchestrator.execute_task(
                query=query,
                config=config,
                task_id=UUID(task_id) if task_id else None,
                user_id=payload.get("user_id", "system"),
            )
            return {
                "task_id": str(output.task_id),
                "task_type": "agent_task",
                "agent_name": agent_name,
                "status": output.status.value if hasattr(output.status, 'value') else str(output.status),
                "result": output.output_data if hasattr(output, 'output_data') else None,
                "error": output.error_message if hasattr(output, 'error_message') else None,
                "success": output.status.name == "SUCCESS" if hasattr(output.status, 'name') else False,
            }

        return asyncio.run(run())

    def HealthCheck(self, request, context):
        """Health check endpoint."""
        return worker_pb2.HealthResponse(
            healthy=True,
            status="healthy",
            timestamp=int(time.time() * 1000)
        )

    def _error_response(self, task_id: str, error: str, start_time: float):
        """Create an error TaskResponse."""
        duration_ms = int((time.time() - start_time) * 1000)
        return worker_pb2.TaskResponse(
            task_id=task_id,
            success=False,
            result="",
            error=error,
            duration_ms=duration_ms
        )


async def serve(port: int = 50052) -> None:
    """
    Start the gRPC executor server.
    
    Args:
        port: Port number to listen on (default: 50052)
    """
    if worker_pb2 is None:
        logger.error("worker_pb2 proto module not available, executor server cannot start")
        return

    server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=10))
    worker_pb2_grpc.add_WorkerExecutorServicer_to_server(
        WorkerExecutorServicer(), server
    )
    server.add_insecure_port(f"[::]:{port}")

    await server.start()
    logger.info(f"Worker Executor Server started on port {port}")
    logger.info("Using real LangGraph orchestration — no mock data")

    try:
        await server.wait_for_termination()
    except asyncio.CancelledError:
        logger.info("Executor server shutdown requested")
    finally:
        await server.stop(grace_period=5)
        logger.info("Worker Executor Server stopped")


if __name__ == "__main__":
    asyncio.run(serve())
