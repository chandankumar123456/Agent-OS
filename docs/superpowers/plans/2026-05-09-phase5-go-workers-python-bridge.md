# Phase 5 Workstream 1: Go Workers Python Bridge - Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement gRPC-based Python bridge for Go worker pool to enable Go workers to execute Python tasks (MCP tool calls, LangGraph workflows) with <1ms dispatch latency.

**Architecture:** Go worker pool (`supervisor/workers/pool.go`) submits tasks via gRPC client to Python executor server (`app/workers/executor_server.py`). Server routes tasks to appropriate handlers (MCP tools, LangGraph graphs) and returns results. Uses unary gRPC calls on port 50052.

**Tech Stack:** Go 1.21+, Python 3.11+, gRPC (google.golang.org/grpc, grpcio), protobuf

---

## File Structure

| File | Purpose | Status |
|------|---------|--------|
| `supervisor/proto/worker.proto` | gRPC service definition | CREATE |
| `supervisor/workers/grpc_client.go` | Go gRPC client wrapper | CREATE |
| `supervisor/workers/pool.go` | Modify `executeViaPython` to use gRPC | MODIFY |
| `app/workers/executor_server.py` | Python gRPC server | CREATE |
| `app/workers/task_dispatcher.py` | Task routing logic | CREATE |
| `app/workers/__init__.py` | Package init | CREATE |
| `tests/test_worker_bridge.py` | Integration tests | CREATE |

---

## Task 1: Create Protobuf Definition

**Files:**
- Create: `supervisor/proto/worker.proto`
- Test: `go build ./...` (verify proto compiles)

- [ ] **Step 1: Create proto directory and definition**

```bash
mkdir -p supervisor/proto
```

Create `supervisor/proto/worker.proto`:

```protobuf
syntax = "proto3";

package worker;

option go_package = "github.com/AgentOS/supervisor/proto/worker";
option python_package = "app.workers.proto";

service WorkerExecutor {
  rpc ExecuteTask(TaskRequest) returns (TaskResponse);
  rpc HealthCheck(HealthRequest) returns (HealthResponse);
}

message TaskRequest {
  string task_id = 1;
  string task_type = 2;
  string payload = 3;
  int32 timeout_seconds = 4;
  map<string, string> metadata = 5;
}

message TaskResponse {
  string task_id = 1;
  bool success = 2;
  string result = 3;
  string error = 4;
  int64 duration_ms = 5;
  string worker_id = 6;
}

message HealthRequest {
  string worker_id = 1;
}

message HealthResponse {
  bool healthy = 1;
  string version = 2;
}
```

- [ ] **Step 2: Install protoc plugins for Go**

```bash
cd supervisor
go install google.golang.org/protobuf/cmd/protoc-gen-go@latest
go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@latest
```

- [ ] **Step 3: Generate Go code from proto**

```bash
cd supervisor
protoc --go_out=. --go_opt=paths=source_relative \
       --go-grpc_out=. --go-grpc_opt=paths=source_relative \
       proto/worker.proto
```

- [ ] **Step 4: Verify Go build succeeds**

```bash
cd supervisor
go build ./...
```

Expected: No errors

- [ ] **Step 5: Commit**

```bash
git add supervisor/proto/
git commit -m "feat: add protobuf definition for worker bridge"
```

---

## Task 2: Create Go gRPC Client

**Files:**
- Create: `supervisor/workers/grpc_client.go`
- Modify: `supervisor/workers/pool.go:435-446` (replace stub)

- [ ] **Step 1: Write failing test for gRPC client**

Create `supervisor/workers/grpc_client_test.go`:

```go
package workers

import (
	"context"
	"testing"
	"time"

	pb "github.com/AgentOS/supervisor/proto/worker"
)

func TestGrpcClientConnection(t *testing.T) {
	client, err := NewGrpcClient("localhost:50052", 5*time.Second)
	if err != nil {
		t.Fatalf("Failed to create client: %v", err)
	}
	defer client.Close()

	// Test health check
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	resp, err := client.HealthCheck(ctx, &pb.HealthRequest{WorkerId: "test-worker"})
	if err != nil {
		t.Fatalf("Health check failed: %v", err)
	}

	if !resp.Healthy {
		t.Errorf("Expected healthy=true, got false")
	}
}

func TestGrpcClientExecuteTask(t *testing.T) {
	client, err := NewGrpcClient("localhost:50052", 5*time.Second)
	if err != nil {
		t.Fatalf("Failed to create client: %v", err)
	}
	defer client.Close()

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	req := &pb.TaskRequest{
		TaskId:         "test-task-123",
		TaskType:       "mcp_tool_call",
		Payload:        `{"tool": "filesystem__read_file", "args": {"path": "/test.txt"}}`,
		TimeoutSeconds: 30,
		Metadata:       map[string]string{"source": "test"},
	}

	resp, err := client.ExecuteTask(ctx, req)
	if err != nil {
		t.Fatalf("Execute task failed: %v", err)
	}

	if resp.TaskId != "test-task-123" {
		t.Errorf("Expected task_id=test-task-123, got %s", resp.TaskId)
	}
}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd supervisor
go test ./workers -run TestGrpcClientConnection -v
```

