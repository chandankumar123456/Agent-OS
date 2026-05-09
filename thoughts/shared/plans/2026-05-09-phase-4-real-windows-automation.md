# Phase 4: Real Windows Automation - Implementation Plan

## Status: 🔄 IN PROGRESS

## Overview
Implement native Windows desktop automation by replacing stub implementations with actual Windows API calls. This phase focuses on screen capture, OCR, window management, and input automation using native Windows APIs.

## Goals

### 1. Native Screen Capture (High Priority)
- [ ] Implement DXGI/Desktop Duplication API for screen capture
- [ ] Support multi-monitor setups
- [ ] Handle DPI scaling automatically
- [ ] Optimize for <5ms capture latency
- [ ] Add region capture support (full screen, window, custom region)

### 2. Windows.Media.Ocr Integration (High Priority)
- [ ] Integrate Windows.Media.Ocr WinRT API
- [ ] Support multiple languages
- [ ] Handle DPI-aware text recognition
- [ ] Return confidence scores and bounding boxes
- [ ] Optimize for <10ms OCR latency

### 3. Window Management (Medium Priority)
- [ ] Replace stub window finding with actual Windows API
- [ ] Implement EnumWindows for window enumeration
- [ ] Add GetWindowRect for position/size retrieval
- [ ] Implement SetForegroundWindow for activation
- [ ] Support window title matching (exact and partial)

### 4. Input Automation (Medium Priority)
- [ ] Replace stub SendInput with real implementation
- [ ] Implement mouse click at screen coordinates
- [ ] Implement keyboard text input
- [ ] Support special keys (Enter, Tab, Ctrl, etc.)
- [ ] Add input validation and safety checks

### 5. Python Server Integration (Medium Priority)
- [ ] Update Python gRPC server to use actual AgentOS components
- [ ] Integrate with DesktopSession
- [ ] Connect to WindowRegistry
- [ ] Link to RecoveryEngine and VerificationEngine
- [ ] Add proper error handling and logging

## Technical Architecture

### Rust Implementation

```
desktop-automation/src/
├── capture/
│   ├── mod.rs              # Screen capture module
│   ├── dxgi.rs             # DXGI/Desktop Duplication implementation
│   └── region.rs           # Region selection utilities
├── ocr/
│   ├── mod.rs              # OCR module
│   ├── winrt.rs            # Windows.Media.Ocr integration
│   └── postprocess.rs      # Text post-processing
├── automation/
│   ├── mod.rs              # Already exists
│   ├── window.rs           # Replace stubs with real impl
│   └── input.rs            # Replace stubs with real impl
└── bridge/
    └── grpc_client.rs      # Already complete
```

### Dependencies

Add to `desktop-automation/Cargo.toml`:

```toml
[dependencies]
# Existing dependencies...

# Windows API bindings
windows = { version = "0.56", features = [
    "Win32_Foundation",
    "Win32_Graphics_Dxgi",
    "Win32_Graphics_Dxgi_Common",
    "Win32_Graphics_Direct3D11",
    "Win32_System_WinRT",
    "Win32_UI_WindowsAndMessaging",
    "Win32_UI_Input_KeyboardAndMouse",
    "Win32_UI_Input",
    "Win32_Storage_FileSystem",
    "Win32_System_Threading",
    "Win32_System_Performance",
    "Win32_System_Memory",
    "Win32_Graphics_Imaging",
    "Win32_Media",
    "Win32_Media_MediaFoundation",
    "Win32_System_Com",
    "Win32_Security",
] }

# Image processing
image = "0.24"

# OCR
# Note: Windows.Media.Ocr requires special handling via WinRT

# Error handling
anyhow = "1.0"

# Logging
tracing = "0.1"
```

## Implementation Details

### 1. DXGI Screen Capture

**API**: `IDXGIOutputDuplication`

**Steps**:
1. Create DXGI factory
2. Enumerate adapters and outputs
3. Create duplication interface
4. Acquire next frame
5. Map texture to CPU-accessible memory
6. Convert to image format (PNG/JPEG)

