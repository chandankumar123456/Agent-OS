# AgentOS CLI & TUI

Phase 5 implementation of AgentOS interfaces - providing both command-line and terminal-based UIs for managing the AgentOS runtime.

## 📁 Structure

```
cli/          - Command-line interface (Rust)
tui/          - Terminal UI (Rust + ratatui)
```

---

## 🔧 CLI (agentos)

A comprehensive command-line interface for AgentOS with full feature parity.

### Installation

```bash
cd cli
cargo build --release
# Binary: target/release/agentos.exe
```

### Commands

#### Task Management
```bash
# Create and execute a task
agentos task create "Open Chrome and search for rust tutorials"
agentos task create "Take a screenshot" --watch  # Watch execution

# List tasks
agentos task list
agentos task list --status running --limit 50

# Get task details
agentos task get <task-id>

# Cancel a task
agentos task cancel <task-id>

# View logs
agentos task logs <task-id> --follow
agentos task logs <task-id> --tail 100
```

#### Daemon Management
```bash
# Start daemon
agentos daemon start
agentos daemon start --background

# Check status
agentos daemon status

# View logs
agentos daemon logs --follow

# Stop daemon
agentos daemon stop

# Restart
agentos daemon restart
```

#### Desktop Control
```bash
# Screenshot
agentos desktop screenshot
agentos desktop screenshot --output ./capture.png --window "Chrome"

# Mouse control
agentos desktop click --x 100 --y 200
agentos desktop click --x 100 --y 200 --button right --clicks 2

# Keyboard input
agentos desktop type "Hello, World!"
agentos desktop type "Hello" --interval 50

# Window management
agentos desktop focus --window "Chrome"
agentos desktop list-windows
agentos desktop list-windows --filter "Visual Studio"

# OCR-based element finding
agentos desktop find "Submit" --screenshot
```

#### Configuration
```bash
# Initialize config
agentos config init

# Set values
agentos config set supervisor.port 9090
agentos config set log_level debug

# Get values
agentos config get supervisor.host

# List all config
agentos config list

# Show config path
agentos config path
```

### Global Flags
```bash
-v, --verbose       Enable verbose output
-o, --output        Output format: text or json
-c, --config        Config file path
-h, --help          Show help
-V, --version       Show version
```

---

## 🖥️ TUI (agentos-tui)

A real-time terminal dashboard for monitoring AgentOS tasks and logs.

### Installation

```bash
cd tui
cargo build --release
# Binary: target/release/agentos-tui.exe
```

### Usage

```bash
# Connect to default supervisor
agentos-tui

# Connect to specific host/port
agentos-tui --host 192.168.1.100 --port 8080

# Faster refresh rate
agentos-tui --refresh 500  # 500ms

# Verbose logging
agentos-tui --verbose
```

### Layout

```
┌──────────────────────────────┬────────────────────────────────────────────┐
│ Tasks                        │ Logs                                       │
│                              │                                            │
│  Status  ID       Query      │  14:32:10 [INFO ]  Task 550e8400 started   │
│  running 550e8400 "Open..."  │  14:32:11 [DEBUG]  Step 1: Clicking at...    │
│  completed 6ba7b810 "Type..."│  14:32:12 [INFO ]  Step 1 completed          │
│  failed 6ba7b811 "Search..." │  14:32:13 [ERROR]  Step 2 failed: timeout    │
│                              │  14:32:14 [INFO ]  Recovery triggered        │
│                              │                                            │
├──────────────────────────────┴────────────────────────────────────────────┤
│ ● connected | running | v0.1.0 | 1h 23m | 1 active / 5 total | 45.2 MB   ? help│
└─────────────────────────────────────────────────────────────────────────────┘
```

### Keyboard Shortcuts

#### Navigation
- `↑/↓` or `j/k` - Navigate task list
- `g` - Go to first task
- `G` - Go to last task
- `Tab` - Switch between panels

#### Log Panel
- `PgUp/PgDn` - Scroll logs
- `t` - Jump to top
- `b` - Jump to bottom
- `Space` - Toggle auto-scroll
- `/` - Filter logs

#### Task Actions
- `Enter` - View task details
- `c` - Cancel selected task
- `r` - Refresh task list
- `q` - Quit
- `?` - Show help

---

## 🎨 Features

### CLI Features
- ✅ Full task lifecycle management
- ✅ Daemon control (start/stop/status/logs)
- ✅ Desktop automation commands
- ✅ Configuration management
- ✅ JSON output mode for scripting
- ✅ Auto-start daemon if not running
- ✅ Colored output
- ✅ Tabular data formatting
- ✅ Timestamp formatting

### TUI Features
- ✅ Real-time task monitoring
- ✅ Live log streaming
- ✅ Interactive task details
- ✅ Status bar with system metrics
- ✅ Keyboard navigation
- ✅ Log filtering
- ✅ Auto-scroll toggle
- ✅ Connection status indicator

---

## 🔌 API Integration

Both CLI and TUI connect to the AgentOS Supervisor via HTTP API:

- **Base URL**: `http://127.0.0.1:8080`
- **Health**: `GET /health`
- **Status**: `GET /status`
- **Tasks**: `GET|POST /api/v1/tasks`
- **Task Details**: `GET /api/v1/tasks/{id}`
- **Cancel Task**: `POST /api/v1/tasks/{id}/cancel`
- **Desktop Control**: Various `/api/v1/desktop/*` endpoints

---

## 📦 Dependencies

### CLI
- `clap` - Command-line argument parsing
- `tokio` - Async runtime
- `reqwest` - HTTP client
- `serde` - Serialization
- `colored` - Terminal colors
- `comfy-table` - Table formatting
- `chrono` - Date/time handling
- `anyhow` - Error handling

### TUI
- `ratatui` - Terminal UI framework
- `crossterm` - Cross-platform terminal handling
- `tokio` - Async runtime
- `reqwest` - HTTP client
- `serde` - Serialization
- `unicode-width` - Unicode text handling

---

## 🚀 Next Steps

1. **Tauri GUI** - Port React frontend to native application
2. **System Tray** - Background operation support
3. **Global Hotkeys** - System-wide shortcuts
4. **Notifications** - Native desktop notifications

---

## 📝 License

MIT License - See parent project LICENSE
