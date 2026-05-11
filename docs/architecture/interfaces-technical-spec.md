# AgentOS Interfaces - Technical Specification

**Version**: 0.1.0  
**Last Updated**: 2026-05-09  
**Scope**: Tauri GUI, Rust CLI, Rust TUI

---

## Overview

AgentOS provides three native interfaces for interacting with the supervisor daemon:

| Interface | Technology | Binary Size | Primary Use |
|-----------|------------|-------------|-------------|
| **Tauri GUI** | Tauri 1.5 + React 18 + Vite 5 | ~15-20 MB | Desktop application with system tray |
| **CLI** | Rust + clap 4.5 | ~5 MB | Command-line operations, scripting |
| **TUI** | Rust + ratatui 0.26 | ~3 MB | Real-time monitoring dashboard |

All interfaces communicate with the Go supervisor via HTTP API at `http://127.0.0.1:8080`.

---

## Tauri GUI

### Architecture

```
gui/
├── src-tauri/           # Rust backend (Tauri commands)
│   ├── Cargo.toml       # Package: agentos-gui v0.1.0
│   ├── tauri.conf.json  # Window config, permissions, bundle settings
│   └── src/
│       ├── main.rs      # Entry point, system tray, shortcuts
│       ├── config.rs    # AppConfig with DaemonConfig
│       ├── tray.rs      # System tray menu (show/hide/quit)
│       ├── shortcuts.rs # Global hotkeys (Ctrl+Shift+A/S/Q)
│       ├── notifications.rs # Native desktop notifications
│       └── commands/    # Tauri invoke handlers
│           ├── mod.rs
│           ├── daemon.rs    # get_daemon_status, start_daemon, stop_daemon
│           ├── config.rs    # get_config, set_config
│           ├── system.rs    # get_app_version
│           └── notifications.rs # show_notification
│
├── src/                 # React frontend
│   ├── main.tsx         # React 18 entry with BrowserRouter
│   ├── App.tsx          # Main app with page routing
│   ├── context/
│   │   └── AppContext.tsx    # Task state management
│   ├── components/
│   │   └── Layout.tsx        # Sidebar navigation + main content
│   └── pages/
│       ├── Dashboard.tsx     # Task list + creation
│       ├── AgentBuilder.tsx  # Agent management
│       ├── Tools.tsx         # Tool registry browser
│       ├── Chat.tsx          # Conversational interface
│       └── Settings.tsx      # Configuration UI
│
├── package.json         # npm deps: React 18, Tailwind, Framer Motion
├── vite.config.ts       # Vite 5 + React plugin
└── tailwind.config.js   # Custom colors (agentos-primary, agentos-dark)
```

### Backend (Rust/Tauri)

**Entry Point**: `gui/src-tauri/src/main.rs:1`

```rust
// Main application builder
tauri::Builder::default()
    .plugin(tauri_plugin_single_instance::init(...))  // Prevent multiple instances
    .system_tray(tray::create_system_tray())            // System tray integration
    .on_system_tray_event(tray::handle_system_tray_event)
    .setup(|app| {
        shortcuts::register_global_shortcuts(app.handle())?;  // Ctrl+Shift+A/S/Q
        Ok(())
    })
    .invoke_handler(generate_handler![
        commands::get_daemon_status,   // Check supervisor connection
        commands::start_daemon,      // Start supervisor process
        commands::stop_daemon,       // Stop supervisor process
        commands::get_config,        // Load app configuration
        commands::set_config,        // Save app configuration
        commands::show_notification, // Show native notification
        commands::get_app_version,   // Get app version
    ])
    .on_window_event(|event| {
        // Hide to tray on close instead of exiting
        if let WindowEvent::CloseRequested { api, .. } = event.event() {
            event.window().hide().unwrap();
            api.prevent_close();
        }
    })
```

**System Tray**: `gui/src-tauri/src/tray.rs:1`

- Menu items: Show AgentOS, Hide AgentOS, Quit
- Left-click toggles window visibility
- Right-click opens context menu