**Latency Target**: <5ms for 1920x1080

**Code Structure**:
```rust
pub struct DxgiCapture {
    device: ID3D11Device,
    duplication: IDXGIOutputDuplication,
}

impl DxgiCapture {
    pub fn new(output_index: u32) -> Result<Self, CaptureError>;
    pub fn capture_frame(&mut self) -> Result<CapturedFrame, CaptureError>;
    pub fn capture_region(&mut self, region: Rect) -> Result<CapturedFrame, CaptureError>;
}
```

### 2. Windows.Media.Ocr

**API**: `Windows.Media.Ocr.OcrEngine`

**Steps**:
1. Initialize WinRT
2. Get default OCR engine for language
3. Create SoftwareBitmap from captured image
4. Call RecognizeAsync
5. Extract text and bounding boxes

**Latency Target**: <10ms for 1920x1080

**Code Structure**:
```rust
pub struct WinRtOcr {
    engine: OcrEngine,
}

impl WinRtOcr {
    pub fn new() -> Result<Self, OcrError>;
    pub fn recognize(&self, image: &[u8]) -> Result<OcrResult, OcrError>;
}

pub struct OcrResult {
    pub text: String,
    pub confidence: f32,
    pub words: Vec<WordInfo>,
}
```

### 3. Window Management

**APIs**: `EnumWindows`, `GetWindowRect`, `SetForegroundWindow`

**Code Structure**:
```rust
pub fn find_window(title: &str, partial_match: bool) -> Option<WindowInfo>;
pub fn enum_windows() -> Vec<WindowInfo>;
pub fn get_window_rect(hwnd: HWND) -> Result<Rect, Error>;
pub fn activate_window(hwnd: HWND) -> Result<(), Error>;
```

### 4. Input Automation

**API**: `SendInput`

**Code Structure**:
```rust
pub fn click(x: i32, y: i32) -> Result<(), Error>;
pub fn type_text(text: &str) -> Result<(), Error>;
pub fn key_down(key: Key) -> Result<(), Error>;
pub fn key_up(key: Key) -> Result<(), Error>;
```

## Testing Strategy

### Unit Tests
- Test each Windows API wrapper individually
- Mock Windows APIs where possible
- Test error handling paths

### Integration Tests
- Test full screen capture → OCR pipeline
- Test window finding → activation → input sequence
- Measure end-to-end latency

### Manual Testing
- Test on different screen resolutions
- Test with multiple monitors
- Test with different DPI settings
- Test with various application windows

## Performance Targets

| Operation | Target | Notes |
|-----------|--------|-------|
| Screen Capture | <5ms | 1920x1080, DXGI |
| OCR | <10ms | Windows.Media.Ocr |
| Window Find | <2ms | EnumWindows |
| Click | <1ms | SendInput |
| Type Text | <1ms per char | SendInput |
| **Total observe cycle** | **<20ms** | Capture + OCR + window enum |

## Build Commands

```bash
# Build with new features
cd desktop && cargo build --release

# Run tests
cargo test --features windows-api

# Run benchmarks
cargo bench
```

## Next Steps After Phase 4

1. **Supervisor Integration**: Add Rust desktop automation to supervisor lifecycle
2. **Production Hardening**: Error recovery, logging, metrics
3. **Performance Optimization**: Connection pooling, batching, caching
4. **Phase 5: Interfaces**: Tauri GUI, Rust CLI/TUI

## Notes

- Windows 10 version 1809+ required for Windows.Media.Ocr
- DXGI Desktop Duplication requires Windows 8+
- Some APIs may require administrator privileges
- DPI awareness manifest required for correct scaling
- Security: Validate all coordinates before input injection

## Related Documents

- Phase 2 Plan: `thoughts/shared/plans/2026-05-09-phase-2-desktop-native-implementation.md`
- Phase 3 Report: `tests/reports/phase3_integration_test_report.md`
- Design Document: `thoughts/shared/designs/2026-05-09-agentos-local-native-redesign.md`
