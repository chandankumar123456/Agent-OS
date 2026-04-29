# AgentOS v2 — LangGraph + MCP Agent Operating System

> **AgentOS is NOT a chatbot.** It is a structured, stateful agent execution system where AI agents reason via LangGraph state machines and act on the system via the Model Context Protocol (MCP). Every execution is traceable, checkpointed, and observable.

## Core Mechanism

```
User Query → Capability Classification → Feasibility Check → Action V1 Fast Path?
→ [Yes] Deterministic Executor → Verifier → Result
→ [No]  LangGraph Compile → Planner → Executor (Tools/MCP) → Verifier → (Approval Gate) → Summarizer → Result
```

A user submits a query. The system classifies required capabilities and checks feasibility. For simple, deterministic tasks (browser navigation, desktop automation, file creation), **Action V1** bypasses the full LangGraph overhead and executes directly via MCP tools with deterministic verification. Complex or ambiguous tasks still flow through the full LangGraph StateGraph (planner → executor → verifier → summarizer). Human approval gates can pause execution via LangGraph `interrupt()`. Every LangGraph step is checkpointed to PostgreSQL for resume across restarts.

## System Architecture

AgentOS is organized into 8 layers, each with strict single responsibility:

```mermaid
graph TB
    subgraph "Layer 1 — Frontend (React 18 + Vite)"
        FE[React UI<br/>Tailwind CSS + Shepherd.js]
    end

    subgraph "Layer 2 — API Gateway (FastAPI)"
        API[FastAPI Server<br/>JWT Auth + Rate Limiting]
        WS[WebSocket Server<br/>Real-time Events]
    end

    subgraph "Layer 3 — Orchestration"
        ORCH[Orchestrator<br/>Mode Selection + Fallback]
        LG[LangGraph Engine<br/>StateGraph Compilation]
        PIPE[PipelineExecutor<br/>Legacy Fallback]
    end

    subgraph "Layer 4 — LangGraph Execution Engine"
        PLAN[planner_node]
        EXEC[executor_node]
        VER[verifier_node]
        APPROV[approval_node<br/>interrupt()]
        SUMM[summarizer_node]
        PLAN --> EXEC --> VER --> APPROV --> SUMM
        EXEC -. replan .-> PLAN
    end

    subgraph "Layer 5 — Agent Runtime"
        RUNTIME[AgentRuntime<br/>Singleton Registry]
        WORKER[AgentWorker<br/>Inbox Queue]
        FACT[AgentFactory<br/>Agent Creation]
        POOL[AgentPool<br/>Semaphore 100]
    end

    subgraph "Layer 6 — MCP + Tools"
        MCP_MGR[MCPClientManager<br/>Server Lifecycle]
        FS[Filesystem Server]
        SH[Shell Server]
        BR[Browser Server]
        TREG[ToolRegistry<br/>Built-in + MCP]
        SANDBOX[ToolSandbox<br/>AST Validation]
    end

    subgraph "Layer 7 — Safety + Observability"
        GUARD[Guardrails<br/>Input/Output Validation]
        TRACE[TraceManager<br/>Span Persistence]
        METRICS[MetricsCollector<br/>Prometheus Export]
        LOG[StructuredLogger<br/>JSON Logs]
    end

    subgraph "Layer 8 — Memory + Persistence"
        PG[(PostgreSQL<br/>Long-term State)]
        REDIS[(Redis<br/>Short-term Cache + PubSub)]
        CHK[Checkpoints<br/>LangGraph State]
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

## LangGraph Execution Engine

AgentOS v2 uses **LangGraph StateGraph** as its primary execution engine. All agent reasoning flows through compiled state graphs with persistent PostgreSQL checkpoints.

### Architecture (LangGraph Nodes + Flow)

```mermaid
graph LR
    BEGIN([BEGIN]) --> PLAN[planner_node]
    PLAN --> EXEC[executor_node]
    EXEC -->|steps remain| EXEC
    EXEC -->|all steps done| VER[verifier_node]
    VER -->|approval required| APPROV[approval_node<br/>interrupt()]
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

### Node Descriptions

| Node | Name | Responsibility |
|------|------|---------------|
| 1 | planner_node | Generates OS-aware execution plan with capability context |
| 2 | executor_node | Executes current step using ToolRegistry (built-in + MCP) |
| 3 | verifier_node | Deterministic verification + LLM semantic validation |
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
        BENV[BrowserEnvironment<br/>Playwright]
    end

    subgraph "MCP Servers (stdio transport)"
        FS[FilesystemServer<br/>FastMCP]
        SH[ShellServer<br/>FastMCP]
        CA[CloudAPIServer<br/>FastMCP]
    end

    subgraph "System Resources"
        DISK[(File System)]
        SHELL[Shell / Process]
        WEB[Web / HTTP]
        BROWSER[(Browser UI<br/>Chromium)]
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
│   ├── langgraph/                     # v2 LangGraph execution engine
│   │   ├── state.py                   # AgentState TypedDict
│   │   ├── nodes.py                   # planner, executor, verifier, approval, summarizer
│   │   ├── graphs.py                  # Graph compilers per mode
│   │   └── checkpointer.py            # PostgreSQL checkpoint saver
│   ├── orchestrator/
│   │   ├── core.py                    # Orchestrator with LangGraph compilation
│   │   ├── pipeline.py                # Legacy plan → execute → verify pipeline
│   │   ├── builder.py                 # Workflow DAG persistence
│   │   ├── executor.py                # Single-step execution service
│   │   ├── workflow.py                # DAG engine with AST sandbox
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
│   │   ├── base.py                    # BaseTool, ToolInput, ToolOutput
│   │   ├── search.py                  # SearchTool
│   │   ├── calculator.py              # CalculatorTool
│   │   └── text_processor.py          # TextProcessorTool
│   ├── capabilities/                  # Capability system
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

## Testing Strategy

- **Unit tests**: Agent logic, tool parsing, guardrails, retry logic
- **Integration tests**: Runtime initialization, mode strategy factory, task lifecycle
- **End-to-end tests**: API routes, task execution with mocked LLM
- **Observability tests**: Trace persistence, metrics export, health endpoints
- **LangGraph tests**: Graph compilation, checkpoint persistence, node execution
- **Action V1 benchmarks**: Deterministic execution paths for browser, desktop, filesystem, and multi-step tasks
- **Validation script**: `python validate_fixes.py` tests all Priority 1 systems

Run Action V1 benchmarks:

```bash
pytest tests/test_action_v1_benchmarks.py -v
```

Run the validation suite:

```bash
python validate_fixes.py
```

Run the full pytest suite:

```bash
pytest -q
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
