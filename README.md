# AgentOS v2 — Desktop Automation Agent System with Closed-Loop Execution

> **AgentOS is NOT a chatbot.** It is a structured, stateful agent execution system where AI agents reason via LangGraph state machines and act on the system via the Model Context Protocol (MCP). Every execution is traceable, checkpointed, and observable.

## Overview

AgentOS executes desktop automation tasks through a **closed-loop execution model**: observe → decide → act → verify → recover. The system receives a user query, plans a sequence of desktop actions, executes each action with tool grounding and safety validation, verifies the result before marking success, and automatically recovers from failures.

For simple, deterministic tasks (browser navigation, desktop automation, file creation), **Action V1** bypasses the full LangGraph overhead and executes directly via MCP tools with deterministic verification. Complex or ambiguous tasks flow through the full LangGraph StateGraph (planner → executor → verifier → summarizer). Human approval gates can pause execution via LangGraph `interrupt()`. Every LangGraph step is checkpointed to PostgreSQL for resume across restarts.

## Architecture

AgentOS is organized into 8 layers, each with strict single responsibility:

```mermaid
graph TB
    subgraph "Layer 1 — Frontend (React 18 + Vite)"
        FE["React UI / Tailwind CSS + Shepherd.js"]
    end

    subgraph "Layer 2 — API Gateway (FastAPI)"
        API["FastAPI Server / JWT Auth + Rate Limiting"]
        WS["WebSocket Server / Real-time Events"]
    end

    subgraph "Layer 3 — Orchestration"
        ORCH["Orchestrator / Mode Selection + Fallback"]
        LG["LangGraph Engine / StateGraph Compilation"]
        PIPE["PipelineExecutor / Legacy Fallback"]
    end

    subgraph "Layer 4 — LangGraph Execution Engine"
        PLAN[planner_node]
        EXEC[executor_node]
        VER[verifier_node]
        APPROV["approval_node / interrupt()"]
        SUMM[summarizer_node]
        PLAN --> EXEC --> VER --> APPROV --> SUMM
        EXEC -. replan .-> PLAN
    end

    subgraph "Layer 5 — Agent Runtime"
        RUNTIME["AgentRuntime / Singleton Registry"]
        WORKER["AgentWorker / Inbox Queue"]
        FACT["AgentFactory / Agent Creation"]
        POOL["AgentPool / Semaphore 100"]
    end

    subgraph "Layer 6 — MCP + Tools"
        MCP_MGR["MCPClientManager / Server Lifecycle"]
        FS[Filesystem Server]
        SH[Shell Server]
        BR[Browser Server]
        TREG["ToolRegistry / Built-in + MCP"]
        SANDBOX["ToolSandbox / AST Validation"]
    end

    subgraph "Layer 7 — Safety + Observability"
        GUARD["Guardrails / Input/Output Validation"]
        TRACE["TraceManager / Span Persistence"]
        METRICS["MetricsCollector / Prometheus Export"]
        LOG["StructuredLogger / JSON Logs"]
    end

    subgraph "Layer 8 — Memory + Persistence"
        PG["PostgreSQL / Long-term State"]
        REDIS["Redis / Short-term Cache + PubSub"]
        CHK["Checkpoints / LangGraph State"]
    end

    FE <-->|REST API| API
    FE <-->|WebSocket| WS
    API --> ORCH
    ORCH --> LG
    ORCH -.-> PIPE
    LG --> PLAN
    LG --> EXEC
    LG --> VER
    LG --> APPROV
    LG --> SUMM
    EXEC --> TREG
    TREG --> MCP_MGR
    MCP_MGR --> FS
    MCP_MGR --> SH
    MCP_MGR --> BR
    TREG --> SANDBOX
    RUNTIME --> WORKER
    WORKER --> FACT
    RUNTIME --> POOL
    ORCH --> RUNTIME
    API --> GUARD
    LG --> TRACE
    LG --> METRICS
    LG --> LOG
    RUNTIME --> PG
    RUNTIME --> REDIS
    LG --> CHK
    CHK --> PG
    WS --> REDIS
    REDIS --> WS
```

| Layer | Responsibility | Technology |
|-------|---------------|------------|
| Frontend | Structured agent interface | React 18, Vite, Tailwind CSS, Shepherd.js |
| API Gateway | Request routing, validation, auth | FastAPI, Uvicorn, Pydantic |
| Orchestration | Mode selection, LangGraph compilation, legacy fallback | LangGraph StateGraph |
| LangGraph Engine | Graph-native execution: plan → execute → verify → summarize | LangGraph, LangChain |
| Agent Runtime | Singleton worker registry, lifecycle, concurrency | Asyncio, Semaphore |
| MCP + Tools | System-level tools via MCP protocol | FastMCP, stdio transport |
| Safety + Observability | Validation, tracing, metrics, structured logging | Pydantic, Prometheus |
| Memory + Persistence | PostgreSQL long-term, Redis short-term, checkpoints | SQLAlchemy async, Redis async |

### Execution Flow

The LangGraph orchestrator compiles mode-specific StateGraphs (task, workflow, autonomous, collaboration). For desktop tasks, the executor delegates to `DesktopGoalLoop`, which runs an observe-act-verify loop with tool grounding and safety gates. If a step fails verification, the recovery engine selects a retry strategy or escalates. Human approval gates pause execution via `interrupt()`.

### DesktopGoalLoop

`DesktopGoalLoop` is the core closed-loop execution engine for desktop automation. It encapsulates the observe-decide-act-verify cycle:

