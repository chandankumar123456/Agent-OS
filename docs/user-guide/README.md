# AgentOS User Guide

Welcome to AgentOS! This guide will help you install, configure, and use AgentOS effectively.

## Table of Contents

1. [Installation Guide](#installation-guide)
2. [Quick Start](#quick-start)
3. [CLI Reference](#cli-reference)
4. [TUI Guide](#tui-guide)
5. [Troubleshooting](#troubleshooting)

---

## Installation Guide

### Windows

#### Option 1: MSI Installer (Recommended)

1. Download the latest MSI from [releases](https://github.com/AgentOS/releases)
2. Double-click the `.msi` file to run the installer
3. Follow the installation wizard
4. AgentOS will be installed to `C:\Program Files\AgentOS\`

The installer will:
- Install the supervisor, CLI, and TUI binaries
- Create desktop shortcuts
- Add AgentOS to your Start Menu
- Set up environment variables

#### Option 2: Portable ZIP

1. Download `AgentOS-v0.1.0-windows.zip`
2. Extract to a folder of your choice
3. Run `supervisor.exe` from the extracted folder

#### Verification

Open Command Prompt and verify installation:
```cmd
supervisor -version
```

### macOS

#### DMG Installer

1. Download the latest DMG from [releases](https://github.com/AgentOS/releases)
2. Open the `.dmg` file
3. Drag "AgentOS" to your Applications folder
4. Eject the disk image

#### Universal Binary

The macOS package includes a universal binary that works on both Intel and Apple Silicon Macs.

#### Verification

Open Terminal and verify installation:
```bash
/Applications/AgentOS.app/Contents/MacOS/supervisor -version
```

### Linux

#### AppImage (Recommended)

1. Download the latest AppImage from [releases](https://github.com/AgentOS/releases)
2. Make it executable:
   ```bash
   chmod +x AgentOS-v0.1.0-x86_64.AppImage
   ```
3. Run it:
   ```bash
   ./AgentOS-v0.1.0-x86_64.AppImage
   ```

#### Option 2: Build from Source

```bash
git clone https://github.com/AgentOS/AgentOS.git
cd AgentOS/supervisor
go build -o supervisor .
```

#### Verification

```bash
./supervisor -version
```

---

## Quick Start

### 1. First Run

Start the AgentOS supervisor:

```bash
# Windows
supervisor

# macOS/Linux
./supervisor
```

The supervisor will:
- Start the HTTP API server on port 8080
- Initialize the SQLite database
- Set up default configuration

### 2. Check Status

Open a new terminal and check the status:

```bash
# Get supervisor status
curl http://localhost:8080/status

# Check health
curl http://localhost:8080/health
```

### 3. Create Your First Task

```bash
# Create a task using the CLI
agent task create "Hello AgentOS"

# List tasks
agent task list

# Get task details
agent task get <task-id>
```

### 4. Use the TUI

For an interactive experience:

```bash
agent-tui
```

Use arrow keys to navigate, Enter to select, and `?` for help.

---

## CLI Reference

### Global Commands

```
agent [command] [flags]
```

### Task Management

| Command | Description | Example |
|---------|-------------|---------|
| `task create <name>` | Create a new task | `agent task create "My Task"` |
| `task list` | List all tasks | `agent task list` |
| `task get <id>` | Get task details | `agent task get 123` |
| `task cancel <id>` | Cancel a task | `agent task cancel 123` |
| `task logs <id>` | View task logs | `agent task logs 123` |

### Daemon Control

| Command | Description | Example |
|---------|-------------|---------|
| `daemon start` | Start supervisor | `agent daemon start` |
| `daemon stop` | Stop supervisor | `agent daemon stop` |
| `daemon status` | Check status | `agent daemon status` |
| `daemon logs` | View logs | `agent daemon logs` |
| `daemon restart` | Restart supervisor | `agent daemon restart` |

### Desktop Automation

| Command | Description | Example |
|---------|-------------|---------|
| `desktop screenshot` | Take a screenshot | `agent desktop screenshot` |
| `desktop click <x> <y>` | Click at coordinates | `agent desktop click 100 200` |
| `desktop type <text>` | Type text | `agent desktop type "Hello"` |
| `desktop focus <window>` | Focus window | `agent desktop focus "Chrome"` |
| `desktop list-windows` | List windows | `agent desktop list-windows` |
| `desktop find <text>` | Find element | `agent desktop find "Submit"` |

### Configuration

| Command | Description | Example |
|---------|-------------|---------|
| `config init` | Initialize config | `agent config init` |
| `config set <key> <value>` | Set config value | `agent config set port 9000` |
| `config get <key>` | Get config value | `agent config get port` |
| `config list` | List all config | `agent config list` |
| `config path` | Show config path | `agent config path` |

### Update Management

| Command | Description | Example |
|---------|-------------|---------|
| `update check` | Check for updates | `agent update check` |
| `update download` | Download update | `agent update download` |
| `update install <path>` | Install update | `agent update install ./update.msi` |
| `update status` | Show update status | `agent update status` |

### Global Flags

| Flag | Description | Default |
|------|-------------|---------|
| `--config <path>` | Config file path | `~/.agentos/config.yaml` |
| `--host <host>` | API host | `127.0.0.1` |
| `--port <port>` | API port | `8080` |
| `--verbose` | Enable verbose logging | `false` |
| `--version` | Show version | - |
| `--help` | Show help | - |

---

## TUI Guide

The Terminal User Interface (TUI) provides a visual way to interact with AgentOS.

### Launching

```bash
agent-tui
```

### Navigation

| Key | Action |
|-----|--------|
| `↑/↓` or `j/k` | Navigate up/down |
| `←/→` or `h/l` | Switch panels |
| `Enter` | Select/execute |
| `Esc` or `q` | Go back/quit |
| `?` | Show help |
| `/` | Search/filter |
| `r` | Refresh |
| `n` | Create new task |
| `d` | Delete task |

### Panels

#### Task List (Left)
- Shows all tasks with status
- Color-coded: green (running), yellow (pending), red (failed)
- Shows task ID, name, status, and timestamp

#### Task Details (Right)
- Shows detailed information about selected task
- Steps, results, logs
- Error messages if failed

#### Status Bar (Bottom)
- Connection status
- Current time
- Keyboard shortcuts hint

### Views

#### Dashboard
Overview of system status, active tasks, recent activity.

#### Tasks
Full task list with filtering and sorting options.

#### Logs
Streaming log view with filtering capabilities.

#### Settings
Configuration editor with validation.

---

## Troubleshooting

### Common Issues

#### Issue: "Connection refused" when running CLI commands

**Cause:** Supervisor is not running

**Solution:**
```bash
agent daemon start
# or
supervisor &
```

#### Issue: "Port already in use"

**Cause:** Another process is using port 8080

**Solution:**
1. Find the process:
   ```bash
   # Windows
   netstat -ano | findstr :8080
   
   # macOS/Linux
   lsof -i :8080
   ```
2. Change AgentOS port:
   ```bash
   supervisor -port 9000
   ```

#### Issue: Task fails with "timeout"

**Cause:** Task exceeded maximum execution time

**Solution:**
- Check task logs: `agent task logs <id>`
- Verify resources are available
- Adjust timeout in config: `agent config set timeout 300`

#### Issue: "Permission denied" on Linux

**Cause:** AppImage needs executable permission

**Solution:**
```bash
chmod +x AgentOS-*.AppImage
```

#### Issue: "supervisor.exe not found" on Windows

**Cause:** Not in PATH or not installed

**Solution:**
1. Add to PATH: `C:\Program Files\AgentOS\bin`
2. Or use full path: `"C:\Program Files\AgentOS\bin\supervisor.exe"`

### Log Locations

| Platform | Location |
|----------|----------|
| Windows | `%APPDATA%\AgentOS\logs\` |
| macOS | `~/Library/Logs/AgentOS/` |
| Linux | `~/.agentos/logs/` |

### Debug Mode

Enable debug logging:

```bash
supervisor -log-level debug
```

### Getting Help

1. Check logs: `agent daemon logs`
2. Run with verbose: `agent --verbose <command>`
3. Visit: https://docs.agentos.dev
4. GitHub Issues: https://github.com/AgentOS/AgentOS/issues

---

## Configuration File

### Location

- **Windows:** `%APPDATA%\AgentOS\config\default.yaml`
- **macOS:** `~/Library/Application Support/AgentOS/config/default.yaml`
- **Linux:** `~/.agentos/config/default.yaml`

### Example Configuration

```yaml
# AgentOS Configuration

# Server settings
server:
  host: 127.0.0.1
  port: 8080

# Logging
logging:
  level: info  # debug, info, warn, error
  format: text  # text, json

# Update settings
update:
  enabled: true
  channel: stable  # stable, beta, dev
  url: https://releases.agentos.dev
  interval: 24h

# Worker pool
workers:
  min: 2
  max: 10
  timeout: 30s

# Database
database:
  path: ~/.agentos/data/supervisor.db

# Features
features:
  auto_start: true
  system_tray: true
  notifications: true
```

---

## Next Steps

- Read the [API Documentation](../api/README.md)
- Learn about [Advanced Configuration](../deployment/configuration.md)
- Explore [Tutorials](../tutorials/)

---

**Version:** 0.1.0  
**Last Updated:** 2026-05-09
