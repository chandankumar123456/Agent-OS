# Agent-OS v2

LangGraph + MCP Agent Operating System for structured AI workflow execution.

## 1) System Overview

Agent-OS v2 is a true **agent operating system** where AI agents reason via LangGraph state machines and act on the system via the Model Context Protocol (MCP). It enforces strict separation between orchestration, execution, communication, tools, safety, and observability.

### Core Design Principles

- **LangGraph as the execution engine**: All agent reasoning flows through compiled state graphs with persistent checkpoints.
- **MCP for system-level tools**: Agents can read files, run commands, and browse the web via standardized MCP servers.
- **Runtime is the ONLY execution entry point**: No module may instantiate or call agents directly.
- **Strategy-based modes**: Task, Workflow, Autonomous, and Collaboration modes are distinct graph compilations.
- **MCP for inter-agent communication**: All cross-agent messaging flows through the Message Control Protocol bus.
- **Sandboxed tool execution**: Custom tools run in a restricted Python environment with blocked builtins and AST validation.
- **Transactional observability**: Spans are persisted in the same conceptual transaction as state updates; metrics are Prometheus-compatible.

---

## 2) Architecture

```text
┌─────────────────────────────────────────────────────────────┐
│  API Layer (FastAPI routes)                                  │
│  - Thin: validation, auth, serialization                    │
├─────────────────────────────────────────────────────────────┤
│  Orchestration Layer                                         │
│  - Orchestrator: compiles LangGraph graphs per mode         │
│  - LangGraph Graphs: plan → execute → verify → summarize    │
│  - PipelineExecutor: legacy plan → execute → verify pipe    │
│  - WorkflowBuilder: DAG construction and persistence        │
│  - StepExecutor: single-step execution via Runtime          │
│  - WorkflowEngine: DAG traversal with condition sandbox     │
├─────────────────────────────────────────────────────────────┤
│  LangGraph Engine (v2 Core)                                  │
│  - StateGraph: compiled per mode (task/workflow/auto/collab)│
│  - Nodes: planner → executor → verifier → approval          │
│  - PostgreSQL Checkpointer: resume across restarts          │
│  - interrupt(): human-in-the-loop approval gates            │
├─────────────────────────────────────────────────────────────┤
│  Mode Strategies                                             │
│  - TaskMode: compile_task_graph — simple REACT agent        │
│  - WorkflowMode: compile_workflow_graph — DAG state graph   │
│  - AutonomousMode: compile_autonomous_graph — loop + replan │
│  - CollaborationMode: compile_collaboration_graph — parallel│
├─────────────────────────────────────────────────────────────┤
│  Agent Layer                                                 │
│  - PlannerAgent, ExecutorAgent, VerifierAgent               │
│  - BaseAgent protocol with execute(input) → output          │
├─────────────────────────────────────────────────────────────┤
│  Runtime Layer (CORE EXECUTION ENGINE)                       │
│  - AgentRuntime: singleton registry agent_id → AgentWorker  │
│  - AgentWorker: owns inbox queue, processes AgentInput      │
│  - AgentFactory: creates agents from config                 │
│  - AgentPool: semaphore-guarded concurrency (~100 workers)  │
├─────────────────────────────────────────────────────────────┤
│  MCP Layer (System Communication + Tools)                    │
│  - MCPClientManager: connects to MCP servers, routes calls  │
│  - System Servers: filesystem, shell, browser (FastMCP)     │
│  - MCPBus: abstract pub/sub (MemoryMCPBus | RedisMCPBus)    │
│  - MessageRouter: routes by receiver_agent to inbox         │
│  - MCPProtocol: message creation, history, bounded log      │
├─────────────────────────────────────────────────────────────┤
│  Tool Layer                                                  │
│  - ToolRegistry: discovers built-in + MCP server tools      │
│  - MCPWrappedTool: adapts MCP tools to BaseTool interface   │
│  - ToolCallParser: extracts tool invocations from LLM text  │
│  - ToolSandbox: restricted builtins + AST validation        │
│  - BaseTool: schema + execute contract                       │
├─────────────────────────────────────────────────────────────┤
│  Safety Layer                                                │
│  - Guardrails: input/output/structural validation           │
│  - ToolSandbox: execution isolation with blocked imports    │
│  - Output validation raises UnrecoverableError on failure   │
├─────────────────────────────────────────────────────────────┤
│  Observability Layer                                         │
│  - StructuredLogger: JSON-structured logs with trace_id      │
│  - TraceManager: span creation, nesting, timing             │
│  - MetricsCollector: Prometheus-compatible counters/hists   │
│  - HealthReporter: /health, /ready, /live, /health/metrics  │
├─────────────────────────────────────────────────────────────┤
│  Memory Layer                                                │
│  - PostgreSQL: long-term persistence (SQLAlchemy async)     │
│  - Redis: short-term context cache + MCP pub/sub            │
│  - Checkpoints: LangGraph state persisted to DB             │
└─────────────────────────────────────────────────────────────┘
```

