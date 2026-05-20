# AgentOS — Autonomous Agent Operating System

**Version:** 0.4.0-desktop-native  
**Architecture:** Multi-language, desktop-native, local-first agent runtime with optional cloud augmentation  
**License:** Proprietary  
**Repository:** https://github.com/Chandankumar123456/agentos  

AgentOS is a production-grade, desktop-native autonomous agent operating system designed to execute complex multi-step tasks across heterogeneous environments — desktop GUI, web browser, filesystem, shell, and cloud APIs — from a single local runtime. It integrates structured LLM orchestration (LangGraph), a Model Context Protocol (MCP) tool server mesh, local-first task scheduling with SQLite persistence, real-time observability, and multi-agent coordination into a single coherent runtime that requires no external infrastructure by default.

The system is written in **Python** (asyncio, LangGraph, gRPC), **Go** (supervisor/control plane), **Rust** (CLI, TUI, desktop automation, Tauri shell), and **TypeScript** (React GUI). Communication between components uses **gRPC** (protobuf v3) as the primary IPC, **HTTP/REST** for GUI/CLI compatibility, **WebSocket** for real-time events, and **SQLite** as the single source of truth in desktop mode.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [System Components](#2-system-components)
   - 2.1 [Python Backend (app/)](#21-python-backend-app)
   - 2.2 [Desktop-Native Kernel (app/desktop_native/)](#22-desktop-native-kernel-appdesktop_native)
   - 2.3 [Go Supervisor (supervisor/)](#23-go-supervisor-supervisor)
   - 2.4 [Rust CLI (cli/)](#24-rust-cli-cli)
   - 2.5 [Rust TUI (tui/)](#25-rust-tui-tui)
   - 2.6 [Rust Desktop Automation (desktop/)](#26-rust-desktop-automation-desktop)
   - 2.7 [Tauri GUI (gui/)](#27-tauri-gui-gui)
3. [Core Subsystems](#3-core-subsystems)
   - 3.1 [Bootstrap & Runtime Initialization](#31-bootstrap--runtime-initialization)
   - 3.2 [AgentKernel](#32-agentkernel)
   - 3.3 [Agent System](#33-agent-system)
   - 3.4 [Orchestrator](#34-orchestrator)
   - 3.5 [Model Context Protocol (MCP)](#35-model-context-protocol-mcp)
   - 3.6 [Tool System](#36-tool-system)
   - 3.7 [Memory & Persistence](#37-memory--persistence)
   - 3.8 [Task Queue & State Machine](#38-task-queue--state-machine)
   - 3.9 [Execution Modes](#39-execution-modes)
   - 3.10 [Capability System](#310-capability-system)
   - 3.11 [Action v1 Framework](#311-action-v1-framework)
   - 3.12 [Workflow Engine](#312-workflow-engine)
   - 3.13 [Guardrails & Safety](#313-guardrails--safety)
4. [API Reference](#4-api-reference)
   - 4.1 [gRPC Services (Primary)](#41-grpc-services-primary)
   - 4.2 [FastAPI HTTP Endpoints (Secondary)](#42-fastapi-http-endpoints-secondary)
   - 4.3 [WebSocket Protocol](#43-websocket-protocol)
5. [Database Schema](#5-database-schema)
   - 5.1 [SQLite Tables (Desktop-Native Primary)](#51-sqlite-tables-desktop-native-primary)
   - 5.2 [PostgreSQL Tables (Cloud Optional)](#52-postgresql-tables-cloud-optional)
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
   - 9.1 [Native Desktop Build](#91-native-desktop-build)
   - 9.2 [Docker Deployment (Cloud Mode)](#92-docker-deployment-cloud-mode)
   - 9.3 [Configuration](#93-configuration)
10. [Architecture Decisions & Patterns](#10-architecture-decisions--patterns)
    - 10.1 [Desktop-Native First](#101-desktop-native-first)
    - 10.2 [LangGraph-First Execution](#102-langgraph-first-execution)
    - 10.3 [Adaptive Execution Routing](#103-adaptive-execution-routing)
    - 10.4 [Dual-Mode Runtime](#104-dual-mode-runtime)
    - 10.5 [Canonical Execution State](#105-canonical-execution-state)
    - 10.6 [Failure Isolation & Circuit Breakers](#106-failure-isolation--circuit-breakers)
    - 10.7 [Inter-Agent Communication](#107-inter-agent-communication)
    - 10.8 [SQLite as Single Source of Truth](#108-sqlite-as-single-source-of-truth)
11. [Observability](#11-observability)
    - 11.1 [Structured Logging](#111-structured-logging)
    - 11.2 [Local Tracing](#112-local-tracing)
    - 11.3 [Local Metrics](#113-local-metrics)
    - 11.4 [Anomaly Detection & Alerting](#114-anomaly-detection--alerting)
    - 11.5 [Cost Tracking](#115-cost-tracking)
12. [Security](#12-security)
    - 12.1 [Authentication](#121-authentication)
    - 12.2 [Authorization & RBAC](#122-authorization--rbac)
    - 12.3 [Capability-Based Tool Permissions](#123-capability-based-tool-permissions)
    - 12.4 [Credential Protection](#124-credential-protection)
    - 12.5 [TLS & mTLS](#125-tls--mtls)
13. [Extending AgentOS](#13-extending-agentos)
    - 13.1 [Adding a New Tool](#131-adding-a-new-tool)
    - 13.2 [Adding a New MCP Server](#132-adding-a-new-mcp-server)
    - 13.3 [Adding a New Agent Type](#133-adding-a-new-agent-type)
    - 13.4 [Adding a New Execution Mode](#134-adding-a-new-execution-mode)
    - 13.5 [Adding a Desktop-Native Subsystem](#135-adding-a-desktop-native-subsystem)
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
│              │  │ gRPC      │ │Checkpoint │ │  EventHub      │  │        │
│              │  │ Client    │ │ Server    │ │  (WebSocket)   │  │        │
│              │  │ (Python)  │ │ (gRPC)    │ │  Broadcast     │  │        │
│              │  └─────┬─────┘ └─────┬─────┘ └────────────────┘  │        │
│              │        │              │                            │        │
│              │  ┌─────▼──────────────▼──────────────────────┐    │        │
│              │  │          SQLite (agentos.db)               │    │        │
│              │  └───────────────────────────────────────────┘    │        │
│              └────────────────┬──────────────────────────────────┘        │
│                               │ gRPC (:50051)                             │
│              ┌────────────────▼──────────────────────────────────┐        │
│              │           Python Desktop Runtime                    │        │
│              │  ┌──────────┐ ┌──────────┐ ┌──────────────────┐    │        │
│              │  │ AgentKernel│ │  gRPC    │ │  LangGraph       │    │        │
│              │  │ (asyncio)│ │  Server  │ │  Executor        │    │        │
│              │  └────┬─────┘ └────┬─────┘ └────────┬─────────┘    │        │
│              │       │            │                  │              │        │
│              │  ┌────▼────────────▼──────────────────▼─────────┐   │        │
│              │  │  SQLite (WAL) + Local Event Bus + Task Queue  │   │        │
│              │  └─────────────────────────────────────────────┘   │        │
│              └────────────────────────────────────────────────────┘        │
│                                                                           │
│              ┌────────────────────────────────────────────────────┐        │
│              │     Rust Desktop Automation (:50051)                │        │
│              │  ┌──────────┐ ┌──────────┐ ┌──────────────────┐    │        │
│              │  │ GDI      │ │ Win32   │ │  OCR (Python)    │    │        │
│              │  │ Capture  │ │ Input   │ │  via gRPC        │    │        │
│              └──────────────┘ └──────────┘ └──────────────────┘    │        │
└─────────────────────────────────────────────────────────────────────────┘
```

### High-Level Data Flow

1. **User Input**: CLI/TUI/GUI sends HTTP/REST request to the Go Supervisor, or directly invokes Tauri commands that manage the Supervisor process.
2. **Task Creation**: The Supervisor forwards the task via gRPC to the Python `AgentKernel`, which creates a task, classifies its capability, selects an execution environment, and determines complexity tier.
3. **Execution Path Selection**:
   - **Tier 0/1 (Direct/Sequential)**: Fast-path deterministic execution via `TaskComplexityRouter` for atomic operations (open app, type text, search web).
   - **Tier 2 (LangGraph)**: Full LangGraph state graph compilation with planner → executor → verifier nodes, checkpointed to SQLite.
   - **Legacy Fallback**: Plan → Execute → Verify pipeline when LangGraph is unavailable.
4. **Tool Invocation**: Agents invoke tools through `ToolRegistry`, which dispatches to built-in tools, MCP server processes (via stdio JSON-RPC), or desktop environment tools. Sensitive tools pass through `CapabilityManager` for approval.
5. **Recovery & Verification**: After execution, verification checks output correctness. On failure, the `RecoveryEngine` determines retry, escalation, or alternative strategy.
6. **Persistence**: Task state, execution trace, agent outputs, and workflow state are persisted to SQLite (desktop mode) or PostgreSQL (cloud mode). All desktop-native subsystems use SQLite as the single source of truth.

### Technology Stack by Component

| Component   | Language   | Framework/Libraries                                       | Purpose                              |
|-------------|------------|----------------------------------------------------------|--------------------------------------|
| Unified Core| Python 3.11| asyncio, aiosqlite, LangGraph, Pydantic 2                | `app/core/` - unified runtime API    |
| Kernel      | Python 3.11| asyncio, aiosqlite, SQLite (WAL)                         | Desktop-native execution engine      |
| Cloud API   | Python 3.11| FastAPI, Uvicorn, SQLAlchemy 2.0 (OPTIONAL)              | `app/cloud_api/` - HTTP/WS for cloud deployment only |
| Orchestrator| Python     | LangGraph, LangChain, Pydantic 2                         | Agent orchestration & state graphs   |
| Task Queue  | Python     | asyncio.PriorityQueue + SQLite                           | Async task processing (local-first)  |
| Supervisor  | Go 1.23    | gRPC, gorilla/websocket, modernc/sqlite                  | Control plane, task lifecycle, SQLite |
| CLI         | Rust       | clap, reqwest, tokio, comfy-table                         | Terminal user commands               |
| TUI         | Rust       | ratatui 0.26, crossterm, tokio-tungstenite                | Terminal dashboard                   |
| Desktop     | Rust       | tonic, prost, windows (Win32 API), image                  | Native desktop automation (gRPC)     |
| GUI         | TypeScript | React 18, Tailwind CSS, Tauri 1.5                        | Desktop GUI application              |
| Database    | --         | SQLite (WAL, sole dependency in desktop mode)            | Persistence                          |

> **Note:** Redis, Celery, and PostgreSQL have been removed from the desktop runtime path. They are no longer required dependencies. FastAPI is preserved in `app/cloud_api/` as an optional module for cloud/remote deployment scenarios only. The desktop-native mode (default) requires only Python, SQLite, and the Go Supervisor.

### Quick Start (Desktop-Native Mode)

Desktop-native is the default and recommended mode. No external infrastructure required.

```bash
# Start the Go Supervisor (which manages the Python runtime)
./supervisor/agentos-supervisor

# Or start the Python runtime directly for development
AGENTOS_RUNTIME_MODE=grpc python -m app.desktop_entry
```

The desktop entry point forces:
- `AGENTOS_RUNTIME_MODE=grpc`
- `DATABASE_URL=sqlite+aiosqlite:///$HOME/.agentos/agentos.db`
- No Redis, no PostgreSQL, no Celery, no FastAPI

---

## 2. System Components

### 2.1 Python Backend (`app/`)

The Python backend is the core execution engine. The unified public API is through `app/core/`, which consolidates access to the kernel, orchestration, state management, agents, memory, tools, recovery, and observability. Implementation details remain in their respective packages (`desktop_native/`, `orchestrator/`, `agents/`, `tools/`, etc.) but all external access is through the `app.core` namespace.

| Package              | Lines   | Key Responsibilities                                          |
|----------------------|---------|---------------------------------------------------------------|
| `app/core/`          | ~500    | **Unified public API**: kernel, orchestration, state, execution, agents, memory, tools, recovery, observability |
| `app/config/`        | ~275    | Settings management, runtime mode detection (HTTP/gRPC)       |
| `app/bootstrap.py`   | 420     | Canonical initialization sequence, lifecycle management       |
| `app/main.py`        | ~50     | Mode-detecting entry point (routes to desktop or cloud)       |
| `app/desktop_entry.py`| 241    | Canonical desktop entry point; forces SQLite, starts gRPC    |
| `app/cloud_api/`     | ~4,500  | **OPTIONAL** FastAPI server for cloud deployment (relocated from app/main.py + app/api/ + app/middleware/) |
| `app/desktop_native/` | ~5,256  | Unified desktop-native runtime kernel and subsystems          |
| `app/runtime/`       | ~3,309  | AgentRuntime singleton, worker pool, factory, scaling, gRPC  |
| `app/orchestrator/`  | ~5,836  | Core orchestrator, task runner, workflow, queue, state machine|
| `app/agents/`        | ~3,500  | Agent types (planner/executor/verifier), LLM, handoff, consensus|
| `app/mcp/`           | ~2,000  | MCP client manager, message bus, protocol, 8 server modules   |
| `app/tools/`         | ~3,550  | Tool registry, grounding, permissions, sandbox, 5 built-in    |
| `app/api/`           | ~4,000  | 17 route modules, schemas, WebSocket, dependency injection   |
| `app/memory/`        | ~4,500  | 37 ORM models, 16 repositories, 7 memory managers, in-memory fallbacks |
| `app/auth/`          | ~300    | JWT utils, RBAC, API key management                          |
| `app/middleware/`     | ~250    | Auth, rate limiting, request logging, input validation       |
| `app/guardrails/`    | ~100    | Input/output validation schemas                              |
| `app/capabilities/`  | ~400    | Environment selection, feasibility, verification             |
| `app/workflows/`     | ~200    | Task decomposition (LLM + deterministic)                     |
| `app/action_v1/`     | ~300    | Legacy v1 action framework (executor, selector, verifier)    |
| `app/langgraph/`     | ~500    | Graph definitions, state, SQLite checkpointer, collaboration nodes |
| `app/logs/`          | ~800    | Logger, metrics, tracing, anomaly detection, alerts, profiler|
| `app/observability/` | ~100    | Event bus for observability data                             |
| `app/queue/`         | ~50     | Celery task definitions (disabled in desktop mode)           |
| `app/migrations/`    | ~120    | SQL migration runner (PostgreSQL + SQLite)                   |

#### 2.1.1 Bootstrap Sequence

The `bootstrap()` function in `app/bootstrap.py` defines the canonical 5-phase initialization, with mode-aware skips:

```
Phase 1: Dependency Validation
  ├── Check DATABASE_URL, OPENAI_API_KEY are set
  ├── Skip Redis check in gRPC mode
  └── Skip SECRET_KEY check in desktop mode

Phase 2: Persistence Layer
  ├── Connect to SQLite (aiosqlite via SQLAlchemy) in desktop mode
  ├── Connect to PostgreSQL (asyncpg via SQLAlchemy) in cloud mode
  ├── Run pending SQL migrations (auto-translated for SQLite)
  ├── Connect to Redis (short-term memory + PubSub) in cloud mode only
  └── Initialize in-memory fallbacks (gRPC mode only)

Phase 3: Core Runtime
  ├── Create AgentRuntime singleton
  ├── Register core agents (core_planner, core_executor, core_verifier)
  ├── Skip Redis mutex in gRPC mode (single-process)
  └── Load additional agents from DB

Phase 4: MCP & Tool Systems
  ├── Start MCP health monitor (periodic health checks every 60s)
  ├── Register built-in tools (search, calculator, text processor)
  ├── Start MCP system servers (filesystem, shell, cloud_api, etc.)
  ├── Discover MCP tools from all servers
  └── Register desktop session cleanup hooks

Phase 5: gRPC Server (gRPC mode only)
  ├── Start embedded gRPC server on port 50051
  ├── Bind RuntimeService, CheckpointService, WorkerService
  └── Register gRPC shutdown hook
```

Each phase has individually configurable skip flags (`skip_database`, `skip_redis`, `skip_runtime`, `skip_mcp`, `skip_grpc`, `skip_in_memory_fallbacks`) to support different deployment topologies.

#### 2.1.2 Desktop Entry Point (`app/desktop_entry.py`)

The canonical entry point for desktop-native mode. It forces the runtime into gRPC mode and SQLite before any app imports occur:

```python
# Forces AGENTOS_RUNTIME_MODE=grpc
# Forces RUNTIME_MODE=grpc
# Forces DATABASE_URL=sqlite+aiosqlite:///~/.agentos/agentos.db
# Starts AgentKernel
# Starts embedded GRPCServer in background task
```

This ensures zero dependency on PostgreSQL, Redis, or FastAPI in the desktop path.

#### 2.1.3 Runtime (`app/runtime/`)

The `AgentRuntime` is a singleton that serves as the execution entry point. In desktop mode, it is owned by `AgentKernel`.

```
AgentRuntime (singleton)
  ├── AgentFactory → creates BaseAgent instances from config
  ├── DynamicAgentFactory → versioned agent creation with health checks
  ├── AgentPool → in-process concurrency semaphore (max 100)
  ├── WorkerPoolManager → Redis-backed cross-process pool (cloud only)
  ├── AgentLifecycleManager → FSM (CREATED→REGISTERED→ACTIVE→EXECUTING→IDLE→DECOMMISSIONED)
  ├── HorizontalScalingCoordinator → Redis-backed cluster coordination (cloud only)
  ├── ResourceLimitEnforcer → concurrent agents, connections, memory
  ├── GRPCServer → wraps RuntimeService + CheckpointService + WorkerService
  │   ├── RuntimeServiceImpl → delegates to AgentKernel (primary) or Orchestrator (legacy)
  │   ├── CheckpointServiceImpl → delegates to SQLiteCheckpointSaver
  │   └── WorkerServiceImpl → delegates to AgentKernel or Orchestrator
  └── WorkerExecutorServer → standalone gRPC server for Go→Python bridge
```

**AgentWorker** wraps an agent config + instance with an async inbox queue. Workers are registered via `runtime.register(agent_id, config)` which acquires a pool slot, creates the agent via factory, and starts the worker's inbox loop.

**DynamicAgentFactory** extends the factory with versioned agent creation, supporting `create_from_config()`, `create_batch()`, and `health_check_agent()`.

---

### 2.2 Desktop-Native Kernel (`app/desktop_native/`)

The `desktop_native/` package is a **local-first, desktop-native runtime layer** that replaces the distributed server stack (Celery, Redis, PostgreSQL) with a single asyncio process using SQLite as the single source of truth. When `AGENTOS_RUNTIME_MODE` is set to `grpc`, this package becomes the primary execution substrate.

**Total source files:** 21 Python modules  
**Total lines of code:** ~5,256 lines

#### Architecture Pattern

```
AgentKernel (kernel.py)
  ├── SQLite Store (sqlite_store.py) — WAL-mode aiosqlite
  ├── Task Queue (task_queue.py) — SQLite-backed priority queue
  ├── State Machine (state_machine.py) — 8-state FSM with transition history
  ├── Event Bus (event_bus.py) — asyncio.Queue pub/sub with SQLite persistence
  ├── Execution Locks (locks.py) — per-task asyncio.Lock with SQLite records
  ├── Timeout Enforcer (timeouts.py) — asyncio.wait_for with SQLite deadlines
  ├── Resource Monitor (resource_monitor.py) — per-task CPU/memory/runtime budgets
  ├── Memory Hierarchy (memory_hierarchy.py) — 4-tier memory system
  ├── Crash Recovery (crash_recovery.py) — scans SQLite on startup, resumes tasks
  ├── Capability Manager (capability_manager.py) — scoped token approval gate
  ├── Cost Tracker (cost_tracker.py) — local cost estimation and aggregation
  ├── Tauri Bridge (tauri_bridge.py) — emits events toward Tauri GUI
  ├── Local Auth (local_auth.py) — OS-identity-based key generation
  ├── Local Logger (local_logger.py) — rotating JSON file logs
  ├── Local Metrics (local_metrics.py) — in-memory metrics with SQLite snapshots
  ├── Local Tracer (local_tracer.py) — SQLite-based span storage
  ├── Local Alerts (local_alerts.py) — rule-based alerting with cooldown
  ├── Sandbox (sandbox.py) — restricted subprocess execution
  └── SQLite Tuning (sqlite_tuning.py) — pragma optimization and maintenance
```

#### AgentKernel (`kernel.py`)

The unified execution kernel. It owns the event loop, worker pool, task lifecycle, crash recovery, and GC.

**Public API:**
- `async start()` — initializes all subsystems, runs crash recovery, starts worker loops and GC
- `async stop(timeout=30.0)` — graceful shutdown with cancellation
- `async submit_task(query, user_id="system", config=None, priority=NORMAL) -> str` — returns task_id
- `async wait_for_task(task_id, timeout=None) -> Dict[str, Any]` — blocks until completion
- `async get_task_status(task_id) -> Dict[str, Any]`
- `async cancel_task(task_id) -> bool`
- `async list_tasks(status=None, limit=100) -> List[Dict]`

**Internal Details:**
- Uses `asyncio.Semaphore(max_concurrent_tasks=5)` for concurrency cap
- Polls resource violations every 2s during task execution
- Lazy imports to avoid circular deps: `AgentRuntime`, `Orchestrator`, `SQLiteCheckpointSaver`, `desktop_session_manager`, `tauri_bridge`
- GC loop (`_gc_loop`) every 60s closes stale desktop sessions, expired locks, old events, and runs SQLite vacuum

#### SQLite Store (`sqlite_store.py`)

Singleton `aiosqlite` connection manager. Single-writer, multi-reader with WAL mode.

**Tables created by `initialize_schema()`:**

| Table | Purpose |
|---|---|
| `task_queue` | Local task queue with priority/score indexing |
| `task_state` | Current state machine state per task |
| `state_transitions` | Immutable history of state changes |
| `execution_locks` | Distributed-style lock records |
| `timeout_configs` | Per-task timeout configuration |
| `timeout_deadlines` | Deadline tracking per scope |
| `cost_records` | Token/cost accounting |
| `event_log` | Persisted event bus for recovery |
| `local_workers` | Worker pool registration and load tracking |
| `capability_tokens` | Scoped capability approval tokens |
| `recovery_log` | Crash recovery actions |
| `gui_task_history` | Task history for GUI dashboard |
| `metrics_snapshots` | Periodic metric persistence |
| `traces` | Local trace span storage |
| `short_term_memory` | TTL-backed short-term memory |
| `long_term_memory` | Long-term memory with optional sqlite-vec |
| `episodic_memory` | Task history for episodic recall |
| `local_auth` | API key hashes for local auth |

#### Task Queue (`task_queue.py`)

SQLite-backed priority queue replacing Redis sorted sets.

**Key Methods:**
- `async enqueue(...) -> QueuePosition` — score = `(priority * 1e12) + timestamp`
- `async dequeue(worker_id) -> Optional[QueuedTask]` — atomic UPDATE with worker assignment
- `async complete(task_id) -> bool`
- `async fail(task_id, error) -> bool`
- `async requeue(task_id, priority=None, delay_seconds=0) -> bool`

#### State Machine (`state_machine.py`)

Finite state machine with 8 `TaskState` values.

```
PENDING → PLANNING → EXECUTING → VERIFYING → AWAITING_APPROVAL → COMPLETED
                                               ↓                                    FAILED
                                         REJECTED                                 CANCELLED
```

Valid transitions are enforced with `AgentOSError` on invalid attempts. All transitions are persisted to `state_transitions` table with 30-day retention.

#### Event Bus (`event_bus.py`)

`asyncio.Queue`-based pub/sub with SQLite persistence for recovery. Every event is logged to `event_log` table. Supports `get_recent_events(channel, limit=100)` for replay on reconnect.

#### Capability Manager (`capability_manager.py`)

Scoped token management for sensitive tool approval.

**Sensitive Capabilities (auto-approved in desktop mode with audit logging):**
- `desktop_env__*` (all desktop automation tools)
- `shell__execute_command`, `shell__run_command`
- `filesystem__delete_file`, `filesystem__delete_directory`
- `browser__navigate`
- `email__send`

**Token Flow:**
1. `request_capability(target, task_id)` checks for existing active token
2. Non-sensitive tools get `APPROVED` immediately
3. Sensitive tools get `PENDING` then auto-approved with `approved_by="auto_desktop"` (configurable to hook into Tauri dialog)
4. `use_capability(token_id)` checks expiry and max_uses

---

### 2.3 Go Supervisor (`supervisor/`)

The Supervisor is the **local-native control plane** written in Go 1.23. It runs on port 8080 and manages child processes (Python desktop runtime, gRPC servers, MCP servers).

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

#### Process Spawning

```
Go Supervisor (:8080)
  ├── Python Desktop Runtime (python -m app.desktop_entry, :50051)
  ├── Checkpoint gRPC Server (in-process, :50052, TLS + API key)
  ├── Python Executor (app.workers.executor_server, optional)
  └── MCP Servers (ports 8001–8007, external)
```

The Supervisor spawns `python -m app.desktop_entry` (not FastAPI), then connects to it as a **gRPC client** on `localhost:50051`. All task HTTP handlers proxy to the Python gRPC server.

#### HTTP Routes

| Method | Path                          | Handler                     |
|--------|-------------------------------|-----------------------------|
| GET    | /health                       | Health check                |
| GET    | /status                       | Supervisor state + metrics  |
| POST   | /api/v1/tasks                 | Create task (proxy → gRPC)  |
| GET    | /api/v1/tasks                 | List tasks (proxy → gRPC)   |
| GET    | /api/v1/tasks/{id}            | Get task (proxy → gRPC)     |
| POST   | /api/v1/tasks/{id}/cancel     | Cancel task (proxy → gRPC)  |
| POST   | /api/v1/tasks/{id}/approve    | Approve task (proxy → gRPC) |
| POST   | /api/v1/tasks/{id}/reject     | Reject task (proxy → gRPC)  |
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

---

### 2.4 Rust CLI (`cli/`)

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

---

### 2.5 Rust TUI (`tui/`)

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

---

### 2.6 Rust Desktop Automation (`desktop/`)

A native Windows desktop automation service using Win32 API via the `windows` crate, exposed via gRPC.

#### Desktop Protocol (desktop.proto)

**Service:** `DesktopAutomation` with 11 RPCs:

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

---

### 2.7 Tauri GUI (`gui/`)

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

### 3.2 AgentKernel

The `AgentKernel` (`app/desktop_native/kernel.py`) is the unified desktop-native runtime. It replaces the fragmented distributed stack with a single asyncio process.

**Design Principles:**
- Single process, single event loop
- SQLite as the single source of truth
- `asyncio.PriorityQueue` for task scheduling (backed by SQLite)
- Direct LangGraph invocation (no Celery hop)
- Cooperative cancellation via `asyncio.Task.cancel()`

**Execution Flow:**
```
User Request -> AgentKernel.submit_task()
    -> SQLite INSERT -> TaskQueue.enqueue()
    -> StateMachine.reset_state(PENDING)
    -> EventBus.publish("task:submitted")

Worker Loop -> TaskQueue.dequeue()
    -> StateMachine.transition(EXECUTING)
    -> ExecutionLock.acquire()
    -> TimeoutEnforcer.set_config()
    -> ResourceMonitor.start_monitoring()
    -> Orchestrator.execute_task()
    -> Result -> StateMachine.transition(COMPLETED/FAILED)
    -> EventBus.publish("task:updated")
    -> TauriBridge.notify_task_complete()
```

**Crash Recovery:** On startup, `crash_recovery.scan_and_resume(kernel)` scans the SQLite `tasks` table for non-terminal states (`pending`, `planning`, `executing`, `paused`) and resubmits them to the kernel.

**GC Loop:** Every 60 seconds, the kernel's `_gc_loop()`:
- Closes stale desktop sessions (`desktop_session_manager.close_all()`)
- Releases expired execution locks
- Cleans up old events (7-day TTL)
- Runs SQLite vacuum if needed

### 3.3 Agent System

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
  │   │   ├── CapabilityManager.request_capability() → token approval
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

### 3.4 Orchestrator

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
| `event_bus.py` | 87 | `RedisEventBus` / `LocalEventBus` | Mode-aware event bus |
| `queue.py` | 571 | `TaskQueue` | Redis priority queue with local fallback |
| `locks.py` | 316 | `ExecutionLock` | Distributed execution lock with local fallback |
| `state_machine.py` | 368 | `TaskStateMachine` | Task FSM (8 states) with local fallback |
| `idempotency.py` | 320 | `IdempotencyEnforcement` | SHA-256 dedup |
| `timeouts.py` | 367 | `TimeoutEnforcer` | Agent/tool/workflow/step timeouts with local fallback |
| `isolation.py` | 363 | `FailureIsolator` | Circuit breaker (3 failures) |
| `loop_detector.py` | 308 | `InfiniteLoopDetector` | SHA-256 fingerprint loop detection |
| `modes/` | 394 | 4 ModeStrategy classes | Task, Workflow, Autonomous, Collaboration |

**Mode-Aware Delegation:** When `RUNTIME_MODE=grpc`, the orchestrator's queue, state machine, locks, timeouts, and event bus all delegate to their `desktop_native/` equivalents:
- `orchestrator/queue.py` → `desktop_native/task_queue.py`
- `orchestrator/state_machine.py` → `desktop_native/state_machine.py`
- `orchestrator/locks.py` → `desktop_native/locks.py`
- `orchestrator/timeouts.py` → `desktop_native/timeouts.py`
- `orchestrator/event_bus.py` → `desktop_native/event_bus.py`

### 3.5 Model Context Protocol (MCP)

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
| `browser.py` | 10 tools (launch, navigate, click, type, screenshot, etc.) | Playwright-based, task-scoped browser sessions with TTL reaper |
| `document.py` | parse, parse_pdf, parse_docx, parse_txt, parse_markdown, chunk, summarize | Multi-format support, LLM summarization, chunking with overlap |
| `code.py` | run_python | ToolSandbox restricted execution, AST-level import blocking |
| `_stdio_sanitize.py` | — | Critical: patches print/logging to stderr to protect JSON-RPC transport |

#### Stdio Transport Protection

Every MCP server imports `app.mcp.servers._stdio_sanitize` as its very first import. This module:
- Patches `builtins.print` to default to `sys.stderr`
- Forces `logging.basicConfig(stream=sys.stderr, force=True)`
- Redirects any existing stdout `logging.Handler` streams to stderr
- Suppresses noisy third-party logs (comtypes, httpx, openai, playwright, etc.)

This ensures JSON-RPC framing over stdio is never corrupted by accidental stdout writes.

### 3.6 Tool System

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
  ├── CapabilityManager → scoped token approval for sensitive tools
  └── FastFileDiscovery → tiered file search engine
```

#### Tool Execution Flow

```
ToolRegistry.execute(tool_name, params)
  │
  ├── 1. ToolInputValidator.validate() → schema check + type check
  ├── 2. SafetyGate.check_tool_call() → severity (SAFE/WARNING/IRREVERSIBLE)
  ├── 3. CapabilityManager.request_capability() → token approval for sensitive tools
  ├── 4. ToolPermissions.check_permission() → RBAC check
  ├── 5. Credential sanitization (desktop tool params)
  ├── 6. TimeoutEnforcer.enforce_tool() → asyncio.wait_for()
  ├── 7. Tool execution:
  │   ├── Built-in: execute directly
  │   ├── MCP: MCPClientManager.call_tool()
  │   └── Desktop: DesktopEnvTool.execute()
  ├── 8. ToolCostTracker.record()
  ├── 9. ObservabilityBus.emit() → event
  └── 10. Return ToolOutput(success, result, error, metadata)
```

#### Capability Enforcement

Sensitive tools require a capability token before execution:

```python
# Severity levels:
#   IRREVERSIBLE — blocks execution without explicit approval
#   WARNING     — requires human confirmation
#   SAFE        — allows execution

# Sensitive capabilities (auto-approved in desktop mode with audit logging):
#   desktop_env__* → auto-approved by "auto_desktop"
#   shell__execute_command → auto-approved by "auto_desktop"
#   filesystem__delete_file → auto-approved by "auto_desktop"
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

### 3.7 Memory & Persistence

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
│  │  SQLite (WAL)│  │    Redis     │  │  PostgreSQL  │  │
│  │  (desktop    │  │  (cloud cache│  │  (cloud      │  │
│  │   primary)   │  │   /TTL)      │  │   durable)   │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────┘
```

#### ORM Models (`app/memory/models.py` — 37 tables)

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
| UserMemoryProfileModel | user_memory_profiles | id, user_id, learned_patterns, preferences, common_tasks |
| ArtifactModel | artifacts | id, artifact_id, task_id, agent_id, artifact_type, uri |
| AgentStateTransitionModel | agent_state_transitions | id, agent_id, from_state, to_state, triggered_by |
| TaskQueueEntryModel | task_queue | id, task_id, user_id, priority, status, worker_id |

#### Repository Classes (16 singletons)

All repositories live in `app/memory/long_term.py` as singletons:

```python
db = Database()
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
| `short_term_memory` | `short_term.py` | Redis (cloud) / In-memory (desktop) | 1 hour |
| `session_memory` | `session_memory.py` | Redis (cloud) / In-memory (desktop) | 2 hours |
| `task_memory` | `task_memory.py` | Redis (cloud) / In-memory (desktop) | 1 hour |
| `user_memory` | `user_memory.py` | Redis + PostgreSQL (cloud) / SQLite (desktop) | cache-through |
| `workflow_memory` | `workflow_memory.py` | PostgreSQL (cloud) / SQLite (desktop) | — |
| `persistent_memory` | `persistent.py` | Redis + PostgreSQL (cloud) / SQLite (desktop) | TTL + LRU |
| `artifact_store` | `artifact_store.py` | Filesystem + PostgreSQL + Redis (cloud) / Filesystem + SQLite (desktop) | — |

#### In-Memory Fallbacks (`app/memory/in_memory.py`)

When `AGENTOS_RUNTIME_MODE=grpc`, Redis is unavailable. This module provides drop-in replacements:

- **`_ExpiringDict`** — async get/set/delete with lazy TTL eviction
- **`_InMemorySortedSet`** — mimics Redis sorted sets for priority queuing
- **`InMemoryPubSub`** — asyncio.Queue-based pub/sub
- **`InMemoryDistributedLock`** — prefix-based lock records in expiring dict
- **`InMemoryTaskQueue`** — priority queue using sorted set + metadata dict
- **`InMemorySessionStore`** — TTL-backed browser/env session storage
- **`InMemoryShortTermMemory`** — TTL-backed context storage

### 3.8 Task Queue & State Machine

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

The `TaskStateMachine` enforces valid transitions with hierarchical persistence: in-memory → Redis cache (cloud) → SQLite durable (desktop).

#### Priority Task Queue

The `TaskQueue` uses Redis sorted sets (score = priority × 10¹² + timestamp) in cloud mode, or SQLite-backed priority scoring in desktop mode:

| Priority | Value | Use Case |
|----------|-------|----------|
| CRITICAL | 0 | System tasks, error recovery |
| HIGH | 1 | User-facing interactive tasks |
| NORMAL | 2 | Default task priority |
| LOW | 3 | Background processing |

Key operations: `enqueue()` → INSERT/UPDATE, `dequeue()` → atomic SELECT+UPDATE (desktop) or ZPOPMIN + HGETALL (cloud), `complete()` → DELETE/UPDATE.

### 3.9 Execution Modes

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

### 3.10 Capability System

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

The `VerificationEngine` validates task output against expected outcomes using configurable strategies (LLM-based, schema-based, regex-based). Desktop verification uses `tasklist`/`pgrep`, `app_launcher.is_process_running`, and `pygetwindow`. Window focus verification uses `ctypes` (`GetForegroundWindow`) on Windows.

### 3.11 Action v1 Framework

The legacy v1 framework (`app/action_v1/`) provides deterministic execution for well-known task types:

| Component | Module | Role |
|-----------|--------|------|
| `ActionV1Runner` | `runner.py` | Fast-path execution of v1 actions |
| `CapabilitySelector` | `selector.py` | Matches queries to v1 capability templates |
| `DeterministicExecutor` | `executor.py` | Executes known action sequences |
| `ActionVerifier` | `verifier.py` | Verifies action outcomes |
| `FallbackHandler` | `fallback.py` | Falls back to LangGraph on v1 failure |

Supported actions: open notepad, write text, open calculator, create spreadsheet, search web, launch browser, create HTML file, etc.

### 3.12 Workflow Engine

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
- **Persistence**: Full DAG (nodes + edges) persisted to SQLite (desktop) or PostgreSQL (cloud)

### 3.13 Guardrails & Safety

#### Input Guardrails

The `InputValidator` (`middleware/validation.py`) intercepts task creation POST requests:

- Blocked keyword patterns (configurable)
- Maximum query length enforcement (10,000 chars)
- SQL injection pattern detection
- Path traversal detection
- Dangerous command patterns: `rm -rf /`, `DROP TABLE`, `FORMAT C:`, `dd if=/dev/zero`, `mkfs.`, `shutdown /s`

#### Safety Gate

The `SafetyGate` (`tools/safety/`) classifies every tool call:

```python
# Severity levels:
#   IRREVERSIBLE — blocks execution without explicit approval
#   WARNING     — requires human confirmation
#   SAFE        — allows execution

# Forbidden tools:
#   filesystem__delete_file, filesystem__delete_directory
#   email__send, slack__post_message, payment__process
#   database__drop_table, aws__terminate_instance
#   github__delete_repository, docker__remove_container

# Dangerous patterns:
#   rm -rf, drop, delete, payment, purchase, buy, transfer
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

### 4.1 gRPC Services (Primary)

In desktop-native mode, gRPC is the primary inter-process communication protocol between the Go Supervisor and the Python runtime.

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

**Service Implementation (`app/runtime/grpc_server.py`):**
- `RuntimeServiceImpl.CreateTask`: prefers `AgentKernel.submit_task()` with background monitoring; falls back to `Orchestrator.execute_task()`
- `RuntimeServiceImpl.GetTask`: syncs with kernel status if available
- `RuntimeServiceImpl.CancelTask`: delegates to kernel or in-memory store
- `RuntimeServiceImpl.GetRuntimeStatus`: returns metrics from kernel or runtime
- `RuntimeServiceImpl.Shutdown`: `kernel.stop()` or `runtime.shutdown_all()`

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

**Service Implementation:** `CheckpointServiceImpl` delegates to `SQLiteCheckpointSaver` (`app/langgraph/sqlite_checkpointer.py`).

#### WorkerExecutor (worker.proto)

```protobuf
service WorkerExecutor {
  rpc ExecuteTask(TaskRequest) returns (TaskResponse);
  rpc HealthCheck(HealthRequest) returns (HealthResponse);
}
```

**Service Implementation:** `WorkerServiceImpl` delegates to `Kernel.submit_task/wait_for_task`, or `Orchestrator.ainvoke()`, or runtime fallback.

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

### 4.2 FastAPI HTTP Endpoints (Secondary)

FastAPI endpoints are available in cloud/HTTP mode (`RUNTIME_MODE=http`). In desktop mode, the Go Supervisor proxies HTTP requests to the Python gRPC server.

All endpoints under `/api/v1/` (except auth and desktop) require JWT Bearer token or API key authentication in cloud mode. Desktop mode uses local auth (`local_auth.py`).

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
| GET | /health/ready | Readiness probe (DB + optional Redis) |
| GET | /health/live | Liveness probe |
| GET | /health/metrics | Prometheus-format metrics |
| GET | /metrics | Aggregated metrics JSON |

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

### 5.1 SQLite Tables (Desktop-Native Primary)

In desktop-native mode, SQLite (`~/.agentos/agentos.db`, WAL mode) is the single source of truth. All desktop-native subsystems persist to this database.

#### Core Tables

```sql
-- Desktop-native task queue
CREATE TABLE task_queue (
    id TEXT PRIMARY KEY,
    task_id TEXT UNIQUE NOT NULL,
    user_id TEXT DEFAULT 'system',
    query TEXT NOT NULL,
    priority INTEGER DEFAULT 2,
    priority_score REAL NOT NULL,
    config TEXT,
    idempotency_key TEXT,
    scheduled_for TEXT,
    worker_id TEXT,
    status TEXT DEFAULT 'queued',
    retry_count INTEGER DEFAULT 0,
    enqueued_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Task state machine current state
CREATE TABLE task_state (
    task_id TEXT PRIMARY KEY,
    current_state TEXT DEFAULT 'pending',
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Immutable state transition history
CREATE TABLE state_transitions (
    transition_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    from_state TEXT NOT NULL,
    to_state TEXT NOT NULL,
    timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
    triggered_by TEXT DEFAULT 'system',
    context TEXT
);

-- Execution locks
CREATE TABLE execution_locks (
    lock_id TEXT PRIMARY KEY,
    task_id TEXT UNIQUE NOT NULL,
    owner TEXT DEFAULT 'system',
    acquired_at TEXT DEFAULT CURRENT_TIMESTAMP,
    expires_at TEXT,
    ttl_seconds INTEGER
);

-- Timeout configuration and deadlines
CREATE TABLE timeout_configs (
    task_id TEXT PRIMARY KEY,
    agent_timeout_seconds INTEGER DEFAULT 60,
    tool_timeout_seconds INTEGER DEFAULT 30,
    workflow_timeout_seconds INTEGER DEFAULT 300,
    step_timeout_seconds INTEGER DEFAULT 60,
    max_total_seconds INTEGER DEFAULT 600
);

CREATE TABLE timeout_deadlines (
    task_id TEXT NOT NULL,
    scope TEXT NOT NULL,
    deadline_timestamp REAL NOT NULL,
    configured_seconds INTEGER NOT NULL,
    started_at TEXT DEFAULT CURRENT_TIMESTAMP,
    triggered INTEGER DEFAULT 0,
    PRIMARY KEY (task_id, scope)
);

-- Cost tracking
CREATE TABLE cost_records (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    scope TEXT NOT NULL,
    scope_id TEXT,
    cost_usd REAL DEFAULT 0,
    tokens_input INTEGER DEFAULT 0,
    tokens_output INTEGER DEFAULT 0,
    model TEXT,
    timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
    metadata TEXT
);

-- Event log for recovery
CREATE TABLE event_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload TEXT,
    source TEXT,
    timestamp TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Local worker registry
CREATE TABLE local_workers (
    worker_id TEXT PRIMARY KEY,
    task_id TEXT,
    status TEXT DEFAULT 'idle',
    registered_at TEXT DEFAULT CURRENT_TIMESTAMP,
    last_heartbeat TEXT
);

-- Capability tokens
CREATE TABLE capability_tokens (
    token_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    scope TEXT NOT NULL,
    target TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    expires_at TEXT,
    last_used_at TEXT,
    use_count INTEGER DEFAULT 0,
    max_uses INTEGER,
    approved_by TEXT
);

-- Recovery log
CREATE TABLE recovery_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    action TEXT NOT NULL,
    old_state TEXT,
    new_state TEXT,
    timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
    details TEXT
);

-- GUI task history
CREATE TABLE gui_task_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    query TEXT,
    status TEXT,
    success INTEGER,
    result TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Memory hierarchy
CREATE TABLE short_term_memory (
    key TEXT PRIMARY KEY,
    value TEXT,
    expires_at REAL
);

CREATE TABLE long_term_memory (
    key TEXT PRIMARY KEY,
    content TEXT,
    metadata TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE episodic_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    query TEXT,
    result TEXT,
    status TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Local auth
CREATE TABLE local_auth (
    key_hash TEXT PRIMARY KEY,
    api_key_prefix TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    revoked_at TEXT
);

-- Metrics snapshots
CREATE TABLE metrics_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    metric_name TEXT NOT NULL,
    metric_type TEXT NOT NULL,
    value REAL NOT NULL,
    labels TEXT,
    timestamp TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Traces
CREATE TABLE traces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trace_id TEXT NOT NULL,
    span_id TEXT NOT NULL,
    operation TEXT NOT NULL,
    agent_name TEXT,
    start_time TEXT,
    end_time TEXT,
    status TEXT,
    error TEXT,
    metadata TEXT
);
```

### 5.2 PostgreSQL Tables (Cloud Optional)

When running in cloud mode (`RUNTIME_MODE=http`), PostgreSQL is used for durable storage. The schema is identical to the SQLite schema above with PostgreSQL-specific types (UUID, JSONB, TIMESTAMP WITH TIME ZONE).

See the original schema in `app/memory/models.py` and migration files in `migrations/`.

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

The migration runner (`app/migrations/runner.py`) supports both PostgreSQL and SQLite with automatic DDL translation:
- `TIMESTAMP WITHOUT TIME ZONE` → `TEXT`
- `UUID` → `TEXT`
- `SERIAL` → `INTEGER PRIMARY KEY AUTOINCREMENT`
- `JSONB` → `TEXT`
- `DOUBLE PRECISION` → `REAL`
- `NOW()` → `CURRENT_TIMESTAMP`

---

## 6. Configuration

### 6.1 Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENAI_API_KEY` | Yes | — | OpenAI API key for LLM access |
| `OPENAI_MODEL` | No | gpt-4o | Default OpenAI model |
| `DATABASE_URL` | Yes* | `sqlite+aiosqlite:///~/.agentos/agentos.db` | Database connection string |
| `REDIS_URL` | Yes* | — | Redis connection string (*not required in gRPC mode) |
| `SECRET_KEY` | Yes* | — | JWT signing secret (*not required in desktop mode) |
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

**Desktop mode defaults:** When `AGENTOS_RUNTIME_MODE=grpc`, `desktop_entry.py` automatically:
- Sets `DATABASE_URL` to `sqlite+aiosqlite:///~/.agentos/agentos.db`
- Skips Redis validation
- Skips SECRET_KEY validation
- Disables Celery

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

Four gRPC services define the protocol between components:

| Service | Proto File | Defined In | Lines | Client | Server |
|---------|-----------|------------|-------|--------|--------|
| RuntimeService | `runtime.proto` | supervisor/proto/ | 293 | Go | Python (:50051) |
| CheckpointService | `checkpoint.proto` | supervisor/proto/ | 170 | Python | Go (:50052) |
| WorkerExecutor | `worker.proto` | supervisor/proto/ | 43 | Go | Python (:50051) |
| DesktopAutomation | `desktop.proto` | desktop/ | 222 | Python | Rust (:50051) |

### 7.2 Inter-Process Communication

| From | To | Protocol | Method | Authentication |
|------|----|----------|--------|----------------|
| CLI/TUI | Supervisor | HTTP/JSON | REST | None (localhost) |
| GUI frontend | Supervisor | HTTP/JSON | REST | None (localhost) |
| GUI frontend | Supervisor | WebSocket | Events | Connection upgrade |
| Supervisor | Python Runtime | gRPC | RPC | Insecure (localhost) |
| Python | Go (checkpoints) | gRPC | RPC | mTLS + API key |
| Go | Python (executor) | gRPC | RPC | API key |
| Python | Python (MCP servers) | JSON-RPC | stdio | None |
| Python | Redis | TCP | Redis protocol | Optional password (cloud only) |
| Python | PostgreSQL | TCP | asyncpg | Password (cloud only) |
| Python | SQLite | File | aiosqlite | File permissions (desktop) |
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

#### Task Queue Message (SQLite / Redis)

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
- Docker & Docker Compose (optional, for cloud mode testing)

**Note:** Redis and PostgreSQL are optional. The system runs fully in desktop-native mode with only SQLite.

### 8.2 Local Setup

```bash
# Clone the repository
git clone https://github.com/Chandankumar123456/agentos.git
cd agentos

# Python backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Copy environment template (optional for desktop mode)
cp .env.example .env
# Edit .env with your API keys. In desktop mode, you only need OPENAI_API_KEY.

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

**Desktop-Native Mode (Recommended):**

```bash
# Start the Go Supervisor (spawns Python runtime automatically)
cd supervisor
.\supervisor.exe

# Or start Python desktop runtime directly
.\.venv\Scripts\python.exe -m app.desktop_entry

# Start Rust desktop automation server (optional, Windows only)
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

**Cloud Mode (FastAPI + PostgreSQL + Redis):**

```bash
# Start infrastructure (PostgreSQL + Redis)
docker-compose -f docker/docker-compose.yml up -d postgres redis

# Run database migrations
python -m app.migrations.runner

# Start Python backend (HTTP mode)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 8.4 Testing

```bash
# Run all Python tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=app --cov-report=term-missing

# Run specific test categories
pytest tests/unit/test_phase2_desktop_native.py -v
pytest tests/unit/test_phase4_security.py -v
pytest tests/unit/test_phase5_observability.py -v
pytest tests/unit/test_phase6_ui_integration.py -v
pytest tests/unit/test_phase7_optimization.py -v

# Run integration tests
pytest tests/integration/test_grpc_integration.py -v
pytest tests/integration/test_desktop_agent_e2e.py -v

# Run connection audit
pytest tests/unit/test_connection_audit.py -v

# Run stress tests
pytest tests/stress/ -v

# Run action v1 benchmarks
pytest tests/test_action_v1_benchmarks.py -v

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

# Go: linting
cd supervisor && golangci-lint run && cd ..

# Rust: linting
cd cli && cargo clippy && cd ..
```

---

## 9. Deployment

### 9.1 Native Desktop Build

**Binary targets:**

| Component | Build Command | Output |
|-----------|---------------|--------|
| Go Supervisor | `cd supervisor && go build -o supervisor.exe` | `supervisor/supervisor.exe` |
| Rust CLI | `cd cli && cargo build --release` | `cli/target/release/agentos.exe` |
| Rust TUI | `cd tui && cargo build --release` | `tui/target/release/agentos-tui.exe` |
| Rust Desktop | `cd desktop && cargo build --release` | `desktop/target/release/desktop-automation.exe` |
| Tauri GUI | `cd gui && cargo tauri build` | `gui/src-tauri/target/release/agentos-gui.exe` |

**Desktop deployment checklist:**

1. Set `OPENAI_API_KEY` in environment or via GUI settings (stored in OS keychain)
2. Ensure `~/.agentos/` directory is writable (SQLite database, logs, checkpoints)
3. Build Supervisor and place in PATH or bundle with GUI
4. Configure auto-start daemon in GUI settings
5. Set proper log levels for production (`INFO` or `WARNING`)
6. Enable global shortcuts if desired (Ctrl+Shift+A/S/Q)
7. Test gRPC connection: `curl http://localhost:8080/health`
8. Verify SQLite database is created at `~/.agentos/agentos.db`

### 9.2 Docker Deployment (Cloud Mode)

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

### 9.3 Configuration

**Production checklist (cloud mode):**

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

### 10.1 Desktop-Native First

**Decision:** The local machine is the primary and only execution environment by default. Network connectivity is used exclusively for cloud LLM inference and optional sync.

**Rationale:** AgentOS is a desktop-native AI runtime, not a web application with desktop features. The previous web-oriented architecture (FastAPI + Celery + Redis + PostgreSQL as mandatory dependencies) created runtime ambiguity, state ownership conflicts, and unnecessary operational fragility for a single-user local application.

**Implementation:**
- `app/desktop_entry.py` is the canonical entry point, forcing SQLite and gRPC mode
- `app/desktop_native/` provides 21 modules replacing Redis/PostgreSQL/Celery with local asyncio + SQLite equivalents
- `AgentKernel` owns the event loop, task queue, and agent pool in a single process
- Go Supervisor spawns `python -m app.desktop_entry` and connects as a gRPC client
- Redis and PostgreSQL are completely optional; the system boots and runs with zero external infrastructure

### 10.2 LangGraph-First Execution

**Decision:** The orchestrator always tries LangGraph execution first, with two fallback layers.

**Rationale:** LangGraph provides structured state graphs with checkpoint/rollback, enabling robust recovery. The fallback chain (LangGraph → Checkpoint Recovery → Legacy Pipeline) ensures availability even when the primary path fails.

**Implementation:** `Orchestrator.execute_task()` → `TaskRunner.run()` (LangGraph) → `CheckpointRecoveryService.recover()` → `ModeStrategyFactory.get().execute()`.

### 10.3 Adaptive Execution Routing

**Decision:** Tasks are classified into 3 tiers with progressively more sophisticated execution.

| Tier | Name | Execution | Latency | Use Case |
|------|------|-----------|---------|----------|
| 0 | Direct | Single tool call | ~100ms | Open app, calculate, search |
| 1 | Sequential | Multi-step, no graph | ~500ms | Type text, create file |
| 2 | Full Runtime | LangGraph compilation | ~2s+ | Complex multi-step tasks |

**Rationale:** Simple tasks (open notepad, calculate 2+2) do not need LangGraph state compilation overhead. The `TaskComplexityRouter` uses regex-based intent extraction to make fast routing decisions.

### 10.4 Dual-Mode Runtime

**Decision:** AgentOS supports both HTTP (cloud/FastAPI) and gRPC (local-native) runtime modes.

**Rationale:** In cloud mode, the Python FastAPI server is the primary API. In local mode, the Go Supervisor is the primary API, managing Python as a child process. The bootstrap module (`app/bootstrap.py`) is shared between both modes, with mode-specific components loaded conditionally.

**Mode detection:** `AGENTOS_RUNTIME_MODE` environment variable, defaulting to `http`. gRPC mode skips Redis initialization and FastAPI middleware.

### 10.5 Canonical Execution State

**Decision:** `ToolExecutionRecord` in `execution_state.py` is the single source of truth for all execution layers.

**Rationale:** Previously, the tool layer, executor, goal loop, verifier, and recovery each maintained separate success/failure opinions, leading to inconsistency. Now, all downstream layers read from `ExecutionState` instead of re-inferring.

**Key fields:** `tool_name`, `params`, `success`, `result`, `error`, `evidence`, `terminal`. The `terminal` flag auto-detects "deterministic success" for desktop/browser/filesystem operations.

### 10.6 Failure Isolation & Circuit Breakers

**Decision:** Each task executes within an isolated context with circuit breaker protection.

**Pattern:** `FailureIsolator.run_isolated()` wraps task execution with:
1. Context creation (resource limits, timeouts)
2. Failure tracking (after 3 failures, circuit opens)
3. Cleanup on exit (release resources, close sessions)

**Rationale:** Prevents cascading failures where one problematic task exhausts system resources or corrupts shared state.

### 10.7 Inter-Agent Communication

**Decision:** Multiple communication patterns for different scenarios.

- **Direct invocation** for simple coordinator → worker calls
- **MCP message bus** for pub/sub event distribution
- **Handoff protocol** for structured state transfer between agents
- **Consensus engine** for multi-agent agreement on ambiguous results
- **Feedback loop** for learning from past execution patterns

**Rationale:** Different scenarios require different communication properties. Direct invocation is fast and simple; the message bus provides decoupling; handoff provides integrity; consensus provides reliability; feedback provides improvement.

### 10.8 SQLite as Single Source of Truth

**Decision:** In desktop-native mode, SQLite (WAL mode) is the single source of truth for all durable state.

**Rationale:** Previously, task state was split across PostgreSQL rows, Redis keys, LangGraph checkpoints, in-memory Python objects, and Go supervisor state. No single subsystem owned the truth. SQLite provides ACID guarantees, zero configuration, and single-file portability for a single-user desktop runtime.

**Implementation:**
- `DesktopSQLiteStore` manages a single `aiosqlite` connection with WAL mode
- All desktop-native subsystems (queue, state machine, locks, timeouts, events, costs, traces, metrics, memory) persist to SQLite
- `SQLiteTuning` applies production pragmas (cache size, mmap, synchronous=NORMAL, busy timeout)
- Automatic vacuum and integrity checks run periodically

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

In desktop mode, logs are also written to rotating files via `LocalLogger` (`~/.agentos/logs/agentos.log`, 10 MB max, 5 backups).

Key methods: `log_task()`, `log_step()`, `log_tool()`, `log_node()`, `log_error()` — all add structured context fields.

### 11.2 Local Tracing

The `LocalTracer` (`app/desktop_native/local_tracer.py`) provides span-based tracing stored in SQLite:

```python
# Usage in orchestrator:
tracer.start_span(trace_id="task-abc", agent_name="planner", operation="plan")
# ... execution ...
tracer.end_span(span_id="task-abc:plan", status="success")
# Spans are persisted to SQLite 'traces' table
```

Span IDs support human-readable names like `"planner.reasoning:2026-04-25T16:12:52.274630"` (hence VARCHAR(255)).

The `TraceManager` (`app/logs/tracing.py`) bridges to `LocalTracer` in desktop mode, maintaining backward compatibility with cloud mode's PostgreSQL span storage.

### 11.3 Local Metrics

The `LocalMetrics` (`app/desktop_native/local_metrics.py`) exposes counters and histograms with periodic SQLite snapshots:

```
# Prometheus-compatible text format (generated from SQLite snapshots):
# HELP agentos_tasks_total Total tasks executed
# TYPE agentos_tasks_total counter
agentos_tasks_total{status="completed"} 42

# HELP agentos_task_duration_seconds Task execution duration
# TYPE agentos_task_duration_seconds histogram
agentos_task_duration_seconds_bucket{le="0.1"} 10
agentos_task_duration_seconds_bucket{le="0.5"} 25
agentos_task_duration_seconds_bucket{le="+Inf"} 42

# HELP desktop_tasks_total Desktop automation tasks
# TYPE desktop_tasks_total counter
desktop_tasks_total{action="screenshot"} 15
desktop_tasks_total{action="click"} 30
```

Snapshot interval: 60 seconds. Cleanup: 30 days.

### 11.4 Anomaly Detection & Alerting

The `AnomalyDetector` uses sliding window statistics (mean + 2 standard deviations) to detect:

- Elevated error rates (e.g., >15% tool failures)
- Latency spikes (e.g., >5s average tool execution)
- Cost anomalies (e.g., sudden token usage increase)
- Loop count anomalies (e.g., >5 repeated attempts)

The `LocalAlertManager` (`app/desktop_native/local_alerts.py`) evaluates default rules with cooldown protection:

| Rule | Metric | Threshold | Severity | Channel |
|------|--------|-----------|----------|---------|
| High Error Rate | error_rate | > 0.15 | WARNING | LOG |
| Critical Error Rate | error_rate | > 0.30 | CRITICAL | LOG + NOTIFICATION |
| High Latency | avg_latency | > 5000ms | WARNING | LOG |
| Cost Spike | cost_rate | > 0.10 | WARNING | LOG |

In desktop mode, critical alerts can trigger Tauri desktop notifications via `TauriBridge`.

### 11.5 Cost Tracking

The `LocalCostTracker` (`app/desktop_native/cost_tracker.py`) records per-invocation costs using `MODEL_COSTS` pricing table:

| Model | Input (per 1K tokens) | Output (per 1K tokens) |
|-------|----------------------|-----------------------|
| gpt-4o | $0.005 | $0.015 |
| gpt-4o-mini | $0.00015 | $0.0006 |
| gpt-4 | $0.03 | $0.06 |
| gpt-3.5-turbo | $0.0005 | $0.0015 |

Tool costs are estimated using baseline tables:
- Filesystem tools: $0
- Shell execution: $0.0001
- Web search: $0.001–$0.002
- LLM interaction: per-token based on model

Costs are aggregated in SQLite with breakdowns by task, agent, user, and tool scope.

---

## 12. Security

### 12.1 Authentication

**Three authentication methods (cloud mode):**

1. **JWT Bearer tokens**: Created on login/signup, short-lived access token (default 30 min) + long-lived refresh token (default 7 days). Uses `python-jose` for JWT encoding with HS256.

2. **API keys**: `sk_` prefix + 32 URL-safe random bytes (hex-encoded). Stored as SHA-256 hash in PostgreSQL. Can be revoked individually.

3. **Password hashing**: bcrypt via `passlib` with SHA-256 preprocessing for passwords >72 bytes. Password strength validation: ≥8 chars, uppercase, lowercase, digit.

**Desktop mode authentication:**

`LocalAuth` (`app/desktop_native/local_auth.py`) uses OS-identity-based key generation:
- Identity derived from `getpass.getuser()` and machine hostname
- Key generation via `secrets.token_urlsafe(32)` with prefix `aos_`
- Encryption: Windows DPAPI (ctypes), macOS/Linux keyring (fallback plaintext)
- All requests from localhost are authorized in desktop mode

### 12.2 Authorization & RBAC

**Roles:** `admin`, `user`, `viewer`

**Permissions:**
- `create_task`, `create_agent`, `create_workflow`
- `delete_any` (admin only)
- `manage_users` (admin only)
- `view_analytics`

**Enforcement:** FastAPI dependency `require_permission(permission)` checks both API key permissions and user role. The `APIKeyMiddleware` sets `request.state.user` and `request.state.api_key_permissions`.

In desktop mode, `local_auth.is_authorized()` always returns `True` for local requests.

### 12.3 Capability-Based Tool Permissions

Role-based tool access control via `ToolPermissions` is augmented by `CapabilityManager` for sensitive operations:

- `planner`: file read/write, web, text processing (no shell)
- `executor`: all tools including shell and desktop
- `verifier`: file read, web (no shell, no desktop)
- `reviewer`: read-only, web
- `coordinator`: all tools
- `admin`: all tools
- Default (no role): deny all

**Capability Token Flow:**
1. Tool registry detects sensitive tool invocation
2. `CapabilityManager.request_capability()` creates scoped token
3. In desktop mode, sensitive capabilities are auto-approved with `approved_by="auto_desktop"` (audit logged)
4. Future: Tauri GUI dialog for interactive approval

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
5. (Optional) If sensitive, add to `CapabilityManager.SENSITIVE_CAPABILITIES`.

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

### 13.5 Adding a Desktop-Native Subsystem

To add a new subsystem to the desktop-native kernel:

1. Create a new module in `app/desktop_native/my_subsystem.py`
2. Use `sqlite_store` for persistence:

```python
from .sqlite_store import sqlite_store
from ..logs.logger import logger

class MySubsystem:
    async def initialize(self):
        await sqlite_store.execute("""
            CREATE TABLE IF NOT EXISTS my_table (
                id TEXT PRIMARY KEY,
                data TEXT
            )
        """)
    
    async def do_something(self, data: str):
        await sqlite_store.execute(
            "INSERT INTO my_table (id, data) VALUES (?, ?)",
            (str(uuid.uuid4()), data)
        )
        await sqlite_store.commit()
```

3. Register initialization in `AgentKernel.start()`:

```python
async def start(self):
    # ... existing init ...
    await my_subsystem.initialize()
    # ... rest of start ...
```

4. Add tests in `tests/unit/test_my_subsystem.py`

---

## 14. Troubleshooting

### Common Issues

| Symptom | Cause | Solution |
|---------|-------|----------|
| `DATABASE_URL is required` | Missing environment variable | In desktop mode, `desktop_entry.py` auto-sets SQLite path. Ensure `AGENTOS_RUNTIME_MODE=grpc` |
| `gRPC not available` | Missing `grpcio-tools` | `pip install grpcio-tools` |
| Playwright errors | Missing browser binaries | `playwright install chromium` |
| Tauri build fails | Missing Rust WASM target | `rustup target add wasm32-unknown-unknown` |
| `module 'app' not found` | Wrong working directory | Run from project root (`E:\Projects\AgentOS`) |
| Supervisor cannot connect to Python | Python runtime not started | Supervisor should auto-spawn `python -m app.desktop_entry`. Check `supervisor.out` logs |
| gRPC connection refused on :50051 | Python gRPC server not running | Run `python -m app.desktop_entry` or restart Supervisor |
| JWT decode errors | Wrong `SECRET_KEY` | In desktop mode, local auth bypasses JWT. Only relevant in cloud mode |
| SQL migration version mismatch | Manual DB changes | Run `python -m app.migrations.runner` |
| WebSocket connection drops | Supervisor not running | Start Go supervisor on port 8080 |
| Desktop automation fails | Windows-specific tools missing | Ensure `pyautogui`, `uiautomation`, `mss` are installed |
| CLI can't connect | Supervisor not running | `agentos daemon start` |
| Rate limited | Too many requests | Wait or adjust `RATE_LIMIT_PER_MINUTE` in `.env` (cloud mode only) |
| SQLite locked | Concurrent writes | SQLite WAL mode handles most concurrency. Ensure no other process holds the DB file |
| Desktop sessions leak | TTL reaper not running | `AgentKernel._gc_loop()` runs every 60s. Ensure kernel is running |
| Capability approval blocks | Sensitive tool without token | In desktop mode, capabilities auto-approve. Check `capability_tokens` table for errors |

### Diagnostic Commands

```bash
# Check supervisor health
curl http://localhost:8080/health

# Check Python gRPC server health
python -c "from app.proto.grpc_client import GRPCClient; import asyncio; c=GRPCClient(); asyncio.run(c.connect()); print('OK')"

# View task trace from SQLite
python -c "
import asyncio
from app.desktop_native.sqlite_store import sqlite_store
async def show():
    await sqlite_store.initialize_schema()
    rows = await sqlite_store.fetchall('SELECT task_id, current_state FROM task_state LIMIT 10')
    for r in rows:
        print(r)
asyncio.run(show())
"

# Test gRPC end-to-end
python scripts/validate_grpc_e2e.py

# Check SQLite database integrity
python -c "
import asyncio
from app.desktop_native.sqlite_tuning import sqlite_tuning
async def check():
    r = await sqlite_tuning.run_integrity_check()
    print(r)
asyncio.run(check())
"

# Reset desktop-native database (WARNING: destroys all data)
rm ~/.agentos/agentos.db

# Check desktop session count
python -c "
from app.environments.desktop_env import desktop_session_manager
print('Sessions:', len(desktop_session_manager._sessions))
"

# Check browser session count
python -c "
from app.environments.browser_env import browser_session_manager
print('Sessions:', len(browser_session_manager._sessions))
"

# View local logs
cat ~/.agentos/logs/agentos.log

# Check capability tokens
python -c "
import asyncio
from app.desktop_native.sqlite_store import sqlite_store
async def show():
    rows = await sqlite_store.fetchall('SELECT token_id, target, status FROM capability_tokens LIMIT 10')
    for r in rows:
        print(r)
asyncio.run(show())
"
```

### Logs

| Component | Log Location | Format |
|-----------|-------------|--------|
| Python backend | stdout (configurable to file) | Text or JSON |
| Desktop-native kernel | `~/.agentos/logs/agentos.log` | JSON (rotating) |
| Go supervisor | stdout + `supervisor.out` | Structured text |
| TUI/CLI | stdout | Formatted text |
| GUI (Tauri) | `~/.local/share/AgentOS/logs/` | Text |
| Desktop automation | stdout | Structured text |

### Getting Help

- Check `docs/superpowers/` for phase plans and design documents
- Review `DESKTOP_NATIVE_MIGRATION_BLUEPRINT.md` for architecture decisions
- Review test files for usage examples
- Check supervisor status: `curl http://localhost:8080/status`
- Run `pytest tests/unit/test_connection_audit.py` to verify zero external dependencies

---

*AgentOS — Local-native autonomous agent runtime. Built with Python, Go, Rust, and TypeScript.*