**Global Shortcuts**: `gui/src-tauri/src/shortcuts.rs:1`

| Shortcut | Action |
|----------|--------|
| Ctrl+Shift+A | Show AgentOS window |
| Ctrl+Shift+S | Take screenshot (TODO) |
| Ctrl+Shift+Q | Show window + focus task input |

**Configuration**: `gui/src-tauri/src/config.rs:1`

```rust
pub struct AppConfig {
    pub daemon: DaemonConfig,           // host: "127.0.0.1", port: 8080
    pub auto_start_daemon: bool,        // default: true
    pub start_minimized: bool,          // default: false
    pub notifications_enabled: bool,    // default: true
    pub global_shortcuts_enabled: bool, // default: true
}
```

### Frontend (React)

**Entry Point**: `gui/src/main.tsx:1`

```typescript
ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
)
```

**App Component**: `gui/src/App.tsx:1`

```typescript
function App() {
  const [currentPage, setCurrentPage] = useState<Page>('dashboard')
  const [daemonConnected, setDaemonConnected] = useState(false)

  // Poll daemon status every 5 seconds
  useEffect(() => {
    checkDaemonStatus()
    const interval = setInterval(checkDaemonStatus, 5000)
    return () => clearInterval(interval)
  }, [])

  const checkDaemonStatus = async () => {
    const status = await invoke<{ running: boolean }>('get_daemon_status')
    setDaemonConnected(status.running)
  }

  // Render current page based on navigation
  const renderPage = () => {
    switch (currentPage) {
      case 'dashboard': return <Dashboard />
      case 'agents': return <AgentBuilder />
      case 'tools': return <Tools />
      case 'chat': return <Chat />
      case 'settings': return <Settings version={version} daemonConnected={daemonConnected} />
    }
  }
}
```

**Layout Component**: `gui/src/components/Layout.tsx:1`

- Sidebar with 5 navigation items: Dashboard, Agents, Tools, Chat, Settings
- Connection status indicator (green/red dot)
- Responsive design with Tailwind CSS

**Pages**:

| Page | File | Features |
|------|------|----------|
| Dashboard | `gui/src/pages/Dashboard.tsx:1` | Task creation, task list with status, step progress bars |
| AgentBuilder | `gui/src/pages/AgentBuilder.tsx:1` | Agent list, agent details, stats (success rate, runs) |
| Tools | `gui/src/pages/Tools.tsx:1` | Tool registry with categories, search, test buttons |
| Chat | `gui/src/pages/Chat.tsx:1` | Message history, input with Enter to send |
| Settings | `gui/src/pages/Settings.tsx:1` | Daemon config, notifications, shortcuts, about |

### Dependencies

**Rust (Tauri)**:
- `tauri = "1.5"` - Core framework
- `tauri-plugin-single-instance` - Prevent multiple app instances
- `serde`, `serde_json` - Serialization
- `tokio` - Async runtime
- `reqwest` - HTTP client for supervisor API

**JavaScript (React)**:
- `react = "^18.2"` - UI framework
- `@tauri-apps/api = "^1.5"` - Tauri invoke API
- `react-router-dom = "^6.22"` - Client-side routing
- `framer-motion = "^11.0"` - Animations
- `lucide-react = "^0.400"` - Icons
- `recharts = "^2.12"` - Charts (for metrics)
- `tailwindcss = "^3.4"` - Styling

### Build Commands

```bash
# Development
cd gui
npm run tauri:dev        # Starts Vite dev server + Tauri

# Production build
cd gui
npm run tauri:build      # Creates: src-tauri/target/release/agentos-gui.exe
```

### Window Configuration

From `gui/src-tauri/tauri.conf.json:1`:

```json
{
  "windows": [{
    "width": 1440,
    "height": 900,
    "minWidth": 1024,
    "minHeight": 768,
    "center": true,
    "resizable": true
  }],
  "systemTray": {
    "iconPath": "icons/icon.png",
    "menuOnLeftClick": true
  }
}
```

---

## Rust CLI

### Architecture

