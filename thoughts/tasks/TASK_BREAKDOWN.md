# AgentOS Task Breakdown - Phase 1 gRPC Bridge Implementation

## Overview
This document contains detailed task breakdowns for implementing the gRPC bridge between Go supervisor and Python runtime. Tasks are organized by implementation stream and marked with specific acceptance criteria.

## Phase 1 Critical Path: gRPC Bridge

### Stream A: Go Supervisor gRPC Extensions

**Task A1: Create Runtime Service Protobuf Bindings**
- **File**: `supervisor/proto/runtime.proto` (already created)
- **Work**: Generate Go bindings using protoc
- **Command**: `protoc --go_out=paths=source_relative:supervisor/proto supervisor/proto/runtime.proto`
- **Acceptance**: Go structs generated in `supervisor/proto/runtime.pb.go`
- **Dependencies**: None

**Task A2: Create Checkpoint Service Protobuf Bindings**
- **File**: `supervisor/proto/checkpoint.proto` (already created)
- **Work**: Generate Go bindings using protoc
- **Command**: `protoc --go_out=paths=source_relative:supervisor/proto supervisor/proto/checkpoint.proto`
- **Acceptance**: Go structs generated in `supervisor/proto/checkpoint.pb.go`
- **Dependencies**: None

**Task A3: Implement Runtime gRPC Server**
- **File**: `supervisor/runtime_server.go` (new file)
- **Work**: 
  - Implement `RuntimeServiceServer` interface
  - Add gRPC server initialization to supervisor
  - Listen on port 50051
  - Wire into supervisor lifecycle (start/stop)
- **Key Methods**:
  - `CreateTask()` - forward to task runner
  - `GetTask()` - query SQLite for task state
  - `CancelTask()` - forward cancellation to runtime
  - `StreamTaskEvents()` - implement streaming
  - `GetRuntimeStatus()` - aggregate runtime metrics
  - `HealthCheck()` - runtime health probe
- **Acceptance**:
  - gRPC server starts on :50051
  - All methods implemented with proper error handling
  - Passes integration test: `go test ./supervisor -run TestRuntimeGRPCServer`
- **Dependencies**: Task A1, A2

**Task A4: Implement Checkpoint gRPC Server**
- **File**: `supervisor/checkpoint_server.go` (new file)
- **Work**:
  - Implement `CheckpointServiceServer` interface
  - SQLite operations for checkpoint storage/retrieval
  - Listen on port 50052
- **Key Methods**:
  - `SaveCheckpoint()` - persist checkpoint to SQLite
  - `GetCheckpoint()` - retrieve checkpoint by ID
  - `ListCheckpoints()` - query checkpoints by thread
  - `CleanupCheckpoints()` - maintenance operations
- **Acceptance**:
  - gRPC server starts on :50052
  - SQLite schema created for checkpoints
  - All CRUD operations working
  - Passes integration test: `go test ./supervisor -run TestCheckpointGRPCServer`
- **Dependencies**: Task A1, A2

**Task A5: Extend Supervisor Main with gRPC Initialization**
- **File**: `supervisor/main.go` (modify existing)
- **Work**:
  - Add gRPC server initialization alongside HTTP API
  - Update service lifecycle: HTTP API (:8080), gRPC Runtime (:50051), gRPC Checkpoint (:50052)
  - Implement graceful shutdown for all servers
- **Acceptance**:
  - All three servers start on their respective ports
  - Graceful shutdown handles all connections
  - No port collisions
  - Passes integration test: `go test ./supervisor -run TestSupervisorStartup`
- **Dependencies**: Task A3, A4

### Stream B: Python Runtime gRPC Wrapper

**Task B1: Generate Python Protobuf Bindings**
- **Files**: 
  - `app/proto/runtime_pb2.py` (generated)
  - `app/proto/runtime_pb2_grpc.py` (generated)
  - `app/proto/checkpoint_pb2.py` (generated)
  - `app/proto/checkpoint_pb2_grpc.py` (generated)
- **Work**:
  ```bash
  python -m grpc_tools.protoc \
    --python_out=app/proto \
    --grpc_python_out=app/proto \
    -I supervisor/proto \
    supervisor/proto/runtime.proto \
    supervisor/proto/checkpoint.proto
  ```
- **Acceptance**:
  - Python gRPC stubs generated
  - Can import: `from app.proto import runtime_pb2_grpc`
- **Dependencies**: Task A1, A2 (protobuf files)

**Task B2: Create gRPC Server Wrapper for Runtime**
- **File**: `app/grpc_server.py` (new file)
- **Work**:
  - Implement `RuntimeServiceServicer`
  - Wrap existing LangGraph runtime
  - Listen on port 50053
  - Implement bidirectional streaming for events
- **Key Methods**:
  - `CreateTask()` - validate request, start LangGraph execution
  - `GetTask()` - query task state from Redis/DB
  - `CancelTask()` - signal cancellation to running task
  - `StreamTaskEvents()` - stream events from LangGraph
  - `HealthCheck()` - return runtime health status
