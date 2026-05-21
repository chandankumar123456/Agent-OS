# AgentOS GUI - Tauri + React Application

A native desktop application built with Tauri and React for AgentOS.

## Features

- **Native Performance**: Built with Tauri for minimal resource usage
- **System Tray**: Run in background with system tray integration
- **Global Hotkeys**: System-wide keyboard shortcuts
- **Native Notifications**: Desktop notifications for task events
- **Auto-updater**: Built-in update mechanism
- **Single Instance**: Prevents multiple app instances

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Frontend Framework | React 18 |
| Build Tool | Vite 5 |
| Native Framework | Tauri 1.5 |
| Styling | Tailwind CSS 3.4 |
| Icons | Lucide React |

## Project Structure

```
gui/
├── package.json              # Frontend dependencies
├── tsconfig.json             # TypeScript config
├── vite.config.ts            # Vite configuration
├── tailwind.config.js        # Tailwind configuration
├── index.html                # Entry HTML
├── src/                      # Frontend source
│   ├── main.tsx              # React entry
│   ├── App.tsx               # Root component
│   ├── App.css               # Global styles
│   ├── index.css             # Tailwind imports
│   ├── components/           # React components
│   │   └── Layout.tsx        # App layout
│   ├── pages/                # Page components
│   │   ├── Dashboard.tsx     # Task dashboard
│   │   ├── AgentBuilder.tsx  # Agent management
│   │   ├── Tools.tsx         # Tool registry
│   │   ├── Chat.tsx          # Chat interface
│   │   └── Settings.tsx      # App settings
│   ├── context/              # React context
│   │   └── AppContext.tsx    # Global state
│   ├── hooks/                # Custom hooks
│   ├── api/                  # API clients
│   └── types/                # TypeScript types
│       └── index.ts
└── src-tauri/                # Rust/Tauri source
    ├── Cargo.toml            # Rust dependencies
    ├── tauri.conf.json       # Tauri configuration
    ├── icons/                # App icons
    └── src/                   # Rust source
        ├── main.rs            # Entry point
        ├── config.rs          # App configuration
        ├── tray.rs            # System tray
        ├── shortcuts.rs       # Global shortcuts
        ├── notifications.rs   # Native notifications
        └── commands/          # Tauri commands
            ├── mod.rs
            ├── daemon.rs
            ├── config.rs
            ├── notifications.rs
            └── system.rs
```

## Development

### Prerequisites

- Node.js 20+
- Rust 1.70+

### Setup

```bash
# Install dependencies
cd gui
npm install

# Install Rust dependencies
cd src-tauri
cargo build
```

### Run Development Server

```bash
# In gui directory
npm run tauri:dev
```

This starts the Vite dev server and Tauri development window.

### Build Production

```bash
# Build for production
npm run tauri:build
```

Binaries are output to `src-tauri/target/release/`.

## Configuration

### App Settings

Stored in OS-specific config directories:
- Windows: `%APPDATA%/com.agentos.app/`
- macOS: `~/Library/Application Support/com.agentos.app/`
- Linux: `~/.config/com.agentos.app/`

### Environment Variables

Create `.env` in `gui/` directory:

```env
VITE_API_URL=http://localhost:8080
VITE_WS_URL=ws://localhost:8080
```

## Global Shortcuts

| Shortcut | Action |
|----------|--------|
| Ctrl+Shift+A | Show AgentOS window |
| Ctrl+Shift+S | Take screenshot |
| Ctrl+Shift+Q | Quick task creation |

## System Tray

The app continues running in the system tray when closed:

- **Left Click**: Toggle window visibility
- **Right Click**: Context menu
  - Show AgentOS
  - Hide AgentOS
  - Quit

## Tauri Commands

Rust functions exposed to the frontend:

```typescript
// Get daemon status
const status = await invoke('get_daemon_status')

// Start/stop daemon
await invoke('start_daemon')
await invoke('stop_daemon')

// Get/set configuration
const config = await invoke('get_config')
await invoke('set_config', { update: { notificationsEnabled: true } })

// Show notification
await invoke('show_notification', { title: 'Task Complete', body: 'Task finished successfully' })

// Get app version
const version = await invoke('get_app_version')
```

## Build Commands

```bash
# Development
npm run dev              # Vite only
npm run tauri:dev        # Vite + Tauri

# Production
npm run build            # Frontend only
npm run tauri:build      # Full application

# Other
npm run preview          # Preview production build
```

## Icons

Place app icons in `src-tauri/icons/`:
- `32x32.png` - System tray
- `128x128.png` - App icon
- `128x128@2x.png` - Retina displays
- `icon.icns` - macOS
- `icon.ico` - Windows

## License

MIT - See parent project LICENSE