Expected: FAIL - "NewGrpcClient not defined"

- [ ] **Step 3: Implement gRPC client**

Create `supervisor/workers/grpc_client.go`:

```go
package workers

import (
	"context"
	"fmt"
	"time"

	pb "github.com/AgentOS/supervisor/proto/worker"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/keepalive"
)

// GrpcClient wraps the gRPC connection to Python executor
type GrpcClient struct {
	conn   *grpc.ClientConn
	client pb.WorkerExecutorClient
	timeout time.Duration
}

// NewGrpcClient creates a new gRPC client
func NewGrpcClient(address string, timeout time.Duration) (*GrpcClient, error) {
	kaParams := keepalive.ClientParameters{
		Time:                10 * time.Second,
		Timeout:             20 * time.Second,
		PermitWithoutStream: true,
	}

	conn, err := grpc.Dial(
		address,
		grpc.WithTransportCredentials(insecure.NewCredentials()),
		grpc.WithKeepaliveParams(kaParams),
		grpc.WithBlock(),
		grpc.WithTimeout(timeout),
	)
	if err != nil {
		return nil, fmt.Errorf("failed to connect to executor: %w", err)
	}

	client := pb.NewWorkerExecutorClient(conn)

	return &GrpcClient{
		conn:    conn,
		client:  client,
		timeout: timeout,
	}, nil
}

// ExecuteTask sends a task to the Python executor
func (c *GrpcClient) ExecuteTask(ctx context.Context, req *pb.TaskRequest) (*pb.TaskResponse, error) {
	ctx, cancel := context.WithTimeout(ctx, time.Duration(req.TimeoutSeconds)*time.Second)
	defer cancel()

	return c.client.ExecuteTask(ctx, req)
}

// HealthCheck performs a health check on the executor
func (c *GrpcClient) HealthCheck(ctx context.Context, req *pb.HealthRequest) (*pb.HealthResponse, error) {
	ctx, cancel := context.WithTimeout(ctx, c.timeout)
	defer cancel()

	return c.client.HealthCheck(ctx, req)
}

// Close closes the gRPC connection
func (c *GrpcClient) Close() error {
	if c.conn != nil {
		return c.conn.Close()
	}
	return nil
}
```

- [ ] **Step 4: Run test to verify it compiles**

```bash
cd supervisor
go test ./workers -run TestGrpcClientConnection -v 2>&1 | head -20
```

Expected: Compiles but fails (Python server not running)

- [ ] **Step 5: Commit**

```bash
git add supervisor/workers/grpc_client.go supervisor/workers/grpc_client_test.go
git commit -m "feat: add gRPC client for Python executor"
```

---

## Task 3: Create Python gRPC Server

**Files:**
- Create: `app/workers/__init__.py`
- Create: `app/workers/executor_server.py`
- Modify: `requirements.txt` (add grpcio)

- [ ] **Step 1: Add grpcio to requirements**

```bash
echo "grpcio>=1.60.0" >> requirements.txt
echo "grpcio-tools>=1.60.0" >> requirements.txt
```

- [ ] **Step 2: Generate Python proto files**

```bash
python -m grpc_tools.protoc \
    --python_out=. \
    --grpc_python_out=. \
    --proto_path=supervisor/proto \
    supervisor/proto/worker.proto
```

- [ ] **Step 3: Create package init**

Create `app/workers/__init__.py`:

```python
"""AgentOS Worker Package - Python executor for Go worker pool."""

from .executor_server import serve

__all__ = ["serve"]
```

- [ ] **Step 4: Write Python executor server**

Create `app/workers/executor_server.py`:

