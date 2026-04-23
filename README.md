# Agent-OS

MCP-based multi-agent operating system for structured AI workflow execution.

## 1) System Overview

Agent-OS is a layered runtime for AI agents, not a single-model chatbot. It enforces strict separation between orchestration, execution, communication, tools, safety, and observability.

### Core Design Principles

- **Runtime is the ONLY execution entry point**: No module may instantiate or call agents directly.
- **Strategy-based modes**: Task, Workflow, Autonomous, and Collaboration modes are distinct strategies with zero conditional branching in the orchestrator.
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
│  - Orchestrator: mode selection → aggregate results         │
│  - PipelineExecutor: plan → execute → verify pipeline       │
│  - WorkflowBuilder: DAG construction and persistence        │
│  - StepExecutor: single-step execution via Runtime          │
│  - WorkflowEngine: DAG traversal with condition sandbox     │
├─────────────────────────────────────────────────────────────┤
│  Mode Strategies                                             │
│  - TaskMode, WorkflowMode, AutonomousMode, CollaborationMode│
│  - Each delegates ALL execution to Runtime                  │
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
│  MCP Layer (System Communication)                            │
│  - MCPBus: abstract pub/sub (MemoryMCPBus | RedisMCPBus)    │
│  - MessageRouter: routes by receiver_agent to inbox         │
│  - MCPProtocol: message creation, history, bounded log      │
├─────────────────────────────────────────────────────────────┤
│  Tool Layer                                                  │
│  - ToolRegistry: central discovery + capability binding      │
│  - ToolCallParser: extracts tool invocations from LLM text  │
│  - ToolSandbox: restricted builtins + AST validation         │
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
└─────────────────────────────────────────────────────────────┘
```

### Data Flow

1. **Task Creation**: Client → API Route → Orchestrator.execute_task()
2. **Mode Selection**: Orchestrator → ModeStrategyFactory → ModeStrategy
3. **Execution Entry**: ModeStrategy → AgentRuntime (NEVER direct agent calls)
4. **Agent Execution**: AgentRuntime → AgentWorker → AgentInstance.execute()
5. **Tool Use**: ExecutorAgent → ToolCallParser → ToolRegistry → ToolSandbox
6. **Collaboration**: CollaborationMode → MCPBus → MessageRouter → AgentWorker inbox
7. **Observability**: Every layer emits spans/logs → TraceManager → DB

---

## 3) Layer-by-Layer Explanation

### API Layer (`app/api/`)

- **Routes**: `tasks.py`, `auth.py`, `tools.py`, `agents.py`, `config.py`, `health.py`
- **Dependency injection**: `deps.py` returns the module-level `orchestrator` singleton
- **No business logic**: Routes validate, serialize, and delegate exclusively

### Orchestration Layer (`app/orchestrator/`)

- **`core.py`** (~182 lines): Thin orchestrator. Selects mode via `ModeStrategyFactory`, delegates pipeline to `PipelineExecutor`.
- **`pipeline.py`**: Full plan → execute → verify pipeline. Creates traces, calls planner/executor/verifier through Runtime, handles errors.
- **`builder.py`**: Persists workflow DAG nodes and edges to PostgreSQL.
- **`executor.py`**: Executes a single step via an agent instance, updating node trace records.
- **`workflow.py`**: `WorkflowEngine` traverses DAGs, evaluates conditions in an AST sandbox, and handles parallel/sequential execution.

### Mode Strategies (`app/orchestrator/modes/`)

- **`base.py`**: `ModeStrategy` ABC. Receives `AgentRuntime`, `Orchestrator`, query, config, task_id, user_id.
- **`task.py`**: Standard pipeline. Delegates to `PipelineExecutor`.
- **`workflow.py`**: Loads predefined workflows by name from DB; falls back to dynamic planning.
- **`autonomous.py`**: Replanning loop up to `max_steps`. Halts on completion heuristic or empty plan.
- **`collaboration.py`**: Distributes steps to different agent types via Runtime and MCP messages.

### Runtime Layer (`app/runtime/`)

- **`runtime.py`**: `AgentRuntime` singleton. Lazy/eager registration. `initialize()` creates core agents at startup. `register()` acquires pool slot. `get()` returns `AgentWorker`.
- **`worker.py`**: `AgentWorker` owns an `asyncio.Queue` inbox. `execute()` calls `agent_instance.execute()`. `on_message()` enqueues MCP messages. `_run_loop()` processes inbox.
- **`factory.py`**: `AgentFactory` creates `PlannerAgent`, `ExecutorAgent`, `VerifierAgent`, or custom agents from DB config.
- **`pool.py`**: `AgentPool` uses `asyncio.Semaphore(max_agents)` to limit concurrent workers.

### MCP Layer (`app/mcp/`)

- **`bus.py`**: `MCPBus` ABC. `MemoryMCPBus` for local dev (bounded history: 10,000 messages). `RedisMCPBus` for production.
- **`router.py`**: `MessageRouter` registers agent handlers and routes messages to channels (`agent:{name}`).
- **`protocol.py`**: `MCPProtocol` creates messages, sends via router, maintains bounded message log.

### Tool Layer (`app/tools/`)

- **`registry.py`**: `ToolRegistry` singleton. `register()`, `get()`, `list_tools()`, `execute()`.
- **`sandbox.py`**: `ToolSandbox` validates code via AST (blocks `import`, `eval`, `exec`, `open`), executes in restricted `__builtins__`, enforces timeout.
- **`base.py`**: `BaseTool`, `ToolInput`, `ToolOutput` dataclasses.
- **`search.py`**, **`calculator.py`**, **`text_processor.py`**: Built-in tools.

### Safety Layer (`app/guardrails/`)

- **`validator.py`**: `Guardrails` validates input/output. On failure, `_validate_output()` now raises `UnrecoverableError` instead of just logging.
- **`schema.py`**: Pydantic-based output schemas.

### Observability Layer (`app/logs/`)

- **`tracing.py`**: `TraceManager` creates spans in memory. `persist_span()` and `persist_trace()` commit to DB on demand.
- **`metrics.py`**: `MetricsCollector` with counters and histograms. `get_prometheus_format()` exports text.
- **`logger.py`**: Structured JSON logging.
- **`middleware`**: `metrics_middleware` in `main.py` records request count, duration, and errors.

### Memory Layer (`app/memory/`)

- **`long_term.py`**: Async SQLAlchemy with connection pooling (`pool_size=20`, `max_overflow=40`, `pool_pre_ping=True`).
- **`short_term.py`**: Redis client for context cache.

---

## 4) API Documentation

### Tasks
- `POST /api/v1/tasks` — Create and execute a task
- `GET /api/v1/tasks` — List tasks
- `GET /api/v1/tasks/{task_id}` — Get task details
- `DELETE /api/v1/tasks/{task_id}` — Cancel/delete task

### Agents
- `GET /api/v1/agents` — List registered agents
- `POST /api/v1/agents` — Register a new agent
- `GET /api/v1/agents/{agent_id}` — Get agent details

### Tools
- `GET /api/v1/tools` — List available tools
- `POST /api/v1/tools` — Register a custom tool
- `POST /api/v1/tools/{tool_id}/execute` — Execute a tool

### Health & Observability
- `GET /health` — Basic health check
- `GET /health/ready` — Readiness probe (checks DB + Redis)
- `GET /health/live` — Liveness probe
- `GET /health/metrics` — Prometheus-format metrics

### Auth
- `POST /api/v1/auth/token` — Obtain access token

---

## 5) Setup and Environment Configuration

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
VERSION=1.0.0
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

## 6) Local Development Guide

### Running Tests

```bash
pytest -q
```

### Adding a New Mode

1. Create `app/orchestrator/modes/my_mode.py`
2. Inherit from `ModeStrategy`
3. Implement `execute(runtime, orchestrator, query, config, task_id, user_id)`
4. Register in `app/orchestrator/modes/factory.py`

### Adding a New Tool

1. Create a class inheriting from `BaseTool`
2. Implement `execute(tool_input: ToolInput) -> ToolOutput`
3. Register in `ToolRegistry._register_default_tools()` or via API

### Adding a New Agent Type

1. Create a class inheriting from `BaseAgent`
2. Register in `AgentFactory.create_agent()`

---

## 7) Testing Strategy

- **Unit tests**: Agent logic, tool parsing, guardrails, retry logic
- **Integration tests**: Runtime initialization, mode strategy factory, task lifecycle
- **End-to-end tests**: API routes, task execution with mocked LLM
- **Observability tests**: Trace persistence, metrics export, health endpoints

Run the full suite:

```bash
pytest -q
```

---

## 8) Deployment Instructions

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

---

## 9) Scaling Considerations

- **Agent Workers**: `AgentPool` semaphore limits concurrent agents (default 100).
- **Database**: SQLAlchemy pool (`pool_size=20`, `max_overflow=40`).
- **Asyncio**: Event loop handles 10,000+ coroutines; the real limit is DB connections.
- **Redis**: Use `RedisMCPBus` for multi-instance deployments.
- **Celery**: Worker exists in Docker but API uses in-process background tasks.

---

## 10) Troubleshooting Guide

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

---

## 11) File Structure

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
  orchestrator/
    core.py              # Thin orchestrator (~182 lines)
    pipeline.py          # Plan → execute → verify pipeline
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
  mcp/
    bus.py               # MCPBus, MemoryMCPBus, RedisMCPBus
    router.py            # MessageRouter
    protocol.py          # MCPProtocol
    message.py           # MCPMessage, Payload, Metadata
  tools/
    registry.py          # ToolRegistry singleton
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
    models.py            # SQLAlchemy models
  config/
    settings.py          # Pydantic Settings
frontend/
  src/
    api/client.ts        # API client
    pages/               # Dashboard, AgentBuilder, Tools, etc.
  dist/                  # Production build
tests/                   # pytest suite
```