```
cli/
├── Cargo.toml           # Package: agentos v0.1.0
└── src/
    ├── main.rs          # Entry point, command parsing
    ├── config.rs        # Configuration management
    ├── ipc.rs           # HTTP API client
    ├── models.rs        # Data structures
    └── commands/
        ├── mod.rs         # Module exports
        ├── task.rs        # Task lifecycle commands
        ├── daemon.rs      # Daemon control commands
        ├── desktop.rs     # Desktop automation commands
        └── config.rs      # Configuration commands
```

### Entry Point

**File**: `cli/src/main.rs:1`

```rust
#[derive(Parser)]
#[command(name = "agentos")]
#[command(about = "AgentOS - Local-native autonomous agent runtime")]
#[command(version = "0.1.0")]
struct Cli {
    #[command(subcommand)]
    command: Commands,
    #[arg(short, long, global = true)]
    verbose: bool,
    #[arg(short, long, global = true, default_value = "text")]
    output: String,  // "text" or "json"
}

#[derive(Subcommand)]
enum Commands {
    Task { #[command(subcommand)] command: TaskCommands },
    Daemon { #[command(subcommand)] command: DaemonCommands },
    Desktop { #[command(subcommand)] command: DesktopCommands },
    Config { #[command(subcommand)] command: ConfigCommands },
}
```

### Command Structure

**Task Commands** (`cli/src/main.rs:30`):

| Command | Alias | Description |
|---------|-------|-------------|
| `agentos task create <query>` | `agentos t c` | Create and execute task |
| `agentos task list` | `agentos t ls` | List tasks with filters |
| `agentos task get <id>` | `agentos t g` | Get task details |
| `agentos task cancel <id>` | `agentos t cancel` | Cancel running task |
| `agentos task logs <id>` | `agentos t log` | Stream task logs |

**Daemon Commands** (`cli/src/main.rs:56`):

| Command | Alias | Description |
|---------|-------|-------------|
| `agentos daemon start` | `agentos d s` | Start supervisor |
| `agentos daemon stop` | `agentos d stop` | Stop supervisor |
| `agentos daemon status` | `agentos d st` | Check daemon status |
| `agentos daemon logs` | `agentos d log` | View daemon logs |
| `agentos daemon restart` | `agentos d rs` | Restart daemon |

**Desktop Commands** (`cli/src/main.rs:78`):

| Command | Description |
|---------|-------------|
| `agentos desktop screenshot [--output path]` | Take screenshot |
| `agentos desktop click --x 100 --y 200` | Click at coordinates |
| `agentos desktop type "text" [--interval 50]` | Type text |
| `agentos desktop focus --window "Chrome"` | Focus window |
| `agentos desktop list-windows` | List all windows |
| `agentos desktop find "text" [--screenshot]` | Find text via OCR |

**Config Commands** (`cli/src/main.rs:120`):

| Command | Description |
|---------|-------------|
| `agentos config init [--force]` | Initialize default config |
| `agentos config set <key> <value>` | Set config value |
| `agentos config get <key>` | Get config value |
| `agentos config list` | List all config |
| `agentos config path` | Show config file path |

### Configuration

**File**: `cli/src/config.rs` (referenced in main.rs)

```rust
pub struct Config {
    pub supervisor: SupervisorConfig,  // host, port
    pub data_dir: PathBuf,
    pub log_level: String,
    pub auto_start_daemon: bool,
    pub default_timeout: u64,
    pub default_output_format: OutputFormat,  // Text or Json
    pub desktop: DesktopConfig,  // screenshot_delay_ms, click_interval_ms, etc.
}
```

Config file location:
- Windows: `%APPDATA%/agentos/config.toml`
- macOS: `~/Library/Application Support/agentos/config.toml`
- Linux: `~/.config/agentos/config.toml`

### Desktop Automation

**File**: `cli/src/commands/desktop.rs:1`

All desktop commands follow this pattern:

