# AgentOS Architecture Audit

**Version:** 0.4.0-desktop-native  
**Date:** 2026-05-20  
**Scope:** Full-stack architecture audit documenting the pre-refactor state, problems identified, FastAPI analysis, and the new unified architecture after the core refactor.

---

## 1. Current Architecture Audit (Pre-Refactor State)

Before this refactor, AgentOS had the following characteristics:

### Scale and Complexity

- **232 Python files** (~48,000 lines of code) under `app/`
- Logic scattered across **20+ subdirectories** with overlapping responsibilities
- Multiple entry points: `app/main.py` (FastAPI), `app/desktop_entry.py` (gRPC), `start.sh`

### Duplicate Infrastructure

The most critical issue was that two parallel implementations existed for every piece of infrastructure:

| Concern | Redis/PostgreSQL Version (app/orchestrator/) | SQLite/asyncio Version (app/desktop_native/) |
|---------|----------------------------------------------|-----------------------------------------------|
| Task Queue | `queue.py` - Redis sorted sets | `task_queue.py` - SQLite-backed priority queue |
| Execution Locks | `locks.py` - Redis SETNX mutex | `locks.py` - asyncio.Lock with SQLite records |
| State Machine | `state_machine.py` - Redis + PostgreSQL | `state_machine.py` - SQLite-backed FSM |
| Event Bus | `event_bus.py` - Redis PubSub | `event_bus.py` - asyncio.Queue + SQLite |
| Timeouts | `timeouts.py` - Redis TTL tracking | `timeouts.py` - asyncio.wait_for + SQLite |

### Web-Server-First Entry Point

`app/main.py` was the FastAPI HTTP server treated as the primary entry point. It loaded:
- CORS middleware (web browser cross-origin)
- CSRF protection (form-based web attacks)
- Rate limiting middleware (Redis-backed)
- Request logging middleware
- 17 route modules
- WebSocket handlers

All of this was loaded even when the actual desktop path used gRPC exclusively.

### Celery Workers

`app/queue/` contained Celery worker definitions for background task execution. These were designed for distributed multi-worker deployment but were completely unnecessary for a single-process desktop runtime.

### AgentRuntime Singleton Overreach

The `AgentRuntime` singleton (`app/runtime/runtime.py`) owned:
- A gRPC client connection
- The agent registry
- A Redis-backed initialization mutex
- A `HorizontalScalingCoordinator` (for multi-node cluster scaling)
- A `WorkerPoolManager` (for distributed worker farms)
- Execution entry point methods that just delegated to the Orchestrator

It tried to be an execution entry point, a registry, and a distributed coordinator simultaneously.

### Dead Orchestrator Methods

The `Orchestrator` (`app/orchestrator/core.py`) contained legacy methods:
- `_execute_with_langgraph` - a compatibility shim that just called AgentLoop
- `_execute_pipeline` - another compatibility shim that just called AgentLoop
- `_hydrate_memory_context` - loaded short-term memory from Redis before execution
- `_save_final_state` - persisted results to both Redis and PostgreSQL

All of these ultimately delegated to `AgentLoop.run()`, adding unnecessary indirection.

---

## 2. Problems in the Current Structure

### 2.1 Fragmented Business Logic

Orchestration logic was split across four packages with unclear ownership:

- `app/orchestrator/` - core orchestration, task runner, workflow engine
- `app/runtime/` - agent runtime singleton, factory, pool, scaling
- `app/desktop_native/` - kernel, task queue, state machine, crash recovery
- `app/langgraph/` - graph definitions, state, checkpointer

A developer trying to understand "how does a task execute?" had to trace through all four packages.

### 2.2 Unnecessary Abstraction Layers

The execution path for a single task involved five layers of delegation:

```
AgentRuntime.execute_task()
  -> Orchestrator.execute_task()
    -> AgentLoop.run()
      -> WorkflowEngine.execute()
        -> StepExecutor.execute_step()
```

Each layer added initialization overhead, error handling, and logging without meaningful logic.

### 2.3 Duplicated Execution Paths

