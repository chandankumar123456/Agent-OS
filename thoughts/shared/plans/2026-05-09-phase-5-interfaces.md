# Phase 5: Interfaces - Implementation Plan

**Status:** 🔄 IN PROGRESS  
**Previous Phase:** Phase 4 - Real Windows Automation (✅ COMPLETE)  
**Timeline:** 2-3 months  
**Priority:** Complete interface hierarchy (CLI → TUI → GUI)

---

## Executive Summary

Phase 5 builds the complete interface hierarchy for AgentOS:
1. **CLI** (Primary): Command-line interface for all operations
2. **TUI** (Operational): Real-time monitoring dashboard  
3. **GUI** (Optional): Tauri-based native application

All interfaces connect to the local-native runtime via named pipes (Windows) or Unix sockets (macOS/Linux).

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    INTERFACE LAYER                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │    CLI      │  │     TUI     │  │  GUI (Tauri/React)  │ │
│  │  (Primary)  │  │(Operational)│  │    (Optional)       │ │
│  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘ │
│         │                │                     │            │
│         └────────────────┴─────────────────────┘            │
│                          │                                  │
│                    Named Pipe / Unix Socket                │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                    SUPERVISOR (Go)                          │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  - Service management                                   ││
│  │  - Process supervision                                  ││
│  └─────────────────────────────────────────────────────────┘│
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│              DESKTOP AUTOMATION (Python)                    │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  - DesktopSession                                       ││
│  │  - WindowRegistry                                       ││
│  │  - ActionStabilizer                                     ││
│  │  - RecoveryEngine                                       ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

---

## Task Breakdown

### T1: Rust CLI with clap
**Priority:** HIGH  
**Duration:** 2-3 weeks

#### T1.1 Core CLI Structure
- [ ] Create `cli/` directory in project root
- [ ] Set up Rust project with `cargo new --bin agentos`
- [ ] Add clap dependency with derive feature
- [ ] Define main CLI structure with subcommands

```rust
#[derive(Parser)]
#[command(name = "agentos")]
#[command(about = "AgentOS - Local-native autonomous agent runtime")]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    Task(TaskCommands),
    Daemon(DaemonCommands),
    Desktop(DesktopCommands),
    Config(ConfigCommands),
}
```

#### T1.2 Task Management Commands
- [ ] `agentos task create "<query>" [--watch]` - Create and execute task
- [ ] `agentos task list [--status <status>] [--limit <n>]` - List tasks
- [ ] `agentos task get <id>` - Get task details
- [ ] `agentos task cancel <id>` - Cancel running task
- [ ] `agentos task logs <id> [--follow]` - Stream task logs

#### T1.3 Daemon Management Commands  
- [ ] `agentos daemon start [--background]` - Start supervisor daemon
- [ ] `agentos daemon stop` - Stop daemon
- [ ] `agentos daemon status` - Check daemon health
- [ ] `agentos daemon logs [--follow]` - View daemon logs
- [ ] `agentos daemon restart` - Restart daemon

#### T1.4 Desktop Control Commands
- [ ] `agentos desktop screenshot [--output <path>]` - Take screenshot
- [ ] `agentos desktop click --x <x> --y <y>` - Click at coordinates
- [ ] `agentos desktop type "<text>"` - Type text
- [ ] `agentos desktop focus --window "<title>"` - Focus window
- [ ] `agentos desktop list-windows` - List open windows

#### T1.5 Configuration Commands
- [ ] `agentos config set <key> <value>` - Set config value
- [ ] `agentos config get <key>` - Get config value
- [ ] `agentos config list` - List all config
- [ ] `agentos config init` - Initialize default config

#### T1.6 Connection Layer
- [ ] Implement IPC client for named pipes (Windows)
- [ ] Implement IPC client for Unix sockets (macOS/Linux)
- [ ] Add connection retry logic
- [ ] Auto-start daemon if not running (with --auto-start flag)

---

### T2: Rust TUI with ratatui
**Priority:** HIGH  
**Duration:** 3-4 weeks

#### T2.1 Core TUI Structure
- [ ] Create `tui/` directory
- [ ] Set up Rust project with `cargo new --bin agentos-tui`
- [ ] Add ratatui, crossterm, tokio dependencies
- [ ] Implement event loop with async support

#### T2.2 Dashboard Layout
- [ ] **Task List Panel** (left, 40% width)
  - Real-time task status updates
  - Color-coded states (running, completed, failed)
  - Scrollable with keyboard navigation
  
- [ ] **Live Logs Panel** (right, 60% width)
  - Streaming log output from selected task
  - Syntax highlighting for log levels
  - Auto-scroll with pause on selection

- [ ] **Status Bar** (bottom)
  - System metrics (CPU, memory, active tasks)
  - Connection status
  - Keyboard shortcuts help

#### T2.3 Keyboard Navigation
- [ ] `↑/↓` - Navigate task list
- [ ] `Enter` - View task details
- [ ] `Space` - Pause/resume task
- [ ] `c` - Cancel selected task
- [ ] `r` - Refresh task list
- [ ] `q` or `Esc` - Quit
- [ ] `Tab` - Switch focus between panels
- [ ] `?` - Show help overlay

#### T2.4 Real-time Updates
- [ ] WebSocket client for live updates
- [ ] Event-driven UI updates
- [ ] Handle reconnection on connection loss
- [ ] Optimized rendering (only update changed regions)

