# AgentOS Desktop-Native Migration Blueprint
## Production-Grade Architecture Audit, Redesign & Execution Plan

**Version:** 1.0  
**Date:** 2026-05-12  
**Classification:** Principal Systems Architecture Review  
**Scope:** Full-stack holistic audit and first-principles redesign from web-oriented distributed architecture to desktop-native autonomous runtime.

---

## 1. Executive Summary

### 1.1 Current State Assessment

AgentOS is not a web application that needs "desktop features." It is a desktop-native AI runtime that was temporarily expressed through web-architecture patterns. The codebase contains **substantial desktop-native groundwork** already executed with foresight:

- **Tauri-based GUI** (`gui/src-tauri/`) providing native windowing, system tray, global shortcuts, and OS keychain integration.
- **Go Supervisor** (`supervisor/`) acting as a local daemon with SQLite persistence, gRPC orchestration, and WebSocket event broadcasting.
- **gRPC Runtime Mode** (`app/desktop_entry.py`, `app/proto/`, `app/runtime/grpc_server.py`) allowing the Python runtime to operate without FastAPI, Redis, or PostgreSQL.
- **SQLite Checkpointer** (`app/langgraph/sqlite_checkpointer.py`) enabling LangGraph state persistence without a database server.
- **Local MCP Servers** (`app/mcp/servers/`) running as stdio subprocesses for filesystem, shell, browser, and desktop automation.
- **Native Desktop Automation** (`app/environments/desktop_env.py`) using Windows UI Automation, pyautogui, and MSS.

**However, the architecture is currently schizophrenic.** The web path (FastAPI + Celery + Redis + PostgreSQL) is treated as the primary execution model, while the desktop-native path (gRPC + SQLite + local) is a secondary mode with numerous implicit dependencies on distributed infrastructure. This creates **runtime ambiguity, state ownership conflicts, and unnecessary operational fragility.**

### 1.2 The Core Problem

The system inherited **distributed-system assumptions** from its web origins that are fundamentally incompatible with a local-first, low-latency, persistent desktop runtime:

1.  **Redis as a Distributed Crutch:** Used for caching, pub/sub, distributed locks, rate limiting, CSRF tokens, cost aggregation, and task queues. In a single-user desktop app, Redis is pure overhead and a single point of failure (middleware fails closed when Redis is down).
2.  **PostgreSQL as a Mandatory Dependency:** All durable state (tasks, workflows, agents, traces, checkpoints, memory) assumes a running Postgres server. SQLite exists but is treated as a fallback, not a first-class citizen.
3.  **Celery for Local Concurrency:** Celery workers are used to run Python async code from a web request. On a desktop, this is an unnecessary process hop; asyncio event loops and thread pools are sufficient.
4.  **Web Authentication in a Local Process:** JWT Bearer tokens, API keys, CSRF protection, and rate limiting are designed for multi-tenant internet services. They add latency and complexity to a single-user local runtime.
5.  **Cloud-Oriented Observability:** Prometheus metrics, Redis-backed counters, and batched DB span flushing are designed for SRE teams monitoring Kubernetes clusters, not for local debugging of a desktop agent.
6.  **State Fragmentation:** Task state is split across PostgreSQL rows, Redis keys, LangGraph checkpoints, in-memory Python objects, and Go supervisor state. No single subsystem owns the truth.

### 1.3 Target State Vision

A **unified desktop-native autonomous runtime** where:

- The local machine is the **primary and only execution environment** by default.
- Network connectivity is used **exclusively** for cloud LLM inference and optional sync.
- All orchestration, state, memory, and IPC are **local-first**.
- The architecture is **opinionatedly simple**: one runtime per machine, one event loop per process, one SQLite database per user.
- The system is **resilient to long-running execution**: crashes are recoverable, state is checkpointed, resources are managed.

### 1.4 Migration Strategy at a Glance

The migration is **not a rewrite.** It is a **refactoring and elevation** of existing desktop-native components to first-class status, coupled with the **surgical removal** of web-specific infrastructure from the local execution path.

**Critical Path:**
1.  Stabilize and baseline the existing gRPC/desktop mode.
2.  Eliminate Redis and PostgreSQL hard dependencies in desktop mode.
3.  Redesign the Python runtime as a unified `AgentKernel` with local asyncio scheduling.
4.  Harden security for a local capability-based permission model.
5.  Replace cloud-oriented observability with local-first diagnostics.
6.  Integrate the Tauri GUI as the primary control plane.
7.  Stress-test for 24+ hour autonomous execution.

---

## 2. Part 1: Holistic Architecture Audit

### 2.1 Runtime & Execution Systems

#### 2.1.1 LangGraph Agent Orchestration
**Current Role:** Core execution engine for planning, execution, verification, approval, and summarization.
**Audit:**
- **Why it exists:** Provides a structured state machine for multi-step agent workflows with checkpointing.
- **Problem it solves:** Prevents spaghetti code for agent loops; enables pause/resume for human approval.
- **Evaluation:** **CRITICAL. KEEP.** LangGraph is a solid choice for agent orchestration. It supports local execution well.
- **Issues:**
  - `AgentState` TypedDict is bloated with web-specific metadata (`cost_estimate_usd`, `execution_lock_id`, `handoff_log`, `complexity_score`) that pollutes the core state.
  - Graph compilation uses an in-memory LRU cache (`_LRUOrderedDict`) which is fine, but the `PostgresCheckpointSaver` is treated as primary over `SQLiteCheckpointSaver`.
  - The `approval_node` uses `langgraph.types.interrupt` correctly, but the approval store is in-memory only (`ApprovalStore`), meaning approval state is lost if the process restarts.
- **Verdict:** Keep LangGraph. Simplify `AgentState`. Make SQLite checkpointer the default in desktop mode. Persist approval state to SQLite.

#### 2.1.2 Agent Runtime (`app/runtime/runtime.py`)
**Current Role:** Singleton registry of `AgentWorker` instances. Manages gRPC client lifecycle.
**Audit:**
- **Why it exists:** Central registry for agent lifecycle and execution entry points.
- **Problem it solves:** Ensures single instances of agents; provides unified access.
- **Evaluation:** **REPLACE / MERGE.** The `AgentRuntime` is a thin registry that delegates to other systems. In a desktop-native kernel, this should be merged into a unified `AgentKernel` that owns the event loop, task queue, and agent pool.
- **Issues:**
  - Uses a Redis mutex (`agentos:runtime:init_mutex`) for DB initialization — unnecessary for local single-process startup.
  - Holds a `GRPCClient` but also supports HTTP mode, creating dual initialization paths.
  - `AgentPool` is just an `asyncio.Semaphore` — too primitive for a production kernel.
- **Verdict:** Merge into `AgentKernel`. Remove Redis mutex.

#### 2.1.3 Orchestrator (`app/orchestrator/core.py`)
**Current Role:** Thin router that selects execution modes and delegates to subsystems.
**Audit:**
- **Why it exists:** Abstracts execution strategy selection (LangGraph vs legacy modes).
- **Problem it solves:** Provides a single entry point for task execution.
- **Evaluation:** **SIMPLIFY / MERGE.** The orchestrator adds a layer of indirection that is no longer necessary once the system is unified. It tries LangGraph first, then falls back to checkpoint recovery, then falls back to legacy strategies. In a desktop kernel, there should be one primary path.
- **Issues:**
  - `_hydrate_memory_context()` loads short-term memory from Redis — adds latency.
  - Retry logic is scattered between orchestrator, task runner, and Celery.
- **Verdict:** Merge retry and routing logic into `AgentKernel`. Remove fallback spaghetti.