As documented in Section 1, every infrastructure concern had both a Redis/distributed version AND a local/asyncio version. Both were maintained, both had tests, and the codebase had conditional logic everywhere to pick the right one based on runtime mode.

### 2.4 Web-Server-First Assumptions

Even in desktop mode, several modules imported FastAPI transitively:
- `app.orchestrator.agent_loop` -> `app.orchestrator.core` -> `app.runtime.runtime` -> FastAPI-related chains
- Middleware modules assumed Redis was available for rate limiting
- Settings validation required CORS_ORIGINS, RATE_LIMIT_PER_MINUTE even in gRPC mode

### 2.5 Dead Architecture

The following components were never used in desktop mode but were loaded/available:
- **Celery workers** (`app/queue/`) - distributed task execution
- **Redis mutex** (`agentos:runtime:init_mutex`) - multi-process initialization lock
- **HorizontalScalingCoordinator** (`app/runtime/scaling.py`) - multi-node cluster coordination
- **WorkerPoolManager** - cross-process worker farm management
- **PostgreSQL repositories** - 16 repository classes for cloud persistence

### 2.6 State Ownership Confusion

Task state existed simultaneously in:
1. **PostgreSQL** - via SQLAlchemy ORM models (37 models)
2. **Redis** - cached state, pub/sub events, distributed locks
3. **LangGraph checkpoints** - execution graph state
4. **In-memory Python dicts** - runtime agent state
5. **Go Supervisor SQLite** - session state, action history
6. **Desktop-native SQLite** - the intended source of truth

No single subsystem owned the canonical state. Race conditions and stale reads were possible.

---

## 3. FastAPI Analysis and Verdict

### 3.1 Why FastAPI Exists

AgentOS was originally designed as a web service with an HTTP API for remote clients. The FastAPI server provided:
- RESTful endpoints for task CRUD, agent management, tool browsing
- WebSocket connections for real-time event streaming
- OAuth2/JWT authentication for multi-tenant access
- Middleware for rate limiting, CORS, CSRF, request logging

### 3.2 What Depends on FastAPI

| Consumer | Uses FastAPI? | Actual Communication Path |
|----------|--------------|---------------------------|
| Tauri GUI | **NO** | HTTP to Go Supervisor (:8080) + WebSocket |
| Rust CLI | **NO** | HTTP to Go Supervisor (:8080) |
| Rust TUI | **NO** | HTTP + WebSocket to Go Supervisor (:8080) |
| Go Supervisor | **NO** | gRPC to Python runtime (:50051) |
| External HTTP clients (curl, Postman) | **YES** | Direct HTTP to FastAPI (when running) |
| Cloud deployment | **YES** | FastAPI serves as the HTTP API |

The GUI, CLI, and TUI all communicate with the Go Supervisor, which proxies requests to Python via gRPC. None of them require FastAPI.

### 3.3 Can IPC/Local Communication Replace FastAPI?

**YES.** The existing architecture already provides complete coverage:

- **Go Supervisor HTTP API (:8080)** - provides all task management, agent, and tool endpoints
- **gRPC (:50051)** - primary IPC between Go Supervisor and Python runtime
- **WebSocket (via Supervisor)** - real-time event streaming to GUI/TUI
- **Tauri IPC** - direct Rust-to-JavaScript bridge for GUI commands

The Go Supervisor's HTTP routes cover every operation that an external client would need. Adding FastAPI as a second HTTP server creates confusion about which API to use.

### 3.4 What Breaks If FastAPI Is Removed

**In desktop mode:** Nothing. The desktop entry point (`app/desktop_entry.py`) starts the gRPC server directly without FastAPI.

**In cloud/remote mode:** External integrations that expected the Python HTTP API on its original port would break. This is why FastAPI is preserved as an optional module.

### 3.5 Verdict

**FastAPI has been RELOCATED to `app/cloud_api/` as an optional deployment mode.**

- The desktop runtime path (`app/desktop_entry.py`) does not require or load FastAPI
- Cloud deployments can still use `app/cloud_api/main.py` as their entry point
- The Go Supervisor provides all HTTP API needs for desktop-native clients
- `app/main.py` now detects runtime mode and routes to the appropriate entry point

---

## 4. Proposed Unified Architecture (Post-Refactor)

