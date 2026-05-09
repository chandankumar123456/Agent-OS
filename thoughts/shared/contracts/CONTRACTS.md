# Contracts

## Subsystem Communication and Boundaries

This document defines all IPC schemas, gRPC contracts, event formats, and cross-language boundaries.

---

## Overview

AgentOS uses gRPC as the primary IPC mechanism between components. All contracts are defined in Protocol Buffers (.proto) for type safety and code generation.

### Communication Patterns

1. **Request/Response**: Synchronous calls (CLI → Supervisor)
2. **Server Streaming**: Asynchronous updates (Supervisor → UI)
3. **Bidirectional Streaming**: Real-time communication (Runtime events)

---

## gRPC Services

### Supervisor Service (Go)

**Port:** 50051 (configurable)  
**Purpose:** Main API for all clients

```protobuf
syntax = "proto3";
package supervisor;

service Supervisor {
  // Session Management
  rpc CreateSession(CreateSessionRequest) returns (Session);
  rpc GetSession(GetSessionRequest) returns (Session);
  rpc ListSessions(ListSessionsRequest) returns (SessionList);
  rpc PauseSession(PauseSessionRequest) returns (Session);
  rpc ResumeSession(ResumeSessionRequest) returns (Session);
  rpc StopSession(StopSessionRequest) returns (Session);
  
  // Real-time updates
  rpc StreamSessionEvents(StreamSessionEventsRequest) returns (stream SessionEvent);
  
  // Runtime Management
  rpc GetRuntimeStatus(GetRuntimeStatusRequest) returns (RuntimeStatus);
  rpc RestartRuntime(RestartRuntimeRequest) returns (RuntimeStatus);
  
  // Configuration
  rpc GetConfig(GetConfigRequest) returns (Config);
  rpc SetConfig(SetConfigRequest) returns (Config);
  
  // Logs
  rpc GetLogs(GetLogsRequest) returns (LogList);
  rpc StreamLogs(StreamLogsRequest) returns (stream LogEntry);
}

message CreateSessionRequest {
  string name = 1;
  string agent_type = 2;
  map<string, string> parameters = 3;
}

message GetSessionRequest {
  string session_id = 1;
}

message ListSessionsRequest {
  SessionStatus filter_status = 1;
  int32 limit = 2;
  int32 offset = 3;
}

message PauseSessionRequest {
  string session_id = 1;
}

message ResumeSessionRequest {
  string session_id = 1;
}

message StopSessionRequest {
  string session_id = 1;
  bool force = 2;
}

message StreamSessionEventsRequest {
  string session_id = 1;
}

message GetRuntimeStatusRequest {}

message RestartRuntimeRequest {
  bool force = 1;
}

message GetConfigRequest {
  string key = 1;
}

message SetConfigRequest {
  string key = 1;
  string value = 2;
}

message GetLogsRequest {
  string session_id = 1;
  int32 limit = 2;
  LogLevel min_level = 3;
}

message StreamLogsRequest {
  string session_id = 1;
  LogLevel min_level = 2;
}
```

### Runtime Service (Python)

**Port:** 50052 (internal)  
**Purpose:** Supervisor ↔ Runtime communication