```rust
pub async fn screenshot(config: &Config, output: Option<String>, window: Option<String>) -> Result<()> {
    let client = ApiClient::new(config);
    
    // Check supervisor health
    if !client.health_check().await? {
        anyhow::bail!("Supervisor is not running. Use 'agentos daemon start' to start it.");
    }
    
    // Execute command
    let screenshot = client.take_screenshot(window.as_deref()).await?;
    
    // Save result
    fs::write(&output_path, screenshot)?;
    println!("✓ Screenshot saved to {}", output_path);
    
    Ok(())
}
```

### Dependencies

From `cli/Cargo.toml:1`:

```toml
[dependencies]
clap = { version = "4.5", features = ["derive", "env"] }  # CLI parsing
tokio = { version = "1.37", features = ["full"] }         # Async runtime
serde = { version = "1.0", features = ["derive"] }        # Serialization
reqwest = { version = "0.12", features = ["json"] }       # HTTP client
colored = "2.1"                                            # Terminal colors
comfy-table = "7.1"                                        # Table formatting
chrono = { version = "0.4", features = ["serde"] }         # Date/time
dirs = "5.0"                                               # Config directories
uuid = { version = "1.6", features = ["v4", "serde"] }     # UUID generation
```

### Build Commands

```bash
cd cli
cargo build --release
# Output: target/release/agentos.exe (~5 MB)
```

### Output Formats

**Text Mode** (default):
```
✓ Task created: 550e8400-e29b-41d4-a716-446655440000
  Status: running
  Query: Open Chrome and search for rust tutorials
```

**JSON Mode** (`--output json`):
```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "running",
  "query": "Open Chrome and search for rust tutorials"
}
```

---

## Rust TUI

### Architecture

```
tui/
├── Cargo.toml           # Package: agentos-tui v0.1.0
└── src/
    ├── main.rs          # Entry point with clap args
    ├── app.rs           # App state + main loop
    ├── config.rs        # TUI configuration
    ├── models.rs        # Task, LogEntry, DaemonStatus structs
    ├── styles.rs        # Color theme definitions
    └── components/
        ├── mod.rs         # Component exports
        ├── task_list.rs   # Task table with selection
        ├── task_detail.rs # Task detail panel
        ├── log_panel.rs   # Scrollable log viewer
        └── status_bar.rs  # Bottom status bar
```

### Entry Point

**File**: `tui/src/main.rs:1`

```rust
#[derive(Parser)]
#[command(name = "agentos-tui")]
#[command(about = "AgentOS TUI - Real-time task monitoring dashboard")]
struct Args {
    #[arg(short, long, default_value = "127.0.0.1")]
    host: String,
    #[arg(short, long, default_value_t = 8080)]
    port: u16,
    #[arg(short, long, default_value_t = 1000)]
    refresh: u64,  // Refresh interval in ms
    #[arg(short, long)]
    verbose: bool,
}

#[tokio::main]
async fn main() -> Result<()> {
    let args = Args::parse();
    
    // Initialize tracing
    tracing_subscriber::fmt()
        .with_env_filter(if args.verbose { "debug" } else { "info" })
        .init();
    
    // Run the TUI app
    app::run()?;
    Ok(())
}
```

### App State

**File**: `tui/src/app.rs:1`

```rust
pub struct App {
    pub tasks: Vec<Task>,
    pub logs: Vec<LogEntry>,
    pub status: DaemonStatus,
    pub connected: bool,
    pub should_quit: bool,
    pub show_help: bool,
}

impl App {
    pub fn on_key(&mut self, key: KeyCode) {
        match key {
            KeyCode::Char('q') | KeyCode::Esc => self.should_quit = true,
            KeyCode::Char('?') | KeyCode::Char('h') => self.show_help = !self.show_help,
            _ => {}
        }
    }

    pub fn draw(&mut self, frame: &mut ratatui::Frame) {
        // Split into content + status bar
        let chunks = Layout::default()
            .direction(Direction::Vertical)
            .constraints([Constraint::Min(10), Constraint::Length(3)])
            .split(frame.size());
        
        // Draw main content (dashboard or help)
        // Draw status bar
    }
}
```

### Components

**TaskList**: `tui/src/components/task_list.rs:1`