1. **Observe**: Capture desktop state (screenshot, UI tree, window list, element map)
2. **Decide**: LLM selects the next action grounded to allowed tools
3. **Act**: Execute the action via `ActionStabilizer` with retry
4. **Verify**: Check if the goal is reached; if not, continue
5. **Recover**: On repeated failures, `RecoveryEngine` selects a recovery strategy

`DesktopGoalLoop` is reusable by both the LangGraph `executor_node` and the legacy `ExecutorAgent`.

### Verification Layer

The verifier integrates with `verification_engine` via `verify_plan()`. For desktop tasks, verification checks:
- Structural state change (screenshot diff, tree hash diff)
- Semantic correctness (expected outcome achieved)
- Presence of required UI elements or window state

Verification runs before marking any step as successful. Unverified state changes are treated as failures.

### Recovery System

`RecoveryEngine` supports `RecoveryStrategy.DESKTOP` for desktop-specific failures. Recovery strategies include:
- Re-focus the target window
- Rebuild the UI element tree
- Escalate to vision fallback
- Dismiss blocking popups

Tool alternatives for desktop tools are constrained to other desktop tools (never browser or shell fallbacks).

### Perception Layer

The perception layer combines multiple input sources for robust desktop state understanding:
- **UIA tree**: Accessibility tree via `uiautomation` with hash-based caching and TTL
- **Vision fallback**: OCR + icon detection via OpenCV with DPI-aware scaling
- **Window registry**: Tracked window positions and class names
- **Screenshot analysis**: Pixel-level diff for structural change detection

DPI scaling is applied to all vision thresholds to maintain detection accuracy across display configurations.

### Stabilization Layer

`ActionStabilizer` wraps every desktop action with:
- **Pre-action stabilization**: Poll screenshots until UI is stable
- **Post-action verification**: Confirm state changed (screenshot + tree hash)
- **Retry orchestration**: Up to `max_retries` with exponential backoff
- **Infinite loop detection**: Abort after 3 identical no-change failures
- **Popup detection**: Identify and dismiss unexpected modals before acting
- **Action snapshots**: Before/after screenshots, tree hashes, element maps, retry counts

### Infrastructure

- **Checkpointer**: PostgreSQL checkpoint saver with savepoint-based duplicate handling and `IntegrityError` recovery
- **Graph cache**: LRU eviction (max 50 entries) for compiled LangGraph graphs
- **Session lifecycle**: Exception-safe `close()` with per-step try/except, screenshot cleanup, and garbage collection hints

### Safety Layer

`SafetyGate` validates desktop tool parameters against credential patterns. Regex blocks `password`, `api_key`, `token`, `secret`, and similar patterns from being passed to desktop actions.

### Observability

`MetricsCollector` exposes desktop-specific metrics:
- `desktop_task_duration` — histogram of task execution time
- `desktop_action_count` — counter of actions executed per task
- `desktop_retry_count` — counter of retries per action
- `desktop_perception_layer` — counter of perception layer usage (UIA vs vision)

## Execution Flow

The step-by-step lifecycle of a desktop automation task:

1. **Plan received**: Planner generates an OS-aware execution plan with capability context
2. **Action decision**: `DesktopGoalLoop` calls LLM with grounded tool list to select the next action
3. **Action execution**: `ActionStabilizer` stabilizes UI, detects popups, executes action, and verifies state change
4. **Verification**: `verifier_node` calls `verify_plan()` to confirm structural and semantic correctness
5. **Retry / recovery**: On failure, `ActionStabilizer` retries; if exhausted, `RecoveryEngine` selects a recovery strategy
6. **Completion or safe failure**: Task returns SUCCESS with verification notes or FAILURE with recovery context

## Features

Implemented desktop automation capabilities:

- **LLM-driven action decision**: Grounded tool selection with JSON parsing and validation
- **Desktop verification via `verify_plan()`**: Explicit verification before marking success
- **Automatic recovery on failure**: `RecoveryStrategy.DESKTOP` with re-focus, rebuild, vision escalate, popup dismiss
- **Infinite loop detection**: Abort after 3 identical no-change failures
- **UI tree caching with TTL**: Hash-based cache invalidation for performance
- **Vision fallback with DPI scaling**: Automatic fallback to OCR + icon detection with DPI-aware thresholds
- **Perception layer tracking**: Expose `perception_layer` (UIA / vision) in task result metadata
- **Exception-safe session cleanup**: Per-step try/except in `close()` with garbage collection
- **LRU graph cache**: Bounded graph compilation cache with eviction
- **Desktop-specific metrics**: Duration, action count, retry count, perception layer usage
- **Credential safety gate**: Regex blocking of credential patterns in desktop tool parameters

## Reliability Guarantees

- **No silent failures**: Every action is verified before success is reported
- **Explicit verification**: `verify_plan()` confirms structural and semantic correctness
- **Controlled retries**: `ActionStabilizer` retries with backoff, bounded by `max_retries`
- **Recovery before failure**: `RecoveryEngine` attempts re-focus, rebuild, or escalation before marking FAILURE
- **Safe abort conditions**: Infinite loop detection and popup dismissal verification prevent runaway execution

## Metrics and Observability

Desktop tasks emit the following metrics:

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `desktop_task_duration` | Histogram | `success` | Total task execution time |
| `desktop_task_total` | Counter | `success` | Total tasks executed |
| `desktop_action_count` | Counter | `action` | Actions executed per type |
| `desktop_retry_count` | Counter | `action` | Retries per action type |
| `desktop_perception_layer` | Counter | `layer` | UIA or vision fallback usage |

