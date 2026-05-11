# AgentOS Protocol Buffer Technical Specification

**Version:** 0.2.0  
**Last Updated:** 2026-05-09  
**Status:** Complete

---

## Executive Summary

AgentOS uses Protocol Buffers (protobuf) for gRPC communication between its multi-language components. This document provides a comprehensive technical reference for all 4 proto service definitions, 31 RPC methods, 70+ message types, and 9 enums.

| Metric | Value |
|--------|-------|
| Total Proto Files | 4 |
| Total Services | 4 |
| Total RPC Methods | 31 |
| Unary Methods | 29 |
| Streaming Methods | 2 |
| Total Message Types | 70+ |
| Total Enums | 9 |
| Enum Values | 50+ |
| Generated Python Files | 7 |

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [RuntimeService (runtime.proto)](#runtimeservice-runtimeproto)
3. [CheckpointService (checkpoint.proto)](#checkpointservice-checkpointproto)
4. [WorkerService (worker.proto)](#workerservice-workerproto)
5. [DesktopService (desktop.proto)](#desktopservice-desktopproto)
6. [Generated Python Classes](#generated-python-classes)
7. [Service Relationships](#service-relationships)
8. [Communication Patterns](#communication-patterns)
9. [Implementation Notes](#implementation-notes)

---

## Architecture Overview

### Service Communication Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    Go Supervisor                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │
│  │   Runtime    │  │  Checkpoint  │  │    Worker    │        │
│  │   Service    │  │   Service    │  │   Service    │        │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘        │
└─────────┼─────────────────┼─────────────────┼────────────────┘
          │                 │                 │
          └─────────────────┴─────────────────┘
                            │
                    gRPC (port 50051)
                            │
┌───────────────────────────┼─────────────────────────────────┐
│              Python Runtime (app/runtime/)                  │
│  ┌────────────────────────┘                                 │
│  │  RuntimeServiceServicer                                   │
│  │  CheckpointServiceServicer                                │
│  │  WorkerServiceServicer                                    │
│  └───────────────────────────────────────────────────────────┘
                              │
                              │ gRPC
                              ▼
┌─────────────────────────────────────────────────────────────┐
│              Rust Desktop Bridge (desktop-bridge/)          │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │           DesktopAutomation Service                     │ │
│  │  (Observe → Decide → Act → Verify → Recover loop)       │ │
│  └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### Proto File Locations

| File | Package | Location | Purpose |
|------|---------|----------|---------|
| runtime.proto | runtime | supervisor/proto/runtime.proto | Primary supervisor-runtime interface |
| checkpoint.proto | checkpoint | supervisor/proto/checkpoint.proto | State persistence via SQLite |
| worker.proto | worker | supervisor/proto/worker.proto | Worker pool task execution |
| desktop.proto | desktop_protocol | desktop/desktop-protocol/desktop.proto | Windows automation operations |

### Go Package Paths

| Proto | Go Package Path |
|-------|----------------|
| runtime.proto | github.com/AgentOS/supervisor/proto/runtime |
| checkpoint.proto | github.com/AgentOS/supervisor/proto/checkpoint |
| worker.proto | github.com/AgentOS/supervisor/proto |

---

## RuntimeService (runtime.proto)

**Location:** `supervisor/proto/runtime.proto`  
**Package:** `runtime`  
**Go Package:** `github.com/AgentOS/supervisor/proto/runtime`

### Service Definition

The primary gRPC interface between Go supervisor and Python runtime.

```protobuf
service RuntimeService {
  // Task management
  rpc CreateTask(CreateTaskRequest) returns (CreateTaskResponse);
  rpc GetTask(GetTaskRequest) returns (GetTaskResponse);
  rpc CancelTask(CancelTaskRequest) returns (CancelTaskResponse);
  rpc ListTasks(ListTasksRequest) returns (ListTasksResponse);
  
  // Real-time streaming
  rpc StreamTaskEvents(TaskEventRequest) returns (stream TaskEvent);
  
  // Approval operations
  rpc ApproveTask(ApproveTaskRequest) returns (ApproveTaskResponse);
  rpc RejectTask(RejectTaskRequest) returns (RejectTaskResponse);
  
  // Runtime management
  rpc GetRuntimeStatus(GetRuntimeStatusRequest) returns (RuntimeStatus);
  rpc Shutdown(ShutdownRequest) returns (ShutdownResponse);
  rpc HealthCheck(HealthCheckRequest) returns (HealthCheckResponse);
  
  // Configuration
  rpc GetConfig(GetConfigRequest) returns (GetConfigResponse);
  rpc SetConfig(SetConfigRequest) returns (SetConfigResponse);
}
```

### RPC Methods Summary

| Method | Request | Response | Pattern | Description |
|--------|---------|----------|---------|-------------|
| CreateTask | CreateTaskRequest | CreateTaskResponse | Unary | Create new task |
| GetTask | GetTaskRequest | GetTaskResponse | Unary | Get task with steps |
| CancelTask | CancelTaskRequest | CancelTaskResponse | Unary | Cancel running task |
| ListTasks | ListTasksRequest | ListTasksResponse | Unary | List with filtering |
| StreamTaskEvents | TaskEventRequest | TaskEvent | **Server Streaming** | Real-time events |
| ApproveTask | ApproveTaskRequest | ApproveTaskResponse | Unary | Approve task |
| RejectTask | RejectTaskRequest | RejectTaskResponse | Unary | Reject task |
| GetRuntimeStatus | GetRuntimeStatusRequest | RuntimeStatus | Unary | Get metrics |
| Shutdown | ShutdownRequest | ShutdownResponse | Unary | Graceful shutdown |
| HealthCheck | HealthCheckRequest | HealthCheckResponse | Unary | Health probe |
| GetConfig | GetConfigRequest | GetConfigResponse | Unary | Get configuration |
| SetConfig | SetConfigRequest | SetConfigResponse | Unary | Set configuration |

### Message Types

#### Task (Core Message)

| Field | Number | Type | Description |
|-------|--------|------|-------------|
| id | 1 | string | Unique task identifier |
| query | 2 | string | User query |
| status | 3 | TaskStatus | Current status enum |
| type | 4 | TaskType | Task type enum |
| created_at | 5 | google.protobuf.Timestamp | Creation time |
| updated_at | 6 | google.protobuf.Timestamp | Last update time |
| started_at | 7 | google.protobuf.Timestamp | Execution start |
| completed_at | 8 | google.protobuf.Timestamp | Completion time |
| result | 9 | string | JSON result |
| error | 10 | string | Error message |
| progress | 11 | int32 | Progress 0-100 |
| metadata | 12 | map<string, string> | Key-value metadata |

#### Step (Sub-message)

| Field | Number | Type | Description |
|-------|--------|------|-------------|
| index | 1 | int32 | Step sequence |
| tool_name | 2 | string | Tool executed |
| tool_input | 3 | string | Tool input JSON |
| tool_output | 4 | string | Tool output JSON |
| status | 5 | StepStatus | Step status enum |
| started_at | 6 | google.protobuf.Timestamp | Start time |
| completed_at | 7 | google.protobuf.Timestamp | End time |
| error | 8 | string | Error message |
| duration_ms | 9 | int64 | Execution duration |

#### LogMessage

| Field | Number | Type | Description |
|-------|--------|------|-------------|
| timestamp | 1 | google.protobuf.Timestamp | Log timestamp |
| level | 2 | LogLevel | Log level enum |
| message | 3 | string | Log message |
| context | 4 | map<string, string> | Context fields |
| source | 5 | string | Log source |

#### RuntimeStatus

| Field | Number | Type | Description |
|-------|--------|------|-------------|
| version | 1 | string | Runtime version |
| state | 2 | RuntimeState | Runtime state enum |
| active_tasks | 3 | int32 | Currently running tasks |
| queued_tasks | 4 | int32 | Tasks in queue |
| completed_tasks | 5 | int32 | Total completed |
| failed_tasks | 6 | int32 | Total failed |
| metrics | 7 | RuntimeMetrics | Performance metrics |
| uptime | 8 | google.protobuf.Timestamp | Runtime start time |
| config | 9 | map<string, string> | Configuration |

#### RuntimeMetrics

| Field | Number | Type | Description |
|-------|--------|------|-------------|
| cpu_percent | 1 | double | CPU usage % |
| memory_bytes | 2 | int64 | Memory in bytes |
| avg_task_duration_ms | 3 | double | Average task duration |
| task_success_rate | 4 | double | Success rate 0-1 |
| total_tool_calls | 5 | int64 | Total tool invocations |

### Enums

#### TaskStatus

| Value | Number | Description |
|-------|--------|-------------|
| TASK_STATUS_UNSPECIFIED | 0 | Default/unknown |
| TASK_STATUS_PENDING | 1 | Waiting to start |
| TASK_STATUS_PLANNING | 2 | Creating plan |
| TASK_STATUS_EXECUTING | 3 | Running steps |
| TASK_STATUS_VERIFYING | 4 | Verifying results |
| TASK_STATUS_AWAITING_APPROVAL | 5 | Paused for approval |
| TASK_STATUS_COMPLETED | 6 | Successfully finished |
| TASK_STATUS_FAILED | 7 | Execution failed |
| TASK_STATUS_CANCELLED | 8 | User cancelled |
| TASK_STATUS_RECOVERING | 9 | Attempting recovery |

#### TaskType

| Value | Number | Description |
|-------|--------|-------------|
| TASK_TYPE_UNSPECIFIED | 0 | Default |
| TASK_TYPE_SIMPLE | 1 | Action V1 fast path |
| TASK_TYPE_COMPLEX | 2 | LangGraph full path |
| TASK_TYPE_DESKTOP | 3 | Desktop automation |
| TASK_TYPE_AUTONOMOUS | 4 | Autonomous mode |

#### StepStatus

| Value | Number |
|-------|--------|
| STEP_STATUS_UNSPECIFIED | 0 |
| STEP_STATUS_PENDING | 1 |
| STEP_STATUS_EXECUTING | 2 |
| STEP_STATUS_COMPLETED | 3 |
| STEP_STATUS_FAILED | 4 |
| STEP_STATUS_SKIPPED | 5 |

#### TaskEventType

| Value | Number | Description |
|-------|--------|-------------|
| TASK_EVENT_UNSPECIFIED | 0 | Default |
| TASK_EVENT_CREATED | 1 | Task created |
| TASK_EVENT_STARTED | 2 | Execution started |
| TASK_EVENT_STEP_STARTED | 3 | Step began |
| TASK_EVENT_STEP_COMPLETED | 4 | Step finished |
| TASK_EVENT_LOG | 5 | Log message |
| TASK_EVENT_PROGRESS | 6 | Progress update |
| TASK_EVENT_COMPLETED | 7 | Task completed |
| TASK_EVENT_FAILED | 8 | Task failed |
| TASK_EVENT_CANCELLED | 9 | Task cancelled |
| TASK_EVENT_AWAITING_APPROVAL | 10 | Waiting for approval |

#### LogLevel

| Value | Number |
|-------|--------|
| LOG_LEVEL_UNSPECIFIED | 0 |
| LOG_LEVEL_DEBUG | 1 |
| LOG_LEVEL_INFO | 2 |
| LOG_LEVEL_WARNING | 3 |
| LOG_LEVEL_ERROR | 4 |
| LOG_LEVEL_CRITICAL | 5 |

#### RuntimeState

| Value | Number | Description |
|-------|--------|-------------|
| RUNTIME_STATE_UNSPECIFIED | 0 | Default |
| RUNTIME_STATE_INITIALIZING | 1 | Starting up |
| RUNTIME_STATE_READY | 2 | Ready for tasks |
| RUNTIME_STATE_BUSY | 3 | At capacity |
| RUNTIME_STATE_SHUTTING_DOWN | 4 | Graceful shutdown |
| RUNTIME_STATE_ERROR | 5 | Error state |

---

## CheckpointService (checkpoint.proto)

**Location:** `supervisor/proto/checkpoint.proto`  
**Package:** `checkpoint`  
**Go Package:** `github.com/AgentOS/supervisor/proto/checkpoint`

### Service Definition

Handles persistent state management via SQLite for LangGraph checkpointing.

```protobuf
service CheckpointService {
  rpc SaveCheckpoint(SaveCheckpointRequest) returns (SaveCheckpointResponse);
  rpc GetCheckpoint(GetCheckpointRequest) returns (GetCheckpointResponse);
  rpc ListCheckpoints(ListCheckpointsRequest) returns (ListCheckpointsResponse);
  rpc GetLatestCheckpoint(GetLatestCheckpointRequest) returns (GetCheckpointResponse);
  rpc CleanupCheckpoints(CleanupCheckpointsRequest) returns (CleanupCheckpointsResponse);
  rpc SubscribeCheckpoints(SubscribeCheckpointsRequest) returns (stream CheckpointEvent);
}
```

### RPC Methods Summary

| Method | Request | Response | Pattern | Description |
|--------|---------|----------|---------|-------------|
| SaveCheckpoint | SaveCheckpointRequest | SaveCheckpointResponse | Unary | Persist checkpoint |
| GetCheckpoint | GetCheckpointRequest | GetCheckpointResponse | Unary | Retrieve checkpoint |
| ListCheckpoints | ListCheckpointsRequest | ListCheckpointsResponse | Unary | List checkpoints |
| GetLatestCheckpoint | GetLatestCheckpointRequest | GetCheckpointResponse | Unary | Most recent |
| CleanupCheckpoints | CleanupCheckpointsRequest | CleanupCheckpointsResponse | Unary | Delete old |
| SubscribeCheckpoints | SubscribeCheckpointsRequest | CheckpointEvent | **Server Streaming** | Subscribe to updates |

### Message Types

#### Checkpoint (Core Message)

| Field | Number | Type | Description |
|-------|--------|------|-------------|
| id | 1 | string | Checkpoint unique ID |
| thread_id | 2 | string | LangGraph thread ID |
| checkpoint_ns | 3 | int64 | Nanosecond timestamp |
| checkpoint_type | 4 | CheckpointType | Storage type enum |
| created_at | 5 | google.protobuf.Timestamp | Creation time |
| updated_at | 6 | google.protobuf.Timestamp | Update time |
| state_blob | 7 | bytes | Serialized LangGraph state |
| channel_values | 8 | bytes | Serialized channel values |
| pending_sends | 9 | bytes | Pending sends data |
| parent_ids | 10 | repeated string | Parent checkpoint IDs |
| metadata | 11 | string | JSON metadata |
| task_id | 12 | string | Associated task ID |

#### SaveCheckpointRequest

| Field | Number | Type | Description |
|-------|--------|------|-------------|
| thread_id | 1 | string | Thread identifier |
| checkpoint_type | 2 | CheckpointType | Storage type |
| state_blob | 3 | bytes | State data |
| channel_values | 4 | bytes | Channel values |
| pending_sends | 5 | bytes | Pending sends |
| parent_ids | 6 | repeated string | Parent references |
| metadata | 7 | string | JSON metadata |
| task_id | 8 | string | Task reference |

#### CleanupCheckpointsRequest

| Field | Number | Type | Description |
|-------|--------|------|-------------|
| thread_id | 1 | string | Filter by thread |
| keep_count | 2 | int32 | Retain N most recent |
| older_than_days | 3 | int32 | Delete if older |
| dry_run | 4 | bool | Preview only |

#### MigrationStatus

| Field | Number | Type | Description |
|-------|--------|------|-------------|
| current_version | 1 | string | Current schema version |
| applied_migrations | 2 | repeated string | Completed migrations |
| pending_migrations | 3 | repeated string | Pending migrations |
| migration_required | 4 | bool | Migration needed |

#### CheckpointHealthResponse

| Field | Number | Type | Description |
|-------|--------|------|-------------|
| healthy | 1 | bool | Health status |
| total_checkpoints | 2 | int64 | Total count |
| total_size_bytes | 3 | int64 | Total storage size |
| migration_status | 4 | MigrationStatus | Migration state |
| error | 5 | string | Error message |

### Enums

#### CheckpointType

| Value | Number | Description |
|-------|--------|-------------|
| CHECKPOINT_TYPE_UNSPECIFIED | 0 | Default |
| CHECKPOINT_TYPE_LOCAL | 1 | Local SQLite storage |
| CHECKPOINT_TYPE_MEMORY | 2 | In-memory (testing) |

#### CheckpointEventType

| Value | Number | Description |
|-------|--------|-------------|
| CHECKPOINT_EVENT_UNSPECIFIED | 0 | Default |
| CHECKPOINT_EVENT_CREATED | 1 | New checkpoint |
| CHECKPOINT_EVENT_UPDATED | 2 | Checkpoint modified |
| CHECKPOINT_EVENT_DELETED | 3 | Checkpoint removed |
| CHECKPOINT_EVENT_CLEANUP | 4 | Cleanup operation |

---

## WorkerService (worker.proto)

**Location:** `supervisor/proto/worker.proto`  
**Package:** `worker`  
**Go Package:** `github.com/AgentOS/supervisor/proto`

### Service Definition

Task execution service for Go worker pool to Python executor communication.

```protobuf
service WorkerExecutor {
  rpc ExecuteTask(TaskRequest) returns (TaskResponse);
  rpc HealthCheck(HealthRequest) returns (HealthResponse);
}
```

### RPC Methods Summary

| Method | Request | Response | Pattern | Description |
|--------|---------|----------|---------|-------------|
| ExecuteTask | TaskRequest | TaskResponse | Unary | Execute task |
| HealthCheck | HealthRequest | HealthResponse | Unary | Worker health |

### Message Types

#### TaskRequest

| Field | Number | Type | Description |
|-------|--------|------|-------------|
| task_id | 1 | string | Task identifier |
| task_type | 2 | string | Type: mcp_tool_call, langgraph_task, agent_task |
| payload | 3 | string | JSON-serialized task data |
| timeout_seconds | 4 | int32 | Execution timeout |
| metadata | 5 | map<string, string> | Additional metadata |

#### TaskResponse

| Field | Number | Type | Description |
|-------|--------|------|-------------|
| task_id | 1 | string | Task identifier |
| success | 2 | bool | Execution success |
| result | 3 | string | JSON-serialized result |
| error | 4 | string | Error message |
| duration_ms | 5 | int64 | Execution time |
| worker_id | 6 | string | Processing worker ID |

#### HealthRequest

| Field | Number | Type | Description |
|-------|--------|------|-------------|
| worker_id | 1 | string | Worker identifier |

#### HealthResponse

| Field | Number | Type | Description |
|-------|--------|------|-------------|
| healthy | 1 | bool | Health status |
| version | 2 | string | Worker version |

---

## DesktopService (desktop.proto)

**Location:** `desktop/desktop-protocol/desktop.proto`  
**Package:** `desktop_protocol`

### Service Definition

Desktop automation service for Windows UI automation via Rust bridge.

```protobuf
service DesktopAutomation {
  // Observation
  rpc ScreenCapture(ScreenCaptureRequest) returns (ScreenCaptureResponse);
  rpc OcrScreen(OcrScreenRequest) returns (OcrScreenResponse);
  rpc FindWindow(FindWindowRequest) returns (FindWindowResponse);
  
  // Action loop: Observe → Decide → Act → Verify → Recover
  rpc Observe(ObserveRequest) returns (ObserveResponse);
  rpc Decide(DecideRequest) returns (DecideResponse);
  rpc Act(ActRequest) returns (ActResponse);
  rpc Verify(VerifyRequest) returns (VerifyResponse);
  rpc Recover(RecoverRequest) returns (RecoveryResponse);
  
  // Session management
  rpc CloseSession(CloseSessionRequest) returns (CloseSessionResponse);
}
```

### RPC Methods Summary

| Method | Request | Response | Description |
|--------|---------|----------|-------------|
| ScreenCapture | ScreenCaptureRequest | ScreenCaptureResponse | Capture screen region |
| OcrScreen | OcrScreenRequest | OcrScreenResponse | OCR on screen/image |
| FindWindow | FindWindowRequest | FindWindowResponse | Locate window by title |
| Observe | ObserveRequest | ObserveResponse | Observe desktop state |
| Decide | DecideRequest | DecideResponse | Make action decision |
| Act | ActRequest | ActResponse | Execute action |
| Verify | VerifyRequest | VerifyResponse | Verify action result |
| Recover | RecoverRequest | RecoveryResponse | Recover from failure |
| CloseSession | CloseSessionRequest | CloseSessionResponse | End session |

### Message Types

#### ScreenCaptureRequest

| Field | Number | Type | Description |
|-------|--------|------|-------------|
| window_id | 1 | string | Target window |
| x | 2 | int32 | X coordinate |
| y | 3 | int32 | Y coordinate |
| width | 4 | int32 | Capture width |
| height | 5 | int32 | Capture height |

#### ScreenCaptureResponse

| Field | Number | Type | Description |
|-------|--------|------|-------------|
| image_data | 1 | bytes | Image bytes |
| format | 2 | string | "png", "jpeg", etc. |
| error | 3 | string | Error message |

#### OcrScreenRequest

| Field | Number | Type | Description |
|-------|--------|------|-------------|
| image_data | 1 | bytes | Image to OCR |
| language | 2 | string | Language code |
| preprocess | 3 | bool | Preprocess image |

#### OcrScreenResponse

| Field | Number | Type | Description |
|-------|--------|------|-------------|
| text | 1 | string | Recognized text |
| confidence | 2 | float | OCR confidence 0-1 |
| error | 3 | string | Error message |

#### FindWindowRequest

| Field | Number | Type | Description |
|-------|--------|------|-------------|
| title | 1 | string | Window title |
| class_name | 2 | string | Window class |
| partial_match | 3 | bool | Allow partial match |

#### FindWindowResponse

| Field | Number | Type | Description |
|-------|--------|------|-------------|
| window_id | 1 | string | Window handle |
| title | 2 | string | Actual title |
| x | 3 | int32 | Position X |
| y | 4 | int32 | Position Y |
| width | 5 | int32 | Width |
| height | 6 | int32 | Height |
| found | 7 | bool | Success flag |
| error | 8 | string | Error message |

#### WindowInfo

| Field | Number | Type | Description |
|-------|--------|------|-------------|
| id | 1 | string | Window handle |
| title | 2 | string | Window title |
| x | 3 | int32 | Position X |
| y | 4 | int32 | Position Y |
| width | 5 | int32 | Width |
| height | 6 | int32 | Height |

#### ObserveResponse

| Field | Number | Type | Description |
|-------|--------|------|-------------|
| observation_id | 1 | string | Observation ID |
| timestamp | 2 | string | ISO timestamp |
| window_count | 3 | int32 | Number of windows |
| windows | 4 | repeated WindowInfo | Window list |
| text_content | 5 | string | Extracted text |
| screenshot_available | 6 | bool | Screenshot flag |
| error | 7 | string | Error message |

#### Action

| Field | Number | Type | Description |
|-------|--------|------|-------------|
| action_type | 1 | string | "click", "type", "screenshot" |
| target | 2 | string | Target element |
| x | 3 | int32 | X coordinate |
| y | 4 | int32 | Y coordinate |
| text | 5 | string | Text to type |
| confidence | 6 | float | Action confidence |
| action_id | 7 | string | Action identifier |

#### DecideResponse

| Field | Number | Type | Description |
|-------|--------|------|-------------|
| observation_id | 1 | string | Observation reference |
| action | 2 | Action | Decided action |
| error | 3 | string | Error message |

#### ActResponse

| Field | Number | Type | Description |
|-------|--------|------|-------------|
| success | 1 | bool | Execution success |
| action_id | 2 | string | Action ID |
| screenshot | 3 | bytes | Result screenshot |
| error | 4 | string | Error message |

#### VerifyResponse

| Field | Number | Type | Description |
|-------|--------|------|-------------|
| verified | 1 | bool | Verification result |
| confidence | 2 | float | Confidence score |
| notes | 3 | string | Verification notes |
| error | 4 | string | Error message |

#### RecoveryResponse

| Field | Number | Type | Description |
|-------|--------|------|-------------|
| success | 1 | bool | Recovery success |
| recovery_action | 2 | string | Action taken |
| notes | 3 | string | Recovery notes |
| error | 4 | string | Error message |

---

## Generated Python Classes

### File Structure

```
app/proto/
├── __init__.py              # Module exports
├── runtime_pb2.py           # Runtime message classes
├── runtime_pb2_grpc.py      # Runtime gRPC stubs/servicers
├── checkpoint_pb2.py        # Checkpoint message classes
├── checkpoint_pb2_grpc.py   # Checkpoint gRPC stubs/servicers
├── worker_pb2.py            # Worker message classes
├── worker_pb2_grpc.py       # Worker gRPC stubs/servicers
└── grpc_client.py           # Custom client wrappers
```

### runtime_pb2.py Classes

#### Messages
- `Task` - Core task representation
- `Step` - Individual execution step
- `LogMessage` - Structured logging
- `RuntimeStatus` - Runtime health/status
- `RuntimeMetrics` - Performance metrics
- `CreateTaskRequest`, `CreateTaskResponse`
- `GetTaskRequest`, `GetTaskResponse`
- `CancelTaskRequest`, `CancelTaskResponse`
- `ListTasksRequest`, `ListTasksResponse`
- `TaskEventRequest`, `TaskEvent`
- `ApproveTaskRequest`, `ApproveTaskResponse`
- `RejectTaskRequest`, `RejectTaskResponse`
- `GetRuntimeStatusRequest`
- `ShutdownRequest`, `ShutdownResponse`
- `HealthCheckRequest`, `HealthCheckResponse`
- `GetConfigRequest`, `GetConfigResponse`
- `SetConfigRequest`, `SetConfigResponse`

#### Enums
- `TaskStatus` - Task lifecycle states
- `TaskType` - Task classification
- `StepStatus` - Step execution states
- `TaskEventType` - Event categories
- `LogLevel` - Log severity levels
- `RuntimeState` - Runtime operational states

### runtime_pb2_grpc.py Classes

#### Client Stub
```python
class RuntimeServiceStub:
    def __init__(self, channel):
        self.CreateTask = channel.unary_unary(...)
        self.GetTask = channel.unary_unary(...)
        self.CancelTask = channel.unary_unary(...)
        self.ListTasks = channel.unary_unary(...)
        self.StreamTaskEvents = channel.unary_stream(...)
        # ... etc
```

#### Server Servicer
```python
class RuntimeServiceServicer:
    def CreateTask(self, request, context): ...
    def GetTask(self, request, context): ...
    def CancelTask(self, request, context): ...
    # ... etc
```

#### Registration
```python
def add_RuntimeServiceServicer_to_server(servicer, server): ...
```

### checkpoint_pb2.py Classes

#### Messages
- `Checkpoint` - LangGraph state checkpoint
- `SaveCheckpointRequest`, `SaveCheckpointResponse`
- `GetCheckpointRequest`, `GetCheckpointResponse`
- `ListCheckpointsRequest`, `ListCheckpointsResponse`
- `GetLatestCheckpointRequest`
- `CleanupCheckpointsRequest`, `CleanupCheckpointsResponse`
- `SubscribeCheckpointsRequest`
- `CheckpointEvent`
- `MigrationStatus`
- `RunMigrationsRequest`, `RunMigrationsResponse`
- `CheckpointHealthRequest`, `CheckpointHealthResponse`

#### Enums
- `CheckpointType` - LOCAL, MEMORY
- `CheckpointEventType` - CREATED, UPDATED, DELETED, CLEANUP

### checkpoint_pb2_grpc.py Classes

#### Client Stub
```python
class CheckpointServiceStub:
    def __init__(self, channel):
        self.SaveCheckpoint = channel.unary_unary(...)
        self.GetCheckpoint = channel.unary_unary(...)
        self.ListCheckpoints = channel.unary_unary(...)
        # ... etc
```

#### Server Servicer
```python
class CheckpointServiceServicer:
    def SaveCheckpoint(self, request, context): ...
    def GetCheckpoint(self, request, context): ...
    # ... etc
```

### worker_pb2.py Classes

#### Messages
- `TaskRequest` - Worker task request
- `TaskResponse` - Worker task response
- `HealthRequest` - Health check request
- `HealthResponse` - Health check response

### worker_pb2_grpc.py Classes

#### Client Stub
```python
class WorkerExecutorStub:
    def __init__(self, channel):
        self.ExecuteTask = channel.unary_unary(
            '/worker.WorkerExecutor/ExecuteTask',
            request_serializer=worker__pb2.TaskRequest.SerializeToString,
            response_deserializer=worker__pb2.TaskResponse.FromString,
        )
        self.HealthCheck = channel.unary_unary(
            '/worker.WorkerExecutor/HealthCheck',
            request_serializer=worker__pb2.HealthRequest.SerializeToString,
            response_deserializer=worker__pb2.HealthResponse.FromString,
        )
```

#### Server Servicer
```python
class WorkerExecutorServicer:
    def ExecuteTask(self, request, context):
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def HealthCheck(self, request, context):
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')
```

#### Registration
```python
def add_WorkerExecutorServicer_to_server(servicer, server):
    rpc_method_handlers = {
        'ExecuteTask': grpc.unary_unary_rpc_method_handler(...),
        'HealthCheck': grpc.unary_unary_rpc_method_handler(...),
    }
    generic_handler = grpc.method_handlers_generic_handler(
        'worker.WorkerExecutor', rpc_method_handlers)
    server.add_generic_rpc_handlers((generic_handler,))
```

### Custom Client Wrapper (grpc_client.py)

The `app/proto/grpc_client.py` provides high-level async wrappers:

| Class | Purpose |
|-------|---------|
| `GRPCClientConfig` | Configuration dataclass |
| `RuntimeServiceClient` | Runtime service operations |
| `CheckpointServiceClient` | Checkpoint operations |
| `WorkerServiceClient` | Worker operations |
| `GRPCClient` | Main client with async context manager |

---

## Service Relationships

### Dependency Flow

```
RuntimeService (Supervisor)
    ├── Delegates tasks to → WorkerService (Workers)
    ├── Manages checkpoints via → CheckpointService (SQLite)
    └── Desktop automation via → DesktopService (Rust Bridge)

WorkerService (Go Pool)
    └── Executes via → Python Runtime
        └── Desktop operations via → DesktopService (Rust)
```

### Service-to-Service Communication

| Source | Target | Purpose | Method |
|--------|--------|---------|--------|
| Supervisor RuntimeService | Python RuntimeService | Task management | gRPC |
| Supervisor WorkerService | Python Runtime | Task execution | gRPC |
| Python Runtime | CheckpointService | State persistence | gRPC |
| Python Runtime | DesktopService | Windows automation | gRPC |

---

## Communication Patterns

### Pattern Summary

| Pattern | Services | Use Case |
|---------|----------|----------|
| Unary | All services | Request-response operations |
| Server Streaming | RuntimeService.StreamTaskEvents, CheckpointService.SubscribeCheckpoints | Real-time event streaming |
| Bi-directional | None currently | Future: bidirectional streaming |

### Streaming Methods Detail

#### StreamTaskEvents
- **Service:** RuntimeService
- **Method:** `rpc StreamTaskEvents(TaskEventRequest) returns (stream TaskEvent)`
- **Purpose:** Real-time task progress updates
- **Client:** Subscribes to events for specific task
- **Server:** Pushes events as they occur

#### SubscribeCheckpoints
- **Service:** CheckpointService
- **Method:** `rpc SubscribeCheckpoints(SubscribeCheckpointsRequest) returns (stream CheckpointEvent)`
- **Purpose:** Real-time checkpoint change notifications
- **Client:** Subscribes to checkpoint updates
- **Server:** Pushes events on create/update/delete

---

## Implementation Notes

### Design Decisions

1. **Three Separate Services:** Clear separation of concerns (tasks, state, workers)
2. **Streaming for Events:** Real-time task progress via server streaming
3. **Binary Blobs for State:** LangGraph state serialized as `bytes` for flexibility
4. **Map Types for Metadata:** Flexible key-value storage across services
5. **Timestamp Usage:** `google.protobuf.Timestamp` for all time fields
6. **Optional Fields:** All fields optional (proto3 default) for backward compatibility

### External Dependencies

| Import | Usage |
|--------|-------|
| `google/protobuf/timestamp.proto` | Time fields across all services |
| `google/protobuf/struct.proto` | Dynamic structured data (Value, Struct) |

### Generated Code Version

| Component | Version |
|-----------|---------|
| gRPC Python | 1.80.0 |
| Protocol Buffers | 3.25+ |
| Generated | grpc_tools.protoc |

### Thread Safety

All generated Python classes are thread-safe for:
- **Reading:** Multiple threads can read messages simultaneously
- **Writing:** Each message should be used by single thread during mutation

The gRPC client wrappers in `grpc_client.py` use `asyncio` for concurrency.

---

## Appendix A: Complete Message Reference

### Runtime Messages (Complete)

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
  int32 progress = 11;
  map<string, string> metadata = 12;
}

message Step {
  int32 index = 1;
  string tool_name = 2;
  string tool_input = 3;
  string tool_output = 4;
  StepStatus status = 5;
  google.protobuf.Timestamp started_at = 6;
  google.protobuf.Timestamp completed_at = 7;
  string error = 8;
  int64 duration_ms = 9;
}

message LogMessage {
  google.protobuf.Timestamp timestamp = 1;
  LogLevel level = 2;
  string message = 3;
  map<string, string> context = 4;
  string source = 5;
}
```

### Checkpoint Messages (Complete)

```protobuf
message Checkpoint {
  string id = 1;
  string thread_id = 2;
  int64 checkpoint_ns = 3;
  CheckpointType checkpoint_type = 4;
  google.protobuf.Timestamp created_at = 5;
  google.protobuf.Timestamp updated_at = 6;
  bytes state_blob = 7;
  bytes channel_values = 8;
  bytes pending_sends = 9;
  repeated string parent_ids = 10;
  string metadata = 11;
  string task_id = 12;
}
```

### Worker Messages (Complete)

```protobuf
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

---

## Appendix B: Enum Value Quick Reference

### TaskStatus Values
```
0: TASK_STATUS_UNSPECIFIED
1: TASK_STATUS_PENDING
2: TASK_STATUS_PLANNING
3: TASK_STATUS_EXECUTING
4: TASK_STATUS_VERIFYING
5: TASK_STATUS_AWAITING_APPROVAL
6: TASK_STATUS_COMPLETED
7: TASK_STATUS_FAILED
8: TASK_STATUS_CANCELLED
9: TASK_STATUS_RECOVERING
```

### TaskType Values
```
0: TASK_TYPE_UNSPECIFIED
1: TASK_TYPE_SIMPLE
2: TASK_TYPE_COMPLEX
3: TASK_TYPE_DESKTOP
4: TASK_TYPE_AUTONOMOUS
```

### CheckpointType Values
```
0: CHECKPOINT_TYPE_UNSPECIFIED
1: CHECKPOINT_TYPE_LOCAL
2: CHECKPOINT_TYPE_MEMORY
```

---

**Document Version:** 1.0.0  
**Generated:** 2026-05-09  
**Status:** Complete