```python
"""gRPC executor server - receives tasks from Go workers."""

import asyncio
import json
import logging
import time
from concurrent import futures
from typing import Dict, Any

import grpc

from supervisor.proto import worker_pb2
from supervisor.proto import worker_pb2_grpc

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class WorkerExecutorServicer(worker_pb2_grpc.WorkerExecutorServicer):
    """Implements the WorkerExecutor gRPC service."""

    def __init__(self):
        self.version = "1.0.0"
        self.task_handlers = {
            "mcp_tool_call": self._handle_mcp_tool_call,
            "langgraph_task": self._handle_langgraph_task,
            "agent_task": self._handle_agent_task,
        }

    async def ExecuteTask(
        self,
        request: worker_pb2.TaskRequest,
        context: grpc.ServicerContext,
    ) -> worker_pb2.TaskResponse:
        """Execute a task and return the result."""
        start_time = time.time()
        worker_id = request.metadata.get("worker_id", "unknown")

        logger.info(f"Received task: {request.task_id} type={request.task_type}")

        try:
            handler = self.task_handlers.get(request.task_type)
            if not handler:
                raise ValueError(f"Unknown task type: {request.task_type}")

            # Parse payload
            payload = json.loads(request.payload)

            # Execute task
            result = await handler(payload)

            duration_ms = int((time.time() - start_time) * 1000)

            return worker_pb2.TaskResponse(
                task_id=request.task_id,
                success=True,
                result=json.dumps(result),
                error="",
                duration_ms=duration_ms,
                worker_id=worker_id,
            )

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(f"Task execution failed: {e}")

            return worker_pb2.TaskResponse(
                task_id=request.task_id,
                success=False,
                result="",
                error=str(e),
                duration_ms=duration_ms,
                worker_id=worker_id,
            )

    async def HealthCheck(
        self,
        request: worker_pb2.HealthRequest,
        context: grpc.ServicerContext,
    ) -> worker_pb2.HealthResponse:
        """Return health status."""
        return worker_pb2.HealthResponse(
            healthy=True,
            version=self.version,
        )

    async def _handle_mcp_tool_call(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle MCP tool execution."""
        tool_name = payload.get("tool")
        args = payload.get("args", {})

        logger.info(f"Executing MCP tool: {tool_name}")

        # TODO: Integrate with actual MCP client
        # For now, return mock result
        return {
            "tool": tool_name,
            "args": args,
            "result": "mock_result",
            "status": "completed",
        }

    async def _handle_langgraph_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle LangGraph workflow execution."""
        workflow_id = payload.get("workflow_id")
        inputs = payload.get("inputs", {})

        logger.info(f"Executing LangGraph workflow: {workflow_id}")

        # TODO: Integrate with LangGraph runtime
        return {
            "workflow_id": workflow_id,
            "inputs": inputs,
            "result": "mock_workflow_result",
            "status": "completed",
        }

    async def _handle_agent_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle single agent execution."""
        agent_type = payload.get("agent_type")
        query = payload.get("query")

        logger.info(f"Executing agent: {agent_type}")

        # TODO: Integrate with agent runtime
        return {
            "agent_type": agent_type,
            "query": query,
            "result": "mock_agent_result",
            "status": "completed",
        }


async def serve(port: int = 50052):
    """Start the gRPC executor server."""
    server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=10))
    worker_pb2_grpc.add_WorkerExecutorServicer_to_server(
        WorkerExecutorServicer(), server
    )

    address = f"[::]:{port}"
    server.add_insecure_port(address)

    logger.info(f"Starting executor server on port {port}")
    await server.start()
    logger.info(f"Executor server started on {address}")

    try:
        await server.wait_for_termination()
    except asyncio.CancelledError:
        logger.info("Shutting down executor server")
        await server.stop(5)


if __name__ == "__main__":
    asyncio.run(serve())
```

- [ ] **Step 5: Test Python server starts**

```bash
cd app/workers
python executor_server.py &
sleep 2
python -c "
import grpc
from supervisor.proto import worker_pb2
from supervisor.proto import worker_pb2_grpc

channel = grpc.insecure_channel('localhost:50052')
stub = worker_pb2_grpc.WorkerExecutorStub(channel)
resp = stub.HealthCheck(worker_pb2.HealthRequest(worker_id='test'))
print(f'Health check: healthy={resp.healthy}, version={resp.version}')
"
kill %1 2>/dev/null
```

Expected: Health check returns healthy=True

- [ ] **Step 6: Commit**

```bash
git add app/workers/ requirements.txt supervisor/proto/*_pb2*.py
git commit -m "feat: add Python gRPC executor server"
```