#### 2.1.4 Task Runner (`app/orchestrator/task_runner.py`)
**Current Role:** Encapsulates LangGraph execution with adaptive routing and capability checks.
**Audit:**
- **Why it exists:** Adds fast paths (ActionV1, Direct, Sequential) before falling back to full LangGraph.
- **Problem it solves:** Avoids heavy graph overhead for simple tasks.
- **Evaluation:** **KEEP BUT SIMPLIFY.** The adaptive routing is smart but over-engineered. The `TaskComplexityRouter` and `feasibility_engine` add classification overhead that may not be worth it for local execution.
- **Issues:**
  - `ActionV1Runner` is a legacy fast path that duplicates tool registry logic.
  - Desktop recovery logic is buried inside the runner instead of being a kernel concern.
- **Verdict:** Keep the fast path concept, but merge into `AgentKernel` scheduler.

#### 2.1.5 Celery Workers (`app/queue/tasks.py`)
**Current Role:** Distributed task queue for background execution.
**Audit:**
- **Why it exists:** Offloads long-running agent tasks from the FastAPI request thread.
- **Problem it solves:** Prevents HTTP request timeouts.
- **Evaluation:** **REMOVE FROM DESKTOP PATH.** Celery is entirely unnecessary for a desktop runtime. The Python runtime is a long-lived process; tasks run in the main asyncio event loop or a thread pool.
- **Issues:**
  - Adds Redis and a separate worker process as mandatory dependencies.
  - Heartbeat events from Celery workers add noise.
  - Task revocation via `SIGTERM` is unreliable for graph-based execution.
- **Verdict:** Remove Celery from desktop mode. Use in-process `asyncio.Task` scheduling with proper cancellation.

#### 2.1.6 Custom Task Queue (`app/orchestrator/queue.py`)
**Current Role:** Priority task queue built on Redis sorted sets.
**Audit:**
- **Why it exists:** Provides priority-based task ordering with FIFO tie-breaking.
- **Problem it solves:** Redis-based distributed priority queue.
- **Evaluation:** **REWRITE FOR LOCAL.** A priority queue is useful, but Redis sorted sets are overkill. Replace with `asyncio.PriorityQueue`.
- **Verdict:** Replace with `LocalTaskQueue` backed by `asyncio.PriorityQueue` and SQLite persistence.

### 2.2 Communication & IPC

#### 2.2.1 Redis Event Bus (`app/orchestrator/event_bus.py`)
**Current Role:** Pub/sub for task lifecycle events.
**Audit:**
- **Why it exists:** Broadcasts events to WebSocket subscribers across multiple API worker processes.
- **Problem it solves:** Decouples event producers from consumers in a distributed web app.
- **Evaluation:** **REPLACE FOR LOCAL.** In a desktop runtime, event consumers are in the same process (Python runtime) or communicate via gRPC/UDS with the Go supervisor.
- **Verdict:** Replace with `LocalEventBus` using `asyncio.Queue` and weak subscriber sets. Keep `RedisEventBus` as an optional cloud plugin.

#### 2.2.2 WebSocket Layer (`app/api/ws.py`)
**Current Role:** Real-time bidirectional communication for web clients.
**Audit:**
- **Why it exists:** Streams task events to browsers.
- **Problem it solves:** HTTP is request/response; WS enables server-push.
- **Evaluation:** **REMOVE FROM DESKTOP PATH.** The Tauri GUI communicates with the Go Supervisor via its own WebSocket (`ws://127.0.0.1:8080/api/v1/events`). The Python runtime does not need to expose a WebSocket directly in desktop mode.
- **Verdict:** Remove FastAPI WebSocket from desktop mode. Python runtime emits events via gRPC streaming to Go Supervisor.

#### 2.2.3 gRPC Layer (`app/proto/`, `app/runtime/grpc_server.py`, `supervisor/`)
**Current Role:** Cross-language IPC between Go Supervisor and Python Runtime.
**Audit:**
- **Why it exists:** Enables the Go supervisor to orchestrate Python execution without HTTP overhead.
- **Problem it solves:** Language boundary between Go (system daemon) and Python (AI runtime).
- **Evaluation:** **CRITICAL. KEEP AND EXPAND.** This is the correct IPC mechanism for a desktop-native architecture.
- **Issues:**
  - Current gRPC services are basic (`RuntimeService`, `CheckpointService`, `WorkerService`). Need richer streaming for events and logs.
  - mTLS is implemented but should be mandatory, not optional.
- **Verdict:** Expand gRPC protocol to include event streaming, log streaming, and resource telemetry.

#### 2.2.4 SSE Endpoints (`app/api/routes/events.py`)
**Current Role:** Server-Sent Events for task updates.
**Audit:**
- **Evaluation:** **REMOVE FROM DESKTOP PATH.** Not needed when Tauri gets events via Supervisor WS.
- **Verdict:** Keep only for optional web dashboard (cloud plugin).

### 2.3 State & Memory

#### 2.3.1 LangGraph Checkpointers (`PostgresCheckpointSaver` / `SQLiteCheckpointSaver`)
**Current Role:** Persist graph state for pause/resume/recovery.
**Audit:**
- **Evaluation:** **KEEP BOTH, BUT PRIORITIZE SQLITE.** SQLite with WAL mode is sufficient for local desktop use and eliminates the Postgres server dependency.
- **Issues:**
  - `PostgresCheckpointSaver` is fetched by default (`get_checkpointer()`).
  - `SQLiteCheckpointSaver` uses `threading.Lock()` which may conflict with asyncio. Should use `aiosqlite` or an asyncio-compatible lock.
- **Verdict:** Make `SQLiteCheckpointSaver` the default in desktop mode. Audit its async safety.

#### 2.3.2 Task State Machine (`app/orchestrator/state_machine.py`)
**Current Role:** Explicit lifecycle state machine with Redis cache + PostgreSQL persistence.
**Audit:**
- **Evaluation:** **SIMPLIFY.** State machine logic is good, but Redis caching adds inconsistency risk. Use SQLite as the single source of truth with in-memory read-through cache if needed.
- **Verdict:** Rewrite to use SQLite exclusively. Remove Redis fallback.

#### 2.3.3 Short-Term Memory (`app/memory/short_term.py`)
**Current Role:** Redis-backed context storage.
**Audit:**
- **Evaluation:** **REPLACE.** For local execution, short-term memory should be in-process Python dicts or SQLite.
- **Verdict:** Replace with `LocalShortTermMemory` (in-process dict with TTL pruning).

#### 2.3.4 Long-Term Memory (`app/memory/long_term.py`)
**Current Role:** PostgreSQL repositories for all persistent entities.
**Audit:**
- **Evaluation:** **ADAPT FOR SQLITE.** The repository pattern is good. Create SQLite equivalents or use an ORM that abstracts the dialect (SQLAlchemy already does this).
- **Verdict:** Ensure all repositories work with `aiosqlite`. Use a single SQLite file (`~/.agentos/agentos.db`).

#### 2.3.5 Persistent Memory (`app/memory/persistent.py`)
**Current Role:** Unified Redis (fast) + PostgreSQL (durable) persistence.
**Audit:**
- **Evaluation:** **SIMPLIFY.** The dual-write pattern is complex and risks inconsistency. Use SQLite with proper indexing.
- **Verdict:** Merge into SQLite-based memory manager.

#### 2.3.6 Knowledge / RAG (`app/knowledge/`)
**Current Role:** Keyword-based retrieval on PostgreSQL.
**Audit:**
- **Evaluation:** **UPGRADE.** Keyword search is insufficient for agent RAG. Add a local vector store.
- **Verdict:** Integrate `sqlite-vec` or Chroma for local embeddings. Keep keyword search as a fallback.