### 4.1 Design Principles

1. **Single public API** - all runtime access goes through `app/core/`
2. **Desktop-native first** - SQLite, asyncio, single-process by default
3. **Cloud as optional layer** - FastAPI/Redis/PostgreSQL available but not required
4. **Clear ownership** - each module owns one concern completely

### 4.2 The `app/core/` Module

```
app/core/                         # Single public API for the runtime
  __init__.py                     # Package exports
  kernel.py                       # UnifiedKernel - central runtime owner
  orchestration.py                # Execution flow (AgentLoop facade)
  state.py                        # State management (SQLite-based)
  execution.py                    # Task execution entry point
  agents/                         # Agent types and registry
    __init__.py
  memory/                         # Memory hierarchy access
    __init__.py
  tools/                          # Tool registry and routing
    __init__.py
  recovery/                       # Crash recovery and verification
    __init__.py
  observability/                  # Logging, metrics, tracing, alerts
    __init__.py
```

### 4.3 Module Responsibilities

| Module | Responsibility | Key Class/Function |
|--------|---------------|-------------------|
| `kernel.py` | Central runtime lifecycle, worker pool, task submission | `UnifiedKernel` (extends `AgentKernel`) |
| `orchestration.py` | Execution flow coordination, LangGraph invocation | `CoreOrchestration` (wraps `AgentLoop`) |
| `state.py` | Task state transitions, SQLite persistence, locks, timeouts | `StateManager` |
| `execution.py` | Task execution entry, routing to orchestration | `TaskExecutor` |
| `agents/` | Agent types (planner, executor, verifier), registry | Re-exports from `app.agents` |
| `memory/` | 4-tier memory hierarchy (working, short-term, long-term, episodic) | Re-exports from `app.desktop_native` |
| `tools/` | Tool registration, discovery, routing, local fallbacks | Re-exports from `app.tools` |
| `recovery/` | Crash recovery, state replay, verification | Re-exports from `app.desktop_native` |
| `observability/` | Structured logging, metrics, tracing, alerts | Re-exports from `app.desktop_native` |

### 4.4 Architecture Diagram (Post-Refactor)

```
                         ┌──────────────────────────────────┐
                         │         User Interfaces           │
                         │  CLI (Rust) | TUI (Rust) | GUI   │
                         └──────────────┬───────────────────┘
                                        │ HTTP / WebSocket
                         ┌──────────────▼───────────────────┐
                         │     Go Supervisor (:8080)         │
                         │  HTTP API | EventHub | SQLite     │
                         └──────────────┬───────────────────┘
                                        │ gRPC (:50051)
                         ┌──────────────▼───────────────────┐
                         │     Python Runtime                 │
                         │  ┌─────────────────────────────┐  │
                         │  │       app/core/              │  │
                         │  │  UnifiedKernel               │  │
                         │  │    ├── orchestration         │  │
                         │  │    ├── state (SQLite)        │  │
                         │  │    ├── agents                │  │
                         │  │    ├── memory                │  │
                         │  │    ├── tools                 │  │
                         │  │    ├── recovery              │  │
                         │  │    └── observability         │  │
                         │  └─────────────────────────────┘  │
                         │                                    │
                         │  ┌─────────────────────────────┐  │
                         │  │  app/cloud_api/ (OPTIONAL)   │  │
                         │  │  FastAPI + middleware        │  │
                         │  └─────────────────────────────┘  │
                         └────────────────────────────────────┘
```

### 4.5 Execution Flow (Post-Refactor)

```
1. User Request -> Go Supervisor HTTP -> gRPC -> Python gRPC Server
2. gRPC Server -> UnifiedKernel.submit_task()
3. UnifiedKernel -> SQLite INSERT + TaskQueue.enqueue()
4. Worker Loop -> TaskQueue.dequeue() -> StateMachine.transition(EXECUTING)
5. Orchestration -> AgentLoop.run() -> LangGraph execution
6. LangGraph -> PlannerAgent -> ExecutorAgent -> VerifierAgent
7. Tools invoked via ToolRegistry -> MCP servers / local fallbacks
8. Result -> StateMachine.transition(COMPLETED) -> EventBus.publish()
9. EventBus -> Go Supervisor EventHub -> WebSocket -> GUI/TUI
```