---

## Task 4: Integrate gRPC Client into Worker Pool

**Files:**
- Modify: `supervisor/workers/pool.go:435-446` (replace stub)
- Modify: `supervisor/workers/pool.go:47-78` (add grpcClient field)
- Modify: `supervisor/workers/pool.go:98-120` (init gRPC client in NewPool)

- [ ] **Step 1: Add gRPC client to Pool struct**

Modify `supervisor/workers/pool.go` lines 47-78, add field after line 78:

```go
// Pool manages a dynamic pool of workers
type Pool struct {
	// ... existing fields ...

	// gRPC connection to Python executor
	grpcClient *GrpcClient
}
```

- [ ] **Step 2: Add gRPC client initialization in NewPool**

Modify `supervisor/workers/pool.go` lines 98-120, add after line 120:

```go
// NewPool creates a new worker pool with the given configuration
func NewPool(config *PoolConfig) *Pool {
	// ... existing code ...

	// Initialize gRPC client
	grpcClient, err := NewGrpcClient("localhost:50052", 30*time.Second)
	if err != nil {
		log.Printf("[WARN] Failed to connect to Python executor: %v. Tasks will fail.", err)
		// Continue without client - tasks will fail gracefully
	}

	pool := &Pool{
		// ... existing fields ...
		grpcClient: grpcClient,
	}

	return pool
}
```

- [ ] **Step 3: Replace executeViaPython stub with gRPC call**

Replace lines 433-446 in `supervisor/workers/pool.go`:

```go
// executeViaPython sends task to Python for execution via gRPC
func (w *Worker) executeViaPython(task *Task) (bool, map[string]interface{}, error) {
	if w.pool.grpcClient == nil {
		return false, nil, fmt.Errorf("gRPC client not initialized")
	}

	ctx, cancel := context.WithTimeout(context.Background(), task.Timeout)
	defer cancel()

	req := &pb.TaskRequest{
		TaskId:         task.ID,
		TaskType:       task.Type,
		Payload:        mustMarshalJSON(task.Payload),
		TimeoutSeconds: int32(task.Timeout.Seconds()),
		Metadata: map[string]string{
			"worker_id": w.id,
			"priority":  fmt.Sprintf("%d", task.Priority),
		},
	}

	resp, err := w.pool.grpcClient.ExecuteTask(ctx, req)
	if err != nil {
		return false, nil, fmt.Errorf("gRPC execution failed: %w", err)
	}

	if !resp.Success {
		return false, nil, fmt.Errorf("task execution failed: %s", resp.Error)
	}

	// Parse result JSON
	var result map[string]interface{}
	if err := json.Unmarshal([]byte(resp.Result), &result); err != nil {
		return false, nil, fmt.Errorf("failed to parse result: %w", err)
	}

	return true, result, nil
}

// mustMarshalJSON marshals data to JSON, panicking on error (should never happen)
func mustMarshalJSON(data map[string]interface{}) string {
	bytes, err := json.Marshal(data)
	if err != nil {
		panic(fmt.Sprintf("failed to marshal JSON: %v", err))
	}
	return string(bytes)
}
```

- [ ] **Step 4: Add imports for gRPC**

Add to imports in `supervisor/workers/pool.go`:

```go
import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"sync"
	"time"

	pb "github.com/AgentOS/supervisor/proto/worker"
)
```

- [ ] **Step 5: Add Close method to clean up gRPC connection**

Add method to `supervisor/workers/pool.go` after line 420:

```go
// Close stops the pool and cleans up resources
func (p *Pool) Close() error {
	p.Stop()
	
	if p.grpcClient != nil {
		if err := p.grpcClient.Close(); err != nil {
			log.Printf("[ERROR] Failed to close gRPC connection: %v", err)
		}
	}
	
	return nil
}
```

- [ ] **Step 6: Build and test**

```bash
cd supervisor
go build ./...
```

Expected: No errors

- [ ] **Step 7: Commit**

```bash
git add supervisor/workers/pool.go
git commit -m "feat: integrate gRPC client into worker pool"
```

---

## Task 5: Create Integration Tests

**Files:**
- Create: `tests/test_worker_bridge.py`

- [ ] **Step 1: Write integration test**

Create `tests/test_worker_bridge.py`:

```python
"""Integration tests for Go-Python worker bridge."""

import asyncio
import json
import subprocess
import sys
import time
import pytest
import grpc

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from supervisor.proto import worker_pb2
from supervisor.proto import worker_pb2_grpc


@pytest.fixture(scope="module")
def python_server():
    """Start Python executor server for testing."""
    proc = subprocess.Popen(
        [sys.executable, "-m", "app.workers.executor_server"],
        cwd=str(Path(__file__).parent.parent),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    time.sleep(2)  # Wait for server to start
    
    yield proc
    
    proc.terminate()
    proc.wait(timeout=5)


@pytest.fixture
def grpc_stub():
    """Create gRPC stub for testing."""
    channel = grpc.insecure_channel("localhost:50052")
    stub = worker_pb2_grpc.WorkerExecutorStub(channel)
    return stub


class TestHealthCheck:
    """Test health check endpoint."""

    def test_health_check_returns_healthy(self, python_server, grpc_stub):
        """Health check should return healthy status."""
        request = worker_pb2.HealthRequest(worker_id="test-worker-1")
        response = grpc_stub.HealthCheck(request)
        
        assert response.healthy is True
        assert response.version == "1.0.0"


class TestExecuteTask:
    """Test task execution endpoint."""

    def test_execute_mcp_tool_call(self, python_server, grpc_stub):
        """Should execute MCP tool call task."""
        request = worker_pb2.TaskRequest(
            task_id="test-mcp-001",
            task_type="mcp_tool_call",
            payload=json.dumps({
                "tool": "filesystem__read_file",
                "args": {"path": "/test.txt"},
            }),
            timeout_seconds=30,
            metadata={"worker_id": "test-worker"},
        )
        
        response = grpc_stub.ExecuteTask(request)
        
        assert response.success is True
        assert response.task_id == "test-mcp-001"
        assert response.error == ""
        
        result = json.loads(response.result)
        assert result["tool"] == "filesystem__read_file"
        assert result["status"] == "completed"

    def test_execute_langgraph_task(self, python_server, grpc_stub):
        """Should execute LangGraph workflow task."""
        request = worker_pb2.TaskRequest(
            task_id="test-lg-001",
            task_type="langgraph_task",
            payload=json.dumps({
                "workflow_id": "test-workflow",
                "inputs": {"query": "test"},
            }),
            timeout_seconds=30,
            metadata={"worker_id": "test-worker"},
        )
        
        response = grpc_stub.ExecuteTask(request)
        
        assert response.success is True
        result = json.loads(response.result)
        assert result["workflow_id"] == "test-workflow"

    def test_execute_unknown_task_type(self, python_server, grpc_stub):
        """Should fail for unknown task type."""
        request = worker_pb2.TaskRequest(
            task_id="test-unknown-001",
            task_type="unknown_type",
            payload=json.dumps({}),
            timeout_seconds=30,
            metadata={},
        )
        
        response = grpc_stub.ExecuteTask(request)
        
        assert response.success is False
        assert "Unknown task type" in response.error

    def test_task_duration_tracking(self, python_server, grpc_stub):
        """Should track task execution duration."""
        request = worker_pb2.TaskRequest(
            task_id="test-duration-001",
            task_type="mcp_tool_call",
            payload=json.dumps({"tool": "test"}),
            timeout_seconds=30,
            metadata={},
        )
        
        response = grpc_stub.ExecuteTask(request)
        
        assert response.success is True
        assert response.duration_ms >= 0


class TestLatency:
    """Test latency requirements."""

    def test_dispatch_latency_under_1ms(self, python_server, grpc_stub):
        """Task dispatch latency should be under 1ms."""
        latencies = []
        
        for i in range(10):
            request = worker_pb2.TaskRequest(
                task_id=f"perf-test-{i}",
                task_type="mcp_tool_call",
                payload=json.dumps({"tool": "test"}),
                timeout_seconds=30,
                metadata={},
            )
            
            start = time.perf_counter()
            response = grpc_stub.ExecuteTask(request)
            end = time.perf_counter()
            
            assert response.success is True
            latencies.append((end - start) * 1000)  # Convert to ms
        
        avg_latency = sum(latencies) / len(latencies)
        print(f"\nAverage dispatch latency: {avg_latency:.3f}ms")
        print(f"Min: {min(latencies):.3f}ms, Max: {max(latencies):.3f}ms")
        
        # Should be under 1ms for dispatch (execution time not included)
        assert avg_latency < 1.0, f"Average latency {avg_latency:.3f}ms exceeds 1ms target"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

- [ ] **Step 2: Run integration tests**

```bash
cd tests
python -m pytest test_worker_bridge.py -v
```

Expected: All tests pass

- [ ] **Step 3: Commit**

```bash
git add tests/test_worker_bridge.py
git commit -m "test: add integration tests for worker bridge"
```

---

## Task 6: Update Supervisor Integration

**Files:**
- Modify: `supervisor/main.go` (start Python executor)
- Modify: `supervisor/config/config.go` (add executor config)

- [ ] **Step 1: Add executor config**

Modify `supervisor/config/config.go`, add to `Config` struct:

```go
type Config struct {
	// ... existing fields ...
	
	// Python Executor
	PythonExecutorEnabled bool   `json:"python_executor_enabled" env:"PYTHON_EXECUTOR_ENABLED" default:"true"`
	PythonExecutorAddress string `json:"python_executor_address" env:"PYTHON_EXECUTOR_ADDRESS" default:"localhost:50052"`
	PythonExecutorTimeout int    `json:"python_executor_timeout" env:"PYTHON_EXECUTOR_TIMEOUT" default:"30"`
}
```

- [ ] **Step 2: Start Python executor from supervisor**

Add to `supervisor/main.go` in main() function:

```go
// Start Python executor if enabled
if config.PythonExecutorEnabled {
	go func() {
		log.Println("[INFO] Starting Python executor...")
		cmd := exec.Command("python", "-m", "app.workers.executor_server")
		cmd.Stdout = os.Stdout
		cmd.Stderr = os.Stderr
		if err := cmd.Run(); err != nil {
			log.Printf("[ERROR] Python executor failed: %v", err)
		}
	}()
	
	// Wait for executor to be ready
	time.Sleep(2 * time.Second)
}
```

- [ ] **Step 3: Test supervisor startup**

```bash
cd supervisor
go build -o supervisor.exe .
./supervisor.exe -port 8080
```

Expected: Supervisor starts, Python executor starts

- [ ] **Step 4: Commit**

```bash
git add supervisor/main.go supervisor/config/config.go
git commit -m "feat: integrate Python executor into supervisor lifecycle"
```

---

## Task 7: Documentation

**Files:**
- Create: `docs/superpowers/specs/2026-05-09-worker-bridge.md`

- [ ] **Step 1: Create architecture document**

Create `docs/superpowers/specs/2026-05-09-worker-bridge.md`:

```markdown
# Worker Bridge Architecture