### 2.4 Data & Persistence

#### 2.4.1 PostgreSQL Database (`app/memory/models.py`, `app/memory/long_term.py`)
**Current Role:** Primary durable store for 30+ tables.
**Audit:**
- **Evaluation:** **REMOVE FROM DESKTOP PATH.** PostgreSQL is a server dependency. SQLite can handle the load of a single-user desktop app.
- **Issues:**
  - Connection pooling (`pool_size=20`, `max_overflow=40`) is oversized for local use.
  - Migrations are hand-rolled SQL (not Alembic), which makes dialect switching harder.
- **Verdict:** Use SQLite for desktop mode. Maintain PostgreSQL support as an optional cloud backend.

#### 2.4.2 Redis (`app/memory/short_term.py`, `app/memory/redis_pubsub.py`)
**Current Role:** Cache, pub/sub, locks, queues, rate limits, CSRF tokens.
**Audit:**
- **Evaluation:** **COMPLETELY REMOVE FROM DESKTOP PATH.** Every Redis use case has a simpler local equivalent.
- **Verdict:** See Dependency Elimination Plan (Section 6).

#### 2.4.3 Artifact Store (`app/memory/artifact_store.py`)
**Current Role:** Durable file storage with PostgreSQL metadata and Redis caching.
**Audit:**
- **Evaluation:** **SIMPLIFY.** Store files on local filesystem (`~/.agentos/artifacts/`). Use SQLite for metadata. Remove Redis cache.
- **Verdict:** Rewrite as `LocalArtifactStore`.

### 2.5 Security & Safety

#### 2.5.1 JWT / API Key Authentication (`app/auth/`, `app/middleware/auth.py`)
**Current Role:** Web authentication for multi-user access.
**Audit:**
- **Evaluation:** **REPLACE FOR LOCAL.** A desktop-native single-user app should not require JWT tokens for local IPC.
- **Issues:**
  - `SECRET_KEY` must be shared across FastAPI, Celery, and workers — fragile.
  - API keys are stored hashed in PostgreSQL. Local processes should use OS-level authentication or mTLS.
- **Verdict:** In desktop mode, authenticate using OS user identity or local keychain secrets. Use mTLS for Go-Python gRPC. Remove JWT/API key layers from local runtime.

#### 2.5.2 RBAC (`app/auth/rbac.py`, `app/safety/rbac.py`)
**Current Role:** Role-based access control for users and agents.
**Audit:**
- **Evaluation:** **SIMPLIFY.** Agent-level RBAC is useful (which agents can use which tools). User-level RBAC is irrelevant for a single-user desktop app.
- **Verdict:** Keep agent-level capability system. Remove user-level RBAC from desktop mode.

#### 2.5.3 Safety Gate (`app/safety/gate.py`)
**Current Role:** Blocks irreversible actions.
**Audit:**
- **Evaluation:** **CRITICAL. KEEP.** This is essential for autonomous desktop agents.
- **Verdict:** Expand to support fine-grained capability tokens.

#### 2.5.4 Approval Flow (`app/safety/approval_store.py`, `app/langgraph/nodes.py`)
**Current Role:** Human-in-the-loop approval with in-memory state.
**Audit:**
- **Evaluation:** **KEEP BUT PERSIST.** Approval state must survive crashes.
- **Verdict:** Persist approval state to SQLite. Integrate with Tauri native dialogs.

#### 2.5.5 Guardrails (`app/guardrails/validator.py`)
**Current Role:** Input/output validation with regex blocks.
**Audit:**
- **Evaluation:** **KEEP.** Simple but effective.
- **Verdict:** Keep as-is. Ensure it runs in the kernel before task execution.

#### 2.5.6 Sandboxing (`app/tools/sandbox.py`, `app/mcp/servers/code.py`)
**Current Role:** AST-level import blocking for Python execution.
**Audit:**
- **Evaluation:** **INSUFFICIENT.** AST blocking is trivial to bypass. For a desktop agent, code execution should use OS-level sandboxing (Windows AppContainer, macOS Seatbelt, Linux namespaces/seccomp) or at least a restricted subprocess with no network/fs access.
- **Verdict:** Replace with subprocess-based sandbox with restricted permissions. Never run untrusted code in the main Python process.

### 2.6 Observability

#### 2.6.1 Prometheus Metrics (`app/logs/metrics.py`, `app/main.py`)
**Current Role:** In-memory metrics with Prometheus text export.
**Audit:**
- **Evaluation:** **REPLACE FOR LOCAL.** Prometheus is a pull-based cluster monitoring system. Local apps need push-based or file-based diagnostics.
- **Verdict:** Replace with SQLite metrics store and in-memory gauges. Optionally expose Prometheus format for power users, but don't require it.

#### 2.6.2 Distributed Tracing (`app/logs/tracing.py`, `app/observability/bus.py`)
**Current Role:** Async span persistence to PostgreSQL via batched flush loop.
**Audit:**
- **Evaluation:** **SIMPLIFY.** Tracing is valuable, but the batched DB flush loop adds complexity. For local use, write traces to SQLite or structured log files immediately.
- **Verdict:** Replace `ObservabilityBus` DB flush with SQLite writes. Remove Redis pub/sub from observability path.

#### 2.6.3 Alerting (`app/logs/alerts.py`)
**Current Role:** Alert rules engine with cooldown.
**Audit:**
- **Evaluation:** **KEEP BUT LOCALIZE.** Alerting is useful for long-running autonomy, but channels should be local (desktop notifications, log files) not webhooks/Slack by default.
- **Verdict:** Integrate with Tauri notification API for desktop alerts.

#### 2.6.4 Cost Tracking (`app/logs/cost_tracker.py`)
**Current Role:** Redis-backed cost aggregates with PostgreSQL fallback.
**Audit:**
- **Evaluation:** **SIMPLIFY.** Use SQLite for cost tracking.
- **Verdict:** Rewrite as `LocalCostTracker` with SQLite backend.

### 2.7 Infrastructure & Deployment

#### 2.7.1 FastAPI (`app/main.py`)
**Current Role:** Web API server.
**Audit:**
- **Evaluation:** **REMOVE FROM DESKTOP PATH.** FastAPI is excellent for web services but adds overhead (HTTP parsing, middleware stack, CORS, Uvicorn) to a local runtime.
- **Verdict:** Keep FastAPI as an optional cloud plugin (`app/cloud_api/`). The desktop runtime uses gRPC.

#### 2.7.2 Docker / Docker Compose (`docker/`)
**Current Role:** Container orchestration for Postgres, Redis, API, and Celery worker.
**Audit:**
- **Evaluation:** **REMOVE FROM DESKTOP PATH.** Docker is unnecessary for a desktop app distributed as an installer.
- **Verdict:** Keep Docker for optional cloud deployment. Desktop builds use native binaries (Tauri + Go Supervisor + Python runtime bundled via PyInstaller or embedded).

#### 2.7.3 Middleware Stack (`app/middleware/`)
**Current Role:** CORS, auth, rate limit, CSRF, validation, request logging.
**Audit:**
- **Evaluation:** **REMOVE FROM DESKTOP PATH.** All middleware is web-specific.
- **Verdict:** Disable entirely in desktop mode.

### 2.8 Frontend & UI

#### 2.8.1 Tauri GUI (`gui/`)
**Current Role:** Native desktop application shell.
**Audit:**
- **Evaluation:** **CRITICAL. KEEP AND EXPAND.** Tauri is the correct choice for a lightweight, secure native UI.
- **Issues:**
  - Daemon commands are stubs (`get_daemon_status`, `start_daemon`, `stop_daemon`).
  - Settings page does not persist config to Tauri config file.
  - Safety dialog uses heuristic keyword matching instead of backend approval state.
