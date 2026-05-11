# AgentOS — Autonomous Agent Operating System

**Version:** 0.3.0  
**Architecture:** Multi-language, distributed, desktop-native agent runtime  
**License:** Proprietary  
**Repository:** https://github.com/Chandankumar123456/agentos  

AgentOS is a production-grade, desktop-native autonomous agent operating system designed to execute complex multi-step tasks across heterogeneous environments — desktop GUI, web browser, filesystem, shell, and cloud APIs. It integrates structured LLM orchestration (LangGraph), a Model Context Protocol (MCP) tool server mesh, distributed task queuing, real-time observability, and multi-agent coordination into a single coherent runtime.

The system is written in **Python** (FastAPI, Celery, LangGraph), **Go** (supervisor/control plane), **Rust** (CLI, TUI, desktop automation, Tauri shell), and **TypeScript** (React GUI). Communication between components uses **gRPC** (protobuf v3), **HTTP/REST**, **WebSocket**, and **Redis PubSub**.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [System Components](#2-system-components)
   - 2.1 [Python Backend (app/)](#21-python-backend-app)
   - 2.2 [Go Supervisor (supervisor/)](#22-go-supervisor-supervisor)
   - 2.3 [Rust CLI (cli/)](#23-rust-cli-cli)
   - 2.4 [Rust TUI (tui/)](#24-rust-tui-tui)
   - 2.5 [Rust Desktop Automation (desktop/)](#25-rust-desktop-automation-desktop)
   - 2.6 [Tauri GUI (gui/)](#26-tauri-gui-gui)
3. [Core Subsystems](#3-core-subsystems)
   - 3.1 [Bootstrap & Runtime Initialization](#31-bootstrap--runtime-initialization)
   - 3.2 [Agent System](#32-agent-system)
   - 3.3 [Orchestrator](#33-orchestrator)
   - 3.4 [Model Context Protocol (MCP)](#34-model-context-protocol-mcp)
   - 3.5 [Tool System](#35-tool-system)
   - 3.6 [Memory & Persistence](#36-memory--persistence)
   - 3.7 [Task Queue & State Machine](#37-task-queue--state-machine)
   - 3.8 [Execution Modes](#38-execution-modes)
   - 3.9 [Capability System](#39-capability-system)
   - 3.10 [Action v1 Framework](#310-action-v1-framework)
   - 3.11 [Workflow Engine](#311-workflow-engine)
   - 3.12 [Guardrails & Safety](#312-guardrails--safety)
4. [API Reference](#4-api-reference)
   - 4.1 [FastAPI HTTP Endpoints](#41-fastapi-http-endpoints)
   - 4.2 [gRPC Services](#42-grpc-services)
   - 4.3 [WebSocket Protocol](#43-websocket-protocol)
5. [Database Schema](#5-database-schema)
   - 5.1 [PostgreSQL Tables](#51-postgresql-tables)
   - 5.2 [SQLite Tables (Supervisor)](#52-sqlite-tables-supervisor)
   - 5.3 [Migrations](#53-migrations)
6. [Configuration](#6-configuration)
   - 6.1 [Environment Variables](#61-environment-variables)
   - 6.2 [CLI Configuration](#62-cli-configuration)
   - 6.3 [GUI Configuration](#63-gui-configuration)
7. [Protocols & Communication](#7-protocols--communication)
   - 7.1 [gRPC Protobuf Definitions](#71-grpc-protobuf-definitions)
   - 7.2 [Inter-Process Communication](#72-inter-process-communication)
   - 7.3 [Message Formats](#73-message-formats)
8. [Development Guide](#8-development-guide)
   - 8.1 [Prerequisites](#81-prerequisites)
   - 8.2 [Local Setup](#82-local-setup)
   - 8.3 [Running Components](#83-running-components)
   - 8.4 [Testing](#84-testing)
   - 8.5 [Code Quality](#85-code-quality)
9. [Deployment](#9-deployment)
   - 9.1 [Docker Deployment](#91-docker-deployment)
   - 9.2 [Native Build](#92-native-build)
   - 9.3 [Configuration](#93-configuration)
10. [Architecture Decisions & Patterns](#10-architecture-decisions--patterns)
    - 10.1 [LangGraph-First Execution](#101-langgraph-first-execution)
    - 10.2 [Adaptive Execution Routing](#102-adaptive-execution-routing)
    - 10.3 [Dual-Mode Runtime](#103-dual-mode-runtime)
    - 10.4 [Canonical Execution State](#104-canonical-execution-state)
    - 10.5 [Failure Isolation & Circuit Breakers](#105-failure-isolation--circuit-breakers)
    - 10.6 [Inter-Agent Communication](#106-inter-agent-communication)
11. [Observability](#11-observability)
    - 11.1 [Structured Logging](#111-structured-logging)
    - 11.2 [Distributed Tracing](#112-distributed-tracing)
    - 11.3 [Prometheus Metrics](#113-prometheus-metrics)
    - 11.4 [Anomaly Detection & Alerting](#114-anomaly-detection--alerting)
    - 11.5 [Cost Tracking](#115-cost-tracking)
12. [Security](#12-security)
    - 12.1 [Authentication](#121-authentication)
    - 12.2 [Authorization & RBAC](#122-authorization--rbac)
    - 12.3 [Tool Permissions](#123-tool-permissions)
    - 12.4 [Credential Protection](#124-credential-protection)
    - 12.5 [TLS & mTLS](#125-tls--mtls)
13. [Extending AgentOS](#13-extending-agentos)
    - 13.1 [Adding a New Tool](#131-adding-a-new-tool)
    - 13.2 [Adding a New MCP Server](#132-adding-a-new-mcp-server)
    - 13.3 [Adding a New Agent Type](#133-adding-a-new-agent-type)
    - 13.4 [Adding a New Execution Mode](#134-adding-a-new-execution-mode)
14. [Troubleshooting](#14-troubleshooting)

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           USER INTERFACES                                │
│  ┌─────────┐  ┌──────────┐  ┌──────────────────┐  ┌──────────────────┐  │
│  │ Rust CLI │  │ Rust TUI │  │ Tauri GUI (React) │  │ HTTP/REST Clients│  │
│  └────┬────┘  └────┬─────┘  └────────┬─────────┘  └────────┬─────────┘  │
│       │            │                 │                       │           │
│       └────────────┼─────────────────┼───────────────────────┘           │
│                    │                 │                                   │
│              ┌─────▼─────────────────▼──────────────────────────┐        │
│              │             Go Supervisor (:8080)                  │        │
│              │  ┌───────────┐ ┌───────────┐ ┌────────────────┐  │        │
│              │  │ Runtime   │ │Checkpoint │ │  EventHub      │  │        │
│              │  │ Server    │ │ Server    │ │  (WebSocket)   │  │        │
│              │  │ (gRPC)    │ │ (gRPC)    │ │  Broadcast     │  │        │
│              │  └─────┬─────┘ └─────┬─────┘ └────────────────┘  │        │
│              │        │              │                            │        │
│              │  ┌─────▼──────────────▼──────────────────────┐    │        │
│              │  │          SQLite (agentos.db)               │    │        │
│              │  └───────────────────────────────────────────┘    │        │
│              └────────────────┬──────────────────────────────────┘        │
│                               │ HTTP/gRPC                                 │
│              ┌────────────────▼──────────────────────────────────┐        │
│              │           Python Runtime (:8000)                    │        │
│              │  ┌──────────┐ ┌──────────┐ ┌──────────────────┐    │        │
│              │  │ FastAPI  │ │  Celery  │ │  LangGraph       │    │        │
│              │  │ Web      │ │  Workers │ │  Executor        │    │        │
│              │  │ Server   │ │  (tasks) │ │  (agents)        │    │        │
│              │  └────┬─────┘ └────┬─────┘ └────────┬─────────┘    │        │
│              │       │            │                  │              │        │
│              │  ┌────▼────────────▼──────────────────▼─────────┐   │        │
│              │  │  PostgreSQL + Redis + MCP Server Mesh        │   │        │
│              │  └─────────────────────────────────────────────┘   │        │
│              └────────────────────────────────────────────────────┘        │
│                                                                           │
│              ┌────────────────────────────────────────────────────┐        │
│              │     Rust Desktop Automation (:50051)                │        │
│              │  ┌──────────┐ ┌──────────┐ ┌──────────────────┐    │        │
│              │  │ GDI      │ │ Win32   │ │  OCR (Python)    │    │        │
│              │  │ Capture  │ │ Input   │ │  via gRPC        │    │        │
│              │  └──────────┘ └──────────┘ └──────────────────┘    │        │
│              └────────────────────────────────────────────────────┘        │
└─────────────────────────────────────────────────────────────────────────┘
```

### High-Level Data Flow

1. **User Input**: CLI/TUI/GUI sends HTTP/REST request to the Go Supervisor or directly to the Python FastAPI server.
2. **Task Creation**: The orchestrator creates a task, classifies its capability, selects an execution environment, and determines complexity tier.
3. **Execution Path Selection**:
   - **Tier 0/1 (Direct/Sequential)**: Fast-path deterministic execution via `TaskComplexityRouter` for atomic operations (open app, type text, search web).
   - **Tier 2 (LangGraph)**: Full LangGraph state graph compilation with planner → executor → verifier nodes.
   - **Legacy Fallback**: Plan → Execute → Verify pipeline when LangGraph is unavailable.
4. **Tool Invocation**: Agents invoke tools through `ToolRegistry`, which dispatches to built-in tools, MCP server processes (via stdio JSON-RPC), or desktop environment tools.
5. **Recovery & Verification**: After execution, verification checks output correctness. On failure, the `RecoveryEngine` determines retry, escalation, or alternative strategy.
6. **Persistence**: Task state, execution trace, agent outputs, and workflow state are persisted to PostgreSQL (cloud mode) or SQLite (local mode).

### Technology Stack by Component

| Component   | Language   | Framework/Libraries                                       | Purpose                              |
|-------------|------------|----------------------------------------------------------|--------------------------------------|
| API Server  | Python 3.11| FastAPI, Uvicorn, SQLAlchemy 2.0, asyncpg                | HTTP/WS API for agent task execution |
| Orchestrator| Python     | LangGraph, LangChain, Pydantic 2                         | Agent orchestration & state graphs   |
| Task Queue  | Python     | Celery 5.6, Redis (broker), PostgreSQL (backend)          | Async task processing                |
| Supervisor  | Go 1.23    | gRPC, gorilla/websocket, modernc/sqlite                  | Control plane, task lifecycle, SQLite |
| CLI         | Rust       | clap, reqwest, tokio, comfy-table                         | Terminal user commands               |
| TUI         | Rust       | ratatui 0.26, crossterm, tokio-tungstenite                | Terminal dashboard                   |
| Desktop     | Rust       | tonic, prost, windows (Win32 API), image                  | Native desktop automation (gRPC)     |
| GUI         | TypeScript | React 18, Tailwind CSS, Tauri 1.5                        | Desktop GUI application              |
| Database    | —          | PostgreSQL 16, Redis 7, SQLite                             | Persistence & caching                |

---

## 2. System Components

### 2.1 Python Backend (`app/`)

The Python backend is the core execution engine. It is organized into 18 packages under `app/`:

| Package              | Lines   | Key Responsibilities                                          |
|----------------------|---------|---------------------------------------------------------------|
| `app/config/`        | ~275    | Settings management, runtime mode detection (HTTP/gRPC)       |
| `app/bootstrap.py`   | 420     | Canonical initialization sequence, lifecycle management       |
| `app/main.py`        | 223     | FastAPI web server entry point, middleware, error handlers    |
| `app/runtime/`       | ~2800   | AgentRuntime singleton, worker pool, factory, scaling, gRPC  |
| `app/orchestrator/`  | ~5400   | Core orchestrator, task runner, workflow, queue, state machine|
| `app/agents/`        | ~3500   | Agent types (planner/executor/verifier), LLM, handoff, consensus|
| `app/mcp/`           | ~2000   | MCP client manager, message bus, protocol, 8 server modules   |
| `app/tools/`         | ~2500   | Tool registry, grounding, permissions, sandbox, 5 built-in    |
| `app/api/`           | ~4000   | 17 route modules, schemas, WebSocket, dependency injection   |
| `app/memory/`        | ~3500   | 30+ ORM models, 15 repositories, 7 memory managers, Redis    |
| `app/auth/`          | ~300    | JWT utils, RBAC, API key management                          |
| `app/middleware/`     | ~250    | Auth, rate limiting, request logging, input validation       |
| `app/guardrails/`    | ~100    | Input/output validation schemas                              |
| `app/capabilities/`  | ~400    | Environment selection, feasibility, verification             |
| `app/workflows/`     | ~200    | Task decomposition (LLM + deterministic)                     |
| `app/action_v1/`     | ~300    | Legacy v1 action framework (executor, selector, verifier)    |
| `app/langgraph/`     | ~500    | Graph definitions, state, checkpointer, collaboration nodes  |
| `app/logs/`          | ~800    | Logger, metrics, tracing, anomaly detection, alerts, profiler|
| `app/observability/` | ~100    | Event bus for observability data                             |
| `app/queue/`         | ~50     | Celery task definitions                                      |
| `app/migrations/`    | ~120    | SQL migration runner                                         |

#### 2.1.1 Bootstrap Sequence

The `bootstrap()` function in `app/bootstrap.py` defines the canonical 5-phase initialization:

```
Phase 1: Dependency Validation
  ├── Check DATABASE_URL, REDIS_URL, OPENAI_API_KEY are set
  └── Skip Redis check in gRPC mode

Phase 2: Persistence Layer
  ├── Connect to PostgreSQL (asyncpg via SQLAlchemy)
  ├── Run pending SQL migrations
  ├── Connect to Redis (short-term memory + PubSub)
  └── Register database/Redis shutdown hooks

Phase 3: Core Runtime
  ├── Create AgentRuntime singleton
  ├── Register core agents (core_planner, core_executor, core_verifier)
  ├── Acquire Redis mutex for cross-process coordination
  └── Load additional agents from DB

Phase 4: MCP & Tool Systems
  ├── Start MCP health monitor (periodic health checks every 60s)
  ├── Register built-in tools (search, calculator, text processor)
  ├── Start MCP system servers (filesystem, shell, cloud_api, etc.)
  ├── Discover MCP tools from all servers
  └── Register desktop session cleanup hooks

Phase 5: gRPC Client (gRPC mode only)
  ├── Configure gRPC client (host, port, TLS, keepalive)
  ├── Connect to Go Supervisor's runtime/checkpoint services
  └── Register gRPC shutdown hook
```

Each phase has individually configurable skip flags (`skip_database`, `skip_redis`, `skip_runtime`, `skip_mcp`, `skip_grpc`) to support different deployment topologies.

#### 2.1.2 Runtime (`app/runtime/`)

The `AgentRuntime` is a singleton that serves as the sole execution entry point. No module may instantiate agents directly.

```
AgentRuntime (singleton)
  ├── AgentFactory → creates BaseAgent instances from config
  ├── DynamicAgentFactory → versioned agent creation with health checks
  ├── AgentPool → in-process concurrency semaphore (max 100)
  ├── WorkerPoolManager → Redis-backed cross-process pool
  ├── AgentLifecycleManager → FSM (CREATED→REGISTERED→ACTIVE→EXECUTING→IDLE→DECOMMISSIONED)
  ├── HorizontalScalingCoordinator → Redis-backed cluster coordination
  ├── ResourceLimitEnforcer → concurrent agents, connections, memory
  ├── GRPCServer → wraps RuntimeService + CheckpointService + WorkerService
  └── WorkerExecutorServer → standalone gRPC server for Go→Python bridge
```

**AgentWorker** wraps an agent config + instance with an async inbox queue. Workers are registered via `runtime.register(agent_id, config)` which acquires a pool slot, creates the agent via factory, and starts the worker's inbox loop.

**DynamicAgentFactory** extends the factory with versioned agent creation (Build Plan Task 3.2.4), supporting `create_from_config()`, `create_batch()`, and `health_check_agent()`.

### 2.2 Go Supervisor (`supervisor/`)

The Supervisor is the **local-native control plane** written in Go 1.23. It runs on port 8080 and manages child processes (Python Uvicorn, gRPC servers, MCP servers).

#### Key Structures

| Struct              | Role                                               |
|---------------------|----------------------------------------------------|
| `Supervisor`        | Central orchestrator — holds all component refs    |
| `Config`            | Host, Port, LogLevel, DataDir, Python configs      |
| `DB`                | SQLite wrapper with migration support              |
| `RuntimeServer`     | gRPC RuntimeService implementation (in-memory + SQLite) |
| `CheckpointServer`  | gRPC CheckpointService (TLS + API key auth)        |
| `AgentSessionStore` | SQLite-backed CRUD for agent sessions/actions      |
| `EventHub`          | WebSocket event broadcaster (gorilla/websocket)    |
| `CryptoManager`     | Self-signed CA/server/client TLS (RSA 4096)        |
| `Updater`           | Auto-update checker with SHA-256 verification      |

#### HTTP Routes

| Method | Path                          | Handler                     |
|--------|-------------------------------|-----------------------------|
| GET    | /health                       | Health check                |
| GET    | /status                       | Supervisor state + metrics  |
| POST   | /api/v1/tasks                 | Create task                 |
| GET    | /api/v1/tasks                 | List tasks                  |
| GET    | /api/v1/tasks/{id}            | Get task                    |
| POST   | /api/v1/tasks/{id}/cancel     | Cancel task                 |
| GET    | /api/v1/agents                | List agent sessions         |
| POST   | /api/v1/agents                | Create agent session        |
| GET    | /api/v1/agents/{id}           | Get agent session           |
| GET    | /api/v1/desktop/screenshot    | Proxy → Python desktop API  |
| POST   | /api/v1/desktop/click         | Desktop click               |
| POST   | /api/v1/desktop/type          | Type text                   |
| POST   | /api/v1/desktop/focus         | Focus window                |
| GET    | /api/v1/desktop/windows       | List windows                |
| GET    | /api/v1/agent-configs         | List agent configs          |
| POST   | /api/v1/agent-configs         | Create agent config         |
| GET    | /api/v1/tools                 | List tool definitions       |
| POST   | /api/v1/tools                 | Create tool definition      |
| GET    | /api/v1/update/check          | Check for updates           |
| GET    | /api/v1/events                | WebSocket event stream      |
| POST   | /api/v1/python/start          | Start Python backend        |
| POST   | /api/v1/python/stop           | Stop Python backend         |
| POST   | /api/v1/grpc/start            | Start gRPC desktop server   |
| POST   | /api/v1/grpc/stop             | Stop gRPC desktop server    |

#### Managed Processes

```
Go Supervisor (:8080)
  ├── Python FastAPI (uvicorn app.main, :8000)
  ├── Python gRPC Desktop Server (app.desktop.grpc_server, :50051)
  ├── Checkpoint gRPC Server (in-process, :50052, TLS + API key)
  ├── Python Executor (app.workers.executor_server, optional)
  └── MCP Servers (ports 8001–8007, external)
```

#### SQLite Schema (6 tables)

```sql
-- Agent execution sessions
CREATE TABLE agent_sessions (
    id TEXT PRIMARY KEY, agent_id TEXT, status TEXT,
    input TEXT, output TEXT, error_message TEXT,
    started_at TEXT, completed_at TEXT, created_at TEXT, updated_at TEXT
);

-- Individual actions/steps within sessions
CREATE TABLE actions (
    id TEXT PRIMARY KEY, session_id TEXT, sequence INTEGER,
    action_type TEXT, target TEXT, arguments TEXT,
    status TEXT, result TEXT, error_message TEXT,
    created_at TEXT, FOREIGN KEY (session_id) REFERENCES agent_sessions(id)
);

-- Key-value store for system state
CREATE TABLE system_state (
    key TEXT PRIMARY KEY, value TEXT
);

-- Agent configuration definitions
CREATE TABLE agent_configs (
    id TEXT PRIMARY KEY, name TEXT, description TEXT, role TEXT,
    system_prompt TEXT, model TEXT, temperature REAL, max_tokens INTEGER,
    status TEXT, created_at TEXT, updated_at TEXT
);

-- Tool definition catalog
CREATE TABLE tool_definitions (
    id TEXT PRIMARY KEY, name TEXT UNIQUE, description TEXT,
    category TEXT, type TEXT, parameters_schema TEXT, status TEXT,
    created_at TEXT, updated_at TEXT
);

-- LangGraph checkpoint persistence
CREATE TABLE checkpoints (
    thread_id TEXT, checkpoint_ns TEXT DEFAULT 'default',
    checkpoint_id TEXT, state_blob BLOB, metadata TEXT,
    created_at TEXT, PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
);
```

### 2.3 Rust CLI (`cli/`)

The CLI binary (`agentos`) provides terminal-based interaction with the Supervisor.

#### Commands

| Command | Subcommand | Description |
|---------|-----------|-------------|
| `task`  | `create <query>` | Create and execute a task |
| `task`  | `list` | List all tasks |
| `task`  | `get <id>` | Get task details |
| `task`  | `cancel <id>` | Cancel a running task |
| `task`  | `logs <id>` | Show task logs |
| `daemon`| `start` | Start the supervisor daemon |
| `daemon`| `stop` | Stop the daemon |
| `daemon`| `status` | Show daemon status |
| `daemon`| `logs` | Show daemon logs |
| `daemon`| `restart` | Restart the daemon |
| `desktop`| `screenshot [path]` | Take a screenshot |
| `desktop`| `click <x> <y>` | Click at coordinates |
| `desktop`| `type <text>` | Type text |
| `desktop`| `focus <title>` | Focus a window |
| `desktop`| `list-windows` | List open windows |
| `desktop`| `find <text>` | Find text via OCR |
| `config`| `set <key> <value>` | Set config value |
| `config`| `get <key>` | Get config value |
| `config`| `list` | List all config |
| `config`| `init` | Initialize default config |
| `config`| `path` | Show config file path |

#### Architecture

```
cli/src/
├── main.rs          # CLI entry point (clap parser)
├── config.rs        # TOML config management
├── models.rs        # Data models (Task, DaemonStatus, etc.)
├── ipc.rs           # ApiClient (HTTP to Supervisor)
└── commands/
    ├── mod.rs
    ├── daemon.rs    # Daemon lifecycle
    ├── task.rs      # Task CRUD
    ├── desktop.rs   # Desktop automation
    └── config.rs    # Config management
```

### 2.4 Rust TUI (`tui/`)

The TUI binary (`agentos-tui`) provides a real-time terminal dashboard using ratatui.

#### Features

- **Dashboard**: Connection status, active/total/failed task counts, recent tasks table
- **Task List**: Scrollable table with status icons, IDs, queries, step counts, timestamps
- **Log Panel**: Bounded buffering (VecDeque), auto-scroll, text filtering, scroll percentage
- **Task Detail**: Overlay panel with full task info, steps with status icons, result/error
- **Status Bar**: Connection health, daemon version/uptime, memory usage, key hints
- **Keyboard Navigation**: Arrow keys, Page Up/Down, Home/End, filters
- **WebSocket Integration**: Real-time updates via Supervisor event stream

#### Theme System

16-color theme defined in `styles.rs` mapping task states (pending/running/completed/failed/cancelled) to styled ratatui colors and log levels (debug/info/warn/error) to distinct visual styles.

### 2.5 Rust Desktop Automation (`desktop/`)

A native Windows desktop automation service using Win32 API via the `windows` crate, exposed via gRPC.

#### Desktop Protocol (desktop.proto)

**Service:** `DesktopAutomation` with 10 RPCs:

| RPC | Request | Response | Description |
|-----|---------|----------|-------------|
| ScreenCapture | — | PNG bytes | Full-screen GDI BitBlt capture |
| OcrScreen | — | Text lines | OCR via Python pytesseract backend |
| FindWindow | Title pattern | WindowInfo | EnumWindows with title matching |
| Click | X, Y | Status | SetCursorPos + SendInput mouse down/up |
| Type | Text | Status | SendInput KEYEVENTF_UNICODE per character |
| Observe | — | WindowInfo[] | Enumerate all visible windows |
| Decide | Observation | Action | Placeholder: returns noop |
| Act | Action | Status | Dispatches click/type actions |
| Verify | Expected, Actual | Match | Simple equality comparison |
| Recover | Failure info | Strategy | Returns strategy based on failure type |
| CloseSession | Session ID | Status | Cleanup session state |

#### Key Modules

| Module | Lines | Description |
|--------|-------|-------------|
| `capture/` | 404 | GDI BitBlt screen capture (full-screen + region) |
| `server/` | 401 | gRPC service implementation with session management |
| `server/window_service.rs` | 309 | Win32 window enumeration, click, SendInput |
| `server/ocr_service.rs` | 208 | Delegates OCR to Python gRPC server (pytesseract) |
| `server/session.rs` | 151 | Session manager with 5-minute activity timeout |
| `automation/window.rs` | 267 | HWND-based window automation API |
| `bridge/grpc_client.rs` | 493 | gRPC client with exponential backoff retry |
| `ocr/windows.rs` | 88 | Native Windows OCR stub (future WinRT) |

### 2.6 Tauri GUI (`gui/`)

A cross-platform desktop GUI built with React 18 + TypeScript, packaged with Tauri 1.5.

#### React Frontend (`gui/src/`)

| File | Lines | Purpose |
|------|-------|---------|
| `main.tsx` | 13 | React DOM entry with HashRouter |
| `App.tsx` | 68 | Root component with page routing (Dashboard/Agents/Tools/Chat/Settings) |
| `api/supervisor.ts` | 216 | HTTP REST client for Supervisor API |
| `api/events.ts` | 92 | WebSocket event bridge client |
| `context/AppContext.tsx` | 100 | Global state (tasks, selected, counts) |
| `pages/Dashboard.tsx` | 261 | Task creation, list, safety approvals |
| `pages/Chat.tsx` | 182 | Conversational chat UI |
| `pages/AgentBuilder.tsx` | 263 | Agent config management |
| `pages/Tools.tsx` | 209 | Tool registry browser with category filtering |
| `pages/Settings.tsx` | 342 | Daemon, API keys, notifications, shortcuts, about |
| `components/Layout.tsx` | 111 | Sidebar navigation shell |
| `components/SafetyDialog.tsx` | 97 | Desktop automation approval modal |

#### Tauri Backend (`gui/src-tauri/`)

| Module | Lines | Description |
|--------|-------|-------------|
| `main.rs` | 79 | Single-instance plugin, system tray, global shortcuts, event bridge |
| `events.rs` | 87 | WebSocket → Tauri event bridge (exponential backoff reconnect) |
| `config.rs` | 80 | TOML config persistence |
| `shortcuts.rs` | 47 | Global hotkeys (Ctrl+Shift+A/S/Q) |
| `tray.rs` | 55 | System tray (Show/Hide/Quit + left-click toggle) |
| `commands/keychain.rs` | 94 | OS keychain (keyring crate) for API keys |
| `commands/config.rs` | 45 | Config get/set IPC |
| `commands/daemon.rs` | 31 | Daemon status/start/stop (stubs) |
| `commands/notifications.rs` | 11 | Native OS notifications |

---

## 3. Core Subsystems

### 3.1 Bootstrap & Runtime Initialization

The `BootstrapContext` object is the canonical container for runtime state. It flows through all bootstrap phases and holds:

```python
class BootstrapContext:
    runtime: Optional[AgentRuntime]    # Core execution engine
    grpc_client: Optional[GRPCClient]  # Supervisor connection (gRPC mode)
    initialized: List[str]             # Component tracking
    _shutdown_hooks: List[Callable]    # LIFO cleanup hooks
    _is_shutting_down: bool            # Guard against double-shutdown
```

The lifespan is available both as FastAPI's `lifespan` handler (for HTTP mode) and as an async context manager `bootstrap_lifespan()` (for gRPC/CLI mode).

### 3.2 Agent System

The agent system (`app/agents/`) defines a protocol-based architecture where all agents implement `BaseAgent` and communicate via structured `AgentInput`/`AgentOutput` messages.

#### Core Agent Types

| Agent | Module | Purpose | Key Method |
|-------|--------|---------|------------|
| `PlannerAgent` | `planner.py` | Decomposes tasks into DAG execution plans | `execute()` → step list |
| `ExecutorAgent` | `executor.py` | Executes plan steps by invoking tools | `execute()` → tool results |
| `VerifierAgent` | `verifier.py` | Validates executor/planner output via LLM | `execute()` → valid/invalid |
| `ReviewerAgent` | `reviewer.py` | Schema-based output validation (no LLM) | `review()` → quality score |
| `CoordinatorAgent` | `coordinator.py` | Fan-out/fan-in multi-agent workflow | `coordinate()` → aggregated results |

#### Planner Decomposition Pipeline

```
User Query
  │
  ├── WorkflowDecomposer.decompose()  # Deterministic intent matching
  │   └── Returns step list if matched
  │
  └── LLM Planner (fallback)
      ├── Generates JSON plan: [{id, step, step_type, allowed_tools, depends_on, ...}]
      ├── ToolGroundingLayer.classify_intent() per step
      ├── _normalize_plan_response() → validates deps, removes phantom refs
      ├── ToolGroundingLayer.get_allowed_tools() per step
      ├── _normalize_paths_in_text() → OS-aware path remapping
      └── Returns normalized execution plan
```

#### Executor Tool Invocation Flow

```
ExecutorAgent.execute()
  │
  ├── For each step (up to MAX_TOOL_ROUNDS=5):
  │   ├── LLM produces tool call JSON
  │   ├── ToolCallParser.parse() → {name, params}
  │   ├── ToolPermissions.check_permission()
  │   ├── ToolInputValidator.validate() (schema + type + safety + permissions)
  │   ├── ToolRegistry.execute() → ToolOutput
  │   │   ├── SafetyGate.check_tool_call() → severity classification
  │   │   ├── IP check & block (for cloud_api tools)
  │   │   ├── Credential protection (desktop params)
  │   │   ├── Tool timeout enforcement
  │   │   └── Observability event emission
  │   └── Result fed back to LLM
  │
  └── For desktop tasks:
      └── DesktopGoalLoop → ActionStabilizer → WindowRegistry → desktop tools
```

#### Inter-Agent Communication

AgentOS supports 5 communication patterns:

1. **Structured Handoff** (`handoff.py`): `HandoffMessage` with SHA-256 signed state snapshots delivered to agent inbox queues. Reasons: `task_delegation`, `escalation`, `review`.

2. **MCP Message Bus** (`mcp/bus.py`): Pub/sub channels named `agent:<name>`. `MemoryMCPBus` for dev, `RedisMCPBus` for production. All messages persisted to PostgreSQL.

3. **Direct Execution** (`base.py`): `CoordinatorAgent` calls `worker.execute()` on resolved agents via `AgentRuntime`.

4. **Consensus** (`consensus.py`): 5 strategies for multi-agent agreement — MAJORITY_VOTE, WEIGHTED_CONFIDENCE, FIRST_TO_RESPOND, UNANIMOUS, LLM_MEDIATED.

5. **Feedback Loop** (`feedback.py`): Past execution results inform future routing via `AgentFeedbackLoop` → `LearningContext` with tool recommendations.

#### LLM Router

The `LLMRouter` (`llm_router.py`) supports multi-provider LLM access with failover:

```
LLMRouter.route(ModelRequest)
  ├── Cache lookup (SHA-256 key, TTL-based)
  ├── Provider resolution: OpenAI → Anthropic → Google → Local (Ollama/vLLM)
  ├── Rate-limit awareness with cost optimization
  ├── Fallback chain: same-provider → other providers by priority
  ├── Response caching with hit/miss stats
  └── Cost tracking via MODEL_COSTS table
```

### 3.3 Orchestrator

The orchestrator (`app/orchestrator/`) is the central execution hub. Its `execute_task()` method defines the canonical execution path:

```python
async def execute_task(query, config, task_id, user_id) -> AgentOutput:
    # 1. Input guardrails validation
    guardrails.validate_input(query)
    
    # 2. Try LangGraph execution (primary path)
    try:
        return await TaskRunner.run(query, config, task_id, user_id, ...)
    except LangGraphError:
        pass  # Fall through to recovery
    
    # 3. Checkpoint recovery (if LangGraph failed)
    try:
        return await CheckpointRecoveryService.recover(task_id)
    except RecoveryError:
        pass  # Fall through to legacy modes
    
    # 4. Legacy mode fallback
    strategy = ModeStrategyFactory.get(mode)  # task | workflow | autonomous | collaboration
    return await strategy.execute(runtime, self, query, config, task_id, user_id)
```

#### Orchestrator Subcomponents

| Module | Lines | Key Class | Role |
|--------|-------|-----------|------|
| `core.py` | 318 | `Orchestrator` | Central hub, fallback chain |
| `task_runner.py` | 561 | `TaskRunner` | LangGraph execution path |
| `pipeline.py` | 342 | `PipelineExecutor` | Legacy plan→execute→verify |
| `workflow.py` | 358 | `WorkflowEngine` | DAG-based workflow execution |
| `builder.py` | 152 | `WorkflowBuilder` | Workflow DAG persistence |
| `executor.py` | 143 | `StepExecutor` | Single step execution |
| `adaptive_routing.py` | 728 | `TaskComplexityRouter` | Tier 0/1/2 fast path |
| `router.py` | 52 | `AgentRouter` | Role-based agent resolution |
| `retry.py` | 87 | — | Exponential backoff |
| `errors.py` | 111 | `AgentOSError` | 25+ error codes, 5 error types |
| `event_bus.py` | 71 | `RedisEventBus` | Redis PubSub events |
| `queue.py` | 504 | `TaskQueue` | Redis priority queue |
| `locks.py` | 269 | `ExecutionLock` | Distributed execution lock |
| `state_machine.py` | 382 | `TaskStateMachine` | Task FSM (8 states) |
| `idempotency.py` | 320 | `IdempotencyEnforcement` | SHA-256 dedup |
| `timeouts.py` | 408 | `TimeoutEnforcer` | Agent/tool/workflow/step timeouts |
| `isolation.py` | 363 | `FailureIsolator` | Circuit breaker (3 failures) |
| `loop_detector.py` | 308 | `InfiniteLoopDetector` | SHA-256 fingerprint loop detection |
| `modes/` | 394 | 4 ModeStrategy classes | Task, Workflow, Autonomous, Collaboration |

### 3.4 Model Context Protocol (MCP)

AgentOS implements the Model Context Protocol for standardized tool exposure to LLMs. The MCP subsystem (`app/mcp/`) provides:

#### MCP Message Format

```python
class MCPMessage:
    message_id: UUID
    task_id: str
    step_id: str
    sender_agent: str
    receiver_agent: str
    timestamp: datetime
    payload: Payload        # input_data, output_data, context_snapshot
    metadata: Metadata      # status, priority, retry_count, execution_time
```

#### MCP Server Architecture

Each MCP server is a standalone Python process using `FastMCP` communicating via stdio JSON-RPC:

```
Agent/Tool → ToolRegistry.execute()
  └── MCPWrappedTool.call_tool()
      └── MCPClientManager.call_tool(server_name, tool_name, args)
          └── ClientSession.call_tool() over stdio
              └── MCP Server Process (FastMCP, transport=stdio)
```

**System MCP Servers** (all under `app/mcp/servers/`):

| Server | Tools | Key Features |
|--------|-------|--------------|
| `filesystem.py` | read_file, write_file, list_directory, search_files | Path sandboxing (cwd, home, Desktop, Documents, Downloads), cross-platform path normalization |
| `shell.py` | execute_command, run_script, get_process_status | Dangerous command blocking (rm, del, format, dd, etc.), interpreter support, timeout |
| `cloud_api.py` | http_request, scrape_page, search_web | DuckDuckGo search, BeautifulSoup scraping, User-Agent rotation |
| `desktop.py` | 12 tools (screenshot, click, type, press_key, window management, UI tree) | Accessibility-tree element interaction, task-scoped sessions |
| `browser.py` | 10 tools (launch, navigate, click, type, screenshot, etc.) | Playwright-based, task-scoped browser sessions |
| `document.py` | parse, parse_pdf, parse_docx, parse_txt, parse_markdown, chunk, summarize | Multi-format support, LLM summarization, chunking with overlap |
| `code.py` | run_python | ToolSandbox restricted execution, AST-level import blocking |
| `_stdio_sanitize.py` | — | Critical: patches print/logging to stderr to protect JSON-RPC transport |

### 3.5 Tool System

The tool system (`app/tools/`) provides the execution substrate for all agent actions.

#### Tool Registry Architecture

```
ToolRegistry (singleton)
  ├── Built-in tools: SearchTool, CalculatorTool, TextProcessorTool
  ├── MCP Wrapped Tools: filesystem__read_file, shell__execute_command, etc.
  ├── Desktop Environment Tools: desktop_env__screenshot, desktop_env__click, etc.
  │
  ├── ToolGroundingLayer → intent-to-tool mapping (keyword-based)
  ├── ToolPermissions → RBAC per tool/agent/role
  ├── ToolInputValidator → schema + type + safety + permissions validation
  ├── ToolCallParser → LLM JSON → {name, params} extraction
  ├── ToolSandbox → restricted Python execution (AST-validated)
  ├── CacheOptimizer → SHA-256 keyed result caching (memory + Redis)
  ├── ToolCostTracker → per-invocation cost estimation
  ├── ToolFailureClassifier → 5 failure types, fallback mappings
  └── FastFileDiscovery → tiered file search engine
```

#### Tool Execution Flow

```
ToolRegistry.execute(tool_name, params)
  │
  ├── 1. ToolInputValidator.validate() → schema check + type check
  ├── 2. SafetyGate.check_tool_call() → severity (SAFE/WARNING/IRREVERSIBLE)
  ├── 3. ToolPermissions.check_permission() → RBAC check
  ├── 4. Credential sanitization (desktop tool params)
  ├── 5. TimeoutEnforcer.enforce_tool() → asyncio.wait_for()
  ├── 6. Tool execution:
  │   ├── Built-in: execute directly
  │   ├── MCP: MCPClientManager.call_tool()
  │   └── Desktop: DesktopEnvTool.execute()
  ├── 7. ToolCostTracker.record()
  ├── 8. ObservabilityBus.emit() → event
  └── 9. Return ToolOutput(success, result, error, metadata)
```

#### Built-in Tools (`app/tools/builtin/`)

| Tool | Module | Description |
|------|--------|-------------|
| GitHubSearchReposTool | `github.py` | GitHub API repository search |
| GitHubGetRepoTool | `github.py` | GitHub API repository details |
| SlackSendMessageTool | `slack.py` | Mock Slack message sending |
| NotionSearchPagesTool | `notion.py` | Mock Notion search |
| WebScraperExtractTextTool | `web_scraper.py` | BeautifulSoup text extraction |
| CodeExecutorRunPythonTool | `code_executor.py` | Legacy sandboxed Python |

### 3.6 Memory & Persistence

AgentOS uses a multi-tier persistence architecture:

```
┌─────────────────────────────────────────────────────────────┐
│                        Application Layer                      │
│  TaskMemory │ SessionMemory │ WorkflowMemory │ UserMemory      │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│                     Consistency Layer                         │
│  3 levels: EVENTUAL | STRONG | READ_THROUGH                  │
│  Timestamp-based conflict resolution                         │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────┴───────────────────────────────┐
│                    Data Stores                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  PostgreSQL  │  │    Redis     │  │  SQLite (WAL)│  │
│  │  (durable)   │  │  (cache/TTL) │  │  (local)     │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────┘
```

#### ORM Models (`app/memory/models.py` — 30+ tables)

| Model | Table | Key Columns |
|-------|-------|-------------|
| TaskModel | tasks | id, user_id, query, status, result, error, created_at, updated_at |
| StepModel | steps | id, task_id, step_number, agent_type, status, depends_on, confidence |
| WorkflowModel | workflows | id, task_id, user_id, name, definition, status |
| WorkflowNodeModel | workflow_nodes | id, workflow_id, step_number, agent_type, status, depends_on, condition_code, node_type, approval_config |
| WorkflowEdgeModel | workflow_edges | id, workflow_id, from_node_id, to_node_id |
| UserModel | users | id, email, name, role, hashed_password, api_key, is_active |
| TraceModel | traces | id, task_id, status, duration_ms |
| TokenUsageModel | token_usage | id, model, prompt_tokens, completion_tokens, cost |
| ToolModel | tools | id, name, description, type, status, invocation_count |
| AgentModel | agents | id, name, role, system_prompt, model, temperature, version |
| CheckpointModel | checkpoints | thread_id, checkpoint_ns, checkpoint_id, state_blob, metadata |
| AuditModel | audits | id, action, entity_type, entity_id, user_id, changes, timestamp |
| ConfigModel | configs | key, value |
| DeploymentModel | deployments | id, user_id, workflow_id, endpoint_path, api_key, status |
| APIKeyModel | api_keys | id, user_id, key_hash, name, last_used_at |
| KnowledgeSourceModel | knowledge_sources | id, user_id, name, type, content_hash |
| KnowledgeChunkModel | knowledge_chunks | id, source_id, chunk_index, content, embedding |

#### Repository Classes (15 singletons)

All repositories live in `app/memory/long_term.py` as singletons:

```python
task_repo = TaskRepository()
user_repo = UserRepository()
workflow_repo = WorkflowRepository()
workflow_node_repo = WorkflowNodeRepository()
workflow_edge_repo = WorkflowEdgeRepository()
trace_repo = TraceRepository()
node_trace_repo = NodeTraceRepository()
span_repo = SpanRepository()
tool_repo = ToolRepository()
mcp_server_repo = MCPServerRepository()
agent_repo = AgentRepository()
message_repo = MessageRepository()
config_repo = ConfigRepository()
deployment_repo = DeploymentRepository()
guardrail_rule_repo = GuardrailRuleRepository()
token_usage_repo = TokenUsageRepository()
```

#### Memory Managers (7 singletons)

| Manager | Module | Backend | TTL |
|---------|--------|---------|-----|
| `short_term_memory` | `short_term.py` | Redis | configurable |
| `session_memory` | `session_memory.py` | Redis | 2 hours |
| `task_memory` | `task_memory.py` | Redis | 1 hour |
| `user_memory` | `user_memory.py` | Redis + PostgreSQL | cache-through |
| `workflow_memory` | `workflow_memory.py` | PostgreSQL | — |
| `persistent_memory` | `persistent.py` | Redis + PostgreSQL | TTL + LRU |
| `artifact_store` | `artifact_store.py` | Filesystem + PostgreSQL + Redis | — |

### 3.7 Task Queue & State Machine

#### Task State Machine

```
                    ┌──────────┐
                    │  PENDING │
                    └────┬─────┘
                         │
                    ┌────▼─────┐
                    │ PLANNING │
                    └────┬─────┘
                         │
                    ┌────▼──────┐
              ┌─────│ EXECUTING │─────┐
              │     └────┬──────┘     │
              │          │            │
         ┌────▼────┐ ┌──▼────────┐   │
         │  FAILED │ │ VERIFYING │   │
         └─────────┘ └──┬────────┘   │
                         │            │
              ┌──────────┼──────────┐ │
         ┌────▼────┐ ┌──▼─────┐ ┌──▼──────┐
         │COMPLETED│ │AWAITING│ │EXECUTING│ (retry)
         └─────────┘ │APPROVAL│ └─────────┘
                     └──┬─────┘
                   ┌────┴────┐
              ┌────▼──┐ ┌───▼────┐
              │REJECTED│ │COMPLETED│
              └────────┘ └────────┘
```

The `TaskStateMachine` enforces valid transitions with hierarchical persistence: in-memory → Redis cache → PostgreSQL durable.

#### Priority Task Queue

The `TaskQueue` uses Redis sorted sets (score = priority × 10¹² + timestamp):

| Priority | Value | Use Case |
|----------|-------|----------|
| CRITICAL | 0 | System tasks, error recovery |
| HIGH | 1 | User-facing interactive tasks |
| NORMAL | 2 | Default task priority |
| LOW | 3 | Background processing |

Key operations: `enqueue()` → ZADD + HSET, `dequeue()` → ZPOPMIN + HGETALL (atomic), `complete()` → ZREM + HDEL.

### 3.8 Execution Modes

Four execution mode strategies are available:

#### TaskMode
Standard plan → execute → verify pipeline. Used as default for most tasks.

#### WorkflowMode
Loads a predefined DAG workflow from the database. Falls back to TaskMode if no predefined workflow exists.

#### AutonomousMode
Self-directed agent loop:
```
for step in range(max_steps):
    plan_single_step() → Runtime
    execute_step() → result
    if is_task_complete(): break
verify_result() → Runtime
```

#### CollaborationMode
Multi-agent coordinated execution:
```
planner → assigns steps to registered agents
for each step:
    resolve_agent(step.agent_type) → AgentWorker
    execute_via_mcp(worker, step) → result
```

### 3.9 Capability System

The capability system (`app/capabilities/`) classifies tasks into execution environments.

#### Capability Classification (`environment_selector.py`)

```python
class CapabilityRouter:
    def classify(query) -> Capability:
        # Keyword-based detection
        capabilities = {
            "RESEARCH": ["search", "research", "find", "look up", "google"],
            "COMMUNICATION": ["email", "slack", "message", "send"],
            "DATA_PROCESSING": ["analyze", "calculate", "process data"],
            "FILE": ["read", "write", "create file", "save"],
            "CODE": ["code", "write code", "python", "script"],
            "WEB": ["browser", "navigate", "go to", "open website"],
            "SHELL": ["terminal", "command", "run", "execute"],
            "DESKTOP": ["click", "type", "press", "screenshot"],
        }
    
    def select_environment(capability) -> ExecutionEnvironment:
        # Maps capabilities to environments
        # DESKTOP → DesktopGoalLoop
        # BROWSER → BrowserSession
        # SHELL → ShellExecution
        # etc.
```

#### Feasibility Analysis

The `FeasibilityAnalyzer` checks whether a task can be executed by available tools and environments. Returns BLOCKED, UNSUPPORTED, or FEASIBLE with reasoning.

#### Verification Engine

The `VerificationEngine` validates task output against expected outcomes using configurable strategies (LLM-based, schema-based, regex-based).

### 3.10 Action v1 Framework

The legacy v1 framework (`app/action_v1/`) provides deterministic execution for well-known task types:

| Component | Module | Role |
|-----------|--------|------|
| `ActionV1Runner` | `runner.py` | Fast-path execution of v1 actions |
| `CapabilitySelector` | `selector.py` | Matches queries to v1 capability templates |
| `DeterministicExecutor` | `executor.py` | Executes known action sequences |
| `ActionVerifier` | `verifier.py` | Verifies action outcomes |
| `FallbackHandler` | `fallback.py` | Falls back to LangGraph on v1 failure |

Supported actions: open notepad, write text, open calculator, create spreadsheet, search web, launch browser, create HTML file, etc.

### 3.11 Workflow Engine

The `WorkflowEngine` (`orchestrator/workflow.py`) provides DAG-based workflow execution:

```python
class WorkflowNode:
    id: str               # Unique node identifier
    step: str             # Step description
    agent_type: str       # planner | executor | verifier | custom
    depends_on: List[str] # Node IDs this node depends on
    condition: str        # AST-safe condition expression
    step_number: int      # Execution order
    node_type: str        # task | wait | approval
    approval_config: dict # Human approval configuration

# Predefined workflow templates:
WORKFLOW_TEMPLATES = {
    "sequential_review": [planner, executor, verifier],
    "parallel_research": [planner, executor_1||executor_2, verifier],
    "error_recovery": [planner, executor, verifier, recovery_planner, executor_2, verifier_2],
}
```

Key features:
- **Cycle detection**: DFS-based validation before execution
- **Safe conditions**: Python AST evaluation (only `context.get()`, comparisons, boolean operators; no lambdas)
- **Parallel execution**: Nodes without dependencies execute concurrently
- **Approval nodes**: Pause execution for human-in-the-loop approval
- **Persistence**: Full DAG (nodes + edges) persisted to PostgreSQL

### 3.12 Guardrails & Safety

#### Input Guardrails

The `InputValidator` (`middleware/validation.py`) intercepts task creation POST requests:

- Blocked keyword patterns (configurable)
- Maximum query length enforcement
- SQL injection pattern detection
- Path traversal detection

#### Safety Gate

The `SafetyGate` (`tools/safety/`) classifies every tool call:

```python
# Severity levels:
#   IRREVERSIBLE — blocks execution without explicit approval
#   WARNING     — requires human confirmation
#   SAFE        — allows execution

# Examples:
#   delete_file(file) → IRREVERSIBLE
#   execute_command("rm -rf /") → WARNING (if dangerous command detected)
#   read_file(path) → SAFE
```

Credential protection scans desktop tool parameters for API keys, tokens, and passwords, blocking them before execution.

#### RBAC Tool Permissions

| Role | File Read | File Write | Shell | Web | Desktop |
|------|-----------|------------|-------|-----|---------|
| admin | ✓ | ✓ | ✓ | ✓ | ✓ |
| planner | ✓ | ✓ | — | ✓ | — |
| executor | ✓ | ✓ | ✓ | ✓ | ✓ |
| verifier | ✓ | ✓ | — | ✓ | — |
| reviewer | ✓ | — | — | ✓ | — |
| coordinator | ✓ | ✓ | ✓ | ✓ | ✓ |
| (default) | — | — | — | — | — |

---

## 4. API Reference

### 4.1 FastAPI HTTP Endpoints

All endpoints under `/api/v1/` (except auth and desktop) require JWT Bearer token or API key authentication.

#### Authentication

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| POST | /api/v1/auth/signup | Register new user | None |
| POST | /api/v1/auth/login | Login, get tokens | None |
| POST | /api/v1/auth/refresh | Refresh access token | Refresh token |

#### Tasks

| Method | Path | Description |
|--------|------|-------------|
| POST | /api/v1/tasks | Create and execute a task |
| GET | /api/v1/tasks/{id} | Get task status with workflow state |
| GET | /api/v1/tasks | List tasks (paginated, user-scoped) |
| DELETE | /api/v1/tasks/{id} | Cancel a task |
| POST | /api/v1/tasks/{id}/approve | Approve waiting task |
| POST | /api/v1/tasks/{id}/reject | Reject waiting task |
| GET | /api/v1/tasks/{id}/trace | Full execution trace with spans |

#### Agents

| Method | Path | Description |
|--------|------|-------------|
| GET | /api/v1/agents | List agent configurations |
| POST | /api/v1/agents | Create agent configuration |
| GET | /api/v1/agents/{id} | Get agent configuration |
| PUT | /api/v1/agents/{id} | Update agent configuration |
| DELETE | /api/v1/agents/{id} | Delete agent configuration |
| GET | /api/v1/agents/{id}/versions | List version history |
| POST | /api/v1/agents/{id}/versions | Create version snapshot |

#### Tools & MCP

| Method | Path | Description |
|--------|------|-------------|
| GET | /api/v1/tools | List all tools (registry + DB) |
| POST | /api/v1/tools | Register custom tool |
| GET | /api/v1/tools/{name} | Get tool details |
| POST | /api/v1/tools/{name}/execute | Execute a tool |
| GET | /api/v1/tools/categories | List tool categories |
| GET | /api/v1/tools/health | Tool health check |
| POST | /api/v1/tools/mcp-servers | Register MCP server |
| GET | /api/v1/tools/mcp-servers | List MCP servers |
| GET | /api/v1/tools/mcp-servers/{name}/tools | Discover MCP server tools |

#### Workflows & Chat

| Method | Path | Description |
|--------|------|-------------|
| GET | /api/v1/workflows | List user workflows |
| POST | /api/v1/workflows | Save workflow definition |
| GET | /api/v1/workflows/templates | List workflow templates |
| POST | /api/v1/chat/sessions | Create chat session |
| GET | /api/v1/chat/sessions | List chat sessions |
| POST | /api/v1/chat/sessions/{id}/messages | Send message |
| GET | /api/v1/chat/sessions/{id}/messages | Get messages |

#### Knowledge & Config

| Method | Path | Description |
|--------|------|-------------|
| POST | /api/v1/knowledge/upload | Upload document for RAG |
| GET | /api/v1/knowledge | List knowledge sources |
| POST | /api/v1/knowledge/{id}/query | Query knowledge source |
| GET | /api/v1/config | Get all config |
| POST | /api/v1/config | Update config value |
| GET | /api/v1/config/{key} | Get config value |

#### Observability & Analytics

| Method | Path | Description |
|--------|------|-------------|
| GET | /api/v1/analytics/dashboard | Aggregated dashboard stats |
| GET | /api/v1/analytics/traces | Paginated trace list |
| GET | /api/v1/analytics/traces/{id} | Detailed trace with spans |
| GET | /api/v1/analytics/metrics | Time-series chart data |
| GET | /api/v1/observability/metrics | JSON metrics summary |
| GET | /api/v1/observability/metrics/prometheus | Prometheus text format |
| GET | /api/v1/observability/costs | Cost breakdown |
| GET | /api/v1/observability/anomalies | Anomaly detection report |
| GET | /api/v1/observability/alerts | Alert history |
| GET | /api/v1/observability/resources | Resource usage & limits |
| GET | /api/v1/observability/cluster | Cluster state |

#### Desktop Automation

| Method | Path | Description |
|--------|------|-------------|
| GET | /api/v1/desktop/screenshot | Capture screenshot |
| POST | /api/v1/desktop/click | Click at coordinates |
| POST | /api/v1/desktop/type | Type text |
| POST | /api/v1/desktop/focus | Focus window by title |
| GET | /api/v1/desktop/windows | List visible windows |
| POST | /api/v1/desktop/find | OCR text search |

#### System & Health

| Method | Path | Description |
|--------|------|-------------|
| GET | /health | Basic health check |
| GET | /health/ready | Readiness probe (DB + Redis) |
| GET | /health/live | Liveness probe |
| GET | /health/metrics | Prometheus-format metrics |
| GET | /metrics | Aggregated metrics JSON |

### 4.2 gRPC Services

#### RuntimeService (runtime.proto)

```protobuf
service RuntimeService {
  rpc CreateTask(CreateTaskRequest) returns (CreateTaskResponse);
  rpc GetTask(GetTaskRequest) returns (GetTaskResponse);
  rpc CancelTask(CancelTaskRequest) returns (CancelTaskResponse);
  rpc ListTasks(ListTasksRequest) returns (ListTasksResponse);
  rpc StreamTaskEvents(TaskEventRequest) returns (stream TaskEvent);
  rpc ApproveTask(ApproveTaskRequest) returns (ApproveTaskResponse);
  rpc RejectTask(RejectTaskRequest) returns (RejectTaskResponse);
  rpc GetRuntimeStatus(GetRuntimeStatusRequest) returns (RuntimeStatus);
  rpc Shutdown(ShutdownRequest) returns (ShutdownResponse);
  rpc HealthCheck(HealthCheckRequest) returns (HealthCheckResponse);
  rpc GetConfig(GetConfigRequest) returns (GetConfigResponse);
  rpc SetConfig(SetConfigRequest) returns (SetConfigResponse);
}
```

**Task Status Enum:**
```
PENDING → PLANNING → EXECUTING → VERIFYING → AWAITING_APPROVAL → COMPLETED
                                                                    FAILED
                                                                    CANCELLED
                                                                    RECOVERING
```

**Task Type Enum:** UNSPECIFIED, SIMPLE, COMPLEX, DESKTOP, AUTONOMOUS

#### CheckpointService (checkpoint.proto)

```protobuf
service CheckpointService {
  rpc SaveCheckpoint(SaveCheckpointRequest) returns (SaveCheckpointResponse);
  rpc GetCheckpoint(GetCheckpointRequest) returns (GetCheckpointResponse);
  rpc ListCheckpoints(ListCheckpointsRequest) returns (ListCheckpointsResponse);
  rpc GetLatestCheckpoint(GetLatestCheckpointRequest) returns (GetCheckpointResponse);
  rpc CleanupCheckpoints(CleanupCheckpointsRequest) returns (CleanupCheckpointsResponse);
  rpc SubscribeCheckpoints(SubscribeCheckpointsRequest) returns (stream CheckpointEvent);
  rpc RunMigrations(RunMigrationsRequest) returns (RunMigrationsResponse);
}
```

#### WorkerExecutor (worker.proto)

```protobuf
service WorkerExecutor {
  rpc ExecuteTask(TaskRequest) returns (TaskResponse);
  rpc HealthCheck(HealthRequest) returns (HealthResponse);
}
```

#### DesktopAutomation (desktop.proto)

```protobuf
service DesktopAutomation {
  rpc ScreenCapture(ScreenCaptureRequest) returns (ScreenCaptureResponse);
  rpc OcrScreen(OcrScreenRequest) returns (OcrScreenResponse);
  rpc FindWindow(FindWindowRequest) returns (FindWindowResponse);
  rpc Click(ClickRequest) returns (ClickResponse);
  rpc Type(TypeRequest) returns (TypeResponse);
  rpc Observe(ObserveRequest) returns (ObserveResponse);
  rpc Decide(DecideRequest) returns (DecideResponse);
  rpc Act(ActRequest) returns (ActResponse);
  rpc Verify(VerifyRequest) returns (VerifyResponse);
  rpc Recover(RecoverRequest) returns (RecoverResponse);
  rpc CloseSession(CloseSessionRequest) returns (CloseSessionResponse);
}
```

### 4.3 WebSocket Protocol

#### Task Events (`/ws/tasks/{task_id}?token=...`)

```typescript
// Server → Client events (every 15s heartbeat):
{
  "type": "task_update" | "step_update" | "heartbeat",
  "task_id": "uuid",
  "status": "running" | "completed" | "failed",
  "payload": { ... }
}
```

#### Supervisor Events (`ws://host:8080/api/v1/events`)

```typescript
interface SupervisorEvent {
  type: "task_created" | "task_updated" | "task_completed" | "task_failed"
      | "task_cancelled" | "task_awaiting_approval" | "step_updated";
  timestamp: string;  // ISO 8601
  payload: {
    task_id: string;
    status: string;
    query?: string;
    error?: string;
    step_index?: number;
    step_status?: string;
  };
}
```

---

## 5. Database Schema

### 5.1 PostgreSQL Tables

#### Core Tables

```sql
-- Migration 001: Initial schema
CREATE TABLE tasks (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) DEFAULT 'system' NOT NULL,
    query TEXT NOT NULL,
    status VARCHAR(20) DEFAULT 'pending' NOT NULL,
    result JSONB,
    error JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);
CREATE INDEX idx_tasks_user_id ON tasks(user_id);
CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_tasks_created_at ON tasks(created_at DESC);
CREATE INDEX idx_tasks_user_id_created_at ON tasks(user_id, created_at DESC);

CREATE TABLE steps (
    id VARCHAR(36) PRIMARY KEY,
    task_id VARCHAR(36) NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    step_number INTEGER NOT NULL,
    agent_type VARCHAR(20) NOT NULL,
    status VARCHAR(20) DEFAULT 'pending' NOT NULL,
    depends_on JSONB,
    input_data JSONB,
    output_data JSONB,
    confidence FLOAT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);
CREATE INDEX idx_steps_task_id ON steps(task_id);

CREATE TABLE workflows (
    id VARCHAR(36) PRIMARY KEY,
    task_id VARCHAR(36) UNIQUE NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    user_id VARCHAR(36) DEFAULT 'system' NOT NULL,
    name VARCHAR(255),
    definition JSONB NOT NULL,
    status VARCHAR(20) DEFAULT 'pending' NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE TABLE workflow_nodes (
    id VARCHAR(36) PRIMARY KEY,
    workflow_id VARCHAR(36) NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    step_number INTEGER NOT NULL,
    agent_type VARCHAR(20) NOT NULL,
    status VARCHAR(20) DEFAULT 'pending' NOT NULL,
    depends_on JSONB,
    condition_code TEXT,
    node_type VARCHAR(20) DEFAULT 'task',
    approval_config JSONB
);

CREATE TABLE workflow_edges (
    id VARCHAR(36) PRIMARY KEY,
    workflow_id VARCHAR(36) NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    from_node_id VARCHAR(36) NOT NULL,
    to_node_id VARCHAR(36) NOT NULL
);
```

#### User & Auth Tables

```sql
CREATE TABLE users (
    id VARCHAR(36) PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255),
    role VARCHAR(20) DEFAULT 'user',
    hashed_password VARCHAR(255) NOT NULL,
    api_key VARCHAR(255),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE TABLE api_keys (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id),
    key_hash VARCHAR(64) NOT NULL,
    name VARCHAR(255),
    last_used_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);
```

#### Observability Tables

```sql
CREATE TABLE traces (
    id VARCHAR(36) PRIMARY KEY,
    task_id VARCHAR(36) NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    status VARCHAR(20) DEFAULT 'running',
    duration_ms INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE TABLE spans (
    id VARCHAR(36) PRIMARY KEY,
    trace_id VARCHAR(36) NOT NULL REFERENCES traces(id) ON DELETE CASCADE,
    span_id VARCHAR(255) NOT NULL,  -- 36+ chars for human-readable names
    operation VARCHAR(100) NOT NULL,
    agent_name VARCHAR(100),
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP,
    status VARCHAR(20),
    error JSONB,
    metadata JSONB
);

CREATE TABLE token_usage (
    id VARCHAR(36) PRIMARY KEY,
    task_id VARCHAR(36) REFERENCES tasks(id),
    model VARCHAR(100) NOT NULL,
    prompt_tokens INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    cost FLOAT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);
```

#### LangGraph Checkpoint Table

```sql
CREATE TABLE checkpoints (
    thread_id VARCHAR(255) NOT NULL,
    checkpoint_ns VARCHAR(255) DEFAULT 'default' NOT NULL,
    checkpoint_id VARCHAR(255) NOT NULL,
    parent_checkpoint_id VARCHAR(255),
    type VARCHAR(20),
    state_blob JSONB,
    channel_values JSONB,
    pending_sends JSONB,
    metadata JSONB,
    task_id VARCHAR(36),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
);
```

#### Migration Tracking

```sql
CREATE TABLE schema_migrations (
    version INTEGER PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);
```

### 5.2 SQLite Tables (Supervisor)

Managed by the `serve` command in Go:

```sql
CREATE TABLE agent_sessions (
    id TEXT PRIMARY KEY, agent_id TEXT, status TEXT,
    input TEXT, output TEXT, error_message TEXT,
    started_at TEXT, completed_at TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE actions (
    id TEXT PRIMARY KEY, session_id TEXT, sequence INTEGER,
    action_type TEXT, target TEXT, arguments TEXT,
    status TEXT, result TEXT, error_message TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES agent_sessions(id)
);

CREATE TABLE system_state (
    key TEXT PRIMARY KEY, value TEXT
);

CREATE TABLE agent_configs (
    id TEXT PRIMARY KEY, name TEXT, description TEXT, role TEXT,
    system_prompt TEXT, model TEXT, temperature REAL, max_tokens INTEGER,
    status TEXT DEFAULT 'active',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE tool_definitions (
    id TEXT PRIMARY KEY, name TEXT UNIQUE, description TEXT,
    category TEXT, type TEXT, parameters_schema TEXT,
    status TEXT DEFAULT 'active',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE checkpoints (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT DEFAULT 'default' NOT NULL,
    checkpoint_id TEXT NOT NULL,
    state_blob BLOB,
    metadata TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
);
```

### 5.3 Migrations

SQL migrations live in `migrations/` with versioned filenames (`NNN_description.sql`):

| Migration | Description |
|-----------|-------------|
| `001_initial_schema.sql` | All base tables (tasks, steps, workflows, users, traces, etc.) |
| `002_add_user_id_to_tasks.sql` | Add user_id to tasks table |
| `003_fix_schema_mismatches.sql` | Fix confidence type, add depends_on JSON, add user role |
| `004_add_missing_schema.sql` | Agent versions, MCP servers, guardrails, checkpoints |
| `005_add_v2_tables.sql` | Tools v2, agent config v2, user onboarding |
| `006_increase_span_id_size.sql` | VARCHAR(36) → VARCHAR(255) for spans.span_id |

The migration runner (`app/migrations/runner.py`) tracks applied migrations in the `schema_migrations` table and applies pending ones in version order.

---

## 6. Configuration

### 6.1 Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENAI_API_KEY` | Yes | — | OpenAI API key for LLM access |
| `OPENAI_MODEL` | No | gpt-4o | Default OpenAI model |
| `DATABASE_URL` | Yes | — | PostgreSQL async connection string |
| `REDIS_URL` | Yes* | — | Redis connection string (*not required in gRPC mode) |
| `SECRET_KEY` | Yes | — | JWT signing secret |
| `RUNTIME_MODE` | No | http | `http` for FastAPI mode, `grpc` for native mode |
| `AGENTOS_RUNTIME_MODE` | No | — | Override for runtime mode detection |
| `MAX_STEPS_DEFAULT` | No | 10 | Default max execution steps |
| `TIMEOUT_DEFAULT` | No | 300 | Default task timeout (seconds) |
| `MAX_RETRIES` | No | 3 | Maximum retry attempts |
| `CORS_ORIGINS` | No | * | Allowed CORS origins |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | 30 | JWT access token TTL |
| `REFRESH_TOKEN_EXPIRE_DAYS` | No | 7 | JWT refresh token TTL |
| `RATE_LIMIT_PER_MINUTE` | No | 60 | API rate limit per client |
| `LOG_LEVEL` | No | INFO | Logging level |
| `AGENTOS_LOG_JSON` | No | false | Enable JSON log output |
| `ANTHROPIC_API_KEY` | No | — | Anthropic Claude API key |
| `GOOGLE_API_KEY` | No | — | Google Gemini API key |
| `EXA_API_KEY` | No | — | Exa.ai search API key |
| `GRPC_HOST` | No | localhost | gRPC server host |
| `GRPC_PORT` | No | 50051 | gRPC server port |
| `AGENTOS_DATA_DIR` | No | ~/.agentos | Data directory |

### 6.2 CLI Configuration

TOML file at `~/.config/agentos/config.toml`:

```toml
[supervisor]
host = "127.0.0.1"
port = 8080

[desktop]
default_save_dir = "~/Pictures/agentos"

data_dir = "~/.local/share/agentos"
log_level = "info"
auto_start_daemon = true
default_timeout = 300
output_format = "text"  # text | json
```

### 6.3 GUI Configuration

TOML file at platform config directory (`AgentOS/config.toml`):

```toml
[daemon]
host = "127.0.0.1"
port = 8080

auto_start_daemon = true
start_minimized = false
notifications_enabled = true
global_shortcuts_enabled = true
```

---

## 7. Protocols & Communication

### 7.1 gRPC Protobuf Definitions

Three gRPC services define the protocol between components:

| Service | Proto File | Defined In | Lines | Client | Server |
|---------|-----------|------------|-------|--------|--------|
| RuntimeService | `runtime.proto` | supervisor/proto/ | 293 | Go | Go (in-process) |
| CheckpointService | `checkpoint.proto` | supervisor/proto/ | 170 | Python | Go (:50052) |
| WorkerExecutor | `worker.proto` | supervisor/proto/ | 43 | Go | Python (configurable) |
| DesktopAutomation | `desktop.proto` | desktop/ | 491 | Python | Rust (:50051) |

### 7.2 Inter-Process Communication

| From | To | Protocol | Method | Authentication |
|------|----|----------|--------|----------------|
| CLI/TUI | Supervisor | HTTP/JSON | REST | None (localhost) |
| GUI frontend | Supervisor | HTTP/JSON | REST | None (localhost) |
| GUI frontend | Supervisor | WebSocket | Events | Connection upgrade |
| Supervisor | Python FastAPI | HTTP/JSON | REST | API key header |
| Supervisor | Python (gRPC desktop) | gRPC | RPC | TLS + API key |
| Python | Go (checkpoints) | gRPC | RPC | mTLS + API key |
| Go | Python (executor) | gRPC | RPC | API key |
| Python | Python (MCP servers) | JSON-RPC | stdio | None |
| Python | Redis | TCP | Redis protocol | Optional password |
| Python | PostgreSQL | TCP | asyncpg | Password |
| Go | SQLite | File | CGo-free (modernc) | File permissions |

### 7.3 Message Formats

#### MCP Message (Python ↔ Python via stdio)

```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "read_file",
    "arguments": {
      "path": "/home/user/document.txt"
    }
  },
  "id": 1
}
```

#### Handoff Message (Agent → Agent)

```json
{
  "from_agent": "core_planner",
  "to_agent": "core_executor",
  "task_id": "abc-123",
  "state_snapshot": {
    "current_step": 2,
    "completed_steps": ["step_1"],
    "intermediate_results": {}
  },
  "context": {"user_id": "user_1"},
  "handoff_reason": "task_delegation",
  "signature": "sha256hex..."
}
```

#### Task Queue Message (Redis)

```json
{
  "task_id": "abc-123",
  "user_id": "user_1",
  "query": "Open notepad and write hello",
  "priority": 2,
  "config": {"mode": "task"},
  "idempotency_key": "sha256hex...",
  "scheduled_for": null,
  "status": "queued"
}
```

---

## 8. Development Guide

### 8.1 Prerequisites

- Python 3.11+
- Go 1.23+
- Rust 1.75+ (with `wasm32-unknown-unknown` target for Tauri)
- Node.js 18+ (for GUI)
- PostgreSQL 16+ (or SQLite for local mode)
- Redis 7+
- Docker & Docker Compose (optional, for containerized deployment)

### 8.2 Local Setup

```bash
# Clone the repository
git clone https://github.com/Chandankumar123456/agentos.git
cd agentos

# Python backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Copy environment template
cp .env.example .env
# Edit .env with your API keys and database URLs

# Go supervisor
cd supervisor
go mod download
go build -o supervisor.exe .
cd ..

# Rust components
cd cli && cargo build && cd ..
cd tui && cargo build && cd ..
cd desktop && cargo build && cd ..

# GUI
cd gui
npm install
npm run build  # or npm run dev for development
cd ..
```

### 8.3 Running Components

```bash
# Start infrastructure (PostgreSQL + Redis)
docker-compose -f docker/docker-compose.yml up -d postgres redis

# Run database migrations
python -m app.migrations.runner

# Start Python backend (HTTP mode)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Start Go supervisor (manages Python backend)
cd supervisor
./supervisor.exe

# Start Rust desktop automation server
cd desktop
cargo run --bin desktop-automation

# CLI usage
cargo run --bin agentos -- task create "open notepad and write hello"

# TUI dashboard
cargo run --bin agentos-tui

# GUI application
cd gui
npm run dev
# or: cargo tauri dev
```

### 8.4 Testing

```bash
# Run all Python tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=app --cov-report=term-missing

# Run specific test categories
pytest tests/test_orchestrator_fallback.py -v
pytest tests/test_desktop_loop.py -v
pytest tests/test_multi_agent.py -v

# Run integration tests
pytest tests/integration/ -v

# Run stress tests
pytest tests/stress/ -v

# Run action v1 benchmarks
pytest tests/test_action_v1_benchmarks.py -v

# Validate all critical fixes
python validate_fixes.py

# Go tests
cd supervisor && go test ./... && cd ..

# Rust tests
cd cli && cargo test && cd ..
cd tui && cargo test && cd ..
cd desktop && cargo test && cd ..

# GUI checks
cd gui && npm run lint && cd ..
```

### 8.5 Code Quality

```bash
# Python: type checking
mypy app/

# Python: linting
ruff check app/
ruff format app/ --check

# Python: audit schema synchronization
python audit_schema.py

# Go: linting
cd supervisor && golangci-lint run && cd ..

# Rust: linting
cd cli && cargo clippy && cd ..
```

---

## 9. Deployment

### 9.1 Docker Deployment

```yaml
# docker-compose.yml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: agentos
      POSTGRES_USER: agentos
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U agentos"]
      interval: 5s
    volumes:
      - postgres_data:/var/lib/postgresql/data
  
  redis:
    image: redis:7-alpine
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
    volumes:
      - redis_data:/data
  
  api:
    build:
      context: .
      dockerfile: docker/Dockerfile
    environment:
      - DATABASE_URL=postgresql+asyncpg://agentos:${POSTGRES_PASSWORD}@postgres:5432/agentos
      - REDIS_URL=redis://redis:6379/0
      - OPENAI_API_KEY=${OPENAI_API_KEY}
    ports:
      - "8000:8000"
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - ./app:/app/app:ro
    deploy:
      resources:
        limits:
          cpus: '1'
          memory: 512M
  
  worker:
    build:
      context: .
      dockerfile: docker/Dockerfile
    command: celery -A app.queue.tasks worker --loglevel=info --concurrency=4
    environment:
      - DATABASE_URL=postgresql+asyncpg://agentos:${POSTGRES_PASSWORD}@postgres:5432/agentos
      - REDIS_URL=redis://redis:6379/0
      - OPENAI_API_KEY=${OPENAI_API_KEY}
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    deploy:
      resources:
        limits:
          cpus: '1'
          memory: 512M
```

### 9.2 Native Build

**Binary targets:**

| Component | Build Command | Output |
|-----------|---------------|--------|
| Go Supervisor | `cd supervisor && go build -o supervisor.exe` | `supervisor/supervisor.exe` |
| Rust CLI | `cd cli && cargo build --release` | `cli/target/release/agentos.exe` |
| Rust TUI | `cd tui && cargo build --release` | `tui/target/release/agentos-tui.exe` |
| Rust Desktop | `cd desktop && cargo build --release` | `desktop/target/release/desktop-automation.exe` |
| Tauri GUI | `cd gui && cargo tauri build` | `gui/src-tauri/target/release/agentos-gui.exe` |

### 9.3 Configuration

**Production checklist:**

1. Set strong `SECRET_KEY` (use `openssl rand -hex 32`)
2. Configure PostgreSQL with connection pooling (pgbouncer recommended)
3. Enable Redis persistence (AOF + RDB)
4. Set `CORS_ORIGINS` to specific origins
5. Configure rate limiting per environment
6. Enable API key authentication
7. Set `RUNTIME_MODE=http` for cloud deployment
8. Configure proper log levels and log shipping
9. Set up Prometheus metrics scraping
10. Configure auto-update endpoint for supervisor

---

## 10. Architecture Decisions & Patterns

### 10.1 LangGraph-First Execution

**Decision:** The orchestrator always tries LangGraph execution first, with two fallback layers.

**Rationale:** LangGraph provides structured state graphs with checkpoint/rollback, enabling robust recovery. The fallback chain (LangGraph → Checkpoint Recovery → Legacy Pipeline) ensures availability even when the primary path fails.

**Implementation:** `Orchestrator.execute_task()` → `TaskRunner.run()` (LangGraph) → `CheckpointRecoveryService.recover()` → `ModeStrategyFactory.get().execute()`.

### 10.2 Adaptive Execution Routing

**Decision:** Tasks are classified into 3 tiers with progressively more sophisticated execution.

| Tier | Name | Execution | Latency | Use Case |
|------|------|-----------|---------|----------|
| 0 | Direct | Single tool call | ~100ms | Open app, calculate, search |
| 1 | Sequential | Multi-step, no graph | ~500ms | Type text, create file |
| 2 | Full Runtime | LangGraph compilation | ~2s+ | Complex multi-step tasks |

**Rationale:** Simple tasks (open notepad, calculate 2+2) do not need LangGraph state compilation overhead. The `TaskComplexityRouter` uses regex-based intent extraction to make fast routing decisions.

### 10.3 Dual-Mode Runtime

**Decision:** AgentOS supports both HTTP (cloud/FastAPI) and gRPC (local-native) runtime modes.

**Rationale:** In cloud mode, the Python FastAPI server is the primary API. In local mode, the Go Supervisor is the primary API, managing Python as a child process. The bootstrap module (`app/bootstrap.py`) is shared between both modes, with mode-specific components (gRPC client, middleware) loaded conditionally.

**Mode detection:** `AGENTOS_RUNTIME_MODE` environment variable, defaulting to `http`. gRPC mode skips Redis initialization and FastAPI middleware.

### 10.4 Canonical Execution State

**Decision:** `ToolExecutionRecord` in `execution_state.py` is the single source of truth for all execution layers.

**Rationale:** Previously, the tool layer, executor, goal loop, verifier, and recovery each maintained separate success/failure opinions, leading to inconsistency. Now, all downstream layers read from `ExecutionState` instead of re-inferring.

**Key fields:** `tool_name`, `params`, `success`, `result`, `error`, `evidence`, `terminal`. The `terminal` flag auto-detects "deterministic success" for desktop/browser/filesystem operations.

### 10.5 Failure Isolation & Circuit Breakers

**Decision:** Each task executes within an isolated context with circuit breaker protection.

**Pattern:** `FailureIsolator.run_isolated()` wraps task execution with:
1. Context creation (resource limits, timeouts)
2. Failure tracking (after 3 failures, circuit opens)
3. Cleanup on exit (release resources, close sessions)

**Rationale:** Prevents cascading failures where one problematic task exhausts system resources or corrupts shared state.

### 10.6 Inter-Agent Communication

**Decision:** Multiple communication patterns for different scenarios.

- **Direct invocation** for simple coordinator → worker calls
- **MCP message bus** for pub/sub event distribution
- **Handoff protocol** for structured state transfer between agents
- **Consensus engine** for multi-agent agreement on ambiguous results
- **Feedback loop** for learning from past execution patterns

**Rationale:** Different scenarios require different communication properties. Direct invocation is fast and simple; the message bus provides decoupling; handoff provides integrity; consensus provides reliability; feedback provides improvement.

---

## 11. Observability

### 11.1 Structured Logging

The `AgentOSLogger` supports two output modes:

```
# Text mode (default):
2026-05-11 10:30:00,123 | INFO  | [app.orchestrator.core] Task abc-123 started

# JSON mode (AGENTOS_LOG_JSON=true):
{"timestamp": "2026-05-11T10:30:00.123", "level": "INFO", "logger": "app.orchestrator.core", "message": "Task abc-123 started", "task_id": "abc-123"}
```

Key methods: `log_task()`, `log_step()`, `log_tool()`, `log_node()`, `log_error()` — all add structured context fields.

### 11.2 Distributed Tracing

The `TraceManager` provides span-based distributed tracing:

```python
# Usage in orchestrator:
trace_manager.start_span(trace_id="task-abc", span_id="planner.reasoning", operation="plan")
# ... execution ...
trace_manager.end_span(span_id="planner.reasoning", status="success")
# Spans are persisted to PostgreSQL 'spans' table
```

Span IDs support human-readable names like `"planner.reasoning:2026-04-25T16:12:52.274630"` (hence VARCHAR(255)).

### 11.3 Prometheus Metrics

The `MetricsCollector` exposes counters and histograms at `/metrics`:

```
# HELP http_requests_total Total HTTP requests
# TYPE http_requests_total counter
http_requests_total{method="POST",path="/api/v1/tasks",status="200"} 42

# HELP http_request_duration_seconds HTTP request duration
# TYPE http_request_duration_seconds histogram
http_request_duration_seconds{method="POST",path="/api/v1/tasks"}_bucket{le="0.1"} 10
http_request_duration_seconds{method="POST",path="/api/v1/tasks"}_bucket{le="0.5"} 25
http_request_duration_seconds{method="POST",path="/api/v1/tasks"}_bucket{le="+Inf"} 42

# HELP desktop_tasks_total Desktop automation tasks
# TYPE desktop_tasks_total counter
desktop_tasks_total{action="screenshot"} 15
desktop_tasks_total{action="click"} 30
```

### 11.4 Anomaly Detection & Alerting

The `AnomalyDetector` uses sliding window statistics (mean + 2 standard deviations) to detect:

- Elevated error rates (e.g., >15% tool failures)
- Latency spikes (e.g., >5s average tool execution)
- Cost anomalies (e.g., sudden token usage increase)
- Loop count anomalies (e.g., >5 repeated attempts)

The `AlertManager` evaluates 4 default rules with cooldown protection:

| Rule | Metric | Threshold | Severity | Channel |
|------|--------|-----------|----------|---------|
| High Error Rate | error_rate | > 0.15 | WARNING | LOG |
| Critical Error Rate | error_rate | > 0.30 | CRITICAL | LOG + WEBHOOK |
| High Latency | avg_latency | > 5000ms | WARNING | LOG |
| Cost Spike | cost_rate | > 0.10 | WARNING | LOG |

### 11.5 Cost Tracking

The `CostTracker` records per-invocation costs using `MODEL_COSTS` pricing table:

| Model | Input (per 1K tokens) | Output (per 1K tokens) |
|-------|----------------------|-----------------------|
| gpt-4o | $0.005 | $0.015 |
| gpt-4o-mini | $0.00015 | $0.0006 |
| claude-3-opus | $0.015 | $0.075 |
| claude-3-sonnet | $0.003 | $0.015 |
| gemini-pro | $0.0005 | $0.0015 |

Tool costs are estimated using baseline tables:
- Filesystem tools: $0
- Shell execution: $0.0001
- Web search: $0.001–$0.002
- LLM interaction: per-token based on model

---

## 12. Security

### 12.1 Authentication

**Three authentication methods:**

1. **JWT Bearer tokens**: Created on login/signup, short-lived access token (default 30 min) + long-lived refresh token (default 7 days). Uses `python-jose` for JWT encoding with HS256.

2. **API keys**: `sk_` prefix + 32 URL-safe random bytes (hex-encoded). Stored as SHA-256 hash in PostgreSQL. Can be revoked individually.

3. **Password hashing**: bcrypt via `passlib` with SHA-256 preprocessing for passwords >72 bytes. Password strength validation: ≥8 chars, uppercase, lowercase, digit.

### 12.2 Authorization & RBAC

**Roles:** `admin`, `user`, `viewer`

**Permissions:**
- `create_task`, `create_agent`, `create_workflow`
- `delete_any` (admin only)
- `manage_users` (admin only)
- `view_analytics`

**Enforcement:** FastAPI dependency `require_permission(permission)` checks both API key permissions and user role. The `APIKeyMiddleware` sets `request.state.user` and `request.state.api_key_permissions`.

### 12.3 Tool Permissions

Role-based tool access control via `ToolPermissions`:

- `planner`: file read/write, web, text processing (no shell)
- `executor`: all tools including shell and desktop
- `verifier`: file read, web (no shell, no desktop)
- `reviewer`: read-only, web
- `coordinator`: all tools
- `admin`: all tools
- Default (no role): deny all

### 12.4 Credential Protection

The `SafetyGate` scans desktop tool parameters for credential patterns:

- API keys (`sk-*`, `sk_*` patterns)
- JWT tokens
- Passwords
- Auth tokens

Matching parameters are blocked with a `BLOCKED_DUE_TO_CREDENTIALS` error code.

### 12.5 TLS & mTLS

The Go Supervisor's `CryptoManager` generates self-signed certificates:

- **CA certificate**: RSA 4096-bit, 10-year validity
- **Server certificate**: Signed by CA, used by gRPC servers
- **Client certificate**: Signed by CA, used by gRPC clients
- **TLS version**: 1.3 minimum
- **Client auth**: `RequireAndVerifyClientCert` for checkpoint gRPC service

Certificate paths:
- CA: `{data_dir}/certs/ca.pem`
- Server cert: `{data_dir}/certs/server.pem`
- Server key: `{data_dir}/certs/server-key.pem`
- Client cert: `{data_dir}/certs/client.pem`
- Client key: `{data_dir}/certs/client-key.pem`

---

## 13. Extending AgentOS

### 13.1 Adding a New Tool

1. Create a new class inheriting from `BaseTool` in `app/tools/`:

```python
from .base import BaseTool, ToolInput, ToolOutput

class MyCustomTool(BaseTool):
    name = "my_custom_tool"
    description = "Does something useful"
    parameters_schema = {
        "type": "object",
        "properties": {
            "input_param": {"type": "string"}
        },
        "required": ["input_param"]
    }
    
    async def execute(self, params: ToolInput) -> ToolOutput:
        result = do_something(params["input_param"])
        return ToolOutput(success=True, result=result)
```

2. Register it in `app/tools/builtin/__init__.py`:

```python
BUILTIN_TOOLS = [..., MyCustomTool]
```

3. Add tests in `tests/test_my_tool.py`.
4. (Optional) Add permissions in `ToolPermissions`.

### 13.2 Adding a New MCP Server

1. Create a new file in `app/mcp/servers/my_server.py`:

```python
from mcp.server.fastmcp import FastMCP
from ._stdio_sanitize import _stdio_sanitize

_stdio_sanitize()

mcp = FastMCP("my-server")

@mcp.tool()
def my_tool(param: str) -> str:
    """Tool description"""
    return f"Processed: {param}"

if __name__ == "__main__":
    mcp.run(transport="stdio")
```

2. Register it in `app/mcp/client_manager.py`:

```python
self.system_servers = [
    ...,
    {"name": "my_server", "command": sys.executable, 
     "args": ["-m", "app.mcp.servers.my_server"]},
]
```

3. The tool will be automatically discovered on next startup.

### 13.3 Adding a New Agent Type

1. Create a new class inheriting from `BaseAgent`:

```python
from .base import BaseAgent, AgentInput, AgentOutput, AgentRole

class ResearcherAgent(BaseAgent):
    name = "researcher"
    role = AgentRole.RESEARCHER
    
    async def execute(self, input_data: AgentInput) -> AgentOutput:
        # Research logic
        return AgentOutput(status="success", output_data=result)
```

2. Register the class in `AgentFactory._agent_map` in `app/runtime/factory.py`.

3. (Optional) Add to `AgentRouter` role mappings in `app/orchestrator/router.py`.

### 13.4 Adding a New Execution Mode

1. Create a new strategy class in `app/orchestrator/modes/`:

```python
from .base import ModeStrategy

class BatchMode(ModeStrategy):
    async def execute(self, runtime, orchestrator, query, config, task_id, user_id):
        # Batch execution logic
        ...
```

2. Register it in `ModeStrategyFactory.__init__`:

```python
self._strategies = {
    ..., 
    "batch": BatchMode()
}
```

---

## 14. Troubleshooting

### Common Issues

| Symptom | Cause | Solution |
|---------|-------|----------|
| `DATABASE_URL is required` | Missing environment variable | Copy `.env.example` to `.env` and fill in values |
| `gRPC not available` | Missing `grpcio-tools` | `pip install grpcio-tools` |
| Playwright errors | Missing browser binaries | `playwright install chromium` |
| Tauri build fails | Missing Rust WASM target | `rustup target add wasm32-unknown-unknown` |
| `module 'app' not found` | Wrong working directory | Run from project root (`E:\Projects\AgentOS`) |
| Redis connection refused | Redis not running | `docker-compose up -d redis` or start local Redis |
| PostgreSQL connection refused | PostgreSQL not running | `docker-compose up -d postgres` or start local PostgreSQL |
| JWT decode errors | Wrong `SECRET_KEY` | Ensure `SECRET_KEY` is consistent across restarts |
| SQL migration version mismatch | Manual DB changes | Run `python audit_schema.py` and apply missing migrations |
| WebSocket connection drops | Supervisor not running | Start Go supervisor on port 8080 |
| Desktop automation fails | Python gRPC server not running | Start via supervisor or `python -m app.desktop.grpc_server` |
| CLI can't connect | Supervisor not running | `agentos daemon start` |
| Rate limited | Too many requests | Wait or adjust `RATE_LIMIT_PER_MINUTE` in `.env` |

### Diagnostic Commands

```bash
# Check database connection
python check_db.py

# Audit schema synchronization
python audit_schema.py

# Run all critical validations
python validate_fixes.py

# Check supervisor health
curl http://localhost:8080/health

# Check Python API health
curl http://localhost:8000/health

# View task trace
python -c "from app.memory.long_term import task_repo; import asyncio; print(asyncio.run(task_repo.get('task-id')))"

# Test gRPC connection
python -c "from app.proto.grpc_client import GRPCClient; import asyncio; c=GRPCClient(); asyncio.run(c.connect()); print('OK')"

# Flush Redis cache
redis-cli FLUSHALL

# Reset migration state
python -c "
import asyncio
from app.memory.long_term import db
async def reset():
    await db.connect()
    async with db.get_session() as s:
        await s.execute('DELETE FROM schema_migrations')
    print('Migration state reset')
asyncio.run(reset())
"
```

### Logs

| Component | Log Location | Format |
|-----------|-------------|--------|
| Python backend | stdout (configurable to file) | Text or JSON |
| Go supervisor | stdout + `supervisor.out` | Structured text |
| TUI/CLI | stdout | Formatted text |
| GUI (Tauri) | `~/.local/share/agentos/gui.log` | Text |
| Desktop automation | stdout | Structured text |

### Getting Help

- Check `workspace/` for phase plans and design documents
- Review test files for usage examples
- Run `VALIDATE_FIXES.py` for system health verification
- Check supervisor status: `curl http://localhost:8080/status`

---

*AgentOS — Local-native autonomous agent runtime. Built with Python, Go, Rust, and TypeScript.*