```protobuf
syntax = "proto3";
package runtime;

service Runtime {
  // Task Execution
  rpc ExecuteTask(ExecuteTaskRequest) returns (ExecuteTaskResponse);
  rpc CancelTask(CancelTaskRequest) returns (CancelTaskResponse);
  
  // State Management
  rpc GetState(GetStateRequest) returns (State);
  rpc UpdateState(UpdateStateRequest) returns (State);
  rpc Checkpoint(CheckpointRequest) returns (CheckpointResponse);
  
  // Tool Management
  rpc ListTools(ListToolsRequest) returns (ToolList);
  rpc ExecuteTool(ExecuteToolRequest) returns (ExecuteToolResponse);
  
  // MCP Management
  rpc ListMCPServers(ListMCPServersRequest) returns (MCPServerList);
  rpc ConnectMCP(ConnectMCPRequest) returns (MCPConnection);
  rpc DisconnectMCP(DisconnectMCPRequest) returns (DisconnectMCPResponse);
  
  // Events
  rpc StreamEvents(StreamEventsRequest) returns (stream RuntimeEvent);
}

message ExecuteTaskRequest {
  string task_id = 1;
  string task_type = 2;
  bytes payload = 3;
  int32 timeout_ms = 4;
}

message ExecuteTaskResponse {
  string task_id = 1;
  TaskStatus status = 2;
  bytes result = 3;
  string error = 4;
  int64 execution_time_ms = 5;
}

message CancelTaskRequest {
  string task_id = 1;
}

message CancelTaskResponse {
  string task_id = 1;
  bool cancelled = 2;
}

message GetStateRequest {
  string session_id = 1;
}

message UpdateStateRequest {
  string session_id = 1;
  State state = 2;
}

message CheckpointRequest {
  string session_id = 1;
  string checkpoint_id = 2;
}

message CheckpointResponse {
  string checkpoint_id = 1;
  int64 timestamp = 2;
}

message ListToolsRequest {}

message ExecuteToolRequest {
  string tool_name = 1;
  map<string, bytes> parameters = 2;
  int32 timeout_ms = 3;
}

message ExecuteToolResponse {
  string tool_name = 1;
  bytes result = 2;
  bool success = 3;
  string error = 4;
}

message StreamEventsRequest {
  string session_id = 1;
}
```

### Desktop Service (Rust)

**Port:** 50053 (internal)  
**Purpose:** Runtime ↔ Desktop Engine communication

```protobuf
syntax = "proto3";
package desktop;

service Desktop {
  // Screen Operations
  rpc CaptureScreen(CaptureScreenRequest) returns (CaptureScreenResponse);
  rpc GetScreenInfo(GetScreenInfoRequest) returns (ScreenInfo);
  
  // Input Simulation
  rpc MouseClick(MouseClickRequest) returns (ActionResponse);
  rpc MouseMove(MouseMoveRequest) returns (ActionResponse);
  rpc KeyPress(KeyPressRequest) returns (ActionResponse);
  rpc TypeText(TypeTextRequest) returns (ActionResponse);
  
  // Window Management
  rpc ListWindows(ListWindowsRequest) returns (WindowList);
  rpc FocusWindow(FocusWindowRequest) returns (ActionResponse);
  rpc GetActiveWindow(GetActiveWindowRequest) returns (Window);
  
  // OCR
  rpc PerformOCR(PerformOCRRequest) returns (OCRResponse);
  
  // Action V1
  rpc ExecuteActionV1(ExecuteActionV1Request) returns (ActionV1Response);
}

message CaptureScreenRequest {
  Rect region = 1;
  ImageFormat format = 2;
}

message CaptureScreenResponse {
  bytes image_data = 1;
  int32 width = 2;
  int32 height = 3;
  int64 capture_time_ms = 4;
}

message MouseClickRequest {
  Point position = 1;
  MouseButton button = 2;
  int32 clicks = 3;
}

message MouseMoveRequest {
  Point position = 1;
  int32 duration_ms = 2;
}

message KeyPressRequest {
  string key = 1;
  repeated string modifiers = 2;
}

message TypeTextRequest {
  string text = 1;
  int32 interval_ms = 2;
}

message ListWindowsRequest {
  bool include_minimized = 1;
}

message FocusWindowRequest {
  string window_id = 1;
}

message PerformOCRRequest {
  Rect region = 1;
  string language = 2;
}

message OCRResponse {
  repeated TextBlock text_blocks = 1;
  int64 processing_time_ms = 2;
}

message ExecuteActionV1Request {
  string action_type = 1;
  map<string, string> parameters = 2;
  bytes context_image = 3;
}

message ActionV1Response {
  bool success = 1;
  string action_taken = 2;
  repeated ActionStep steps = 3;
  int64 execution_time_ms = 4;
}
```