- **Verdict:** Implement real daemon lifecycle management. Integrate with SQLite backend for settings and task history.

#### 2.8.2 Terminal UI (`tui/`)
**Current Role:** Lightweight terminal dashboard.
**Audit:**
- **Evaluation:** **KEEP AS DEBUG TOOL.** Useful for developers and power users.
- **Verdict:** Complete HTTP/WS polling implementation.

#### 2.8.3 Go Supervisor (`supervisor/`)
**Current Role:** System daemon, HTTP proxy, gRPC orchestrator, SQLite store.
**Audit:**
- **Evaluation:** **CRITICAL. KEEP AND EXPAND.** The Go supervisor is the correct system-level anchor for a desktop runtime.
- **Issues:**
  - WebSocket event hub is basic; needs backpressure and reconnection handling.
  - SQLite schema is simpler than Python's; may diverge.
- **Verdict:** Make Go Supervisor the primary process. Python runtime is a child process managed by Supervisor.

---

## 3. Part 2: Runtime Correctness Analysis

### 3.1 State Ownership & Concurrency

**Finding:** State ownership is fragmented across at least five subsystems:
1.  `TaskModel` (PostgreSQL) — created by FastAPI routes, updated by Celery workers.
2.  `TaskStateMachine` (Redis + PostgreSQL + in-memory dict) — runtime state transitions.
3.  `AgentState` (LangGraph checkpoint — PostgreSQL/SQLite) — graph execution state.
4.  `ApprovalStore` (in-memory dict) — approval session state.
5.  `event_bus` (Redis pub/sub) — ephemeral event state.

**Risk:** Inconsistent state during recovery. If the process crashes, `ApprovalStore` is lost, but the checkpoint may indicate an `interrupt` state. On resume, the graph will hang waiting for an approval that no longer exists.

**Mitigation:** Consolidate all durable state into SQLite. The `AgentKernel` must own the single writer principle for task state.

### 3.2 Async Execution Correctness

**Finding:** The codebase mixes `asyncio` (FastAPI, LangGraph), `threading` (`SQLiteCheckpointSaver`), and multiprocessing (Celery workers, MCP stdio servers).

**Risk:** `SQLiteCheckpointSaver` uses `threading.Lock()`. If called from an asyncio event loop without an executor, it may block the loop. The `ToolSandbox` runs code in a thread pool, which is fine, but AST analysis happens in the main thread.

**Mitigation:** Ensure all SQLite access in the asyncio path uses `aiosqlite` or runs in `loop.run_in_executor`. Never hold locks across await points.

### 3.3 Execution Determinism Boundaries

**Finding:** Tool execution is non-deterministic (desktop automation, browser interaction, LLM generation). The replay service (`app/recovery/replay.py`) attempts deterministic replay from checkpoints, but diverges if tool outputs change.

**Risk:** Replay is largely useless for desktop agents because the environment changes between runs.

**Mitigation:** Deprecate deterministic replay for desktop tasks. Focus on checkpoint resume (stateful recovery) rather than deterministic replay.

### 3.4 Cancellation / Interruption Semantics

**Finding:** Task cancellation uses `celery_app.control.revoke(..., terminate=True, signal='SIGTERM')` and a Redis cancellation key. `SIGTERM` in a Celery worker running an asyncio event loop is unreliable and may leave browser/desktop sessions in an inconsistent state.

**Risk:** Orphaned browser contexts, leaked desktop sessions, or corrupted checkpoints.

**Mitigation:** Implement cooperative cancellation in the `AgentKernel`. Use `asyncio.Task.cancel()` and proper `finally` blocks to clean up browser and desktop sessions.

### 3.5 Resource Lifecycle & Memory Leak Risks

**Finding:** `DesktopSessionManager` uses TTL-based reaping, but `BrowserSessionManager` shares a persistent browser process across tasks. Playwright contexts can leak if not explicitly closed.

**Risk:** Long-running autonomous workflows will exhaust memory or file descriptors.

**Mitigation:** Implement strict resource budgets per task. Use context managers (`async with`) for all session lifecycles. Add periodic garbage collection of orphaned sessions.

### 3.6 Event Recursion Risks

**Finding:** The `ObservabilityBus` emits events to the `event_bus`, which WebSocket subscribers consume. If an observability event triggers a tool call (e.g., an alert triggers a recovery action), this could create an event loop.

**Risk:** Uncontrolled agent recursion and event storms.

**Mitigation:** Enforce a strict DAG for event handling. Observability events must be read-only; they cannot trigger new actions.

### 3.7 Deadlock / Starvation Possibilities

**Finding:** `ExecutionLock` uses Redis `SET NX EX`. In a local runtime replaced with `asyncio.Lock`, improper nesting (e.g., holding a lock while awaiting a tool call) can deadlock the event loop.

**Risk:** Kernel freeze.

**Mitigation:** Audit all lock acquisitions. Never hold locks across I/O boundaries. Use semaphore-based concurrency limits instead of binary locks where possible.

---

## 4. Part 3: Desktop-Native Target Architecture

### 4.1 Design Principles

1.  **Single Process is the Default:** The Python runtime runs as a single asyncio process. No worker pools, no Celery, no process forking for normal operation.
2.  **SQLite is the Source of Truth:** One SQLite database (`~/.agentos/agentos.db`) with WAL mode enabled. All durable state lives here.
3.  **gRPC is the IPC Boundary:** Go Supervisor manages the Python runtime as a child process. All cross-language communication is gRPC with mTLS.
4.  **Local-First, Cloud-Never-Required:** The system must function fully with zero network connectivity (except for cloud LLM calls if the user chooses).
5.  **Capability-Based Security:** Tools declare capabilities. Agents request capabilities. Users approve capabilities. No RBAC roles.
6.  **Event-Driven, Not Queue-Driven:** The kernel uses an in-memory event bus. Tasks are scheduled, not enqueued.

### 4.2 Core Runtime: AgentKernel