---

## 5. Clear Module Boundaries

### 5.1 Language Responsibilities

| Language | Responsibility | Boundary |
|----------|---------------|----------|
| **Python** | Core runtime: orchestration, execution, state, agents, memory, tools, LLM integration | Communicates outward via gRPC server on `:50051` |
| **Go** | Systems layer: process management, HTTP API proxy, WebSocket events, TLS/crypto, SQLite reader | Controls Python as child process, provides HTTP API on `:8080` |
| **Rust** | Performance/native layer: CLI commands, TUI dashboard, desktop automation (Win32/GDI), OCR | Communicates with Go Supervisor via HTTP/gRPC |
| **TypeScript** | UI layer only: React components, Tauri commands, visual display | Communicates with Go Supervisor via HTTP+WebSocket |

### 5.2 Communication Protocols

```
TypeScript (GUI) ──HTTP+WS──> Go Supervisor ──gRPC──> Python Runtime
Rust (CLI/TUI)   ──HTTP+WS──> Go Supervisor ──gRPC──> Python Runtime
Rust (Desktop)   ──gRPC─────> Python Runtime (OCR)
Go Supervisor    ──Process──> Python (child process management)
```

### 5.3 Data Ownership

| Data | Owner | Storage |
|------|-------|---------|
| Task state, execution history | Python (app/core/state) | SQLite (desktop_native) |
| Agent sessions, actions | Go Supervisor | Go SQLite (agentos.db) |
| LangGraph checkpoints | Python (langgraph/) | SQLite (checkpoints table) |
| Configuration | Each component | TOML files + env vars |
| Tool definitions | Go Supervisor (serves) / Python (registers) | Go SQLite |
| Memory (short/long/episodic) | Python (app/core/memory) | SQLite (desktop_native) |
| Real-time events | Go Supervisor EventHub | In-memory broadcast |
| Metrics, traces, logs | Python (app/core/observability) | SQLite + rotating files |

---

## 6. Migration Plan (Status)

Reference: `DESKTOP_NATIVE_MIGRATION_BLUEPRINT.md`

| Phase | Description | Status |
|-------|-------------|--------|
| **Phase 1** | Foundation and Baseline - stabilize gRPC mode, fix startup crashes | COMPLETED (previous session) |
| **Phase 2** | Decoupling and Dependency Elimination - remove Redis, Celery, PostgreSQL from desktop path | COMPLETED (this session) |
| **Phase 3** | Runtime Kernel Redesign - create unified `app/core/` package | PARTIALLY COMPLETED (this session) |
| **Phase 4** | Security Hardening - capability-based permissions, local auth | Future work |
| **Phase 5** | Observability Overhaul - local-first diagnostics, cost tracking | Future work |
| **Phase 6** | UI Integration - Tauri as primary control plane | Future work |
| **Phase 7** | Optimization - performance tuning, memory efficiency | Future work |
| **Phase 8** | Cloud Mode - optional cloud deployment via app/cloud_api/ | Future work |

### What Was Done in This Refactor

1. **Created `app/core/`** - unified public API with kernel, orchestration, state, execution, agents, memory, tools, recovery, observability modules
2. **Relocated FastAPI to `app/cloud_api/`** - desktop path no longer requires FastAPI
3. **Deleted Redis-backed infrastructure** - queue, locks, timeouts, state_machine, event_bus from `app/orchestrator/`
4. **Removed Celery** - deleted `app/queue/` directory entirely
5. **Removed distributed scaling** - deleted `HorizontalScalingCoordinator`, `WorkerPoolManager`
6. **Simplified AgentRuntime** - now a pure agent registry, no longer owns gRPC or execution
7. **Simplified Orchestrator** - removed 4 dead legacy methods
8. **Deleted `app/workers/`** - standalone distributed executor server
9. **Net result:** ~3,678 lines of dead code removed, 9 files deleted, 7 test files removed

---

## 7. Final Target Folder Structure