#### T2.5 Task Detail View
- [ ] Modal overlay for task details
- [ ] Show: ID, status, created_at, steps, results
- [ ] Action buttons: Approve, Reject, Cancel

---

### T3: Tauri GUI (Port React Frontend)
**Priority:** MEDIUM  
**Duration:** 4-6 weeks

#### T3.1 Tauri Project Setup
- [ ] Create `gui/` directory
- [ ] Initialize Tauri project with React template
- [ ] Configure tauri.conf.json
- [ ] Set up build pipeline

#### T3.2 Port Existing React Components
- [ ] Port Dashboard page
- [ ] Port Agent Builder page
- [ ] Port Tools page
- [ ] Port Chat page
- [ ] Port Workflow Builder with XYFlow
- [ ] Port Monitor page

#### T3.3 Native Integration
- [ ] System tray icon (Windows/macOS/Linux)
- [ ] Context menu: Show, Hide, Quit
- [ ] Window state persistence
- [ ] Native menu bar (macOS)

#### T3.4 Auto-updater
- [ ] Integrate Tauri updater
- [ ] Check for updates on startup
- [ ] Download in background
- [ ] Prompt user to restart

---

### T4: System Tray Integration
**Priority:** MEDIUM  
**Duration:** 1 week

#### T4.1 System Tray (Tauri)
- [ ] Add system tray to tauri.conf.json
- [ ] Implement tray icon (AgentOS logo)
- [ ] Context menu:
  - Show/Hide window
  - Start/Stop daemon
  - View status
  - Quit

#### T4.2 System Tray (Standalone - Optional)
- [ ] Windows: Use `tray-icon` crate
- [ ] macOS: Use `cocoa` crate
- [ ] Linux: Use `libappindicator` or `ksni`

---

### T5: Global Hotkeys
**Priority:** LOW  
**Duration:** 1 week

- [ ] Define default hotkeys:
  - `Ctrl+Shift+A` - Show AgentOS window
  - `Ctrl+Shift+S` - Take screenshot
  - `Ctrl+Shift+Q` - Quick task creation
- [ ] Configurable hotkeys via config
- [ ] Register/unregister hotkeys on daemon start/stop

---

### T6: Native Notifications
**Priority:** LOW  
**Duration:** 1 week

- [ ] Task completion notifications
- [ ] Human-in-the-loop approval requests
- [ ] Error/recovery notifications
- [ ] Click notification to open TUI/GUI

---

## Technology Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| CLI Framework | clap v4 | Command-line parsing |
| TUI Framework | ratatui v0.26 | Terminal UI |
| GUI Framework | Tauri v2 | Native GUI |
| Async Runtime | tokio | Async I/O |
| IPC (Windows) | Named pipes | CLI/TUI ↔ Supervisor |
| IPC (Unix) | Unix sockets | CLI/TUI ↔ Supervisor |
| WebSocket | tokio-tungstenite | Real-time updates |
| Config | serde + toml | Configuration files |
| Logging | tracing | Structured logging |

---

## Build Commands

```bash
# Build CLI
cd cli && cargo build --release

# Build TUI  
cd tui && cargo build --release

# Build GUI
cd gui && npm install && npm run tauri build

# Build all
./scripts/build-all.sh
```

---

## Testing Strategy

### Unit Tests
- [ ] CLI argument parsing
- [ ] Config serialization/deserialization
- [ ] IPC message encoding/decoding

### Integration Tests
- [ ] CLI ↔ Supervisor communication
- [ ] TUI event handling
- [ ] End-to-end task execution via CLI

### Manual Testing
- [ ] Test on Windows 10/11
- [ ] Test on macOS
- [ ] Test on Ubuntu Linux
- [ ] Test terminal emulators (Windows Terminal, iTerm2, GNOME Terminal)

---

## Success Criteria

### CLI
- [ ] All commands work without GUI/TUI
- [ ] JSON output mode for scripting
- [ ] Auto-completion (shell scripts)
- [ ] Comprehensive help text

### TUI
- [ ] Smooth real-time updates (<100ms latency)
- [ ] Works in all major terminal emulators
- [ ] Keyboard-only navigation
- [ ] Graceful handling of resize/connection loss

### GUI
- [ ] Single binary distribution
- [ ] Native look and feel on all platforms
- [ ] System tray works when window closed
- [ ] Auto-updater functional

---

## Dependencies from Previous Phases

- ✅ Supervisor HTTP API (Phase 1)
- ✅ Desktop automation gRPC (Phase 2-4)
- ✅ Python runtime management (Phase 1)

---

## Next Steps After Phase 5

1. **Phase 6: Performance Optimization**
   - Replace Python workers with Go
   - Native IPC instead of Redis
   - Optimize vision layer

2. **Phase 7: Polish & Distribution**
   - Installers (.msi, .dmg, .deb/.rpm)
   - Documentation
   - Performance benchmarks

---

## Related Documents

- Phase 4 Plan: `thoughts/shared/plans/2026-05-09-phase-4-real-windows-automation.md`
- Design Document: `thoughts/shared/designs/2026-05-09-agentos-local-native-redesign.md`
- Phase 3 Test Report: `tests/reports/phase3_integration_test_report.md`
