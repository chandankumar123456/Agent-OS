"""
Worker Executor Server - Python gRPC server for task execution.

Receives task execution requests from Go workers and routes them
to appropriate handlers based on task type.
"""

import asyncio
import json
import time
from typing import Dict, Any, Callable
from concurrent import futures

import grpc

# Import generated proto files
from supervisor.proto import worker_pb2
from supervisor.proto import worker_pb2_grpc


class WorkerExecutorServicer(worker_pb2_grpc.WorkerExecutorServicer):
    """
    gRPC servicer for worker task execution.
    
    Handles task execution requests from Go workers and routes
them to appropriate handlers based on task type.
    """
    
    def __init__(self):
        """Initialize the executor servicer with task handlers."""
        self._handlers: Dict[str, Callable] = {
            "mcp_tool_call": self._handle_mcp_tool_call,
            "langgraph_task": self._handle_langgraph_task,
            "agent_task": self._handle_agent_task,
        }
    
    def ExecuteTask(
        self, 
        request: worker_pb2.TaskRequest, 
        context: grpc.ServicerContext
    ) -> worker_pb2.TaskResponse:
        """
        Execute a task based on its type.
        
        Args:
            request: TaskRequest containing task details
            context: gRPC servicer context
            
        Returns:
            TaskResponse with result or error
        """
        start_time = time.time()
        task_id = request.task_id
        task_type = request.task_type
        
        try:
            # Parse JSON payload
            try:
                payload = json.loads(request.payload) if request.payload else {}
            except json.JSONDecodeError as e:
                duration_ms = int((time.time() - start_time) * 1000)
                return worker_pb2.TaskResponse(
                    task_id=task_id,
                    success=False,
                    result="",
                    error=f"Invalid JSON payload: {str(e)}",
                    duration_ms=duration_ms
                )
            
            # Route to appropriate handler
            handler = self._handlers.get(task_type)
            if not handler:
                duration_ms = int((time.time() - start_time) * 1000)
                return worker_pb2.TaskResponse(
                    task_id=task_id,
                    success=False,
                    result="",
                    error=f"Unknown task type: {task_type}",
                    duration_ms=duration_ms
                )
            
            # Execute handler
            result = handler(task_id, payload)
            duration_ms = int((time.time() - start_time) * 1000)
            
            return worker_pb2.TaskResponse(
                task_id=task_id,
                success=True,
                result=json.dumps(result),
                error="",
                duration_ms=duration_ms
            )
            
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            return worker_pb2.TaskResponse(
                task_id=task_id,
                success=False,
                result="",
                error=f"Execution error: {str(e)}",
                duration_ms=duration_ms
            )
    
    def HealthCheck(
        self, 
        request: worker_pb2.HealthRequest, 
        context: grpc.ServicerContext
    ) -> worker_pb2.HealthResponse:
        """
        Health check endpoint.
        
        Args:
            request: HealthRequest
            context: gRPC servicer context
            
        Returns:
            HealthResponse indicating service health
        """
        return worker_pb2.HealthResponse(
            healthy=True,
            status="healthy",
            timestamp=int(time.time() * 1000)
        )
    
    def _handle_mcp_tool_call(
        self, 
        task_id: str, 
        payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Handle MCP tool call tasks.
        
        Args:
            task_id: Unique task identifier
            payload: Task payload containing tool call details
            
        Returns:
            Dict with execution result
        """
        # TODO: Implement actual MCP tool call execution
        # For now, return mock result
        tool_name = payload.get("tool_name", "unknown")
        return {
            "task_id": task_id,
            "task_type": "mcp_tool_call",
            "status": "completed",
            "tool_name": tool_name,
            "result": f"Mock result for {tool_name}",
            "mock": True
        }
    
    def _handle_langgraph_task(
        self, 
        task_id: str, 
        payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Handle LangGraph workflow tasks.
        
        Args:
            task_id: Unique task identifier
            payload: Task payload containing workflow details
            
        Returns:
            Dict with execution result
        """
        # TODO: Implement actual LangGraph task execution
        # For now, return mock result
        workflow_name = payload.get("workflow_name", "unknown")
        return {
            "task_id": task_id,
            "task_type": "langgraph_task",
            "status": "completed",
            "workflow_name": workflow_name,
            "result": f"Mock result for workflow {workflow_name}",
            "mock": True
        }
    
    def _handle_agent_task(
        self, 
        task_id: str, 
        payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Handle single agent execution tasks.
        
        Args:
            task_id: Unique task identifier
            payload: Task payload containing agent execution details
            
        Returns:
            Dict with execution result
        """
        # TODO: Implement actual agent task execution
        # For now, return mock result
        agent_name = payload.get("agent_name", "unknown")
        return {
            "task_id": task_id,
            "task_type": "agent_task",
            "status": "completed",
            "agent_name": agent_name,
            "result": f"Mock result for agent {agent_name}",
            "mock": True
        }


async def serve(port: int = 50052) -> None:
    """
    Start the gRPC executor server.
    
    Args:
        port: Port number to listen on (default: 50052)
    """
    server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=10))
    worker_pb2_grpc.add_WorkerExecutorServicer_to_server(
        WorkerExecutorServicer(), server
    )
    server.add_insecure_port(f"[::]:{port}")
    
    await server.start()
    print(f"Worker Executor Server started on port {port}")
    
    try:
        await server.wait_for_termination()
    except asyncio.CancelledError:
        print("Server shutdown requested")
    finally:
        await server.stop(grace_period=5)
        print("Worker Executor Server stopped")


if __name__ == "__main__":
    # Run the server
    asyncio.run(serve())