### Data Flow

1. **Task Creation**: Client → API Route → Orchestrator.execute_task()
2. **LangGraph Compilation**: Orchestrator compiles mode-specific StateGraph + PostgreSQL checkpointer
3. **Graph Execution**: Graph runs planner → executor → verifier → (approval) → summarizer
4. **Tool Use**: Executor node → ToolRegistry (built-in + MCP) → MCPClientManager → MCP Server
5. **Human-in-the-Loop**: Approval node calls `interrupt()` → checkpoint saved → resumed via API
6. **Collaboration**: CollaborationMode → MCPBus → MessageRouter → AgentWorker inbox
7. **Observability**: Every layer emits spans/logs → TraceManager → DB

---

## 3) Layer-by-Layer Explanation

### LangGraph Engine (`app/langgraph/`)

The v2 core execution engine. All agent reasoning flows through compiled state graphs.

- **`state.py`**: `AgentState` TypedDict — shared state with messages, plan, steps, results, approval status.
- **`nodes.py`**: Async node functions:
  - `planner_node`: Calls LLM to generate step-by-step plan
  - `executor_node`: Executes current step using ToolRegistry
  - `verifier_node`: Validates outputs against original query
  - `approval_node`: Uses `langgraph.types.interrupt()` for human approval
  - `summarizer_node`: Compiles final result
- **`graphs.py`**: Graph compilers:
  - `compile_task_graph()`: plan → execute loop → verify → summarize
  - `compile_autonomous_graph()`: loop with replanning condition
  - `compile_workflow_graph()`: state graph from workflow definition nodes
  - `compile_collaboration_graph()`: parallel subgraphs (fan-out/fan-in)
- **`checkpointer.py`**: `PostgresCheckpointSaver` implements `BaseCheckpointSaver` with `JsonPlusSerializer` for persistent checkpoints.

### MCP System Servers (`app/mcp/servers/`)

FastMCP servers that provide system-level capabilities to agents.

- **`filesystem.py`**: `read_file`, `write_file`, `list_directory`, `search_files`
- **`shell.py`**: `execute_command`, `run_script`, `get_process_status`
- **`browser.py`**: `http_request`, `scrape_page`, `search_web`

All servers run as child processes via stdio transport, managed by `MCPClientManager`.

### MCP Client Manager (`app/mcp/client_manager.py`)

- **`MCPClientManager`**: Manages connections to multiple MCP servers
  - `connect_stdio(name, command, args)`: Spawns local MCP server
  - `connect_http(name, url)`: Connects to remote HTTP MCP server (future)
  - `list_tools()`: Aggregates tools from all connected servers
  - `call_tool(name, arguments)`: Routes tool call to correct server
  - `start_system_servers()`: Auto-starts filesystem, shell, browser servers

Tool naming convention: `{server_name}__{tool_name}` (e.g., `filesystem__read_file`).

### Tool Registry 2.0 (`app/tools/registry.py`)