- **Acceptance**:
  - gRPC server starts on :50053
  - Can create and execute tasks via gRPC
  - Events stream correctly
  - Passes test: `pytest tests/test_grpc_runtime.py -v`
- **Dependencies**: Task B1

**Task B3: Implement SQLite Checkpointer**
- **File**: `app/langgraph/checkpoint_sqlite.py` (new file)
- **Work**:
  - Implement `BaseCheckpointSaver` interface from LangGraph
  - Replace Redis checkpoint saver for local mode
  - Store checkpoints in SQLite (not PostgreSQL/Redis)
  - Implement migration support
- **Key Class**: `SQLiteCheckpointer`
- **Methods**:
  - `get_tuple()` - retrieve checkpoint by config
  - `put()` - save checkpoint
  - `list()` - list checkpoints for a thread
  - `delete()` - cleanup old checkpoints
- **Acceptance**:
  - Implements LangGraph `BaseCheckpointSaver`
  - All methods tested and working
  - Migrations handled automatically
  - Passes test: `pytest tests/test_sqlite_checkpointer.py -v`
- **Dependencies**: None (can parallelize)

**Task B4: Update Runtime to Use gRPC + SQLite**
- **File**: `app/runtime/runtime.py` (modify existing)
- **Work**:
  - Add gRPC server initialization to runtime startup
  - Replace PostgreSQL checkpointer with SQLite checkpointer in local mode
  - Update configuration: add `MODE=local` flag
  - Maintain backward compatibility (FastAPI still works)
- **Acceptance**:
  - Runtime can start in gRPC mode (`MODE=local python -m app.main`)
  - Runtime starts in HTTP mode (existing behavior preserved)
  - SQLite checkpointer used in local mode
  - Passes integration test: `pytest tests/test_runtime_grpc_mode.py -v`
- **Dependencies**: Task B2, B3

**Task B5: Implement Checkpoint gRPC Client**
- **File**: `app/grpc_checkpoint_client.py` (new file)
- **Work**:
  - Create client for CheckpointService on :50052
  - Integrate with SQLiteCheckpointer
  - Handle connection pooling and retries
- **Acceptance**:
  - Can save/retrieve checkpoints via gRPC
  - Proper error handling and reconnection
  - Passes test: `pytest tests/test_checkpoint_client.py -v`
- **Dependencies**: Task B1

### Stream C: Rust Desktop Automation Completion

**Task C1: Complete gRPC Bridge in Rust Desktop**
- **File**: `desktop/desktop-automation/src/grpc_client.rs` (modify)
- **Work**:
  - Wire gRPC client to desktop automation functions
  - Implement streaming for desktop events
  - Error handling and reconnection logic
- **Acceptance**:
  - Desktop automation can be called via gRPC
  - <5ms latency for window operations
  - Passes test: `cargo test --package desktop-automation`
- **Dependencies**: Task A1 (protobuf)

**Task C2: Complete OCR Integration**
- **File**: `desktop/desktop-automation/src/ocr/windows.rs` (complete stub)
- **Work**:
  - Implement Windows OCR using Windows.Media.Ocr
  - Integrate with screenshot functionality
  - Handle text extraction and bounding boxes
- **Acceptance**:
  - OCR returns text from screenshots
  - <50ms for full screen OCR
  - Passes test: `cargo test --package desktop-automation ocr`
- **Dependencies**: None

**Task C3: Desktop gRPC Server**
- **File**: `desktop/desktop-automation/src/server.rs` (new file)
- **Work**:
  - Implement gRPC server for desktop automation
  - Listen on port 50054
  - Expose all desktop automation methods
- **Acceptance**:
  - Server starts on :50054
  - All desktop operations callable via gRPC
  - <5ms latency maintained
- **Dependencies**: Task C1, C2

### Stream D: TUI and Tauri GUI

**Task D1: Build Rust TUI with Ratatui**
- **File**: `cli/src/tui.rs` (new file)
- **Work**:
  - Create TUI interface using ratatui
  - Real-time task monitoring
  - Agent status display
  - Log viewer
- **Acceptance**:
  - TUI runs with: `agentos tui`
  - Shows real-time task progress
  - Keyboard navigation works
- **Dependencies**: None

**Task D2: Create Tauri GUI Wrapper**
- **Directory**: `gui/` (new)
- **Work**:
  - Initialize Tauri project with React
  - Integrate existing React frontend
  - System tray integration
  - Native window controls
- **Acceptance**:
  - Tauri app builds and runs
  - System tray shows agent status
  - React frontend loads correctly
  - Passes: `cd gui && cargo tauri dev`
- **Dependencies**: None (React frontend exists)

**Task D3: System Tray Integration**
- **File**: `gui/src-tauri/src/tray.rs` (new file)
- **Work**:
  - Implement system tray for Windows
  - Show agent status icon
  - Quick actions (pause, resume, settings)