All metrics are exposed via the Prometheus `/health/metrics` endpoint.

## Safety

Desktop tool parameters are validated by `SafetyGate` before execution. Credential patterns are blocked via regex matching on serialized parameters. Blocked patterns include `password=...`, `api_key=...`, `token=...`, `secret=...`, and similar. If a credential pattern is detected, the action is blocked with a clear reason string.

## LangGraph Execution Engine

AgentOS v2 uses **LangGraph StateGraph** as its primary execution engine. All agent reasoning flows through compiled state graphs with persistent PostgreSQL checkpoints.

### Architecture (LangGraph Nodes + Flow)

```mermaid
graph LR
    BEGIN([BEGIN]) --> PLAN[planner_node]
    PLAN --> EXEC[executor_node]
    EXEC -->|steps remain| EXEC
    EXEC -->|all steps done| VER[verifier_node]
    VER -->|approval required| APPROV["approval_node / interrupt()"]
    VER -->|no approval| SUMM[summarizer_node]
    APPROV -->|approved| SUMM
    APPROV -->|rejected| END_REJECT([REJECTED])
    SUMM --> FINISH([FINISH])
    EXEC -. autonomous mode .-> REPLAN[replanner_node]
    REPLAN --> EXEC
```

### AgentState Schema

The engine uses a central `AgentState` (TypedDict) containing:

| Field | Written By | Description |
|-------|-----------|-------------|
| `task_id` | Input | Unique task identifier |
| `user_id` | Input | User who submitted the task |
| `trace_id` | Orchestrator | Trace identifier for observability |
| `query` | Input | The user's original query |
| `config` | Input | Execution configuration (mode, max_steps, etc.) |
| `messages` | All nodes | Conversation history via `add_messages` reducer |
| `plan` | planner_node | Generated execution plan |
| `current_step_index` | executor_node | Index of current plan step |
| `steps` | executor_node | Executed step outputs |
| `step_results` | executor_node | Step result mapping |
| `tool_calls` | executor_node | Record of all tool invocations |
| `verified` | verifier_node | Whether output passed verification |
| `verification_notes` | verifier_node | Human-readable verification result |
| `approved` | approval_node | Human approval status |
| `approval_reason` | approval_node | Reason for approval/rejection |
| `result` | summarizer_node | Final compiled result |
| `error` | Any node | Error message if execution failed |
| `capability_assessment` | Orchestrator | Classified capabilities for query |
| `feasibility_report` | Orchestrator | Feasibility analysis result |
| `environment_config` | Orchestrator | Selected execution environment |
| `verification_reports` | executor/verifier | Deterministic verification reports |
| `recovery_decisions` | executor | Recovery actions taken |
| `execution_state` | executor | Canonical `ExecutionState` with tool truth |

### Node Descriptions

| Node | Name | Responsibility |
|------|------|---------------|
| 1 | planner_node | Generates OS-aware execution plan with capability context |
| 2 | executor_node | Executes current step; delegates desktop steps to `DesktopGoalLoop` |
| 3 | verifier_node | Deterministic verification + LLM semantic validation via `verify_plan()` |
| 4 | approval_node | LangGraph `interrupt()` for human-in-the-loop |
| 5 | summarizer_node | Compiles step outputs into final result |
| 6 | replanner_node | (Autonomous mode) Regenerates plan when stuck |

### Execution Modes

| Mode | Graph | Use Case |
|------|-------|----------|
| **task** | `compile_task_graph()` | Simple REACT agent: plan → execute → verify → summarize |
| **workflow** | `compile_workflow_graph()` | Predefined DAG from workflow definition |
| **autonomous** | `compile_autonomous_graph()` | Self-replanning loop up to `max_steps` |
| **collaboration** | `compile_collaboration_graph()` | Multi-agent parallel execution (fan-out/fan-in) |

### Human-in-the-Loop

The approval node uses LangGraph `interrupt()` to pause execution:

```mermaid
sequenceDiagram
    participant U as User
    participant FE as Frontend
    participant API as FastAPI
    participant LG as LangGraph
    participant DB as PostgreSQL

    U->>FE: Submit query requiring approval
    FE->>API: POST /tasks {query, require_approval: true}
    API->>LG: orchestrator.execute_task()
    LG->>LG: planner_node → executor_node → verifier_node
    LG->>LG: approval_node → interrupt()
    LG->>DB: Checkpoint saved with status "paused"
    API-->>FE: Task status: "awaiting_approval"

    U->>FE: Click Approve
    FE->>API: POST /tasks/{id}/approve
    API->>LG: Resume from checkpoint
    LG->>LG: summarizer_node → completed
    LG->>DB: Final checkpoint saved
    API-->>FE: Task completed with result
```

## Action V1 Fast Path

AgentOS includes an **Action V1** deterministic fast-path layer for simple, single-intent tasks. When the router detects a straightforward instruction (e.g., "open Chrome and search AI news", "create a static HTML page about healthy breakfasts", or "open Notepad and type hello"), Action V1 bypasses the full LangGraph planner/executor/verifier loop and invokes MCP tools directly.

### Architecture

```mermaid
graph LR
    QUERY[User Query] --> SEL[Action V1 Selector]
    SEL -->|deterministic| EXEC[Deterministic Executor]
    SEL -->|complex / ambiguous| LG[LangGraph Engine]
    EXEC --> VER[Deterministic Verifier]
    VER --> RES[Result]
    EXEC -->|failure| FALL[Vision / Human Fallback]
    FALL --> LG
```