```rust
pub struct TaskList {
    pub tasks: Vec<Task>,
    pub state: TableState,      // ratatui table state for selection
    pub scroll_offset: usize,
}

impl TaskList {
    pub fn next(&mut self) { /* Move selection down */ }
    pub fn previous(&mut self) { /* Move selection up */ }
    pub fn first(&mut self) { /* Select first */ }
    pub fn last(&mut self) { /* Select last */ }
    
    pub fn draw<B: Backend>(&mut self, frame: &mut Frame<B>, area: Rect, theme: &Theme) {
        // Render table with columns: Status, ID, Query, Steps, Created
    }
}
```

**LogPanel**: `tui/src/components/log_panel.rs:1`

```rust
pub struct LogPanel {
    pub logs: VecDeque<LogEntry>,
    pub auto_scroll: bool,      // Auto-scroll to bottom
    pub scroll_offset: usize,
    pub max_lines: usize,       // Max log lines to keep
    pub filter: Option<String>, // Filter by text/level
}

impl LogPanel {
    pub fn add_log(&mut self, entry: LogEntry) { /* Add and maintain max size */ }
    pub fn scroll_up(&mut self, amount: usize) { /* Scroll up, disable auto-scroll */ }
    pub fn scroll_down(&mut self, amount: usize) { /* Scroll down */ }
    pub fn toggle_auto_scroll(&mut self) { /* Toggle auto-scroll */ }
    pub fn set_filter(&mut self, filter: Option<String>) { /* Filter logs */ }
}
```

**TaskDetail**: `tui/src/components/task_detail.rs:1`

```rust
pub struct TaskDetail {
    pub visible: bool,
}

impl TaskDetail {
    pub fn draw<B: Backend>(&self, frame: &mut Frame<B>, area: Rect, task: Option<&Task>) {
        // Show: ID, Query, Status, Created/Updated/Completed
        // Steps with status icons (○ pending, ▶ running, ✓ completed, ✗ failed)
        // Result or Error if present
    }
}
```

**StatusBar**: `tui/src/components/status_bar.rs:1`

```rust
pub struct StatusBar {
    pub connected: bool,
    pub status: Option<DaemonStatus>,
}

impl StatusBar {
    pub fn draw<B: Backend>(&self, frame: &mut Frame<B>, area: Rect, theme: &Theme) {
        // Format: "● connected | running | v0.1.0 | 1h 23m | 1 active / 5 total | 45.2 MB   ? help"
    }
}
```

### Models