- Discovers built-in tools (Search, Calculator, TextProcessor)
- Discovers MCP server tools via `MCPClientManager`
- Unifies into single list with `MCPWrappedTool` adapter
- Passes unified tool list to LangGraph executor nodes

### API Layer (`app/api/`)

- **Routes**: `tasks.py`, `auth.py`, `tools.py`, `agents.py`, `config.py`, `health.py`
- **Dependency injection**: `deps.py` returns the module-level `orchestrator` singleton
- **No business logic**: Routes validate, serialize, and delegate exclusively

### Orchestration Layer (`app/orchestrator/`)

- **`core.py`**: Orchestrator compiles LangGraph graphs per mode. Falls back to legacy mode strategies if LangGraph fails.
- **`pipeline.py`**: Legacy plan → execute → verify pipeline.
- **`builder.py`**: Persists workflow DAG nodes and edges to PostgreSQL.
- **`executor.py`**: Executes a single step via an agent instance.
- **`workflow.py`**: `WorkflowEngine` traverses DAGs with AST sandbox.

### Mode Strategies (`app/orchestrator/modes/`)

- **`base.py`**: `ModeStrategy` ABC.
- **`task.py`**: Standard pipeline (delegates to LangGraph task graph).
- **`workflow.py`**: Loads predefined workflows from DB.
- **`autonomous.py`**: Replanning loop up to `max_steps`.
- **`collaboration.py`**: Distributes steps via Runtime and MCP messages.

### Runtime Layer (`app/runtime/`)

- **`runtime.py`**: `AgentRuntime` singleton.
- **`worker.py`**: `AgentWorker` owns inbox queue.
- **`factory.py`**: `AgentFactory` creates agents from config.
- **`pool.py`**: `AgentPool` limits concurrent workers.

### MCP Layer (`app/mcp/`)

- **`bus.py`**: `MCPBus` ABC. `MemoryMCPBus` for local dev, `RedisMCPBus` for production.
- **`router.py`**: `MessageRouter` routes messages to channels.
- **`protocol.py`**: `MCPProtocol` creates and sends messages.
- **`client_manager.py`**: Connects to MCP servers and routes tool calls.

### Safety Layer (`app/guardrails/`)

- **`validator.py`**: Input/output validation.
- **`schema.py`**: Pydantic-based output schemas.

### Observability Layer (`app/logs/`)

- **`tracing.py`**: `TraceManager` creates spans.
- **`metrics.py`**: `MetricsCollector` with Prometheus export.
- **`logger.py`**: Structured JSON logging.

### Memory Layer (`app/memory/`)

- **`long_term.py`**: Async SQLAlchemy with connection pooling.
- **`short_term.py`**: Redis client for context cache.
- **`models.py`**: SQLAlchemy models including `CheckpointModel` for LangGraph.

---

## 4) Agent Execution Flow

### Task Mode

```
User Query
    ↓
Orchestrator.compile_graph("task")
    ↓
LangGraph StateGraph:
    planner_node → generates step plan
    executor_node → runs steps with tools
    verifier_node → validates results
    summarizer_node → compiles final output
    ↓
AgentOutput → API Response
```

### With Human Approval

```
...
verifier_node
    ↓
approval_node → interrupt() → checkpoint saved to DB
    ↓
User calls POST /tasks/{id}/approve
    ↓
Graph resumes from checkpoint
    ↓
summarizer_node
```

### Autonomous Mode

```
planner_node
    ↓
executor_node → step complete?
    ↓ no
replanner_node → new plan
    ↓
executor_node → ...
    ↓ yes
verifier_node → summarizer_node
```

---

## 5) MCP Server Setup

MCP system servers start automatically when the FastAPI app starts up. No manual configuration is required.

### Available Tools

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

### Custom MCP Servers

You can register additional MCP servers via the API:

```bash
POST /api/v1/mcp-servers
{
  "name": "my-server",
  "endpoint": "python -m my_mcp_server",
  "auth_scope": "admin"
}
```

Or connect programmatically:

```python
from app.mcp.client_manager import mcp_client_manager
await mcp_client_manager.connect_stdio("my-server", "python", ["-m", "my_mcp_server"])
tools = await mcp_client_manager.list_tools()
```