### Capabilities

| Capability | Example Query | Tools Used |
|------------|--------------|------------|
| **Browser** | "Open Chrome and search latest AI news" | `browser_env__launch`, `browser_env__navigate`, `browser_env__get_text` |
| **Desktop** | "Open Notepad and type Hello World" | `desktop_env__open_application`, `desktop_env__type_text` |
| **Filesystem** | "Create a static HTML page about breakfast" | `cloud_api__search_web`, `filesystem__write_file` |
| **Multi-step** | "Search AI trends, summarize, and save to file" | `cloud_api__search_web` → LLM summary → `filesystem__write_file` |

### Why Action V1?

- **Speed**: Eliminates LangGraph compilation, checkpoint writes, and multi-node traversal for simple tasks.
- **Reliability**: Avoids PostgreSQL `uq_checkpoint_write` unique-constraint errors that can occur during LangGraph persistence.
- **Cost**: No LLM calls for planning or verification on deterministic successes; LLM is used only for content generation when needed.
- **Safety**: Dangerous keywords (`delete`, `password`, `payment`) trigger an automatic human-approval gate before execution.

### Fallback Behavior

If Action V1 fails or the query is classified as ambiguous, the orchestrator automatically falls back to the full LangGraph execution engine. Complex modes (`workflow`, `autonomous`, `collaboration`) always use LangGraph.

## MCP (Model Context Protocol) Integration

AgentOS uses MCP for system-level tool access. Agents can read files, execute commands, and browse the web through standardized MCP servers.

### MCP Architecture

```mermaid
graph TB
    subgraph "AgentOS Core"
        EX[Executor Node]
        TREG[ToolRegistry]
        MCP_MGR[MCPClientManager]
        BENV["BrowserEnvironment / Playwright"]
    end

    subgraph "MCP Servers (stdio transport)"
        FS["FilesystemServer / FastMCP"]
        SH["ShellServer / FastMCP"]
        CA["CloudAPIServer / FastMCP"]
    end

    subgraph "System Resources"
        DISK[(File System)]
        SHELL[Shell / Process]
        WEB[Web / HTTP]
        BROWSER["Browser UI / Chromium"]
    end

    EX -->|tool_call| TREG
    TREG -->|MCPWrappedTool| MCP_MGR
    TREG -->|BrowserEnvTool| BENV
    MCP_MGR -->|stdio| FS
    MCP_MGR -->|stdio| SH
    MCP_MGR -->|stdio| CA
    FS --> DISK
    SH --> SHELL
    CA --> WEB
    BENV --> BROWSER
```

### Available MCP Tools

**Filesystem Server** (`filesystem`)
- `filesystem__read_file(path)` — Read file contents
- `filesystem__write_file(path, content)` — Write file contents
- `filesystem__list_directory(path)` — List directory entries
- `filesystem__search_files(path, pattern)` — Search files recursively

**Shell Server** (`shell`)
- `shell__execute_command(command, timeout, cwd)` — Run shell command
- `shell__run_script(script, interpreter, timeout)` — Run script with interpreter
- `shell__get_process_status(pid)` — Check process status

**Browser Server** (`browser`)
- `browser__http_request(url, method, headers, body)` — Make HTTP request
- `browser__scrape_page(url, selector)` — Extract text from web page
- `browser__search_web(query, max_results)` — Search web via DuckDuckGo

Tool naming convention: `{server_name}__{tool_name}`.

## Data Flow Diagrams

### Task Execution Flow

```mermaid
sequenceDiagram
    participant U as User
    participant FE as Frontend
    participant API as FastAPI
    participant ORCH as Orchestrator
    participant CAP as Capability Router
    participant FEAS as Feasibility Engine
    participant LG as LangGraph
    participant DB as PostgreSQL
    participant REDIS as Redis

    U->>FE: Submit task query
    FE->>API: POST /tasks {query, mode}
    API->>ORCH: execute_task(query, config)
    ORCH->>CAP: classify(query)
    CAP-->>ORCH: CapabilityAssessment
    ORCH->>FEAS: check(assessment, config)
    FEAS-->>ORCH: FeasibilityResult

    alt BLOCKED or UNSUPPORTED
        ORCH-->>API: AgentOutput(FAILURE)
        API-->>FE: Error response
    else ALLOWED
        ORCH->>LG: compile_mode_graph() + ainvoke(state)
        Note over LG: planner_node generates OS-aware plan
        LG->>LG: executor_node runs steps with ToolRegistry
        LG->>LG: verifier_node validates outputs
        alt require_approval
            LG->>DB: Save checkpoint (interrupt)
            LG-->>ORCH: Status: awaiting_approval
        else no approval
            LG->>LG: summarizer_node compiles result
        end
        ORCH->>DB: Save final task state
        ORCH->>REDIS: Cache context (30 min)
        ORCH-->>API: AgentOutput(SUCCESS)
        API-->>FE: Task result
    end
```

### WebSocket Real-Time Events