```
┌─────────────────────────────────────────────────────────────┐
│                     AgentKernel (Python)                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │   Scheduler  │  │  Task Queue  │  │  Lifecycle Mgr   │  │
│  │ (asyncio)    │  │ (PriorityQ)  │  │ (start/stop/gc)  │  │
│  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘  │
│         │                 │                    │            │
│  ┌──────▼─────────────────▼────────────────────▼─────────┐  │
│  │                  Execution Engine                       │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │  │
│  │  │ LangGraph│ │  Fast    │ │  Tool    │ │  Desktop │  │  │
│  │  │ Runtime  │ │  Path    │ │  Router  │ │  Loop    │  │  │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘  │  │
│  └─────────────────────────────────────────────────────────┘  │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │                  State Manager (SQLite)                 │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │  │
│  │  │ Checkpts │ │  Tasks   │ │  Memory  │ │  Traces  │  │  │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘  │  │
│  └─────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

**AgentKernel Responsibilities:**
-   **Scheduler:** `asyncio` based. Manages task priorities, timeouts, and cancellation.
-   **Task Queue:** `asyncio.PriorityQueue` with SQLite-backed persistence for durability.
-   **Lifecycle Manager:** Handles startup, graceful shutdown, crash recovery, and garbage collection of orphaned sessions.
-   **Execution Engine:** Routes tasks to LangGraph (complex), Fast Path (simple), or Direct Tool Call (immediate).
-   **State Manager:** Single writer to SQLite. Handles checkpoints, task metadata, memory, and traces.

### 4.3 Agent System

**Multi-Agent Orchestration:**
-   Use LangGraph's built-in `Send` mechanism for collaboration graphs.
-   Agents are lightweight stateless functions, not persistent processes.
-   Agent communication is via the shared `AgentState` (immutable updates), not message queues.

**Tool Routing:**
-   Unified `ToolRegistry` remains.
-   Tools are categorized by capability (`desktop`, `browser`, `fs`, `shell`, `code`).
-   `CapabilityManager` grants/denies capabilities per task based on user approval and safety gates.

**Memory Hierarchy:**
1.  **Working Memory:** In-process Python dicts (current conversation context, active sessions).
2.  **Short-Term Memory:** SQLite table (`memory_context`) with TTL-based pruning.
3.  **Long-Term Memory:** SQLite table (`knowledge_chunks`) with local vector embeddings (`sqlite-vec`).
4.  **Episodic Memory:** SQLite table (`task_history`) storing past task summaries and outcomes.

### 4.4 Desktop Control Layer

**UI Automation:**
-   Keep `uiautomation` + `pyautogui` for Windows.
-   Abstract behind `DesktopController` interface to allow macOS (`AXUIElement`) and Linux (`AT-SPI`) implementations later.
-   Run desktop automation in the main process (it already does). Use `asyncio.to_thread` for blocking calls.

**Browser Automation:**
-   Keep Playwright.
-   Manage browser lifecycle strictly: one persistent context per user, task-scoped pages.
-   Isolate browser automation in a separate subprocess ONLY if stability issues arise. Currently, in-process is acceptable for local use.

**OS Interaction:**
-   Go Supervisor handles OS-level operations (file watching, process management, window management).
-   Python runtime requests OS actions via gRPC to Go Supervisor.

### 4.5 AI Runtime

**Inference Routing:**
-   `InferenceRouter` selects between local (Ollama, local transformers) and cloud (OpenAI, Anthropic) providers.
-   Local models are preferred for sensitive operations (data never leaves machine).
-   Cloud models are used for complex reasoning when local models are insufficient.
-   Implement request/response caching in SQLite to reduce API costs and enable offline replay of recent contexts.

**Context / Window Management:**
-   Implement sliding window summarization when context exceeds model limits.
-   Persist conversation history to SQLite and load it into `AgentState.messages` at task start.

**Embeddings:**
-   Use lightweight local embedding models (e.g., `sentence-transformers` small models) or `sqlite-vec` for RAG.
-   Avoid cloud embedding APIs for local-first operation.

### 4.6 Security Architecture

**Sandboxing:**
-   **Code Execution:** Use a restricted subprocess with no network access, read-only filesystem (except temp dir), and resource limits (CPU time, memory). Never run in main process.
-   **Browser:** Playwright contexts with `--isolate-origins`, disabled downloads, and restricted extensions.
-   **Desktop:** OS-level capability tokens. Before any desktop action, the agent must hold a capability token granted by the user.

**Capability Isolation:**
-   Replace RBAC with a capability token system:
    -   User grants `desktop:click`, `fs:read:~/Documents`, `browser:navigate` tokens.
    -   Tokens are signed by the local keychain and validated by the safety gate.
    -   Tokens expire after task completion or user-defined TTL.

**Human Approval Layers:**
-   **Level 0 (Full Trust):** User pre-approves all actions for a session (dangerous, but available).
-   **Level 1 (Standard):** Irreversible actions require approval via Tauri native dialog.
-   **Level 2 (Paranoid):** Every tool call requires approval.
-   Approval state is persisted to SQLite and synchronized with the Tauri GUI via gRPC -> Supervisor -> WS.

### 4.7 Infrastructure

**IPC Strategy:**
```
┌──────────────┐     gRPC (mTLS)      ┌──────────────────┐
│  Tauri GUI   │◄────────────────────►│  Go Supervisor   │
│  (React)     │   + WebSocket Events │  (Daemon)        │
└──────────────┘                      └────────┬─────────┘
       │                                       │
       │ Tauri Commands                        │ Process Mgmt
       │ (start/stop/status)                   │ (spawn/kill/monitor)
       │                                       │
       ▼                                       ▼
┌──────────────────────────────────────────────────────────┐
│              Python AgentKernel (Child Process)          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │ gRPC Server  │  │  Event Bus   │  │   Runtime    │   │
│  │ (RuntimeSvc) │  │ (Local async)│  │   Kernel     │   │
│  └──────────────┘  └──────────────┘  └──────────────┘   │
└──────────────────────────────────────────────────────────┘
```

**Event Bus (Local):**
-   `LocalEventBus`: `asyncio.Queue` based with weak subscriber references.
-   Events are typed Pydantic models (not raw JSON).
-   Go Supervisor subscribes to a gRPC bi-directional stream for kernel events.

**Streaming Layer:**
-   Kernel events -> gRPC streaming -> Go Supervisor -> WebSocket -> Tauri frontend.
-   No Redis, no SSE, no FastAPI WebSocket in the hot path.

**Observability:**
-   **Logs:** Structured JSON lines to `~/.agentos/logs/agentos.log` with rotation (10MB x 5 files).
-   **Metrics:** In-memory gauges + SQLite table `metrics_snapshots` (1-minute resolution, 30-day retention).
-   **Traces:** SQLite table `traces` with span tree structure.
-   **Alerts:** Local desktop notifications via Tauri API for anomaly detection.

**Crash Recovery:**
-   Go Supervisor monitors Python process health via gRPC health checks.
-   On crash, Supervisor restarts Python runtime.
-   On restart, `AgentKernel` scans SQLite for `INTERRUPTED` or `RUNNING` tasks and resumes them from checkpoints.
-   Browser and desktop sessions are marked as stale and re-initialized on resume.

**State Persistence:**
-   SQLite with WAL mode (`PRAGMA journal_mode=WAL`).
-   Single writer (AgentKernel), multiple readers (Go Supervisor for API queries).
-   Automated VACUUM on startup if DB size > 1GB.

---

## 5. Part 4: Migration Strategy & Execution Plan

### 5.1 Phase 1: Foundation & Baseline (Weeks 1-2)
**Objective:** Establish a stable, fully tested baseline of the current desktop-native path.

**Systems Involved:**
-   `app/desktop_entry.py`
-   `app/bootstrap.py`
-   `app/runtime/grpc_server.py`
-   `app/langgraph/sqlite_checkpointer.py`
-   `supervisor/`
-   `gui/src-tauri/`

**Deliverables:**
1.  **Dependency Inventory:** Document every import and runtime touchpoint that accesses Redis or PostgreSQL when `RUNTIME_MODE=grpc`.
2.  **Stub Fixes:** Implement real `start_daemon`, `stop_daemon`, `get_daemon_status` in Tauri commands.
3.  **Test Baseline:** Ensure `pytest tests/` passes with:
    -   `AGENTOS_RUNTIME_MODE=grpc`
    -   `DATABASE_URL=sqlite+aiosqlite:///:memory:`
    -   `REDIS_URL=""`
4.  **gRPC Validation:** Verify Go Supervisor can launch Python runtime, execute a task, and receive events end-to-end.

**Architectural Decisions:**
-   Confirm Go Supervisor as the parent process and Python runtime as the child.
-   Decide on SQLite file location (`~/.agentos/agentos.db` on all platforms).

**Validation Criteria:**
-   [ ] All unit tests pass in gRPC mode.
-   [ ] All integration tests pass in gRPC mode.
-   [ ] Tauri GUI can start/stop the daemon.
-   [ ] Zero Redis/PostgreSQL connections initiated in gRPC mode (verified via monkeypatch or connection auditing).

**Exit Condition:** The existing desktop path is stable and fully characterized.

---

### 5.2 Phase 2: Decoupling & Dependency Elimination (Weeks 3-6)
**Objective:** Remove hard dependencies on Redis and PostgreSQL in desktop mode without breaking HTTP mode.

