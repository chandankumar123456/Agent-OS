"""
Worker Executor gRPC Server
Implements the WorkerExecutor service for Go-Python worker bridge communication.
This server runs as a subprocess and handles task execution requests from the Go supervisor.
"""

import asyncio
import json
import logging
import time
from concurrent import futures
from typing import Dict, Any

import grpc
from grpc import aio

# Import protobuf modules
import worker_pb2
import worker_pb2_grpc

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class WorkerExecutorServicer(worker_pb2_grpc.WorkerExecutorServicer):
    """
    Implementation of the WorkerExecutor gRPC service.
    Handles task execution requests from the Go supervisor.
    """
    
    def __init__(self):
        self.task_count = 0
        self.health_status = {
            "healthy": True,
            "status": "running",
            "start_time": int(time.time() * 1000)
        }
        logger.info("WorkerExecutorServicer initialized")
    
    def HealthCheck(self, request, context):
        """
        Health check endpoint for the worker executor.
        
        Returns:
            HealthResponse with healthy status and timestamp
        """
        logger.debug(f"Health check received for service: {request.service}")
        
        response = worker_pb2.HealthResponse(
            healthy=self.health_status["healthy"],
            status=self.health_status["status"],
            timestamp=int(time.time() * 1000)
        )
        
        return response
    
    def ExecuteTask(self, request, context):
        """
        Execute a task based on the task type.
        
        Supported task types:
        - mcp_tool_call: Execute an MCP tool
        - langgraph_task: Execute a LangGraph workflow
        - agent_task: Execute an agent task
        
        Args:
            request: TaskRequest with task details
            context: gRPC context
            
        Returns:
            TaskResponse with execution results
        """
        start_time = time.time()
        self.task_count += 1
        
        logger.info(f"Executing task {request.task_id} of type {request.task_type}")
        
        try:
            # Parse the payload
            try:
                payload = json.loads(request.payload) if request.payload else {}
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse payload for task {request.task_id}: {e}")
                duration_ms = int((time.time() - start_time) * 1000)
                return worker_pb2.TaskResponse(
                    task_id=request.task_id,
                    success=False,
                    result="",
                    error=f"Invalid JSON payload: {str(e)}",
                    duration_ms=duration_ms
                )
            
            # Route to appropriate handler based on task type
            if request.task_type == "mcp_tool_call":
                result = self._execute_mcp_tool_call(request.task_id, payload)
            elif request.task_type == "langgraph_task":
                result = self._execute_langgraph_task(request.task_id, payload)
            elif request.task_type == "agent_task":
                result = self._execute_agent_task(request.task_id, payload)
            else:
                # Unknown task type
                duration_ms = int((time.time() - start_time) * 1000)
                logger.warning(f"Unknown task type: {request.task_type}")
                return worker_pb2.TaskResponse(
                    task_id=request.task_id,
                    success=False,
                    result="",
                    error=f"Unknown or unsupported task type: {request.task_type}",
                    duration_ms=duration_ms
                )
            
            # Calculate duration
            duration_ms = int((time.time() - start_time) * 1000)
            
            # Add duration to result
            result["duration_ms"] = duration_ms
            
            logger.info(f"Task {request.task_id} completed in {duration_ms}ms")
            
            return worker_pb2.TaskResponse(
                task_id=request.task_id,
                success=result.get("success", True),
                result=json.dumps(result.get("result", {})),
                error=result.get("error", ""),
                duration_ms=duration_ms
            )
            
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.exception(f"Task {request.task_id} failed: {e}")
            return worker_pb2.TaskResponse(
                task_id=request.task_id,
                success=False,
                result="",
                error=f"Internal error: {str(e)}",
                duration_ms=duration_ms
            )
    
    def _execute_mcp_tool_call(self, task_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute an MCP tool call.
        
        Args:
            task_id: Unique task identifier
            payload: Task payload with tool name and parameters
            
        Returns:
            Dict with success status and result/error
        """
        tool_name = payload.get("tool", "")
        params = payload.get("params", {})
        
        logger.info(f"Executing MCP tool: {tool_name} for task {task_id}")
        
        # For now, return a mock successful result
        # In production, this would integrate with the MCPClientManager
        return {
            "success": True,
            "result": {
                "tool": tool_name,
                "params": params,
                "status": "completed",
                "mock": True,
                "message": f"Tool {tool_name} executed successfully"
            },
            "error": ""
        }
    
    def _execute_langgraph_task(self, task_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a LangGraph task.
        
        Args:
            task_id: Unique task identifier
            payload: Task payload with graph type and input
            
        Returns:
            Dict with success status and result/error
        """
        graph_type = payload.get("graph_type", "task")
        input_data = payload.get("input", {})
        config = payload.get("config", {})
        
        logger.info(f"Executing LangGraph {graph_type} for task {task_id}")
        
        # For now, return a mock successful result
        # In production, this would integrate with the LangGraph engine
        return {
            "success": True,
            "result": {
                "graph_type": graph_type,
                "input": input_data,
                "config": config,
                "status": "completed",
                "mock": True,
                "message": f"LangGraph {graph_type} executed successfully"
            },
            "error": ""
        }
    
    def _execute_agent_task(self, task_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute an agent task.
        
        Args:
            task_id: Unique task identifier
            payload: Task payload with agent type and input
            
        Returns:
            Dict with success status and result/error
        """
        agent_type = payload.get("agent_type", "executor")
        input_data = payload.get("input", {})
        context = payload.get("context", {})
        
        logger.info(f"Executing {agent_type} agent for task {task_id}")
        
        # For now, return a mock successful result
        # In production, this would integrate with the AgentRuntime
        return {
            "success": True,
            "result": {
                "agent_type": agent_type,
                "input": input_data,
                "context": context,
                "status": "completed",
                "mock": True,
                "message": f"Agent {agent_type} executed successfully"
            },
            "error": ""
        }


class WorkerExecutorServer:
    """
    gRPC server for the worker executor.
    Manages the server lifecycle and graceful shutdown.
    """
    
    def __init__(self, port: int = 50051, max_workers: int = 10):
        self.port = port
        self.max_workers = max_workers
        self.server = None
        self._shutdown_event = asyncio.Event()
    
    async def start(self):
        """Start the gRPC server."""
        self.server = aio.server(
            futures.ThreadPoolExecutor(max_workers=self.max_workers)
        )
        
        # Add servicer
        worker_pb2_grpc.add_WorkerExecutorServicer_to_server(
            WorkerExecutorServicer(), self.server
        )
        
        # Bind to port
        listen_addr = f"[::]:{self.port}"
        self.server.add_insecure_port(listen_addr)
        
        await self.server.start()
        logger.info(f"Worker Executor gRPC server started on port {self.port}")
        
        # Wait for shutdown
        await self._shutdown_event.wait()
    
    async def stop(self):
        """Stop the gRPC server gracefully."""
        logger.info("Shutting down Worker Executor gRPC server...")
        self._shutdown_event.set()
        if self.server:
            await self.server.stop(grace_period=5)
        logger.info("Worker Executor gRPC server stopped")


def serve_sync(port: int = 50051, max_workers: int = 10):
    """
    Synchronous entry point for the gRPC server.
    Used when running as a subprocess.
    """
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=max_workers)
    )
    
    # Add servicer
    worker_pb2_grpc.add_WorkerExecutorServicer_to_server(
        WorkerExecutorServicer(), server
    )
    
    # Bind to port
    listen_addr = f"[::]:{port}"
    server.add_insecure_port(listen_addr)
    
    server.start()
    logger.info(f"Worker Executor gRPC server started on port {port}")
    
    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
        server.stop(grace_period=5)


async def serve_async(port: int = 50051, max_workers: int = 10):
    """
    Async entry point for the gRPC server.
    """
    server = WorkerExecutorServer(port=port, max_workers=max_workers)
    await server.start()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Worker Executor gRPC Server")
    parser.add_argument(
        "--port",
        type=int,
        default=50051,
        help="Port to listen on (default: 50051)"
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=10,
        help="Maximum worker threads (default: 10)"
    )
    parser.add_argument(
        "--async",
        dest="use_async",
        action="store_true",
        help="Use async server implementation"
    )
    
    args = parser.parse_args()
    
    if args.use_async:
        asyncio.run(serve_async(port=args.port, max_workers=args.max_workers))
    else:
        serve_sync(port=args.port, max_workers=args.max_workers)
