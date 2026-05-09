# Phase 2: Desktop Native Foundation - Implementation Plan

## Overview
Implement Rust-based desktop automation infrastructure for local-native AgentOS runtime. This phase establishes the foundation for native Windows desktop automation with <5ms latency requirements.

## Current State (Phase 1 Complete)
- ✅ Go supervisor with SQLite persistence
- ✅ Python runtime management (FastAPI/uvicorn)
- ✅ 7 MCP servers configured (ports 8001-8007)
- ✅ HTTP API endpoints for lifecycle management

## Phase 2 Goals

### 1. Rust Project Structure
- [ ] Create `desktop/` directory with Rust workspace
- [ ] Initialize `desktop-automation` crate with Cargo.toml
- [ ] Add dependencies: `tokio`, `tonic` (gRPC), `image`, `windows`
- [ ] Create module structure:
  ```
  desktop/
  ├── Cargo.toml
  ├── src/
  │   ├── lib.rs
  │   ├── main.rs
  │   ├── bridge/
  │   │   ├── mod.rs
  │   │   └── grpc_client.rs
  │   ├── ocr/
  │   │   ├── mod.rs
  │   │   └── windows.rs
  │   ├── automation/
  │   │   ├── mod.rs
  │   │   ├── window.rs
  │   │   └── input.rs
  │   └── protocol/
  │       ├── mod.rs
  │       └── messages.rs
  ```

### 2. Native Windows OCR Implementation
- [ ] Implement Windows UI Automation-based OCR
- [ ] Use Windows.Media.Ocr or native GDI+ OCR
- [ ] Support DPI scaling for high-resolution displays
- [ ] Add image preprocessing pipeline (grayscale, binarization)
- [ ] Benchmark performance: target <5ms for screen capture + OCR

### 3. gRPC Bridge to Python Runtime
- [ ] Define gRPC service in `.proto` file:
  ```protobuf
  service DesktopAutomation {
    rpc ScreenCapture(ScreenCaptureRequest) returns (ScreenCaptureResponse);
    rpc OcrScreen(OcrScreenRequest) returns (OcrScreenResponse);
    rpc FindWindow(FindWindowRequest) returns (FindWindowResponse);
    rpc Click(ClickRequest) returns (ClickResponse);
    rpc Type(TypeRequest) returns (TypeResponse);
  }
  ```
- [ ] Generate Rust gRPC client from proto
- [ ] Implement Python gRPC server stub in `app/desktop/`
- [ ] Set up bidirectional communication between Rust and Python

### 4. Desktop Automation Protocol
- [ ] Design observe-decide-act-verify-recover loop messages
- [ ] Create message types for desktop actions:
  - `ObserveRequest` - Capture screen, text, window state
  - `DecideRequest` - Send to LangGraph for planning
  - `ActRequest` - Execute automation commands
  - `VerifyRequest` - Validate action results
  - `RecoverRequest` - Handle failures

### 5. Integration with Existing Architecture
- [ ] Update supervisor to start Rust desktop automation process
- [ ] Add health check endpoint for desktop automation
- [ ] Configure MCP servers to delegate desktop actions to Rust
- [ ] Implement path remapping for cross-OS compatibility

## Implementation Tasks

### Task 1: Rust Workspace Setup
- [ ] Create `desktop/Cargo.toml` with workspace configuration
- [ ] Initialize `desktop-automation` library crate
- [ ] Add required dependencies (tokio, tonic, windows, image)
- [ ] Set up basic module structure
- [ ] Build and verify compilation

### Task 2: Windows OCR Implementation
- [ ] Implement screen capture using Windows API
- [ ] Integrate Windows OCR engine or GDI+ OCR
- [ ] Add image preprocessing (grayscale, thresholding)
- [ ] Handle DPI scaling for high-resolution displays
- [ ] Create benchmark tests for OCR performance

### Task 3: gRPC Service Definition
- [ ] Create `desktop/protocol/desktop.proto`
- [ ] Define all required RPC methods
- [ ] Generate Rust client code with `tonic`
- [ ] Create Python gRPC server stub
- [ ] Test basic connectivity between Rust and Python

### Task 4: Desktop Automation Messages
- [ ] Design message types for observe-decide-act-verify-recover
- [ ] Create Rust structs with serde serialization
- [ ] Implement message conversion between Rust and Python
- [ ] Add validation and error handling

### Task 5: Integration with Supervisor
- [ ] Update supervisor to start Rust desktop automation
- [ ] Add health check endpoint for desktop automation
- [ ] Configure MCP servers to route desktop actions to Rust
- [ ] Implement fallback mechanisms

### Task 6: Testing & Validation
- [ ] Write unit tests for OCR functionality
- [ ] Integration tests for gRPC communication
- [ ] End-to-end tests for desktop automation loop
- [ ] Performance benchmarks (<5ms latency target)

## Success Criteria
- [ ] Rust desktop automation builds and runs
- [ ] Screen capture + OCR completes in <5ms
- [ ] gRPC bridge established between Rust and Python
- [ ] Supervisor can start/stop Rust desktop automation
- [ ] All tests pass with >90% coverage

## Notes
- Windows is the primary target OS
- All desktop automation must be native (no Python overhead)
- gRPC chosen for low-latency IPC between Rust and Python
- OCR must handle DPI scaling for high-resolution displays