```
app/
  __init__.py
  main.py                          # Mode-detecting entry point (desktop vs cloud)
  desktop_entry.py                 # Desktop-native entry: forces gRPC + SQLite
  bootstrap.py                     # Mode-aware initialization sequence
  
  core/                            # PUBLIC API - unified runtime interface
    __init__.py
    kernel.py                      # UnifiedKernel (extends AgentKernel)
    orchestration.py               # Execution flow (AgentLoop facade)
    state.py                       # State management (SQLite)
    execution.py                   # Task execution entry
    agents/                        # Agent types re-export
    memory/                        # Memory hierarchy re-export
    tools/                         # Tool registry re-export
    recovery/                      # Crash recovery re-export
    observability/                 # Logging/metrics/tracing re-export
  
  cloud_api/                       # OPTIONAL - cloud deployment mode
    main.py                        # FastAPI application
    api/                           # HTTP routes, schemas
    middleware/                    # CORS, CSRF, rate limiting, auth
  
  desktop_native/                  # IMPLEMENTATION - desktop runtime internals
    kernel.py                      # AgentKernel (core execution kernel)
    sqlite_store.py                # SQLite connection manager (WAL)
    task_queue.py                  # SQLite-backed priority queue
    state_machine.py               # 8-state FSM with history
    event_bus.py                   # asyncio.Queue pub/sub + SQLite
    locks.py                       # Per-task asyncio.Lock + SQLite
    timeouts.py                    # asyncio.wait_for + SQLite deadlines
    resource_monitor.py            # CPU/memory/runtime budgets
    memory_hierarchy.py            # 4-tier memory system
    crash_recovery.py              # Startup recovery scan
    capability_manager.py          # Tool permission tokens
    cost_tracker.py                # Token/cost accounting
    tauri_bridge.py                # GUI event bridge
    local_auth.py                  # OS-identity auth
    local_logger.py                # Rotating JSON logs
    local_metrics.py               # In-memory + SQLite metrics
    local_tracer.py                # SQLite span storage
    local_alerts.py                # Rule-based alerting
    sandbox.py                     # Restricted subprocess
    sqlite_tuning.py               # Pragma optimization
  
  orchestrator/                    # Execution logic (simplified)
    core.py                        # Orchestrator (thin router to AgentLoop)
    agent_loop.py                  # AgentLoop (primary execution engine)
    workflow.py                    # WorkflowEngine (DAG execution)
    builder.py                     # WorkflowBuilder (step construction)
    executor.py                    # StepExecutor (individual step execution)
    task_runner.py                 # TaskRunner (retry + error handling)
    types.py                       # Shared type definitions
  
  agents/                          # Agent implementations
    base.py                        # BaseAgent protocol
    planner.py                     # PlannerAgent
    executor.py                    # ExecutorAgent
    verifier.py                    # VerifierAgent
    coordinator.py                 # CoordinatorAgent
    llm_client.py                  # LLM provider client
    types.py                       # Agent type definitions
  
  runtime/                         # Runtime support (simplified)
    runtime.py                     # AgentRuntime (pure agent registry)
    grpc_server.py                 # gRPC server (RuntimeService)
    factory.py                     # Agent factory
  
  tools/                           # Tool system
    registry.py                    # ToolRegistry
    local_fallbacks.py             # Offline tool implementations
    builtin/                       # Built-in tools (search, calc, etc.)
  
  memory/                          # Persistence layer
    long_term.py                   # Long-term memory (SQLite)
    short_term.py                  # Short-term memory (local, was Redis)
    in_memory.py                   # In-memory fallbacks
  
  langgraph/                       # LangGraph integration
    graphs.py                      # Graph definitions
    nodes.py                       # Graph nodes
    state.py                       # AgentState TypedDict
    sqlite_checkpointer.py         # SQLite checkpoint persistence
  
  mcp/                             # Model Context Protocol
    client_manager.py              # MCP server lifecycle
    router.py                      # Tool routing to MCP servers
    servers/                       # MCP server implementations
  
  config/                          # Configuration
    settings.py                    # Pydantic settings with mode awareness
  
  llm/                             # LLM provider abstraction
    providers/                     # OpenAI, Anthropic, etc.
  
  auth/                            # Authentication (local + cloud)
  capabilities/                    # Capability system
  environments/                    # Execution environments
  guardrails/                      # Input/output validation
  knowledge/                       # Knowledge base
  logs/                            # Legacy logging (-> core/observability)
  migrations/                      # SQL migration runner
  observability/                   # Legacy observability event bus
  onboarding/                      # User onboarding flows
  pipelines/                       # Pipeline definitions
  proto/                           # gRPC protobuf definitions
  recovery/                        # Recovery service
  safety/                          # Safety constraints
  utils/                           # Shared utilities
  workflows/                       # Workflow decomposition
```

