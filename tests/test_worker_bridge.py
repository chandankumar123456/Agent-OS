#!/usr/bin/env python3
"""
Integration Test Suite for AgentOS Go-Python Worker Bridge
Tests the gRPC communication between Go supervisor and Python worker executor

This test suite validates:
- Health check endpoint
- Task execution for different task types (MCP tool calls, LangGraph tasks, Agent tasks)
- Error handling for unknown task types
- Performance/latency requirements (<1ms dispatch latency)
"""

import pytest
import asyncio
import subprocess
import time
import statistics
import json
from typing import Generator, Any
from contextlib import contextmanager

# Import protobuf modules from app.proto package
from app.proto import worker_pb2, worker_pb2_grpc

# gRPC imports
import grpc


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture(scope="session")
def python_server() -> Generator[subprocess.Popen, None, None]:
    """
    Pytest fixture to launch the Python gRPC executor server as a subprocess.
    
    This fixture:
    1. Starts the Python gRPC server on localhost:50051
    2. Waits for the server to be ready (health check)
    3. Yields the subprocess for use in tests
    4. Cleans up the subprocess after tests complete
    
    Yields:
        subprocess.Popen: The running Python gRPC server process
    """
    # Start the Python gRPC executor server
    # Note: This assumes a worker_executor_server.py exists that implements WorkerExecutor
    process = subprocess.Popen(
        ["python", "-m", "app.runtime.worker_executor_server"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    
    # Wait for server to be ready (max 10 seconds)
    max_wait = 10
    start_time = time.time()
    server_ready = False
    
    while time.time() - start_time < max_wait:
        try:
            # Try to connect and health check
            channel = grpc.insecure_channel("localhost:50051")
            grpc.channel_ready_future(channel).result(timeout=1)
            stub = worker_pb2_grpc.WorkerExecutorStub(channel)
            response = stub.HealthCheck(
                worker_pb2.HealthRequest(service="worker"),
                timeout=1
            )
            if response.healthy:
                server_ready = True
                break
        except Exception:
            time.sleep(0.1)
    
    if not server_ready:
        process.terminate()
        process.wait()
        pytest.skip("Python gRPC executor server not available - skipping worker bridge tests")
    
    yield process
    
    # Cleanup: terminate the subprocess
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


@pytest.fixture
def grpc_stub(python_server: subprocess.Popen) -> worker_pb2_grpc.WorkerExecutorStub:
    """
    Pytest fixture to create a gRPC stub for the worker executor service.
    
    Args:
        python_server: The running Python gRPC server subprocess
        
    Returns:
        WorkerExecutorStub: gRPC stub for making RPC calls
    """
    channel = grpc.insecure_channel("localhost:50051")
    stub = worker_pb2_grpc.WorkerExecutorStub(channel)
    return stub


# =============================================================================
# Test Cases
# =============================================================================

class TestWorkerBridgeHealth:
    """Test suite for worker bridge health check functionality"""
    
    def test_health_check_returns_healthy(self, grpc_stub: worker_pb2_grpc.WorkerExecutorStub) -> None:
        """
        Test that the health check endpoint returns healthy status.
        
        Acceptance Criteria:
        - HealthCheck RPC returns response with healthy=True
        - Response includes status message and timestamp
        """
        request = worker_pb2.HealthRequest(service="worker")
        response = grpc_stub.HealthCheck(request)
        
        assert response.healthy is True, "Health check should return healthy=True"
        assert response.status != "", "Health check should return a status message"
        assert response.timestamp > 0, "Health check should return a valid timestamp"


class TestWorkerBridgeTaskExecution:
    """Test suite for worker bridge task execution functionality"""
    
    def test_execute_mcp_tool_call(self, grpc_stub: worker_pb2_grpc.WorkerExecutorStub) -> None:
        """
        Test executing an MCP tool call task.
        
        Acceptance Criteria:
        - ExecuteTask RPC with task_type="mcp_tool_call" returns success=True
        - Response includes task_id matching request
        - Response includes JSON-encoded result
        - Response includes duration_ms
        """
        task_id = "test-mcp-task-001"
        payload = json.dumps({
            "tool": "filesystem__read_file",
            "params": {"path": "/tmp/test.txt"}
        })
        
        request = worker_pb2.TaskRequest(
            task_id=task_id,
            task_type="mcp_tool_call",
            payload=payload,
            priority=1,
            trace_id="trace-001"
        )
        
        response = grpc_stub.ExecuteTask(request)
        
        assert response.task_id == task_id, "Response task_id should match request"
        assert response.success is True, "MCP tool call should succeed"
        assert response.result != "", "Response should include a result"
        # Verify result is valid JSON
        result_data = json.loads(response.result)
        assert isinstance(result_data, dict), "Result should be JSON object"
        assert response.duration_ms >= 0, "Duration should be non-negative"
    
    def test_execute_langgraph_task(self, grpc_stub: worker_pb2_grpc.WorkerExecutorStub) -> None:
        """
        Test executing a LangGraph task.
        
        Acceptance Criteria:
        - ExecuteTask RPC with task_type="langgraph_task" returns success=True
        - Response includes task_id matching request
        - Response includes JSON-encoded result with graph execution output
        """
        task_id = "test-langgraph-task-001"
        payload = json.dumps({
            "graph_type": "task",
            "input": {"query": "Test query for LangGraph"},
            "config": {"max_steps": 5}
        })
        
        request = worker_pb2.TaskRequest(
            task_id=task_id,
            task_type="langgraph_task",
            payload=payload,
            priority=2,
            trace_id="trace-002"
        )
        
        response = grpc_stub.ExecuteTask(request)
        
        assert response.task_id == task_id, "Response task_id should match request"
        assert response.success is True, "LangGraph task should succeed"
        assert response.result != "", "Response should include a result"
        # Verify result is valid JSON
        result_data = json.loads(response.result)
        assert isinstance(result_data, dict), "Result should be JSON object"
    
    def test_execute_agent_task(self, grpc_stub: worker_pb2_grpc.WorkerExecutorStub) -> None:
        """
        Test executing an agent task.
        
        Acceptance Criteria:
        - ExecuteTask RPC with task_type="agent_task" returns success=True
        - Response includes task_id matching request
        - Response includes JSON-encoded result with agent output
        """
        task_id = "test-agent-task-001"
        payload = json.dumps({
            "agent_type": "executor",
            "input": {"task": "Execute test action"},
            "context": {"session_id": "session-001"}
        })
        
        request = worker_pb2.TaskRequest(
            task_id=task_id,
            task_type="agent_task",
            payload=payload,
            priority=1,
            trace_id="trace-003"
        )
        
        response = grpc_stub.ExecuteTask(request)
        
        assert response.task_id == task_id, "Response task_id should match request"
        assert response.success is True, "Agent task should succeed"
        assert response.result != "", "Response should include a result"
        # Verify result is valid JSON
        result_data = json.loads(response.result)
        assert isinstance(result_data, dict), "Result should be JSON object"


class TestWorkerBridgeErrorHandling:
    """Test suite for worker bridge error handling"""
    
    def test_execute_unknown_task_type(self, grpc_stub: worker_pb2_grpc.WorkerExecutorStub) -> None:
        """
        Test that unknown task types are handled gracefully.
        
        Acceptance Criteria:
        - ExecuteTask RPC with unknown task_type returns success=False
        - Response includes error message
        - Response includes task_id matching request
        """
        task_id = "test-unknown-task-001"
        payload = json.dumps({"data": "test"})
        
        request = worker_pb2.TaskRequest(
            task_id=task_id,
            task_type="unknown_task_type",
            payload=payload,
            priority=1,
            trace_id="trace-004"
        )
        
        response = grpc_stub.ExecuteTask(request)
        
        assert response.task_id == task_id, "Response task_id should match request"
        assert response.success is False, "Unknown task type should fail"
        assert response.error != "", "Response should include error message"
        assert "unknown" in response.error.lower() or "unsupported" in response.error.lower(), \
            "Error message should indicate unknown task type"


class TestWorkerBridgePerformance:
    """Test suite for worker bridge performance requirements"""
    
    def test_dispatch_latency_under_1ms(self, grpc_stub: worker_pb2_grpc.WorkerExecutorStub) -> None:
        """
        Test that task dispatch latency is under 1ms.
        
        Acceptance Criteria:
        - Average dispatch latency over 10 tasks should be < 1ms
        - Measures only the RPC call latency (network + dispatch)
        
        Note: This test measures the time from sending the request to receiving
        the response, which includes network latency and server processing time.
        """
        num_tasks = 10
        latencies = []
        
        for i in range(num_tasks):
            task_id = f"perf-test-task-{i:03d}"
            payload = json.dumps({"test": True, "iteration": i})
            
            request = worker_pb2.TaskRequest(
                task_id=task_id,
                task_type="mcp_tool_call",
                payload=payload,
                priority=1,
                trace_id=f"perf-trace-{i}"
            )
            
            # Measure latency
            start_time = time.perf_counter()
            response = grpc_stub.ExecuteTask(request)
            end_time = time.perf_counter()
            
            latency_ms = (end_time - start_time) * 1000  # Convert to milliseconds
            latencies.append(latency_ms)
            
            # Verify task succeeded
            assert response.success is True, f"Task {i} should succeed"
        
        # Calculate statistics
        avg_latency = statistics.mean(latencies)
        max_latency = max(latencies)
        min_latency = min(latencies)
        
        # Log performance metrics
        print(f"\nPerformance Results ({num_tasks} tasks):")
        print(f"  Average latency: {avg_latency:.3f} ms")
        print(f"  Min latency: {min_latency:.3f} ms")
        print(f"  Max latency: {max_latency:.3f} ms")
        print(f"  Std deviation: {statistics.stdev(latencies):.3f} ms")
        
        # Assert performance requirement
        assert avg_latency < 1.0, \
            f"Average dispatch latency ({avg_latency:.3f} ms) exceeds 1ms threshold"


# =============================================================================
# Async Test Support (for future async implementation)
# =============================================================================

@pytest.mark.asyncio
class TestWorkerBridgeAsync:
    """Async test suite for worker bridge (for future async gRPC implementation)"""
    
    async def test_async_health_check(self) -> None:
        """
        Test async health check (placeholder for future async implementation).
        
        Note: This test is skipped if async gRPC is not implemented.
        """
        pytest.skip("Async gRPC not yet implemented")


# =============================================================================
# Main Entry Point
# =============================================================================

if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "--tb=short"])