```mermaid
sequenceDiagram
    participant FE as Frontend
    participant API as FastAPI
    participant MGR as ConnectionManager
    participant BUS as RedisEventBus
    participant REDIS as Redis
    participant LG as LangGraph

    FE->>API: WebSocket /ws/tasks/{task_id}?token=...
    API->>API: verify_access_token(token)
    API->>MGR: connect(task_id, websocket)
    MGR-->>FE: Connection accepted

    par Event Subscription
        API->>BUS: subscribe("task:{task_id}")
        BUS->>REDIS: SUBSCRIBE agentos:task:{task_id}
    and Task Execution
        LG->>LG: Node execution
        LG->>BUS: publish("task:{task_id}", Event)
        BUS->>REDIS: PUBLISH agentos:task:{task_id}
    end

    REDIS-->>BUS: Message received
    BUS-->>API: Event parsed
    API->>MGR: broadcast(task_id, event.json())
    MGR-->>FE: SSE data: {event}

    FE->>API: ping
    API-->>FE: pong

    FE->>API: Close connection
    API->>MGR: disconnect(task_id, websocket)
    API->>BUS: unsubscribe cleanup
```

### Tool Execution Flow

```mermaid
sequenceDiagram
    participant EX as Executor Node
    participant LLM as LLM Client
    participant TREG as ToolRegistry
    participant MCP as MCPWrappedTool
    participant MGR as MCPClientManager
    participant FS as Filesystem Server

    EX->>LLM: complete_json(messages)
    LLM-->>EX: {tool_call: {name, params}}
    EX->>TREG: get(tool_name)
    TREG-->>EX: MCPWrappedTool
    EX->>MCP: execute(ToolInput)
    MCP->>MGR: call_tool(name, arguments)
    MGR->>FS: stdio transport
    FS-->>MGR: result
    MGR-->>MCP: result
    MCP-->>EX: ToolOutput(success, result)
    EX->>EX: _remap_tool_params (path normalization)
    EX->>EX: verification_engine.verify()
    EX->>LLM: Feed result back as message
```

### Authentication Flow

```mermaid
sequenceDiagram
    participant U as User
    participant FE as Frontend
    participant API as FastAPI
    participant AUTH as Auth Router
    participant USER as User Repo
    participant DB as PostgreSQL

    U->>FE: Login with email/password
    FE->>API: POST /auth/login
    API->>AUTH: login(request)
    AUTH->>USER: get_by_email(email)
    USER->>DB: SELECT user
    DB-->>USER: user record
    USER-->>AUTH: user

    alt User not found or wrong password
        AUTH-->>API: HTTP 401
        API-->>FE: {error: "Invalid credentials"}
    else Valid credentials
        AUTH->>AUTH: create_access_token({sub, email, role})
        AUTH->>AUTH: create_refresh_token({sub, email, role})
        AUTH-->>API: TokenResponse
        API-->>FE: {access_token, refresh_token, user}
        FE->>FE: Store tokens in localStorage
    end

    Note over FE,API: Token Refresh
    FE->>API: API request with expired token
    API-->>FE: HTTP 401 {error: "token_expired"}
    FE->>API: POST /auth/refresh {refresh_token}
    API->>AUTH: refresh(request)
    AUTH->>AUTH: verify_access_token(refresh_token)
    AUTH->>AUTH: create_access_token(...)
    AUTH-->>API: TokenResponse
    API-->>FE: {access_token, refresh_token}
    FE->>FE: Update localStorage
```

## Runtime Initialization

The `AgentRuntime` is a singleton that manages all agent workers. It uses idempotent initialization with a Redis mutex to prevent duplicate setup across processes.

```mermaid
sequenceDiagram
    participant MAIN as FastAPI Main
    participant RT as AgentRuntime
    participant LOCK as asyncio.Lock
    participant REDIS as Redis
    participant DB as PostgreSQL

    MAIN->>RT: initialize()
    RT->>LOCK: acquire _init_lock
    RT->>RT: if _initialized: return

    RT->>REDIS: SET agentos:runtime:init_mutex NX EX 3600
    alt Mutex acquired
        REDIS-->>RT: OK
        RT->>RT: Register core_planner, core_executor, core_verifier
        RT->>DB: Persist core agents to DB
    else Mutex held by other process
        REDIS-->>RT: nil
        RT->>RT: Skip DB writes
    end

    RT->>DB: load_from_db()
    RT->>RT: _initialized = True
    RT-->>MAIN: Done
```

## Path Awareness

AgentOS ensures paths are OS-aware. The planner generates absolute paths appropriate for the current OS, and the executor remaps any hallucinated foreign paths.

| OS | Desktop Path Format | Home Path Format |
|----|-------------------|-----------------|
| Windows | `C:\Users\Name\Desktop` | `C:\Users\Name` |
| macOS | `/Users/name/Desktop` | `/Users/name` |
| Linux | `/home/name/Desktop` | `/home/name` |

Path remapping rules:
- Unix-style paths on Windows are remapped to the current home/desktop
- Windows-style paths on Unix are remapped by stripping the drive letter
- `~` is expanded to the user's home directory
- File extensions (`.txt`, `.py`, etc.) are preserved during remapping

## API Endpoint Summary

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `POST` | `/api/v1/auth/signup` | User registration | Public |
| `POST` | `/api/v1/auth/login` | User login | Public |
| `POST` | `/api/v1/auth/refresh` | Token refresh | Public |
| `GET` | `/api/v1/agents` | List agents | Bearer |
| `POST` | `/api/v1/agents` | Register agent | Bearer |
| `GET` | `/api/v1/agents/{id}` | Get agent | Bearer |
| `GET` | `/api/v1/tools` | List tools | Bearer |
| `POST` | `/api/v1/tools` | Register tool | Bearer |
| `POST` | `/api/v1/tools/{name}/execute` | Execute tool | Bearer |
| `GET` | `/api/v1/tools/mcp-servers` | List MCP servers | Bearer |
| `POST` | `/api/v1/tools/mcp-servers` | Register MCP server | Bearer |
| `GET` | `/api/v1/tools/categories` | Tool categories | Bearer |
| `POST` | `/api/v1/tasks` | Create task | Bearer |
| `GET` | `/api/v1/tasks` | List tasks | Bearer |
| `GET` | `/api/v1/tasks/{id}` | Get task | Bearer |
| `POST` | `/api/v1/tasks/{id}/approve` | Approve task | Bearer |
| `POST` | `/api/v1/tasks/{id}/reject` | Reject task | Bearer |
| `GET` | `/ws/tasks/{id}` | WebSocket events | Query token |
| `GET` | `/health` | Health check | Public |
| `GET` | `/health/ready` | Readiness probe | Public |
| `GET` | `/health/live` | Liveness probe | Public |
| `GET` | `/health/metrics` | Prometheus metrics | Public |