---

## 8. Risks and Tradeoffs

### 8.1 Removed Test Coverage

Seven test files that tested Redis/Celery-specific behavior were removed:
- Tests for Redis-backed queue, locks, state_machine, event_bus, timeouts
- Tests for Celery task dispatch
- Tests for distributed scaling coordination

These tested infrastructure that no longer exists. The desktop-native equivalents have their own tests (54 tests pass, including 25 state machine tests).

### 8.2 Cloud Deployment Mode Less Tested

`app/cloud_api/` is preserved for cloud deployment but receives less testing attention now. The re-export modules delegate to the original `app/api/` and `app/middleware/` packages, which remain functional but are not exercised in the standard test suite.

### 8.3 Residual Redis References

- `app/memory/short_term.py` still imports Redis conditionally for backward compatibility
- `app/bootstrap.py` retains Redis initialization code for HTTP mode
- These are intentional: they support the cloud deployment path and will be fully cleaned up in Phase 8

### 8.4 Transitive FastAPI Imports

FastAPI is still transitively imported through the orchestrator chain (`app.orchestrator.agent_loop` -> `app.orchestrator.core` -> `app.runtime.runtime` -> ...) in certain code paths. This is a pre-existing issue that was verified to exist before this refactor. Fixing it requires deep lazy-import refactoring of the orchestrator module.

### 8.5 Python Version Mismatch

The development sandbox uses Python 3.9.25, while the target runtime is Python 3.11. This required:
- A stub `mcp` package (MCP SDK requires Python 3.10+)
- Replacing `str | None` type syntax with `Optional[str]` in three files
- Adding `from __future__ import annotations` in two modules

Production deployments should use Python 3.11+.

### 8.6 Indirect Import Chains

Some modules in `app/core/` use lazy imports to avoid circular dependencies. This means import errors may surface at runtime rather than at import time. The test suite exercises the primary paths but edge cases could exist.

### 8.7 State Synchronization

The Go Supervisor maintains its own SQLite database (`agentos.db`) with agent sessions and actions, while the Python runtime maintains a separate SQLite database for task state. These two databases are not synchronized directly - the Go Supervisor reads Python state via gRPC calls. If the Python process crashes between a state write and the gRPC response, the Supervisor may have stale information until it re-queries.

---

## Appendix: Key Files Modified in This Refactor

| File | Change |
|------|--------|
| `app/core/__init__.py` | Created - unified package exports |
| `app/core/kernel.py` | Created - UnifiedKernel class |
| `app/core/orchestration.py` | Created - AgentLoop facade |
| `app/core/state.py` | Created - StateManager |
| `app/core/execution.py` | Created - TaskExecutor |
| `app/cloud_api/main.py` | Created - relocated FastAPI app |
| `app/cloud_api/api/` | Created - relocated routes |
| `app/cloud_api/middleware/` | Created - relocated middleware |
| `app/main.py` | Rewritten - mode-detecting entry |
| `app/runtime/runtime.py` | Simplified - pure agent registry |
| `app/orchestrator/core.py` | Simplified - removed dead methods |
| `app/orchestrator/queue.py` | Deleted |
| `app/orchestrator/locks.py` | Deleted |
| `app/orchestrator/timeouts.py` | Deleted |
| `app/orchestrator/state_machine.py` | Deleted |
| `app/orchestrator/event_bus.py` | Deleted |
| `app/queue/` | Deleted (entire directory) |
| `app/workers/` | Deleted (entire directory) |
| `app/memory/redis_pubsub.py` | Deleted |