**Systems Involved:**
-   `app/memory/short_term.py`
-   `app/memory/persistent.py`
-   `app/memory/redis_pubsub.py`
-   `app/orchestrator/event_bus.py`
-   `app/orchestrator/locks.py`
-   `app/orchestrator/timeouts.py`
-   `app/orchestrator/state_machine.py`
-   `app/orchestrator/queue.py`
-   `app/runtime/worker_pool.py`
-   `app/runtime/scaling.py`
-   `app/middleware/rate_limit.py`
-   `app/middleware/csrf.py`
-   `app/logs/cost_tracker.py`

**Deliverables:**
1.  **LocalEventBus:** Implement `LocalEventBus` (asyncio Queue-based). Refactor `RedisEventBus` to be swappable via factory based on `RUNTIME_MODE`.
2.  **LocalTaskQueue:** Implement `LocalTaskQueue` using `asyncio.PriorityQueue` with SQLite persistence for durability across restarts.
3.  **LocalStateMachine:** Rewrite `TaskStateMachine` to use SQLite as the single source of truth. Remove Redis cache layer.
4.  **LocalLocks:** Replace `ExecutionLock` (Redis) with `asyncio.Lock` and `asyncio.Semaphore` in desktop mode.
5.  **LocalTimeouts:** Replace Redis-backed deadline tracking with in-process `asyncio.wait_for` and `asyncio.timeout`.
6.  **Disable Distributed Coordinators:** Make `WorkerPoolManager` and `HorizontalScalingCoordinator` no-ops in desktop mode.
7.  **Disable Web Middleware:** Ensure `RateLimitMiddleware`, `CSRFMiddleware`, `APIKeyMiddleware` are not loaded in desktop mode.
8.  **LocalCostTracker:** Rewrite cost tracking to use SQLite aggregates.

**Architectural Decisions:**
-   Use a **strategy pattern** for all infrastructure dependencies: `RedisX` vs `LocalX`, `PostgresX` vs `SQLiteX`.
-   Define a clear `DesktopMode` feature flag that gates all distributed behavior.

**Validation Criteria:**
-   [ ] Desktop runtime starts successfully with no `REDIS_URL` and no `DATABASE_URL` (or pointing to SQLite).
-   [ ] Tasks can be created, executed, and completed end-to-end.
-   [ ] Events stream to Tauri GUI in real-time.
-   [ ] State machine transitions are correct and durable (verified by crash-testing).
-   [ ] HTTP mode still passes all tests (no regression).

**Exit Condition:** Desktop mode has zero runtime dependency on Redis or PostgreSQL.

---

### 5.3 Phase 3: Runtime Kernel Redesign (Weeks 7-10)
**Objective:** Design and implement the unified `AgentKernel` as the single execution authority.

**Systems Involved:**
-   `app/runtime/runtime.py`
-   `app/runtime/worker.py`
-   `app/runtime/pool.py`
-   `app/orchestrator/core.py`
-   `app/orchestrator/task_runner.py`
-   `app/orchestrator/retry.py`
-   `app/queue/tasks.py` (to be removed)
-   `app/langgraph/state.py`
-   `app/langgraph/nodes.py`

**Deliverables:**
1.  **AgentKernel Class:** A single class that owns:
    -   Task scheduling (`asyncio.PriorityQueue`).
    -   Agent lifecycle (`AgentPool` as semaphore).
    -   Execution routing (Fast Path -> LangGraph).
    -   State management (SQLite writer).
    -   Event emission (`LocalEventBus`).
    -   Resource GC (session reaper).
2.  **Scheduler:** Cooperative cancellation. Timeout enforcement. Priority inheritance for user-facing tasks vs background tasks.
3.  **Simplified TaskRunner:** Merge `ActionV1`, `DirectExecutor`, and `TaskComplexityRouter` into a single decision tree inside the kernel.
4.  **Simplified AgentState:** Remove web-specific metadata. Keep only fields necessary for graph execution.
5.  **Approval State Persistence:** Move `ApprovalStore` from in-memory dict to SQLite table (`approval_sessions`).
6.  **Celery Removal:** Delete `app/queue/tasks.py` from desktop mode. Remove Celery imports from `app/desktop_entry.py`.

**Architectural Decisions:**
-   **Process Model:** Python runtime = single process, single event loop.
-   **Thread Model:** Desktop automation runs in `asyncio.to_thread`. Browser automation stays async (Playwright is async-native).
-   **State Ownership:** `AgentKernel` is the ONLY writer to SQLite task/checkpoint tables. Go Supervisor is a reader.

**Validation Criteria:**
-   [ ] Can execute 100 sequential tasks without restart.
-   [ ] Can execute a 50-step autonomous workflow with checkpointing.
-   [ ] Task cancellation cleans up all sessions (desktop + browser) within 5 seconds.
-   [ ] Crash and restart resumes interrupted tasks correctly.

**Exit Condition:** A single `AgentKernel` process can fully orchestrate all agent execution locally.

---

### 5.4 Phase 4: Security & Safety Hardening (Weeks 11-13)
**Objective:** Implement a desktop-native security model.

**Systems Involved:**
-   `app/auth/`
-   `app/middleware/auth.py`
-   `app/safety/`
-   `app/tools/sandbox.py`
-   `app/mcp/servers/code.py`
-   `app/mcp/servers/shell.py`
-   `gui/src-tauri/src/commands/keychain.rs`
-   `supervisor/crypto.go`

**Deliverables:**
1.  **LocalAuth:** Replace JWT/API key validation in desktop mode with OS user identity check or local keychain secret verification.
2.  **CapabilityManager:** New subsystem. Agents request capabilities. Users grant them via Tauri dialog. Tokens are stored in SQLite and validated by the safety gate.
3.  **Sandboxed Code Execution:** Replace `ToolSandbox` (AST blocking) with a restricted subprocess:
    -   No network access (firewall rules or unshare).
    -   Read-only root filesystem.
    -   Temp directory only.
    -   Resource limits (`ulimit` or Windows Job Objects).
4.  **mTLS Enforcement:** Make mTLS mandatory for Go-Python gRPC. Generate and rotate certs automatically.
5.  **Approval Flow Integration:** Tauri native dialog for human approval. Approval state synced via Supervisor WS.

**Architectural Decisions:**
-   **Trust Model:** User > Supervisor > Kernel > Agent > Tool. Each layer validates the layer below.
-   **Secret Storage:** LLM API keys stored in OS keychain (Tauri `keyring` API), not `.env` files.

**Validation Criteria:**
-   [ ] Unauthorized gRPC connections are rejected.
-   [ ] Sandboxed code cannot read `/etc/passwd` or make network requests.
-   [ ] Irreversible tool calls trigger Tauri approval dialog within 1 second.
-   [ ] Capability tokens expire and are invalidated correctly.

**Exit Condition:** The system is secure for autonomous desktop execution.

---

### 5.5 Phase 5: Observability & Memory Redesign (Weeks 14-16)
**Objective:** Replace cloud-oriented observability with local-first diagnostics.

**Systems Involved:**
-   `app/logs/`
-   `app/observability/`
-   `app/memory/`
-   `app/knowledge/`

**Deliverables:**
1.  **LocalLogger:** Structured JSON logging to rotating files (`~/.agentos/logs/`). Remove dependency on `AGENTOS_LOG_STDERR` hacks.
2.  **LocalMetrics:** In-memory gauges with SQLite persistence. Optional Prometheus export for power users.
3.  **LocalTracer:** SQLite-based span storage. Simple query API for task history.
4.  **LocalAlertManager:** Desktop notifications via Tauri for anomalies.
5.  **Memory Hierarchy Implementation:**
    -   `WorkingMemory`: In-process dict.
    -   `ShortTermMemory`: SQLite with TTL.
    -   `LongTermMemory`: SQLite + `sqlite-vec` for embeddings.