---

## Data Types

### Common Types

```protobuf
syntax = "proto3";
package common;

// Basic Types
message Point {
  int32 x = 1;
  int32 y = 2;
}

message Rect {
  int32 x = 1;
  int32 y = 2;
  int32 width = 3;
  int32 height = 4;
}

message Size {
  int32 width = 1;
  int32 height = 2;
}

// Enums
enum SessionStatus {
  SESSION_STATUS_UNSPECIFIED = 0;
  SESSION_STATUS_PENDING = 1;
  SESSION_STATUS_RUNNING = 2;
  SESSION_STATUS_PAUSED = 3;
  SESSION_STATUS_COMPLETED = 4;
  SESSION_STATUS_FAILED = 5;
  SESSION_STATUS_STOPPED = 6;
}

enum TaskStatus {
  TASK_STATUS_UNSPECIFIED = 0;
  TASK_STATUS_PENDING = 1;
  TASK_STATUS_RUNNING = 2;
  TASK_STATUS_COMPLETED = 3;
  TASK_STATUS_FAILED = 4;
  TASK_STATUS_CANCELLED = 5;
}

enum LogLevel {
  LOG_LEVEL_UNSPECIFIED = 0;
  LOG_LEVEL_DEBUG = 1;
  LOG_LEVEL_INFO = 2;
  LOG_LEVEL_WARN = 3;
  LOG_LEVEL_ERROR = 4;
  LOG_LEVEL_FATAL = 5;
}

enum MouseButton {
  MOUSE_BUTTON_UNSPECIFIED = 0;
  MOUSE_BUTTON_LEFT = 1;
  MOUSE_BUTTON_RIGHT = 2;
  MOUSE_BUTTON_MIDDLE = 3;
}

enum ImageFormat {
  IMAGE_FORMAT_UNSPECIFIED = 0;
  IMAGE_FORMAT_PNG = 1;
  IMAGE_FORMAT_JPEG = 2;
  IMAGE_FORMAT_BMP = 3;
}

// Complex Types
message Session {
  string session_id = 1;
  string name = 2;
  SessionStatus status = 3;
  string agent_type = 4;
  int64 created_at = 5;
  int64 updated_at = 6;
  map<string, string> metadata = 7;
}

message SessionList {
  repeated Session sessions = 1;
  int32 total = 2;
}

message SessionEvent {
  string session_id = 1;
  string event_type = 2;
  int64 timestamp = 3;
  bytes payload = 4;
}

message RuntimeStatus {
  bool healthy = 1;
  string version = 2;
  int64 uptime_seconds = 3;
  int32 active_sessions = 4;
  int64 memory_usage_mb = 5;
  int64 cpu_usage_percent = 6;
}

message Config {
  map<string, string> values = 1;
  int64 version = 2;
  int64 updated_at = 3;
}

message LogEntry {
  int64 timestamp = 1;
  LogLevel level = 2;
  string component = 3;
  string session_id = 4;
  string message = 5;
  map<string, string> context = 6;
}

message LogList {
  repeated LogEntry entries = 1;
  bool has_more = 2;
}

message State {
  string session_id = 1;
  bytes state_data = 2;
  int64 checkpoint_id = 3;
  int64 timestamp = 4;
}

message Tool {
  string name = 1;
  string description = 2;
  bytes schema = 3;  // JSON schema
  bool requires_confirmation = 4;
}

message ToolList {
  repeated Tool tools = 1;
}

message Window {
  string window_id = 1;
  string title = 2;
  string process_name = 3;
  Rect bounds = 4;
  bool is_active = 5;
  bool is_minimized = 6;
}

message WindowList {
  repeated Window windows = 1;
}

message TextBlock {
  string text = 1;
  Rect bounds = 2;
  float confidence = 3;
}

message ActionResponse {
  bool success = 1;
  string error = 2;
  int64 execution_time_ms = 3;
}

message ActionStep {
  string step_type = 1;
  map<string, string> parameters = 2;
  bool success = 3;
  int64 execution_time_ms = 4;
}

message MCPServer {
  string server_id = 1;
  string name = 2;
  string command = 3;
  repeated string args = 4;
  map<string, string> env = 5;
  bool connected = 6;
}

message MCPServerList {
  repeated MCPServer servers = 1;
}

message MCPConnection {
  string server_id = 1;
  bool connected = 2;
  string error = 3;
}

message RuntimeEvent {
  string event_type = 1;
  int64 timestamp = 2;
  bytes payload = 3;
}
```