## Overview
Go worker pool submits tasks to Python executor via gRPC on port 50052.

## Components
- Go Worker Pool (`supervisor/workers/pool.go`)
- gRPC Client (`supervisor/workers/grpc_client.go`)
- Python Executor (`app/workers/executor_server.py`)

## Task Types
1. `mcp_tool_call` - Direct MCP tool execution
2. `langgraph_task` - LangGraph workflows
3. `agent_task` - Single agent execution

## Latency
- Target: <1ms dispatch latency
- Measured: See benchmarks

## Configuration
- `PYTHON_EXECUTOR_ENABLED=true` - Enable executor
- `PYTHON_EXECUTOR_ADDRESS=localhost:50052` - gRPC address
- `PYTHON_EXECUTOR_TIMEOUT=30` - Default timeout (seconds)
```

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/specs/2026-05-09-worker-bridge.md
git commit -m "docs: add worker bridge architecture documentation"
```

---

## Success Criteria Verification

- [ ] **P0: Task dispatch latency <1ms**
  - Run: `pytest tests/test_worker_bridge.py::TestLatency -v`
  - Expected: Average < 1ms

- [ ] **P0: All tests pass**
  - Run: `pytest tests/test_worker_bridge.py -v`
  - Expected: 100% pass

- [ ] **P0: Supervisor starts successfully**
  - Run: `cd supervisor && go build -o supervisor.exe . && ./supervisor.exe`
  - Expected: No errors, Python executor starts

- [ ] **P1: gRPC health check works**
  - Run: `cd supervisor && go test ./workers -run TestGrpcClientConnection -v`
  - Expected: PASS

---

## Post-Implementation

### Next Steps
1. Integrate actual MCP client in Python executor
2. Add LangGraph workflow execution
3. Implement streaming for long-running tasks
4. Add metrics collection (Prometheus)
5. Workstream 2: Native IPC (Redis replacement)

### Monitoring
- Log: `supervisor/workers/pool.go` metrics every 30s
- Error: Failed gRPC connections
- Alert: Task execution failures > threshold

---

**Plan Created:** 2026-05-09
**Status:** Ready for implementation