---

## 6) API Documentation

### Tasks
- `POST /api/v1/tasks` — Create and execute a task
- `GET /api/v1/tasks` — List tasks
- `GET /api/v1/tasks/{task_id}` — Get task details (includes LangGraph state)
- `DELETE /api/v1/tasks/{task_id}` — Cancel/delete task
- `POST /api/v1/tasks/{task_id}/approve` — Approve a paused task
- `POST /api/v1/tasks/{task_id}/reject` — Reject a paused task

### Agents
- `GET /api/v1/agents` — List registered agents
- `POST /api/v1/agents` — Register a new agent
- `GET /api/v1/agents/{agent_id}` — Get agent details

### Tools
- `GET /api/v1/tools` — List available tools (built-in + MCP)
- `POST /api/v1/tools` — Register a custom tool
- `POST /api/v1/tools/{tool_id}/execute` — Execute a tool

### MCP Servers
- `GET /api/v1/mcp-servers` — List MCP servers
- `POST /api/v1/mcp-servers` — Register an MCP server
- `GET /api/v1/mcp-servers/{server_id}/health` — Check server health

### Health & Observability
- `GET /health` — Basic health check
- `GET /health/ready` — Readiness probe (checks DB + Redis)
- `GET /health/live` — Liveness probe
- `GET /health/metrics` — Prometheus-format metrics

### Auth
- `POST /api/v1/auth/token` — Obtain access token

---

## 7) Setup and Environment Configuration

Create a `.env` file:

```env
OPENAI_API_KEY=<your-key>
OPENAI_MODEL=gpt-4o
DATABASE_URL=postgresql+asyncpg://agentos:agentos@localhost:5432/agentos
REDIS_URL=redis://:@localhost:6379/0
MAX_STEPS_DEFAULT=10
TIMEOUT_DEFAULT=300
MAX_RETRIES=3
APP_NAME=Agent-OS
VERSION=0.2.0
```

### Backend