6.  **Knowledge Upgrade:** Integrate `sqlite-vec` or lightweight local embeddings for RAG.

**Architectural Decisions:**
-   **Retention:** Logs rotate (10MB x 5). Metrics keep 30 days. Traces keep 90 days. Old data is archived or deleted.
-   **Performance:** Observability must add <5% overhead to task execution.

**Validation Criteria:**
-   [ ] Can query full task history, traces, and costs from local SQLite.
-   [ ] Log files rotate without data loss.
-   [ ] RAG retrieval returns relevant chunks for domain queries.

**Exit Condition:** Full observability and memory systems work locally without Redis/Postgres.

---

### 5.6 Phase 6: UI Integration & Polish (Weeks 17-19)
**Objective:** Unify the Tauri GUI with the new runtime.

**Systems Involved:**
-   `gui/src-tauri/`
-   `gui/src/`
-   `supervisor/event_bus.go`
-   `supervisor/server.go`

**Deliverables:**
1.  **Daemon Lifecycle:** Real start/stop/restart of Python runtime from Tauri.
2.  **Settings Persistence:** Save/load settings to `~/.config/AgentOS/config.toml`.
3.  **Real-Time Events:** Replace polling with Tauri event listeners for all task updates.
4.  **Native Notifications:** Desktop notifications for task completion, failures, and approval requests.
5.  **Task History:** Load task list and chat history from Supervisor SQLite API.
6.  **Global Shortcuts:** Quick-invoke agent with `Ctrl+Shift+A`.

**Architectural Decisions:**
-   Tauri is the control plane, not the execution plane. It never runs agent logic.
-   All data flows: GUI -> Supervisor -> Kernel -> SQLite -> Supervisor -> GUI.

**Validation Criteria:**
-   [ ] User can create and monitor a task entirely from the GUI.
-   [ ] Approval dialog appears as a native OS notification/dialog.
-   [ ] GUI remains responsive during long-running tasks.
-   [ ] Settings persist across app restarts.

**Exit Condition:** The Tauri GUI is the primary and complete user interface.

---

### 5.7 Phase 7: Optimization & Production Hardening (Weeks 20-22)
**Objective:** Optimize for long-running autonomy and resource efficiency.

**Systems Involved:**
-   `app/runtime/` (kernel)
-   `app/environments/desktop_env.py`
-   `app/environments/browser_env.py`
-   `app/memory/` (SQLite tuning)

**Deliverables:**
1.  **Memory Leak Audit:** Profile desktop sessions and browser contexts. Fix leaks.
2.  **Resource Limits:** Enforce CPU/memory limits per task. Kill runaway tasks.
3.  **SQLite Tuning:** WAL mode config, connection pooling (`aiosqlite`), indexing strategy.
4.  **Background Execution:** Agent continues running when Tauri GUI is closed (system tray mode).
5.  **Crash Recovery:** Automated restart and task resume. Test with simulated kernel crashes.
6.  **24-Hour Stress Test:** Continuous autonomous operation with periodic tasks.

**Architectural Decisions:**
-   **Resource Budgets:** Each task gets a memory budget (e.g., 500MB) and CPU budget (e.g., 1 core). Exceeding them triggers graceful termination.
-   **Session Limits:** Max 5 concurrent browser tabs, max 1 desktop session per task.

**Validation Criteria:**
-   [ ] 24-hour stress test completes with <10% memory growth.
-   [ ] No state corruption after 10 simulated crashes.
-   [ ] Background tasks complete successfully while GUI is closed.
-   [ ] SQLite query times <50ms for all common operations.

**Exit Condition:** The system is ready for production desktop deployment.

---

### 5.8 Phase 8: Cloud Augmentation (Optional, Weeks 23-24)
**Objective:** Re-introduce cloud capabilities as optional plugins.

**Systems Involved:**
-   New `app/cloud_sync/` module
-   New `app/cloud_api/` module
-   `app/config/settings.py`

**Deliverables:**
1.  **Cloud Sync Module:** Optional background sync of local SQLite to cloud PostgreSQL.
2.  **Web Dashboard:** Lightweight FastAPI app (separate process) for remote monitoring.
3.  **Cloud LLM Cache:** Cache cloud LLM responses locally for offline replay.

**Validation Criteria:**
-   [ ] Desktop runtime functions fully offline.
-   [ ] Cloud sync is opt-in and encrypted.

**Exit Condition:** Cloud is a value-add, not a dependency.

---

## 6. Dependency Elimination Plan

| Dependency | Current Usage | Desktop Replacement | Elimination Complexity | Risk |
|------------|---------------|---------------------|------------------------|------|
| **Redis** | Event bus, locks, queues, rate limits, CSRF, caching, cost tracking, pub/sub | `LocalEventBus`, `asyncio.Lock`, `asyncio.PriorityQueue`, disabled middleware, SQLite caching | Medium | High (many touchpoints) |
| **PostgreSQL** | Primary DB for 30+ tables, checkpoints, traces | SQLite with WAL mode (`aiosqlite`) | Medium | Medium (dialect differences, migrations) |
| **Celery** | Background task execution | In-process `asyncio.Task` scheduling | Low | Low (already bypassed in gRPC) |
| **FastAPI** | Web API, WS, SSE, middleware | gRPC server + Go Supervisor HTTP proxy | Medium | Medium (frontend depends on Supervisor API) |
| **Uvicorn** | ASGI server for FastAPI | Not needed in desktop mode | Low | Low |
| **JWT / API Keys** | Auth for web requests | OS identity / mTLS / local keychain | Medium | Medium (auth is security-critical) |
| **Prometheus Client** | Metrics export | In-memory gauges + optional export | Low | Low |
| **Redis Pub/Sub** | Real-time events | Local asyncio Queue + gRPC streaming | Low | Low |
| **CORS Middleware** | Browser security | Not needed in desktop mode | Low | Low |
| **CSRF Middleware** | Web form security | Not needed in desktop mode | Low | Low |
| **Rate Limit Middleware** | API abuse prevention | Not needed in desktop mode | Low | Low |
| **Docker** | Local deployment | Native binaries / installers | Low | Low |

---

## 7. Risk Analysis

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| **Hidden Coupling to Redis/Postgres** | High | High | Phase 1 audit + monkeypatch connection blocking during tests |
| **SQLite Concurrency Bottlenecks** | Medium | High | WAL mode + single writer + read-only readers. Stress test in Phase 7. |
| **Asyncio Blocking in Desktop Automation** | Medium | High | Audit all desktop calls; use `asyncio.to_thread` for blocking Win32 APIs |
| **State Corruption on Crash** | Medium | Critical | WAL mode + checkpoint resume + approval state persistence |
| **Tauri-Go-Python Version Drift** | Medium | Medium | Protocol buffers enforce interface contracts. CI builds all three. |
| **Over-Simplification Breaking Features** | Low | Medium | Maintain HTTP mode as a branch. Feature parity tested per phase. |
| **Memory Leaks in Long Runs** | High | High | Phase 7 dedicated profiling. Resource budgets. Session limits. |
| **Security Regression (Local Auth)** | Low | Critical | Phase 4 security audit. Penetration test of IPC boundaries. |

---

## 8. Validation Criteria Summary

