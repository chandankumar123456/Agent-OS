# AgentOS API & Interface Documentation

> **Complete reference for all production interfaces: REST API, gRPC, WebSocket, MCP, and BaseAgent**
> 
> Version: 0.1.0 | Last Updated: 2026-05-09

---

## Table of Contents

1. [REST API (FastAPI)](#1-rest-api-fastapi)
2. [gRPC Services](#2-grpc-services)
3. [WebSocket Interface](#3-websocket-interface)
4. [MCP (Multi-Component Protocol)](#4-mcp-multi-component-protocol)
5. [BaseAgent Interface](#5-baseagent-interface)
6. [Authentication](#6-authentication)
7. [Error Handling](#7-error-handling)
8. [Rate Limiting](#8-rate-limiting)

---

## 1. REST API (FastAPI)

### 1.1 Overview

| Property | Value |
|----------|-------|
| **Base URL** | `http://localhost:8000` (development) |
| **Default Port** | `8000` |
| **Protocol** | HTTP/1.1 or HTTP/2 (with TLS) |
| **Content-Type** | `application/json` |
| **OpenAPI** | Disabled in production (`/docs`, `/redoc`, `/openapi.json` not available) |

### 1.2 Health & Status Endpoints

#### `GET /health`
System health check endpoint.

**Request:**
```http
GET /health HTTP/1.1
Host: localhost:8000
```

**Response (200 OK):**
```json
{
  "status": "ok"
}
```

#### `GET /health/ready`
Readiness probe - checks database and Redis connectivity.

**Response (200 OK):**
```json
{
  "status": "ready",
  "checks": {
    "database": "ok",
    "redis": "ok"
  }
}
```

**Response (503 Service Unavailable):**
```json
{
  "status": "not_ready",
  "checks": {
    "database": "error: connection refused",
    "redis": "ok"
  }
}
```

#### `GET /health/live`
Liveness check.

**Response (200 OK):**
```json
{
  "status": "alive"
}
```

#### `GET /health/metrics`
Prometheus metrics endpoint.

**Response (200 OK):**
```text
# HELP agentos_tasks_total Total number of tasks
# TYPE agentos_tasks_total counter
agentos_tasks_total{status="completed"} 150
...
```

---

### 1.3 Task Management Endpoints

#### `POST /tasks`
Create a new task.

**Request:**
```http
POST /tasks HTTP/1.1
Host: localhost:8000
Content-Type: application/json
Authorization: Bearer {access_token}

{
  "query": "Research quantum computing applications",
  "config": {
    "max_steps": 10,
    "timeout": 300
  },
  "mode": "task"
}
```

**Request Schema:**
```python
class TaskConfig(BaseModel):
    max_steps: int = Field(default=10, ge=1, le=100)
    timeout: int = Field(default=300, ge=1, le=3600)

class TaskCreateRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=10000)
    config: Optional[TaskConfig] = None
    mode: Optional[str] = Field(default="task", pattern="^(task|workflow|autonomous|collaboration)$")
```

**Response (201 Created):**
```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "PENDING",
  "created_at": "2026-05-09T14:58:54.778Z"
}
```

**Response Schema:**
```python
class TaskCreateResponse(BaseModel):
    task_id: UUID
    status: TaskStatus  # PENDING, RUNNING, COMPLETED, FAILED
    created_at: datetime
```

#### `GET /tasks/{task_id}`
Get task status and results.

**Response (200 OK):**
```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "COMPLETED",
  "result": {
    "summary": "Quantum computing has applications in cryptography...",
    "confidence": 0.92
  },
  "steps": [
    {
      "id": "step-001",
      "step_number": 1,
      "agent_type": "planner",
      "status": "completed",
      "input_data": {...},
      "output_data": {...}
    }
  ],
  "workflow_state": {
    "workflow": {...},
    "nodes": [...],
    "edges": [...]
  },
  "error": null,
  "created_at": "2026-05-09T14:58:54.778Z"
}
```

**Response Schema:**
```python
class TaskStatusResponse(BaseModel):
    task_id: UUID
    status: TaskStatus
    result: Optional[Dict[str, Any]] = None
    steps: Optional[List[Dict[str, Any]]] = None
    workflow_state: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None
    retry_info: Optional[Dict[str, Any]] = None
    fallback_chain: Optional[List[str]] = None
    created_at: Optional[datetime] = None
```

#### `GET /tasks`
List tasks with pagination.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | int | 50 | Max results (1-200) |
| `offset` | int | 0 | Pagination offset |

**Response (200 OK):**
```json
[
  {
    "task_id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "COMPLETED",
    "result": {...},
    "created_at": "2026-05-09T14:58:54.778Z"
  }
]
```

#### `DELETE /tasks/{task_id}`
Cancel/delete a task.

**Response (200 OK):**
```json
{
  "message": "Task deleted"
}
```

#### `POST /tasks/{task_id}/approve`
Approve a task waiting for approval.

**Response (200 OK):**
```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "approved"
}
```

#### `POST /tasks/{task_id}/reject`
Reject a task waiting for approval.

**Response (200 OK):**
```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "rejected"
}
```

#### `GET /tasks/{task_id}/trace`
Get detailed task trace.

**Response (200 OK):**
```json
{
  "trace_id": "trace-550e8400",
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "workflow_state": {...},
  "node_traces": [...],
  "spans": [...]
}
```

---

### 1.4 Agent Management Endpoints

#### `GET /agents`
List all agents.

**Response (200 OK):**
```json
{
  "agents": [
    {
      "agent_id": "agent-550e8400",
      "name": "Research Assistant",
      "role": "researcher",
      "status": "active",
      "created_at": "2026-05-09T14:58:54.778Z",
      "model": "gpt-4",
      "tools": ["web_search", "pdf_reader"]
    }
  ]
}
```

#### `POST /agents`
Create a new agent.

**Request:**
```json
{
  "name": "Research Assistant",
  "role": "researcher",
  "system_prompt": "You are a research assistant...",
  "model": "gpt-4",
  "temperature": 0.7,
  "max_tokens": 2048,
  "tools": ["web_search", "pdf_reader"]
}
```

**Request Schema:**
```python
class AgentConfig(BaseModel):
    name: str
    role: str
    system_prompt: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 2048
    tools: List[str] = []
    version: Optional[str] = "1.0.0"
```

**Response (201 Created):**
```json
{
  "agent_id": "agent-550e8400",
  "name": "Research Assistant",
  "role": "researcher",
  "status": "active",
  "created_at": "2026-05-09T14:58:54.778Z",
  "system_prompt": "You are a research assistant...",
  "model": "gpt-4",
  "temperature": 0.7,
  "max_tokens": 2048,
  "tools": ["web_search", "pdf_reader"],
  "version": "1.0.0"
}
```

#### `GET /agents/{agent_id}`
Get agent details.

**Response (200 OK):** Same as create response.

#### `PUT /agents/{agent_id}`
Update agent configuration.

**Request/Response:** Same as create.

#### `DELETE /agents/{agent_id}`
Delete an agent. Core agents cannot be deleted.

**Response (200 OK):**
```json
{
  "message": "Agent agent-550e8400 deleted"
}
```

**Error (400 Bad Request):**
```json
{
  "detail": "Core agents cannot be deleted"
}
```

#### `GET /agents/{agent_id}/versions`
List agent versions.

**Response (200 OK):**
```json
{
  "versions": [
    {
      "version": "1.0.0",
      "name": "Research Assistant",
      "role": "researcher",
      "created_at": "2026-05-09T14:58:54.778Z"
    }
  ]
}
```

#### `POST /agents/{agent_id}/versions`
Create a new agent version.

**Request:** Same as create agent.

**Response (201 Created):** AgentVersionResponse

---

### 1.5 Tool Management Endpoints

#### `GET /tools`
List all tools (registry + database).

**Response (200 OK):**
```json
[
  {
    "name": "web_search",
    "description": "Search the web",
    "type": "builtin",
    "status": "active",
    "parameters": {...},
    "category": "search",
    "version": "1.0.0",
    "health_status": "healthy",
    "tags": []
  }
]
```

#### `POST /tools`
Register a new tool.

**Request:**
```json
{
  "name": "custom_tool",
  "description": "A custom tool",
  "type": "custom",
  "parameters_schema": {
    "type": "object",
    "properties": {...}
  },
  "template": "..."
}
```

**Response (201 Created):**
```json
{
  "success": true,
  "tool": {...}
}
```

#### `GET /tools/{tool_name}`
Get tool details.

**Response (200 OK):** ToolInfo

#### `POST /tools/{tool_name}/execute`
Execute a tool.

**Request:**
```json
{
  "parameters": {
    "query": "quantum computing"
  }
}
```

**Response (200 OK):**
```json
{
  "success": true,
  "result": {...}
}
```

#### `GET /tools/{tool_name}/health`
Check tool health.

**Response (200 OK):**
```json
{
  "name": "web_search",
  "status": "healthy"
}
```

#### `GET /tools/categories`
List tool categories.

**Response (200 OK):**
```json
{
  "categories": ["search", "file", "system", "custom"]
}
```

#### `GET /tools/health`
List all tools health status.

**Response (200 OK):** Array of tool health objects.

---

### 1.6 MCP Server Endpoints

#### `GET /tools/mcp-servers`
List all MCP servers.

**Response (200 OK):**
```json
[
  {
    "id": "server-001",
    "name": "brave-search",
    "endpoint": "http://localhost:3001",
    "health_status": "healthy",
    "version": "1.0.0",
    "status": "active"
  }
]
```

#### `POST /tools/mcp-servers`
Register an MCP server.

**Request:**
```json
{
  "name": "brave-search",
  "endpoint": "http://localhost:3001",
  "tools_list": [...],
  "auth_scope": "search",
  "version": "1.0.0"
}
```

**Response (201 Created):** MCPServerInfo

#### `GET /tools/mcp-servers/{name}`
Get MCP server details.

**Response (200 OK):** MCPServerInfo

#### `GET /tools/mcp-servers/{name}/health`
Check MCP server health.

**Response (200 OK):**
```json
{
  "name": "brave-search",
  "health_status": "healthy"
}
```

#### `GET /tools/mcp-servers/{name}/tools`
Discover tools from MCP server.

**Response (200 OK):** List of tool definitions.

---

### 1.7 Authentication Endpoints

#### `POST /auth/signup`
Register a new user.

**Request:**
```json
{
  "email": "user@example.com",
  "password": "SecurePass123!",
  "name": "John Doe"
}
```

**Request Schema:**
```python
class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=100)
    name: Optional[str] = Field(None, max_length=100)
```

**Response (201 Created):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
  "api_key": "aos_live_xxxxxxxxxxxx",
  "user": {
    "id": "user-550e8400",
    "email": "user@example.com",
    "name": "John Doe",
    "role": "user",
    "created_at": "2026-05-09T14:58:54.778Z"
  }
}
```

**Response Schema:**
```python
class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    api_key: str
    user: UserResponse
```

#### `POST /auth/login`
Authenticate user.

**Request:**
```json
{
  "email": "user@example.com",
  "password": "SecurePass123!"
}
```

**Response (200 OK):** Same as signup.

#### `POST /auth/refresh`
Refresh access token.

**Request:**
```json
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIs..."
}
```

**Response (200 OK):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
  "api_key": "aos_live_xxxxxxxxxxxx",
  "user": {...}
}
```

---

## 2. gRPC Services

### 2.1 Overview

| Property | Value |
|----------|-------|
| **Host** | `localhost` |
| **Port** | `50051` |
| **Protocol** | gRPC with Protocol Buffers |
| **Proto Path** | `supervisor/proto/` |
| **Services** | Runtime, Checkpoint, Worker |
| **Latency Target** | <5ms |

### 2.2 RuntimeService

```protobuf
service RuntimeService {
  // Task Management
  rpc CreateTask(CreateTaskRequest) returns (CreateTaskResponse);
  rpc GetTask(GetTaskRequest) returns (GetTaskResponse);
  rpc CancelTask(CancelTaskRequest) returns (CancelTaskResponse);
  rpc ListTasks(ListTasksRequest) returns (ListTasksResponse);
  rpc StreamTaskEvents(TaskEventRequest) returns (stream TaskEvent);
  
  // Task Actions
  rpc ApproveTask(ApproveTaskRequest) returns (ApproveTaskResponse);
  rpc RejectTask(RejectTaskRequest) returns (RejectTaskResponse);
  
  // Runtime Management
  rpc GetRuntimeStatus(GetRuntimeStatusRequest) returns (RuntimeStatus);
  rpc Shutdown(ShutdownRequest) returns (ShutdownResponse);
  
  // Health Check
  rpc HealthCheck(HealthCheckRequest) returns (HealthCheckResponse);
  
  // Configuration
  rpc GetConfig(GetConfigRequest) returns (GetConfigResponse);
  rpc SetConfig(SetConfigRequest) returns (SetConfigResponse);
}
```

#### Task Messages

```protobuf
message Task {
  string id = 1;
  string query = 2;
  TaskStatus status = 3;
  TaskType type = 4;
  google.protobuf.Timestamp created_at = 5;
  google.protobuf.Timestamp updated_at = 6;
  google.protobuf.Timestamp started_at = 7;
  google.protobuf.Timestamp completed_at = 8;
  string result = 9;
  string error = 10;
  int32 progress = 11; // 0-100
  map<string, string> metadata = 12;
}

enum TaskStatus {
  TASK_STATUS_UNSPECIFIED = 0;
  TASK_STATUS_PENDING = 1;
  TASK_STATUS_PLANNING = 2;
  TASK_STATUS_EXECUTING = 3;
  TASK_STATUS_VERIFYING = 4;
  TASK_STATUS_AWAITING_APPROVAL = 5;
  TASK_STATUS_COMPLETED = 6;
  TASK_STATUS_FAILED = 7;
  TASK_STATUS_CANCELLED = 8;
  TASK_STATUS_RECOVERING = 9;
}

enum TaskType {
  TASK_TYPE_UNSPECIFIED = 0;
  TASK_TYPE_SIMPLE = 1;        // Action V1 fast path
  TASK_TYPE_COMPLEX = 2;       // LangGraph full path
  TASK_TYPE_DESKTOP = 3;       // Desktop automation
  TASK_TYPE_AUTONOMOUS = 4;      // Autonomous mode
}
```

#### Request/Response Messages

```protobuf
// Create Task
message CreateTaskRequest {
  string query = 1;
  TaskType type = 2;
  bool require_approval = 3;
  int32 timeout_seconds = 4;
  string parent_task_id = 5;
  map<string, string> config = 6;
}

message CreateTaskResponse {
  Task task = 1;
  bool success = 2;
  string error = 3;
}

// Get Task
message GetTaskRequest {
  string task_id = 1;
}

message GetTaskResponse {
  Task task = 1;
  repeated Step steps = 2;
  bool success = 3;
  string error = 4;
}

// Cancel Task
message CancelTaskRequest {
  string task_id = 1;
  string reason = 2;
}

message CancelTaskResponse {
  bool success = 1;
  string error = 2;
}
```

#### Streaming Events

```protobuf
message TaskEventRequest {
  string task_id = 1;
  bool include_history = 2;
}

message TaskEvent {
  string task_id = 1;
  TaskEventType event_type = 2;
  google.protobuf.Timestamp timestamp = 3;
  Task task = 4;
  Step step = 5;
  LogMessage log = 6;
  string error = 7;
}

enum TaskEventType {
  TASK_EVENT_UNSPECIFIED = 0;
  TASK_EVENT_CREATED = 1;
  TASK_EVENT_STARTED = 2;
  TASK_EVENT_STEP_STARTED = 3;
  TASK_EVENT_STEP_COMPLETED = 4;
  TASK_EVENT_LOG = 5;
  TASK_EVENT_PROGRESS = 6;
  TASK_EVENT_COMPLETED = 7;
  TASK_EVENT_FAILED = 8;
  TASK_EVENT_CANCELLED = 9;
  TASK_EVENT_AWAITING_APPROVAL = 10;
}
```

### 2.3 CheckpointService

```protobuf
service CheckpointService {
  rpc SaveCheckpoint(SaveCheckpointRequest) returns (SaveCheckpointResponse);
  rpc GetCheckpoint(GetCheckpointRequest) returns (GetCheckpointResponse);
  rpc ListCheckpoints(ListCheckpointsRequest) returns (ListCheckpointsResponse);
  rpc GetLatestCheckpoint(GetLatestCheckpointRequest) returns (GetCheckpointResponse);
  rpc CleanupCheckpoints(CleanupCheckpointsRequest) returns (CleanupCheckpointsResponse);
  rpc SubscribeCheckpoints(SubscribeCheckpointsRequest) returns (stream CheckpointEvent);
}

message Checkpoint {
  string id = 1;
  string thread_id = 2;
  int64 checkpoint_ns = 3;
  CheckpointType checkpoint_type = 4;
  google.protobuf.Timestamp created_at = 5;
  bytes state_blob = 7;
  bytes channel_values = 8;
  bytes pending_sends = 9;
  repeated string parent_ids = 10;
  string metadata = 11;
  string task_id = 12;
}

enum CheckpointType {
  CHECKPOINT_TYPE_UNSPECIFIED = 0;
  CHECKPOINT_TYPE_LOCAL = 1;
  CHECKPOINT_TYPE_MEMORY = 2;
}
```

### 2.4 WorkerService

```protobuf
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
```

### 2.5 gRPC Error Codes

| gRPC Status | Description | Retryable |
|-------------|-------------|-----------|
| `OK` | Success | N/A |
| `CANCELLED` | Operation cancelled | No |
| `UNKNOWN` | Unknown error | Yes |
| `INVALID_ARGUMENT` | Invalid parameters | No |
| `DEADLINE_EXCEEDED` | Timeout | Yes |
| `NOT_FOUND` | Resource not found | No |
| `ALREADY_EXISTS` | Resource already exists | No |
| `PERMISSION_DENIED` | Access denied | No |
| `RESOURCE_EXHAUSTED` | Rate limit | Yes |
| `UNAVAILABLE` | Service unavailable | Yes |

---

## 3. WebSocket Interface

### 3.1 Overview

| Property | Value |
|----------|-------|
| **URL** | `ws://localhost:8000/ws/tasks/{task_id}?token={jwt}` |
| **Protocol** | WebSocket (RFC 6455) |
| **Message Format** | JSON |
| **Authentication** | JWT in query parameter |
| **Max Connections** | 100 per task |
| **Ping Interval** | 15 seconds |

### 3.2 Connection

```javascript
// Browser
const token = encodeURIComponent('Bearer eyJhbGciOiJIUzI1NiIs...');
const ws = new WebSocket(`ws://localhost:8000/ws/tasks/${taskId}?token=${token}`);

// Python
import websockets
uri = f"ws://localhost:8000/ws/tasks/{task_id}?token={token}"
async with websockets.connect(uri) as websocket:
    # Connection established
```

### 3.3 Client → Server Messages

**Ping:**
```json
"ping"
```

### 3.4 Server → Client Messages

**Heartbeat:**
```json
{
  "type": "heartbeat",
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "ts": "2026-05-09T14:58:54.778Z"
}
```

**Task Events (from event bus):**
```json
{
  "type": "task.status_changed",
  "data": {
    "status": "RUNNING",
    "task_id": "550e8400-e29b-41d4-a716-446655440000"
  },
  "timestamp": "2026-05-09T14:58:54.778Z"
}
```

### 3.5 Error Codes

| Code | Description |
|------|-------------|
| `1008` | Policy violation (auth failed, too many connections) |

### 3.6 ConnectionManager Implementation

```python
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, task_id: str, websocket: WebSocket) -> None:
        # Accepts connection, limits to 100 per task
        pass

    async def disconnect(self, task_id: str, websocket: WebSocket) -> None:
        # Removes connection
        pass

    async def broadcast(self, task_id: str, message: str) -> None:
        # Broadcasts to all connections for task
        pass
```

---

## 4. MCP (Multi-Component Protocol)

### 4.1 Overview

| Property | Value |
|----------|-------|
| **Purpose** | Inter-agent communication |
| **Transport** | In-memory (dev), Redis (production) |
| **Serialization** | JSON |
| **Pattern** | Pub/Sub with request/response |

### 4.2 Core Message Structure

```python
class MCPMessage(BaseModel):
    message_id: UUID = Field(default_factory=uuid4)
    task_id: UUID
    step_id: Optional[UUID] = None
    sender_agent: str = "system"
    receiver_agent: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    payload: Payload = Field(default_factory=Payload)
    metadata: Metadata = Field(default_factory=Metadata)

class Payload(BaseModel):
    input_data: Any = None
    output_data: Any = None
    context_snapshot: Optional[Dict[str, Any]] = None

class Metadata(BaseModel):
    status: str = "pending"  # pending, processing, completed, failed
    priority: int = 0
    retry_count: int = 0
    execution_time: Optional[float] = None
```

### 4.3 MCP Bus Interface

```python
class MCPBus(ABC):
    """Abstract message bus for inter-agent communication."""

    @abstractmethod
    async def publish(self, channel: str, message: MCPMessage) -> None:
        """Publish a message to a channel."""
        pass

    @abstractmethod
    async def subscribe(
        self, 
        channel: str, 
        handler: Callable[[MCPMessage], Any]
    ) -> None:
        """Subscribe to a channel with a handler."""
        pass

    @abstractmethod
    async def unsubscribe(
        self, 
        channel: str, 
        handler: Callable[[MCPMessage], Any]
    ) -> None:
        """Unsubscribe a handler from a channel."""
        pass
```

### 4.4 Implementations

**MemoryMCPBus** (Development):
- In-memory storage
- Max history: 10,000 messages
- No persistence

**RedisMCPBus** (Production):
- Redis pub/sub backend
- Requires background listener task
- Supports distributed deployments

### 4.5 Channel Patterns

| Pattern | Example | Purpose |
|---------|---------|---------|
| `agent.{agent_id}` | `agent.planner-001` | Direct messages |
| `task.{task_id}` | `task.550e8400` | Task updates |
| `broadcast.agents` | `broadcast.agents` | Broadcast |
| `system.events` | `system.events` | System events |

---

## 5. BaseAgent Interface

### 5.1 Overview

**Location:** `app/agents/base.py`

All agents must implement this protocol.

### 5.2 Protocol Definition

```python
class AgentRole(str, Enum):
    PLANNER = "planner"
    EXECUTOR = "executor"
    VERIFIER = "verifier"
    RESEARCHER = "researcher"

class AgentStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILURE = "failure"
    PAUSED = "paused"

class AgentInput(BaseModel):
    task_id: UUID
    step_id: UUID
    role: AgentRole
    input_data: Dict[str, Any] = Field(default_factory=dict)
    context: Dict[str, Any] = Field(default_factory=dict)
    constraints: Optional[Dict[str, Any]] = None
    allowed_tools: Optional[List[str]] = None
    fallback_tools: Optional[List[str]] = None

class AgentOutput(BaseModel):
    task_id: UUID
    step_id: UUID
    status: AgentStatus
    output_data: Dict[str, Any] = Field(default_factory=dict)
    confidence: float = 1.0
    reasoning_trace: Optional[List[str]] = None
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    recoverable: bool = True

@runtime_checkable
class BaseAgent(Protocol):
    name: str
    role: AgentRole
    
    async def execute(self, input_data: AgentInput) -> AgentOutput:
        ...
```

### 5.3 Agent Lifecycle

```
PENDING → RUNNING → SUCCESS
    ↓         ↓
    └────→ FAILURE
```

**States:**
- `PENDING`: Task queued, not started
- `RUNNING`: Currently executing
- `SUCCESS`: Completed successfully
- `FAILURE`: Failed with error
- `PAUSED`: Waiting for approval/external

---

## 6. Authentication

### 6.1 Authentication Methods

| Method | Use Case | Header |
|--------|----------|--------|
| **JWT Bearer** | User sessions | `Authorization: Bearer {token}` |
| **API Key** | Service-to-service | `X-API-Key: {api_key}` |

### 6.2 JWT Token

**Access Token:**
- **Type:** JWT (HS256)
- **Lifetime:** 30 minutes (configurable)
- **Payload:**
```json
{
  "sub": "user-550e8400",
  "email": "user@example.com",
  "role": "user",
  "iat": 1744204734,
  "exp": 1744206534
}
```

**Refresh Token:**
- **Type:** JWT
- **Lifetime:** 7 days

**API Key:**
- **Format:** `aos_live_{random}`
- **Lifetime:** Permanent (until revoked)

### 6.3 Token Validation

**Algorithm:**
1. Extract token from header/query
2. Verify JWT signature
3. Check expiration
4. Load user from database
5. Attach to request context

---

## 7. Error Handling

### 7.1 Error Response Format

All errors follow this structure:

```json
{
  "error": {
    "code": "TASK_NOT_FOUND",
    "message": "Task not found",
    "type": "runtime",
    "recoverable": false,
    "context": {
      "task_id": "550e8400..."
    }
  }
}
```

### 7.2 Error Schemas

```python
class ErrorContext(BaseModel):
    task_id: Optional[str] = None
    user_id: Optional[str] = None
    trace_id: Optional[str] = None
    details: Optional[Dict[str, Any]] = None

class ErrorEnvelope(BaseModel):
    code: str
    message: str
    context: ErrorContext = Field(default_factory=ErrorContext)
```

### 7.3 Error Codes

| Code | HTTP | Type | Description |
|------|------|------|-------------|
| `VALIDATION_ERROR` | 400 | validation | Invalid parameters |
| `TASK_NOT_FOUND` | 404 | runtime | Task doesn't exist |
| `AGENT_NOT_FOUND` | 404 | runtime | Agent doesn't exist |
| `TASK_ACCESS_DENIED` | 404 | auth | Not authorized for task |
| `RATE_LIMIT_EXCEEDED` | 429 | runtime | Too many requests |
| `TASK_QUEUE_UNAVAILABLE` | 503 | runtime | Celery unavailable |
| `EXECUTION_ERROR` | 500 | runtime | Execution failed |

---

## 8. Rate Limiting

### 8.1 Rate Limit Headers

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 60

{
  "error": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "Maximum active tasks (10) reached",
    "context": {
      "active_tasks": 10,
      "limit": 10
    }
  }
}
```

### 8.2 Rate Limits

| Resource | Limit | Notes |
|----------|-------|-------|
| Active tasks per user | 10 | Configurable via `MAX_ACTIVE_TASKS_PER_USER` |
| WebSocket connections per task | 100 | Hard limit |
| Task creation rate | Configurable | Via settings |

### 8.3 Rate Limit Response

```json
{
  "error": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "Maximum active tasks (10) reached",
    "type": "runtime",
    "recoverable": true,
    "context": {
      "active_tasks": 10,
      "limit": 10
    }
  }
}
```

---

## Appendix A: HTTP Status Codes

| Status | Meaning | Usage |
|--------|---------|-------|
| 200 | OK | Successful GET, PUT, DELETE |
| 201 | Created | Successful POST |
| 204 | No Content | Successful DELETE |
| 400 | Bad Request | Validation error |
| 401 | Unauthorized | Authentication required |
| 403 | Forbidden | Insufficient permissions |
| 404 | Not Found | Resource doesn't exist |
| 409 | Conflict | Resource conflict (duplicate) |
| 429 | Too Many Requests | Rate limit exceeded |
| 500 | Internal Server Error | Unexpected error |
| 503 | Service Unavailable | Dependency unavailable |

---

## Appendix B: UUID Formats

All IDs use UUID v4:
- **Task IDs:** `550e8400-e29b-41d4-a716-446655440000`
- **Agent IDs:** `agent-{uuid}`
- **User IDs:** `user-{uuid}`
- **Trace IDs:** `trace-{uuid}`

---

*Document generated from source analysis on 2026-05-09*
*For updates, see: https://github.com/agentos/agentos*