## Tech Stack

| Component | Technology | Version | Purpose |
|-----------|-----------|---------|---------|
| Frontend Framework | React | 19.x | UI components |
| Build Tool | Vite | 8.x+ | Dev server & bundling |
| CSS | Tailwind CSS | 3.4+ | Utility-first styling |
| State Management | React Context | Built-in | Auth, global state |
| Tour Library | Shepherd.js | 12.x+ | User onboarding |
| Backend Framework | FastAPI | 0.121+ | REST API server |
| ASGI Server | Uvicorn | 0.34+ | Production server |
| Validation | Pydantic | 2.12+ | Request/response schemas |
| Auth | python-jose | 3.3+ | JWT token handling |
| Password Hashing | passlib | 1.7+ | Bcrypt with SHA-256 fallback |
| LLM Client | OpenAI SDK | 1.0+ | Async completions |
| Orchestration | LangGraph | 1.1+ | StateGraph execution |
| LangChain | langchain-core | 1.3+ | Message types |
| MCP SDK | mcp | 1.0+ | Model Context Protocol |
| PDF Processing | PyMuPDF (fitz) | 1.23+ | Text extraction |
| Pipeline | Celery | 5.3+ | Background task queue |
| Browser Automation | Playwright | 1.51+ | Real UI browser automation |
| Relational DB | PostgreSQL | 14+ | Session, task, checkpoint storage |
| ORM | SQLAlchemy async | 2.0+ | Async database operations |
| Vector DB | ChromaDB | 0.4+ | Vector storage & similarity search |
| Cache + PubSub | Redis | 7+ | Short-term memory, event bus |
| Monitoring | Prometheus client | 0.19+ | Metrics collection |

## System Guarantees

1. **LangGraph is the primary execution engine.** The orchestrator compiles mode-specific StateGraphs and falls back to legacy pipelines only on exception.
2. **Every execution is checkpointed.** LangGraph state is persisted to PostgreSQL via `PostgresCheckpointSaver` for resume across restarts.
3. **Human-in-the-loop uses LangGraph interrupt.** Approval gates pause execution via `interrupt()` and resume via API calls.
4. **Runtime is the ONLY execution entry point.** No module may instantiate or call agents directly.
5. **MCP tools are auto-discovered.** System servers (filesystem, shell, browser) start automatically and register tools via `MCPWrappedTool`.
6. **Tool registration is idempotent.** Built-in tools register once via singleton; MCP discovery skips if already registered.
7. **Runtime initialization is idempotent.** Redis mutex prevents duplicate core agent registration across processes.
8. **Paths are OS-aware.** Planner generates OS-appropriate paths; executor remaps hallucinated foreign paths.
9. **Authentication uses JWT with refresh tokens.** Access tokens expire in 30 minutes; refresh tokens expire in 7 days.
10. **WebSocket connections authenticate via query token.** Invalid or expired tokens close the connection with code 1008.
11. **All data is strictly typed.** Pydantic models validate every request/response; no untyped dicts in core flow.
12. **Output is validated before persistence.** Guardrails validate pipeline output before database insertion.
13. **Desktop actions are verified before success.** `verify_plan()` confirms structural and semantic correctness.
14. **Desktop tool parameters are safety-checked.** Credential patterns are blocked by `SafetyGate` before execution.
15. **Infinite loops are detected and aborted.** `ActionStabilizer` aborts after 3 identical no-change failures.

## Project Structure