```bash
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Full Stack (Docker)

```bash
cd docker
docker compose up --build
```

---

## 8) Local Development Guide

### Running Tests

```bash
pytest -q
```

### Adding a New Mode

1. Create a graph compiler in `app/langgraph/graphs.py`
2. Register it in `app/orchestrator/core.py` `_execute_with_langgraph()`

### Adding a New MCP Server

1. Create a FastMCP server in `app/mcp/servers/my_server.py`
2. Add it to `MCPClientManager.start_system_servers()`
3. Tools are auto-discovered on connection

### Adding a New Tool

1. Create a class inheriting from `BaseTool`
2. Implement `execute(tool_input: ToolInput) -> ToolOutput`
3. Register in `ToolRegistry._register_default_tools()` or via API

### Adding a New Agent Type

1. Create a class inheriting from `BaseAgent`
2. Register in `AgentFactory.create_agent()`

---

## 9) Testing Strategy

- **Unit tests**: Agent logic, tool parsing, guardrails, retry logic
- **Integration tests**: Runtime initialization, mode strategy factory, task lifecycle
- **End-to-end tests**: API routes, task execution with mocked LLM
- **Observability tests**: Trace persistence, metrics export, health endpoints
- **LangGraph tests**: Graph compilation, checkpoint persistence, node execution

Run the full suite:

```bash
pytest -q
```

---

## 10) Deployment Instructions

### Requirements
- Python 3.11+
- PostgreSQL 14+
- Redis 7+
- Node.js 20+ (for frontend)

### Production Checklist
- [ ] Set `DATABASE_URL` with connection pooling tuned for load
- [ ] Set `REDIS_URL` for MCP pub/sub and caching
- [ ] Configure `MAX_RETRIES`, `TIMEOUT_DEFAULT`, `MAX_STEPS_DEFAULT`
- [ ] Set `OPENAI_API_KEY` and `OPENAI_MODEL`
- [ ] Enable `RedisMCPBus` instead of `MemoryMCPBus` for multi-instance deployments
- [ ] Monitor `/health/ready` for load balancer health checks
- [ ] Scrape `/health/metrics` with Prometheus
- [ ] Ensure MCP system servers have appropriate resource limits

---

## 11) Scaling Considerations

- **LangGraph Checkpoints**: PostgreSQL table `checkpoints` stores graph state. Index on `thread_id` for fast resume.
- **Agent Workers**: `AgentPool` semaphore limits concurrent agents (default 100).
- **Database**: SQLAlchemy pool (`pool_size=20`, `max_overflow=40`).
- **Asyncio**: Event loop handles 10,000+ coroutines; the real limit is DB connections.
- **Redis**: Use `RedisMCPBus` for multi-instance deployments.
- **Celery**: Worker exists in Docker but API uses in-process background tasks.
- **MCP Servers**: Each server runs as a child process. Monitor memory usage.

---

## 12) Troubleshooting Guide

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

---

## 13) File Structure

```
app/
  api/
    deps.py              # Singleton orchestrator dependency
    routes/
      tasks.py           # Task CRUD + execution
      agents.py          # Agent CRUD
      tools.py           # Tool registry + dynamic tool execution
      auth.py            # JWT token generation
      config.py          # System configuration
      health.py          # Health, ready, live, metrics
  langgraph/             # v2 LangGraph execution engine
    state.py             # AgentState TypedDict
    nodes.py             # planner, executor, verifier, approval, summarizer
    graphs.py            # Graph compilers per mode
    checkpointer.py      # PostgreSQL checkpoint saver
  orchestrator/
    core.py              # Orchestrator with LangGraph compilation
    pipeline.py          # Legacy plan → execute → verify pipeline
    builder.py           # Workflow DAG persistence
    executor.py          # Single-step execution service
    workflow.py          # DAG engine with AST sandbox
    context.py           # TaskContext dataclass
    modes/
      base.py            # ModeStrategy ABC
      task.py            # Standard mode
      workflow.py        # Predefined workflow mode
      autonomous.py      # Replanning loop mode
      collaboration.py   # Multi-agent mode with MCP
      factory.py         # Mode registry
  runtime/
    runtime.py           # AgentRuntime singleton
    worker.py            # AgentWorker with inbox
    factory.py           # AgentFactory
    pool.py              # AgentPool with semaphore
  agents/
    base.py              # BaseAgent, AgentInput, AgentOutput
    planner.py           # PlannerAgent
    executor.py          # ExecutorAgent with tool loop
    verifier.py          # VerifierAgent
    types.py             # TaskStatus, StepStatus
    llm_client.py        # OpenAI async client
  mcp/
    __init__.py          # Package init
    client_manager.py    # MCPClientManager
    servers/
      filesystem.py      # File system MCP server
      shell.py           # Shell command MCP server
      browser.py         # Web browsing MCP server
    bus.py               # MCPBus, MemoryMCPBus, RedisMCPBus
    router.py            # MessageRouter
    protocol.py          # MCPProtocol
    message.py           # MCPMessage, Payload, Metadata
  tools/
    registry.py          # ToolRegistry (built-in + MCP discovery)
    sandbox.py           # ToolSandbox with AST validation
    base.py              # BaseTool, ToolInput, ToolOutput
    search.py            # SearchTool
    calculator.py        # CalculatorTool
    text_processor.py    # TextProcessorTool
  guardrails/
    validator.py         # Input/output validation
    schema.py            # Pydantic schemas
  logs/
    tracing.py           # TraceManager
    metrics.py           # MetricsCollector
    logger.py            # Structured logger
  memory/
    long_term.py         # PostgreSQL + SQLAlchemy
    short_term.py        # Redis client
    models.py            # SQLAlchemy models (incl. CheckpointModel)
  config/
    settings.py          # Pydantic Settings
frontend/
  src/
    api/client.ts        # API client
    pages/               # Dashboard, AgentBuilder, Tools, etc.
  dist/                  # Production build
tests/                   # pytest suite
```