---

## Event Formats

### Session Events

Events streamed from Supervisor to UIs:

```json
{
  "session_id": "sess_abc123",
  "event_type": "state_change",
  "timestamp": "2026-05-09T10:30:00Z",
  "payload": {
    "previous_state": "planning",
    "new_state": "executing",
    "action": "open_browser"
  }
}
```

**Event Types:**
- `session_created`: New session started
- `state_change`: Agent state transitioned
- `action_started`: Action execution began
- `action_completed`: Action finished (success/failure)
- `human_checkpoint`: Waiting for human input
- `error`: Error occurred
- `log`: Log message emitted
- `completed`: Session finished

### Runtime Events

Events streamed from Python Runtime:

```json
{
  "event_type": "tool_execution",
  "timestamp": "2026-05-09T10:30:00Z",
  "payload": {
    "tool_name": "desktop__click",
    "parameters": {"x": 100, "y": 200},
    "result": {"success": true},
    "execution_time_ms": 15
  }
}
```

**Event Types:**
- `llm_request`: LLM API call started
- `llm_response`: LLM response received
- `tool_execution`: Tool executed
- `tool_result`: Tool returned result
- `checkpoint`: State checkpointed
- `error`: Runtime error

---

## MCP Contracts

MCP (Model Context Protocol) uses JSON-RPC over stdio or HTTP.

### Request Format

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "browser_navigate",
    "arguments": {
      "url": "https://example.com"
    }
  }
}
```

### Response Format

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Navigated to https://example.com"
      }
    ],
    "isError": false
  }
}
```

### Tool Namespacing

Tools are namespaced as `{server}__{tool}`:
- `desktop__click`
- `desktop__type`
- `browser__navigate`
- `browser__screenshot`
- `files__read`
- `files__write`

---

## Ownership Rules

### State Ownership

| State | Owner | Writes | Reads |
|-------|-------|--------|-------|
| Session metadata | Supervisor | Supervisor | All |
| Agent runtime state | Python Runtime | Python Runtime | Supervisor (via events) |
| Desktop context | Rust Engine | Rust Engine | Python Runtime (via gRPC) |
| Configuration | Supervisor | Supervisor | All |
| Logs | Supervisor | All | All |
| MCP connections | Python Runtime | Python Runtime | Supervisor (via events) |

### Resource Ownership

| Resource | Owner | Lifecycle |
|----------|-------|-----------|
| SQLite database | Supervisor | Created on first start, persists |
| Python subprocess | Supervisor | Spawned on startup, restarted on crash |
| Rust subprocess | Supervisor | Spawned on first desktop action |
| MCP servers | Python Runtime | Managed per-server, lifecycle varies |
| UI connections | Supervisor | Ephemeral, attach/detach |

---

## Serialization Formats

### Protocol Buffers
- **Use for:** gRPC communication
- **Advantages:** Efficient, type-safe, code generation
- **Generated code:** Committed to repo for each language

### JSON
- **Use for:** Event payloads, logs, configuration
- **Advantages:** Human-readable, debugging
- **Schema:** Defined in .proto (JSON encoding)

### SQLite
- **Use for:** Persistent state, session history, configuration
- **Schema:** Versioned migrations
- **Access:** Via Go supervisor only

### MessagePack (Optional)
- **Use for:** High-performance IPC if needed
- **Advantages:** Smaller than JSON, faster parsing
- **Consider:** If JSON becomes bottleneck