- **Acceptance**:
  - Tray icon appears in system tray
  - Context menu with actions works
  - Status updates reflect agent state
- **Dependencies**: Task D2

### Stream E: Installers and Auto-Updater

**Task E1: Build Windows MSI Installer**
- **Files**: `supervisor/installers/windows/` (modify existing scripts)
- **Work**:
  - Update WiX script to include new binaries
  - Include supervisor, cli, and runtime
  - Create installer with proper registry entries
- **Acceptance**:
  - MSI installer builds successfully
  - Installs to Program Files\AgentOS
  - Creates start menu shortcuts
  - Uninstaller works correctly
- **Dependencies**: All binaries built

**Task E2: Build macOS DMG Installer**
- **Files**: `supervisor/installers/macos/` (modify)
- **Work**:
  - Create DMG with app bundle
  - Sign binaries for macOS
  - Include all components
- **Acceptance**:
  - DMG mounts and shows app
  - App bundle is signed
  - Can drag to Applications
- **Dependencies**: All binaries built

**Task E3: Build Linux AppImage**
- **Files**: `supervisor/installers/linux/` (modify)
- **Work**:
  - Create AppImage with all components
  - Include desktop entry
- **Acceptance**:
  - AppImage runs on Ubuntu 22.04+
  - Desktop entry created
- **Dependencies**: All binaries built

**Task E4: Complete Auto-Updater**
- **File**: `supervisor/updater.go` (complete)
- **Work**:
  - Implement version checking
  - Download and apply updates
  - Support stable/beta channels
  - Delta updates
- **Acceptance**:
  - Checks for updates in background
  - Downloads and installs updates
  - Supports rollback
- **Dependencies**: Installers working

## Integration Test Plan

### Phase 1 Integration Tests

**Test 1: End-to-End gRPC Bridge**
```python
# supervisor→runtime→checkpoint flow
1. Start supervisor with gRPC (:50051, :50052)
2. Start Python runtime with gRPC (:50053)
3. Create task via supervisor HTTP API
4. Verify supervisor forwards to runtime via gRPC
5. Verify runtime executes LangGraph
6. Verify checkpoints saved via gRPC
7. Verify events streamed back to supervisor
8. Verify task completes and result returned
```

**Test 2: Desktop Automation gRPC**
```
1. Start Rust desktop automation server (:50054)
2. Create task requiring desktop action
3. Verify runtime calls desktop via gRPC
4. Verify screenshot/OCR works
5. Verify <5ms latency
```

**Test 3: SQLite Checkpointer**
```
1. Start runtime in local mode
2. Execute complex multi-step task
3. Verify checkpoints saved to SQLite
4. Kill runtime mid-execution
5. Restart runtime
6. Verify task resumes from last checkpoint
```

### Performance Targets

| Metric | Target | Actual | Status |
|--------|--------|--------|--------|
| gRPC Latency | <5ms | TBD | ⏳ |
| HTTP Latency | <2ms | 1-2ms | ✅ |
| SQLite Checkpoint Save | <10ms | TBD | ⏳ |
| Startup Time (all services) | <50ms | ~40ms | ✅ |
| Desktop OCR | <50ms | TBD | ⏳ |
| Binary Size (supervisor) | <50MB | ~23MB | ✅ |
| Binary Size (cli) | <10MB | ~5MB | ✅ |

## Deployment Order

1. **Week 1**: Tasks A1-A5 (Go gRPC servers) + B1-B3 (Python bindings + checkpointer)
2. **Week 2**: Task B4-B5 (Python gRPC server + checkpoint client) + C1-C2 (Desktop bridge + OCR)
3. **Week 3**: Task C3 (Desktop server) + D1-D3 (TUI + GUI + System tray)
4. **Week 4**: Task E1-E4 (Installers + Auto-updater) + Integration testing

## Critical Dependencies

- **A3, A4** require A1, A2 (protobuf bindings)
- **A5** requires A3, A4 (both servers)
- **B2** requires B1 (Python bindings)
- **B4** requires B2, B3 (gRPC server + checkpointer)
- **B5** requires B1 (bindings)
- **C1** requires A1 (protobuf)
- **C3** requires C1, C2
- **D2** requires existing React frontend
- **D3** requires D2
- **E1-E4** require all binaries compiled

## Success Criteria for Phase 1

- [ ] Supervisor can create tasks via gRPC to Python runtime
- [ ] Python runtime executes LangGraph and streams events back
- [ ] Checkpoints saved to SQLite via gRPC
- [ ] Desktop automation accessible via gRPC with <5ms latency
- [ ] All services start and communicate correctly
- [ ] Integration tests pass
- [ ] Performance targets met

## Next Phase Planning

After Phase 1 completion:
- Phase 2: Rust desktop automation completion + OCR
- Phase 3: TUI + Tauri GUI + System tray
- Phase 4: Performance optimization (Go workers, native IPC)
- Phase 5: Compiled installers + auto-updater
