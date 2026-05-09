# Task Plan: Rust TUI and Tauri GUI for AgentOS

## Goal
Build complete Rust TUI (Terminal User Interface) and Tauri GUI implementations for AgentOS.

## Part 1: TUI (Terminal User Interface)

### Phase 1.1: Create TUI Module
- [ ] Create `cli/src/tui.rs` - Main TUI implementation with ratatui
  - Real-time task monitoring
  - Agent status display with tables
  - Log viewer with scrollback
  - Keyboard navigation
  - Event handling
  - UI components (task list, log view, status bar, help panel)

### Phase 1.2: Integrate TUI into CLI
- [ ] Modify `cli/src/main.rs` - Add `agentos tui` subcommand
- [ ] Update `cli/Cargo.toml` - Add ratatui dependencies

## Part 2: Tauri GUI

### Phase 2.1: Initialize Tauri Project
- [ ] Create `gui/` directory structure
- [ ] Create `gui/package.json` - Tauri + React setup
- [ ] Create `gui/src-tauri/Cargo.toml` - Tauri dependencies
- [ ] Create `gui/src-tauri/tauri.conf.json` - Tauri configuration

### Phase 2.2: Tauri Rust Backend
- [ ] Create `gui/src-tauri/src/main.rs` - Main Tauri entry point
- [ ] Create `gui/src-tauri/src/tray.rs` - System tray integration
  - Status icon updates
  - Context menu (pause, resume, settings)
  - Window management

### Phase 2.3: Frontend Integration
- [ ] Create `gui/src/` - React frontend wrapper
- [ ] Integrate existing frontend from `frontend/` directory
- [ ] Configure build scripts for production

## Files to Create/Modify

### TUI Files:
1. `cli/src/tui.rs` (NEW)
2. `cli/src/main.rs` (MODIFY - add tui command)
3. `cli/Cargo.toml` (MODIFY - add ratatui deps)

### Tauri GUI Files:
1. `gui/package.json` (NEW)
2. `gui/src-tauri/Cargo.toml` (NEW)
3. `gui/src-tauri/tauri.conf.json` (NEW)
4. `gui/src-tauri/src/main.rs` (NEW)
5. `gui/src-tauri/src/tray.rs` (NEW)
6. `gui/src-tauri/src/lib.rs` (NEW)
7. `gui/src/main.tsx` (NEW)
8. `gui/index.html` (NEW)
9. `gui/vite.config.ts` (NEW)
10. `gui/tsconfig.json` (NEW)

## Dependencies

### TUI (ratatui):
- ratatui = "0.24"
- crossterm = "0.27"
- tokio = { version = "1.37", features = ["full"] }
- reqwest = { version = "0.12", features = ["json"] }
- serde = { version = "1.0", features = ["derive"] }
- serde_json = "1.0"
- chrono = "0.4"

### Tauri:
- tauri = { version = "1.6", features = ["system-tray"] }
- tokio = { version = "1.37", features = ["full"] }
- serde = { version = "1.0", features = ["derive"] }

## Acceptance Criteria
1. `agentos tui` launches working TUI
2. TUI shows real-time task progress
3. Tauri app builds and runs (`cargo tauri dev`)
4. System tray shows agent status
5. React frontend loads in Tauri window

## Status
**In Progress** - Starting implementation