**File**: `tui/src/models.rs:1`

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Task {
    pub id: String,
    pub query: String,
    pub status: TaskStatus,  // Pending, Running, Paused, Completed, Failed, Cancelled
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
    pub completed_at: Option<DateTime<Utc>>,
    pub steps: Vec<TaskStep>,
    pub result: Option<String>,
    pub error: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DaemonStatus {
    pub running: bool,
    pub pid: Option<u32>,
    pub version: String,
    pub uptime_seconds: Option<u64>,
    pub active_tasks: usize,
    pub total_tasks: usize,
    pub memory_usage_mb: Option<f64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LogEntry {
    pub timestamp: DateTime<Utc>,
    pub level: String,  // error, warn, info, debug, trace
    pub task_id: Option<String>,
    pub message: String,
}
```

### Theme/Styles

**File**: `tui/src/styles.rs:1`

```rust
pub struct Theme {
    pub background: Color,      // Black
    pub foreground: Color,    // White
    pub primary: Color,       // Cyan
    pub success: Color,       // Green
    pub warning: Color,       // Yellow
    pub error: Color,         // Red
    pub muted: Color,         // Gray
    pub border: Color,        // DarkGray
    pub border_focused: Color, // Cyan
}

impl Theme {
    pub fn task_status(&self, status: &TaskStatus) -> Style {
        match status {
            TaskStatus::Running => Style::default().fg(self.primary).add_modifier(Modifier::BOLD),
            TaskStatus::Completed => Style::default().fg(self.success),
            TaskStatus::Failed => Style::default().fg(self.error),
            _ => Style::default().fg(self.muted),
        }
    }
    
    pub fn log_level(&self, level: &str) -> Style {
        match level {
            "error" => Style::default().fg(self.error),
            "warn" => Style::default().fg(self.warning),
            "info" => Style::default().fg(self.info),
            _ => Style::default().fg(self.muted),
        }
    }
}
```

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `q` / `Esc` | Quit |
| `?` / `h` | Toggle help |
| `↑` / `↓` / `j` / `k` | Navigate task list |
| `g` | Go to first task |
| `G` | Go to last task |
| `Enter` | View task details |
| `c` | Cancel selected task |
| `r` | Refresh task list |
| `Tab` | Switch between panels |
| `PgUp` / `PgDn` | Scroll logs |
| `t` | Jump to top of logs |
| `b` | Jump to bottom of logs |
| `Space` | Toggle auto-scroll |
| `/` | Filter logs |

### Dependencies

From `tui/Cargo.toml:1`:

```toml
[dependencies]
ratatui = "0.26"                                    # TUI framework
crossterm = { version = "0.27", features = ["event-stream"] }  # Terminal handling
tokio = { version = "1.37", features = ["full"] }   # Async runtime
reqwest = { version = "0.12", features = ["json", "stream"] }  # HTTP client
serde = { version = "1.0", features = ["derive"] }    # Serialization
chrono = { version = "0.4", features = ["serde"] }    # Date/time
unicode-width = "0.1"                               # Unicode text handling
clap = { version = "4.5", features = ["derive"] }   # CLI args
```

### Build Commands

```bash
cd tui
cargo build --release
# Output: target/release/agentos-tui.exe (~3 MB)
```

### Usage

```bash
# Connect to default supervisor (127.0.0.1:8080)
agentos-tui

# Connect to specific host/port
agentos-tui --host 192.168.1.100 --port 8080

# Faster refresh (500ms)
agentos-tui --refresh 500

# Verbose logging
agentos-tui --verbose
```

---

## API Integration

All three interfaces communicate with the Go supervisor via HTTP API:

### Endpoints Used

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/status` | GET | Daemon status |
| `/api/v1/tasks` | GET/POST | List/Create tasks |
| `/api/v1/tasks/{id}` | GET | Get task details |
| `/api/v1/tasks/{id}/cancel` | POST | Cancel task |
| `/api/v1/desktop/screenshot` | POST | Take screenshot |
| `/api/v1/desktop/click` | POST | Click at coordinates |
| `/api/v1/desktop/type` | POST | Type text |
| `/api/v1/desktop/focus` | POST | Focus window |
| `/api/v1/desktop/windows` | GET | List windows |
| `/api/v1/desktop/find` | POST | Find element via OCR |

### Base URL

```
http://127.0.0.1:8080
```

---

## Binary Sizes

| Component | Binary | Size (Release) |
|-----------|--------|----------------|
| CLI | `agentos.exe` | ~5 MB |
| TUI | `agentos-tui.exe` | ~3 MB |
| Tauri GUI | `agentos-gui.exe` | ~15-20 MB |

---

## Build Summary

```bash
# Build all interfaces
cd cli && cargo build --release
cd tui && cargo build --release
cd gui && npm run tauri:build

# Binaries location
cli/target/release/agentos.exe
tui/target/release/agentos-tui.exe
gui/src-tauri/target/release/agentos-gui.exe
```

---

## File Reference

### Tauri GUI

| File | Lines | Purpose |
|------|-------|---------|
| `gui/src-tauri/src/main.rs` | ~80 | Entry point, tray, shortcuts |
| `gui/src-tauri/src/config.rs` | ~40 | AppConfig struct |
| `gui/src-tauri/src/tray.rs` | ~60 | System tray menu |
| `gui/src-tauri/src/shortcuts.rs` | ~50 | Global hotkeys |
| `gui/src-tauri/src/notifications.rs` | ~30 | Native notifications |
| `gui/src-tauri/src/commands/daemon.rs` | ~30 | Daemon commands |
| `gui/src-tauri/src/commands/config.rs` | ~50 | Config commands |
| `gui/src-tauri/src/commands/system.rs` | ~10 | Version command |
| `gui/src-tauri/tauri.conf.json` | ~150 | Window config, permissions |
| `gui/src-tauri/Cargo.toml` | ~30 | Rust dependencies |
| `gui/src/App.tsx` | ~60 | Main React app |
| `gui/src/context/AppContext.tsx` | ~100 | Task state management |
| `gui/src/components/Layout.tsx` | ~120 | Sidebar navigation |
| `gui/src/pages/Dashboard.tsx` | ~250 | Task dashboard |
| `gui/src/pages/Chat.tsx` | ~200 | Chat interface |
| `gui/src/pages/Tools.tsx` | ~180 | Tool registry |
| `gui/src/pages/AgentBuilder.tsx` | ~200 | Agent management |
| `gui/src/pages/Settings.tsx` | ~280 | Configuration UI |
| `gui/package.json` | ~40 | npm dependencies |

### CLI

| File | Lines | Purpose |
|------|-------|---------|
| `cli/src/main.rs` | ~250 | Entry point, command definitions |
| `cli/src/config.rs` | ~100 | Configuration management |
| `cli/src/ipc.rs` | ~150 | HTTP API client |
| `cli/src/models.rs` | ~80 | Data structures |
| `cli/src/commands/task.rs` | ~150 | Task commands |
| `cli/src/commands/daemon.rs` | ~120 | Daemon commands |
| `cli/src/commands/desktop.rs` | ~200 | Desktop automation |
| `cli/src/commands/config.rs` | ~100 | Config commands |
| `cli/Cargo.toml` | ~60 | Dependencies |

### TUI

| File | Lines | Purpose |
|------|-------|---------|
| `tui/src/main.rs` | ~50 | Entry point |
| `tui/src/app.rs` | ~150 | App state, main loop |
| `tui/src/config.rs` | ~50 | Configuration |
| `tui/src/models.rs` | ~150 | Data structures |
| `tui/src/styles.rs` | ~100 | Theme definitions |
| `tui/src/components/task_list.rs` | ~200 | Task table |
| `tui/src/components/task_detail.rs` | ~150 | Task detail panel |
| `tui/src/components/log_panel.rs` | ~200 | Log viewer |
| `tui/src/components/status_bar.rs` | ~100 | Status bar |
| `tui/Cargo.toml` | ~50 | Dependencies |

---

## Total Statistics

| Metric | Value |
|--------|-------|
| **Total Files** | 35 |
| **Total Lines** | ~3,500 |
| **Rust Files** | 25 |
| **TypeScript/React Files** | 10 |
| **Config Files** | 5 |

---

## Dependencies Summary

### Rust Dependencies (All Interfaces)

| Crate | Version | Used By | Purpose |
|-------|---------|---------|---------|
| tauri | 1.5 | GUI | Desktop framework |
| clap | 4.5 | CLI, TUI | CLI parsing |
| ratatui | 0.26 | TUI | Terminal UI |
| crossterm | 0.27 | TUI | Terminal handling |
| tokio | 1.37 | All | Async runtime |
| reqwest | 0.12 | All | HTTP client |
| serde | 1.0 | All | Serialization |
| chrono | 0.4 | All | Date/time |
| colored | 2.1 | CLI | Terminal colors |
| comfy-table | 7.1 | CLI | Table formatting |
| unicode-width | 0.1 | TUI | Unicode handling |

### JavaScript Dependencies (GUI Only)

| Package | Version | Purpose |
|---------|---------|---------|
| react | 18.2 | UI framework |
| @tauri-apps/api | 1.5 | Tauri bindings |
| react-router-dom | 6.22 | Routing |
| framer-motion | 11.0 | Animations |
| lucide-react | 0.400 | Icons |
| recharts | 2.12 | Charts |
| tailwindcss | 3.4 | Styling |
| vite | 5.0 | Build tool |

---

*End of Technical Specification*