```
AgentOS/
├── README.md                          # This file
├── validate_fixes.py                  # Priority 1 validation script
├── v2_implementation_plan.md          # v2 implementation tracking
├── app/
│   ├── main.py                        # FastAPI application entry point
│   ├── config/
│   │   └── settings.py                # Pydantic Settings with env validation
│   ├── api/
│   │   ├── deps.py                    # Dependency injection (orchestrator singleton)
│   │   ├── ws.py                      # WebSocket connection manager + endpoint
│   │   └── routes/
│   │       ├── auth.py                # JWT login/signup/refresh
│   │       ├── agents.py              # Agent CRUD
│   │       ├── tasks.py               # Task execution + approval
│   │       ├── tools.py               # Tool registry + MCP servers
│   │       ├── config.py              # System configuration
│   │       └── health.py              # Health/readiness/metrics endpoints
│   ├── action_v1/                     # Deterministic fast-path execution
│   │   ├── selector.py                # Lightweight capability selector
│   │   ├── executor.py                # Direct MCP tool executor
│   │   ├── verifier.py                # Deterministic result verifier
│   │   ├── fallback.py                # Vision & human fallback layers
│   │   └── runner.py                  # Action V1 pipeline orchestrator
│   ├── desktop/                       # Desktop automation core
│   │   ├── __init__.py
│   │   └── goal_loop.py               # DesktopGoalLoop: observe-decide-act-verify
│   ├── langgraph/                     # v2 LangGraph execution engine
│   │   ├── state.py                   # AgentState TypedDict
│   │   ├── nodes.py                   # planner, executor, verifier, approval, summarizer
│   │   ├── graphs.py                  # Graph compilers per mode (with LRU cache)
│   │   └── checkpointer.py            # PostgreSQL checkpoint saver
│   ├── orchestrator/
│   │   ├── core.py                    # Orchestrator with LangGraph compilation
│   │   ├── pipeline.py                # Legacy plan → execute → verify pipeline
│   │   ├── builder.py                 # Workflow DAG persistence
│   │   ├── executor.py                # Single-step execution service
│   │   ├── workflow.py                # DAG engine with AST sandbox
│   │   ├── task_runner.py             # Task runner with recovery + perception
│   │   └── modes/                     # Mode strategy implementations
│   ├── runtime/
│   │   ├── runtime.py                 # AgentRuntime singleton with idempotent init
│   │   ├── worker.py                  # AgentWorker with inbox queue
│   │   ├── factory.py                 # AgentFactory
│   │   └── pool.py                    # AgentPool semaphore
│   ├── agents/
│   │   ├── base.py                    # BaseAgent, AgentInput, AgentOutput
│   │   ├── planner.py                 # PlannerAgent
│   │   ├── executor.py                # ExecutorAgent with tool loop + path remapping
│   │   ├── verifier.py                # VerifierAgent
│   │   └── llm_client.py              # OpenAI async client with JSON extraction
│   ├── environments/                  # Execution environments
│   │   ├── desktop_env.py             # DesktopSession (UIA, vision, stabilizer)
│   │   ├── execution_stabilizer.py    # ActionStabilizer + StabilizerConfig
│   │   ├── vision_fallback.py         # HybridVisionParser with DPI scaling
│   │   └── window_registry.py         # WindowRegistry for desktop windows
│   ├── capabilities/                  # Capability system
│   │   ├── recovery.py                # RecoveryEngine + RecoveryStrategy enum
│   │   └── verification.py            # VerificationEngine
│   ├── safety/
│   │   └── gate.py                    # SafetyGate with credential regex
│   ├── mcp/
│   │   ├── client_manager.py          # MCPClientManager (server lifecycle)
│   │   ├── servers/
│   │   │   ├── filesystem.py          # File system MCP server
│   │   │   ├── shell.py               # Shell command MCP server
│   │   │   └── browser.py             # Web browsing MCP server
│   │   ├── bus.py                     # MCPBus (Memory + Redis)
│   │   ├── router.py                  # MessageRouter
│   │   └── protocol.py                # MCPProtocol
│   ├── tools/
│   │   ├── registry.py                # ToolRegistry singleton (built-in + MCP)
│   │   ├── sandbox.py                 # ToolSandbox with AST validation
│   │   ├── grounding.py               # ToolGroundingLayer (exact-match validation)
│   │   ├── base.py                    # BaseTool, ToolInput, ToolOutput
│   │   ├── search.py                  # SearchTool
│   │   ├── calculator.py              # CalculatorTool
│   │   └── text_processor.py          # TextProcessorTool
│   ├── guardrails/                    # Input/output validation
│   ├── logs/                          # Structured logging, tracing, metrics
│   ├── memory/                        # PostgreSQL + Redis persistence
│   └── middleware/                    # Auth middleware, rate limiting
├── frontend/
│   ├── src/
│   │   ├── api/client.ts              # API client with auto-refresh
│   │   ├── context/AuthContext.tsx    # React auth context
│   │   ├── hooks/useWebSocket.ts      # WebSocket hook with reconnect
│   │   ├── pages/                     # Dashboard, Builder, Tools, etc.
│   │   └── components/                # Shared components + Onboarding
│   └── README.md                      # Frontend documentation
└── docker/                            # Docker Compose configuration
```

## Testing

All desktop automation hardening features were implemented using **test-first development**: write a failing test, implement the feature, verify the test passes.

### Major Test Suites

| Test Suite | Coverage |
|-----------|----------|
| `tests/test_execution_stabilizer.py` | Stabilization, verification, retry, infinite loop detection, popup dismissal |
| `tests/test_desktop_env.py` | DesktopSession lifecycle, snapshot history, exception-safe close, tree caching |
| `tests/test_desktop_loop.py` | DesktopGoalLoop, task runner, verifier integration, executor delegation |
| `tests/test_desktop_recovery.py` | RecoveryStrategy.DESKTOP enum, tool alternatives, recovery execution |
| `tests/test_desktop_metrics.py` | MetricsCollector desktop helpers |
| `tests/test_graph_cache.py` | LRU graph cache eviction |
| `tests/test_safety_gate.py` | SafetyGate credential blocking |
| `tests/test_checkpointer.py` | Checkpoint duplicate handling, IntegrityError recovery |
| `tests/test_vision_fallback.py` | DPI scaling, text proximity, text region sizing |
| `tests/test_tool_grounding.py` | Phantom tool removal, exact-match validation |
| `tests/test_executor_agent.py` | Legacy executor reusing DesktopSession, ActionStabilizer, WindowRegistry |

### Running Tests

Run Action V1 benchmarks:

```bash
pytest tests/test_action_v1_benchmarks.py -v
```

Run desktop-specific tests:

```bash
pytest tests/test_desktop_env.py tests/test_desktop_loop.py tests/test_execution_stabilizer.py -v
```