| Phase | Key Validation |
|-------|----------------|
| **1** | Tests pass in gRPC mode. Zero Redis/PG connections. |
| **2** | Runtime starts without Redis/PG. Tasks execute end-to-end. |
| **3** | 100 tasks / 50-step workflow. Cancellation cleans up. Crash resumes. |
| **4** | mTLS enforced. Sandbox escapes blocked. Approval dialog <1s. |
| **5** | Full history queryable from SQLite. RAG works. Logs rotate. |
| **6** | Full task lifecycle in GUI. Native notifications. Settings persist. |
| **7** | 24h stress test. <10% memory growth. No corruption. |
| **8** | Full offline capability. Cloud sync opt-in. |

---

## 9. Appendices

### Appendix A: Recommended Folder Structure (Target)

```
AgentOS/
├── desktop_kernel/              # NEW: Unified Python runtime
│   ├── __main__.py              # Entry point for Supervisor
│   ├── kernel.py                # AgentKernel
│   ├── scheduler.py             # asyncio PriorityQueue scheduler
│   ├── state_manager.py         # SQLite single-writer
│   ├── event_bus.py             # LocalEventBus
│   ├── lifecycle.py             # Startup, shutdown, GC
│   ├── auth/
│   │   ├── local_auth.py        # OS identity / keychain
│   │   └── capabilities.py      # Capability token manager
│   ├── agents/
│   │   ├── runtime.py           # LangGraph integration
│   │   ├── state.py             # Simplified AgentState
│   │   ├── nodes.py             # Planner, executor, verifier
│   │   └── router.py            # Fast path routing
│   ├── tools/
│   │   ├── registry.py          # ToolRegistry
│   │   ├── sandbox.py           # Subprocess sandbox
│   │   └── capabilities.py      # Tool capability definitions
│   ├── environments/
│   │   ├── desktop_controller.py
│   │   ├── browser_controller.py
│   │   └── os_bridge.py         # gRPC calls to Go Supervisor
│   ├── memory/
│   │   ├── working.py
│   │   ├── short_term.py        # SQLite TTL
│   │   ├── long_term.py         # SQLite + sqlite-vec
│   │   └── episodic.py
│   ├── observability/
│   │   ├── logger.py            # File-based structured logs
│   │   ├── metrics.py           # In-memory + SQLite
│   │   ├── tracer.py            # SQLite spans
│   │   └── alerts.py            # Desktop notifications
│   ├── safety/
│   │   ├── gate.py              # Safety gate
│   │   ├── approval.py          # SQLite-backed approval
│   │   └── guardrails.py
│   └── persistence/
│       ├── sqlite.py            # aiosqlite connection pool
│       ├── checkpoints.py       # SQLiteCheckpointSaver
│       └── artifacts.py         # Local filesystem store
│
├── supervisor/                  # Go daemon (existing, expanded)
│   ├── main.go
│   ├── runtime_server.go
│   ├── event_bus.go
│   ├── sqlite_store.go          # Expand for all tables
│   └── grpc/
│       └── desktop.proto        # Expand for streaming
│
├── gui/                         # Tauri app (existing, expanded)
│   ├── src-tauri/
│   └── src/
│
├── desktop/                     # Rust desktop automation (existing)
│
├── cli/                         # Rust CLI (existing)
│
├── tui/                         # Rust TUI (existing)
│
└── cloud_api/                   # OPTIONAL: FastAPI for cloud mode
    └── main.py
```

### Appendix B: Component Decision Matrix (Detailed)

| Component | Verdict | Action | Rationale |
|-----------|---------|--------|-----------|
| LangGraph | **KEEP** | Simplify state | Correct abstraction for agent workflows |
| FastAPI | **REMOVE** | Move to `cloud_api/` | Not needed for local IPC |
| Celery | **REMOVE** | Delete from desktop | Local asyncio is sufficient |
| Redis | **REMOVE** | Replace with local equivalents | Single point of failure; overkill for 1 user |
| PostgreSQL | **DEPRECATE** | Make optional cloud backend | SQLite is sufficient locally |
| SQLite | **ELEVATE** | Make primary store | WAL mode handles concurrency |
| Go Supervisor | **ELEVATE** | Make primary daemon | Correct system-level anchor |
| Tauri GUI | **ELEVATE** | Make primary UI | Native, lightweight, secure |
| gRPC | **EXPAND** | Add streaming protos | Correct IPC for desktop |
| MCP Servers | **KEEP** | Harden sandboxing | Good tool abstraction |
| Playwright | **KEEP** | Manage lifecycle strictly | Standard for browser automation |
| uiautomation/pyautogui | **KEEP** | Abstract behind interface | Standard for Windows desktop |
| JWT/API Keys | **REPLACE** | Local auth / mTLS | Wrong model for local app |
| Prometheus | **REPLACE** | Local metrics store | Wrong model for local debugging |
| Redis Event Bus | **REPLACE** | Local asyncio bus | Wrong model for single process |
| Redis Locks | **REPLACE** | asyncio locks | Wrong model for single process |

### Appendix C: Event Flow Diagram (Pseudocode)

```
# User creates task via Tauri GUI
Tauri.invoke('create_task', { query: '...' })
  -> POST http://127.0.0.1:8080/api/v1/tasks  (Go Supervisor)
    -> gRPC CreateTask to Python AgentKernel
      -> AgentKernel.Scheduler.enqueue(task)
        -> AgentKernel.ExecutionEngine.run(task)
          -> LangGraph.invoke(state, config)
            -> executor_node -> tool_registry.execute('desktop__click')
              -> DesktopController.click(x, y)
                -> gRPC OSBridge to Go Supervisor (optional, for elevated ops)
          -> LocalEventBus.publish('task:updated', event)
            -> gRPC streaming to Go Supervisor
              -> Supervisor.EventHub.broadcast(ws_clients)
                -> Tauri WS Client receives message
                  -> app_handle.emit_all('supervisor:task:updated')
                    -> React Dashboard component updates
```

### Appendix D: IPC Strategy Details

**Go Supervisor -> Python Kernel (gRPC):**
-   **Transport:** Unix Domain Socket (Linux/macOS) or Named Pipe (Windows) for zero-overhead local IPC. Fallback to TCP localhost only for debugging.
-   **Security:** mTLS with auto-generated RSA-4096 certs stored in `~/.agentos/certs/`.
-   **Services:**
    -   `RuntimeService`: Task CRUD, execution control.
    -   `EventService`: Bi-directional streaming for events and logs.
    -   `HealthService`: Liveness and readiness probes.

**Tauri GUI -> Go Supervisor (HTTP + WebSocket):**
-   **REST:** For CRUD operations (tasks, settings, history).
-   **WebSocket:** For real-time event streaming.
-   **Auth:** None required for local localhost communication (OS firewall isolates). If remote access is enabled, use mTLS client certs.

**Python Kernel -> Go Supervisor (gRPC):**
-   **OS Bridge Service:** For privileged operations (file watching, process spawning, elevated permissions) that are safer in Go than Python.

---

## 10. Conclusion

AgentOS has the right bones for a world-class desktop-native autonomous agent platform. The Tauri GUI, Go Supervisor, and gRPC runtime mode are architecturally sound decisions that should be **elevated to first-class status**.

The migration is fundamentally an exercise in **subtraction and unification:**
-   **Subtract:** Redis, Celery, PostgreSQL (as mandatory), FastAPI, JWT, and distributed middleware from the local path.
-   **Unify:** Merge the fragmented runtime into a single `AgentKernel` with SQLite as the source of truth.

By following the phased execution plan, the system will evolve from a web-oriented distributed prototype into a production-grade, local-first autonomous desktop runtime capable of the long-running, low-latency, reliable execution required by systems like Claude Computer Use and Operator.

**The North Star is simple: one user, one machine, one database, one kernel.**

---
*End of Blueprint*