---

## Cross-Language Boundaries

### Go ↔ Python

**Interface:** gRPC  
**Data:** Protobuf  
**Patterns:**
- Go (supervisor) calls Python (runtime) for task execution
- Python streams events to Go
- Python requests desktop actions via Go proxy or direct to Rust

### Python ↔ Rust

**Interface:** gRPC  
**Data:** Protobuf  
**Patterns:**
- Python (runtime) calls Rust (desktop) for automation
- Rust returns results synchronously (<5ms)
- Rust streams events for long-running operations

### Rust ↔ Rust (CLI ↔ Supervisor)

**Interface:** gRPC  
**Data:** Protobuf  
**Patterns:**
- CLI makes synchronous calls to supervisor
- CLI subscribes to event streams
- Shared types in common Rust crate

### Rust ↔ JavaScript (Tauri)

**Interface:** Tauri commands / gRPC (sidecar)  
**Data:** JSON / Protobuf  
**Patterns:**
- Tauri main process calls supervisor gRPC
- Tauri uses sidecar for supervisor subprocess
- Frontend (React) talks to Tauri backend

---

## State Synchronization

### Eventual Consistency Model

**Supervisor:**
- Authoritative for session metadata
- Receives events from runtime
- Updates SQLite
- Broadcasts to connected UIs

**Runtime:**
- Authoritative for agent state
- Streams events to supervisor
- Receives commands from supervisor
- Checkpoint to SQLite via supervisor

**UI:**
- Eventually consistent view
- Receives events from supervisor
- Optimistic updates allowed
- Conflicts resolved by supervisor

### Conflict Resolution

**Last-Write-Wins:**
- Session metadata: Supervisor wins
- Configuration: User preference wins
- Runtime state: Runtime wins

**Version Vectors:**
- Consider if concurrent edits become issue
- Start with simple timestamps

---

## Security Boundaries

### Authentication

**Phase 1:** Local only, no authentication  
**Phase 3+:** Optional token-based auth for remote access

### Authorization

**Default Deny:**
- New MCP servers require explicit approval
- File access requires user confirmation
- Network access requires permission

### Encryption

**At Rest:**
- SQLite: File permissions
- Config: Encrypted API keys
- Logs: Unencrypted (local)

**In Transit:**
- gRPC: TLS optional for local, required for remote
- IPC: Local sockets (no encryption needed)

---

## Error Handling

### gRPC Status Codes

| Code | Use Case |
|------|----------|
| OK | Success |
| CANCELLED | Request cancelled by client |
| UNKNOWN | Unexpected error |
| INVALID_ARGUMENT | Bad parameter |
| DEADLINE_EXCEEDED | Timeout |
| NOT_FOUND | Resource not found |
| ALREADY_EXISTS | Duplicate resource |
| PERMISSION_DENIED | Unauthorized |
| RESOURCE_EXHAUSTED | Quota exceeded |
| FAILED_PRECONDITION | State not ready |
| ABORTED | Conflict, retry |
| UNAVAILABLE | Service unavailable |
| INTERNAL | Server error |

### Error Response Format

```protobuf
message ErrorDetails {
  string error_type = 1;
  string message = 2;
  bool recoverable = 3;
  string code = 4;
  map<string, string> context = 5;
  int32 retry_after_ms = 6;
}
```

---

## Versioning

### API Versioning

**gRPC:**
- Breaking changes: New service version (v1, v2)
- Non-breaking: Add fields (backward compatible)
- Deprecation: Keep old versions for 2 releases

**Protobuf:**
- Use reserved fields for deleted fields
- Add new fields with next available number
- Never change field numbers

### Protocol Negotiation

**Handshake:**
1. Client sends supported versions
2. Server responds with chosen version
3. Both use agreed version for session

---

## Last Updated

**Date:** 2026-05-09  
**By:** Agent  
**Version:** 1.0.0