Run the validation suite:

```bash
python validate_fixes.py
```

Run the full pytest suite:

```bash
pytest -q
```

**Test results**: All new tests pass. One pre-existing failure in `test_executor_node_invokes_tool_when_llm_requests_it` (tool registry mock issue) is unrelated to desktop automation changes.

## Limitations

- **Depends on LLM decision quality**: Action selection relies on LLM output; incorrect tool selection can cause failures
- **Perception may fail in complex UIs**: UIA tree and vision fallback may miss elements in heavily customized or non-standard UI frameworks
- **Not fully validated across all desktop environments**: Tested primarily on Windows; behavior on other platforms may vary
- **Vision fallback is heuristic-based**: OCR + icon detection thresholds are tuned for common cases; edge cases may require manual adjustment

## Future Improvements

- **End-to-end benchmarking**: Measure task success rates and latency across diverse desktop applications
- **Improving LLM prompts and grounding**: Refine system prompts and tool descriptions for better action selection accuracy
- **Expanding recovery strategies**: Add more desktop-specific recovery strategies (e.g., window resize, alternative launch methods)
- **Performance optimization**: Reduce screenshot comparison overhead and tree hash computation for faster stabilization

## Setup & Installation

### Prerequisites

- Python 3.11+
- Node.js 20+
- PostgreSQL 14+
- Redis 7+
- Playwright Chromium (for browser automation)

### Environment Configuration

Create a `.env` file:

```env
OPENAI_API_KEY=<your-openai-key>
OPENAI_MODEL=gpt-4o
DATABASE_URL=postgresql+asyncpg://agentos:agentos@localhost:5432/agentos
REDIS_URL=redis://:@localhost:6379/0
SECRET_KEY=your-secret-key-min-32-bytes-long!!!
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
MAX_STEPS_DEFAULT=10
TIMEOUT_DEFAULT=300
MAX_RETRIES=3
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
```

### Backend

```bash
cd AgentOS
pip install -r requirements.txt
playwright install chromium
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

The backend starts on `http://localhost:8000`.

### Frontend

```bash
cd AgentOS/frontend
npm install
npm run dev
```

The frontend starts on `http://localhost:5173`.

### Full Stack (Docker)

```bash
cd docker
docker compose up --build
```

## Deployment Instructions

### Requirements
- Python 3.11+
- PostgreSQL 14+
- Redis 7+
- Node.js 20+ (for frontend)

### Production Checklist
- [ ] Set `DATABASE_URL` with connection pooling tuned for load
- [ ] Set `REDIS_URL` for MCP pub/sub and caching
- [ ] Set `SECRET_KEY` to a persistent 32+ byte secret
- [ ] Configure `MAX_RETRIES`, `TIMEOUT_DEFAULT`, `MAX_STEPS_DEFAULT`
- [ ] Set `OPENAI_API_KEY` and `OPENAI_MODEL`
- [ ] Enable `RedisMCPBus` instead of `MemoryMCPBus` for multi-instance deployments
- [ ] Monitor `/health/ready` for load balancer health checks
- [ ] Scrape `/health/metrics` with Prometheus
- [ ] Ensure MCP system servers have appropriate resource limits

## Scaling Considerations

- **LangGraph Checkpoints**: PostgreSQL table `checkpoints` stores graph state. Index on `thread_id` for fast resume.
- **Agent Workers**: `AgentPool` semaphore limits concurrent agents (default 100).
- **Database**: SQLAlchemy pool (`pool_size=20`, `max_overflow=40`).
- **Asyncio**: Event loop handles 10,000+ coroutines; the real limit is DB connections.
- **Redis**: Use `RedisMCPBus` and `RedisEventBus` for multi-instance deployments.
- **MCP Servers**: Each server runs as a child process. Monitor memory usage.
- **WebSocket**: Connection manager limits 100 connections per task; dead sockets are cleaned up on broadcast failure.

## Troubleshooting Guide

### "Agent core_planner not found in runtime"
Ensure `AgentRuntime.initialize()` is called in the FastAPI lifespan hook. Check `app/main.py`.

### Database connection errors
Verify `DATABASE_URL` and that PostgreSQL is running. Check `/health/ready`.

### Redis connection errors
Verify `REDIS_URL`. Check `/health/ready`.

### Tool execution timeout
Increase timeout in `ToolSandbox` or simplify tool code.

### Output validation failures
Check `app/guardrails/validator.py` rules. Validation failures now raise `UnrecoverableError`.

### Mode not recognized
Ensure the mode name matches a key in `ModeStrategyFactory.STRATEGIES`.

### MCP server not starting
Check logs for `MCP system servers start failed`. Ensure Python modules are importable.

### Checkpoint resume fails
Verify the `checkpoints` table exists in PostgreSQL. It is auto-created on startup.

### WebSocket authentication failures
Ensure the WebSocket URL includes the token query parameter: `/ws/tasks/{task_id}?token={access_token}`.

### Path remapping not working
Verify the executor's `_normalize_paths_in_text` regex matches your path format. The regex supports alphanumeric characters, underscores, hyphens, dollar signs, and dots.

## Contributing

Contributions are welcome. When submitting changes:

1. Follow the existing test-first approach: write a failing test, implement the fix, verify the test passes.
2. Ensure all tests pass before submitting: `pytest -q`
3. Run the validation suite: `python validate_fixes.py`
4. Update this README if your changes affect architecture, features, or guarantees.
5. Keep commits focused and descriptive.

## License

[Add license information here]
