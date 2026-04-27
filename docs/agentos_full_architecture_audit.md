# AgentOS Full Architecture Audit

> **Audit Date:** 2026-04-27  
> **Scope:** Complete end-to-end analysis of the AgentOS codebase at `E:\Projects\AgentOS`  
> **Method:** Read-only analysis via 6 specialized subagents (repo-analyzer, architecture-auditor, langgraph-builder, mcp-builder, debugger, observability-agent)  
> **Constraint:** No code modifications, no commits, no assumptions — every claim cites exact files and functions.

---

## Table of Contents

1. [System Architecture Overview](#1-system-architecture-overview)
2. [End-to-End Execution Flow](#2-end-to-end-execution-flow)
3. [File-by-File Responsibility Map](#3-file-by-file-responsibility-map)
4. [Agent Responsibility Map](#4-agent-responsibility-map)
5. [Tool Registry Flow](#5-tool-registry-flow)
6. [LangGraph Flow](#6-langgraph-flow)
7. [Verification Flow](#7-verification-flow)
8. [Current Bottlenecks](#8-current-bottlenecks)
9. [Dangerous Architectural Flaws](#9-dangerous-architectural-flaws)
10. [Recommended Fix Priority Order](#10-recommended-fix-priority-order)
11. [Appendix: Desktop Execution Trace](#appendix-desktop-execution-trace-open-notepad-and-type-hello)

---

## 1. System Architecture Overview

AgentOS is a FastAPI-based multi-agent execution platform with a React 18 frontend. It orchestrates LLM-driven task execution through a primary LangGraph StateGraph engine, with a legacy fallback pipeline.

### High-Level Component Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              REACT 18 FRONTEND                               │
│  (Vite + TypeScript + Tailwind + Recharts + XYFlow)                         │
│  Pages: Dashboard, Chat, AgentBuilder, WorkflowBuilder, Tools, Monitor      │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │ HTTP / WebSocket
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           FASTAPI BACKEND (app/main.py)                      │
│  Lifespan Bootstrap:                                                         │
│    1. Validate DATABASE_URL, REDIS_URL, OPENAI_API_KEY                      │
│    2. Connect PostgreSQL + run migrations                                   │
│    3. Connect Redis (cache + PubSub clients)                                │
│    4. Initialize AgentRuntime (singleton, Redis mutex)                      │
│    5. Start MCP health monitor                                              │
│    6. Register built-in tools                                               │
│    7. Start MCP system servers (stdio child processes)                      │
│    8. Discover MCP tools                                                    │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
              ┌───────────────────────┼───────────────────────┐
              ▼                       ▼                       ▼
    ┌─────────────────┐   ┌─────────────────────┐   ┌─────────────────┐
    │   API Routes    │   │   Celery Worker     │   │  WebSocket/SSE  │
    │  (18 routers)   │   │  (Redis broker)     │   │  Real-time      │
    └────────┬────────┘   └──────────┬──────────┘   └─────────────────┘
             │                       │
             ▼                       ▼
    ┌─────────────────────────────────────────────────────────────────┐
    │                         ORCHESTRATOR                             │
    │  (app/orchestrator/core.py) — God Object                         │
    │  Primary path: _execute_with_langgraph()                         │
    │  Fallback path: ModeStrategyFactory (legacy pipeline)            │
    └─────────────────────────────────────────────────────────────────┘
             │
             ▼
    ┌─────────────────────────────────────────────────────────────────┐
    │                        AGENT RUNTIME                             │
    │  (app/runtime/runtime.py) — Singleton                            │
    │  Holds: planner, executor, verifier, router, memory             │
    └─────────────────────────────────────────────────────────────────┘
             │
    ┌────────┴────────┐
    ▼                 ▼
┌──────────┐   ┌──────────────────┐
│ LangGraph│   │ Legacy Pipeline  │
│ Engine   │   │ (modes/)         │
└────┬─────┘   └──────────────────┘
     │
     ├──────────────────────────────────────────────┐
     ▼                                              ▼
┌──────────────┐   ┌──────────────┐   ┌──────────────────────────────┐
│   Planner    │   │   Executor   │   │         Tools                 │
│  (nodes.py)  │──▶│  (nodes.py)  │──▶│  ┌────────┐ ┌──────────────┐ │
│  Decompose   │   │  Tool calls  │   │  │Built-in│ │ MCP Servers  │ │
│  LLM plan    │   │  Grounding   │   │  │        │ │ (stdio)      │ │
└──────────────┘   └──────────────┘   │  │Search  │ │ filesystem   │ │
                                      │  │GitHub  │ │ shell        │ │
┌──────────────┐   ┌──────────────┐   │  │Slack   │ │ cloud_api    │ │
│  Verifier    │   │ Summarizer   │   │  │...     │ │ desktop      │ │
│  (nodes.py)  │◀──│  (nodes.py)  │◀──│  └────────┘ └──────────────┘ │
└──────────────┘   └──────────────┘   └──────────────────────────────┘
```

### Technology Stack

| Layer | Technology |
|-------|------------|
| Backend Framework | FastAPI (Python 3.11+) |
| Frontend | React 18 + Vite + TypeScript + Tailwind CSS |
| Execution Engine | LangGraph StateGraph (primary), legacy pipeline (fallback) |
| Database | PostgreSQL 14+ (asyncpg + SQLAlchemy 2.0) |
| Cache / PubSub | Redis 7+ (aioredis) |
| Task Queue | Celery (Redis broker + result backend) |
| LLM Provider | OpenAI (GPT-4) via `app/agents/llm_client.py` |
| Browser Automation | Playwright |
| Desktop Automation | pyautogui + mss |
| MCP Transport | stdio (child processes) |
| Auth | JWT (python-jose, HS256) + API Key |

### Entry Points

| Entry Point | File | Purpose |
|-------------|------|---------|
| FastAPI App | `app/main.py` | Uvicorn ASGI entry, lifespan bootstrap, middleware, routers |
| Celery Worker | `app/queue/tasks.py` | Task queue worker, mirrors lifespan bootstrap |
| Frontend App | `frontend/src/main.tsx` | React DOM root render |
| Validation | `validate_fixes.py` | Priority 1 system health check (DB + Redis + runtime) |

---

## 2. End-to-End Execution Flow

This section traces the complete lifecycle from user task submission to final result delivery.

### Phase A: API Ingress & Task Creation

1. **HTTP Request Received**
   - Endpoint: `POST /api/v1/tasks`
   - File: `app/api/routes/tasks.py:132`, function `create_task()`
   - Auth dependency: `app/api/deps.py:22`, `get_current_user()` validates JWT from `Authorization` header.

2. **Task Persistence**
   - File: `app/api/routes/tasks.py:163`
   - Calls `task_repo.create(task_id=str(task_id), query=request.query, status="PENDING", ...)`
   - Repository: `app/memory/long_term.py` (TaskRepository)
   - Event bus fires `task.status_changed` → `PENDING`

3. **Dispatch Decision**
   - File: `app/api/routes/tasks.py:175`
   - Logic: `if use_celery():`
     - **Celery path**: `celery_app.send_task("agent_os.execute_task", args=[...])` (line 178)
     - **Inline path**: `background_tasks.add_task(_run_task)` (line 237) → directly calls `orchestrator.execute_task()`

### Phase B: Celery Worker Bootstrap (if applicable)

4. **Worker Process Initialization**
   - File: `app/queue/tasks.py:42`, signal `@worker_process_init.connect` → `on_worker_process_init()`
   - Actions:
     - Sets Windows `ProactorEventLoopPolicy` (line 52)
     - Connects DB (`db.connect()`) + Redis (`redis_client.connect()`) (lines 69-71)
     - Eagerly initializes `AgentRuntime` via `_ensure_runtime_initialized()` (line 73)
     - Registers built-in tools (`register_builtin_tools(tool_registry)`) (line 76)
     - Starts MCP system servers (`mcp_client_manager.start_system_servers()`) (line 89)
     - Discovers MCP tools (`tool_registry.discover_mcp_tools()`) (line 94)
   - **CRITICAL**: This is a complete duplicate of the FastAPI lifespan logic. See flaw analysis in Section 9.

5. **Celery Task Body**
   - File: `app/queue/tasks.py:127`, function `execute_task(self, task_id, query, config, user_id)`
   - Verifies `core_planner` exists in runtime (line 160) — legacy check, LangGraph path does not strictly need this.
   - Starts heartbeat asyncio task (line 180)
   - Calls `orchestrator.execute_task(query, config, task_id, user_id)` at line 186 with `asyncio.wait_for(..., timeout=task_timeout)`

### Phase C: Orchestrator Primary Path (LangGraph)

6. **Orchestrator Entry**
   - File: `app/orchestrator/core.py:216`, function `execute_task()`
   - Immediately delegates to LangGraph: line 231 `return await self._execute_with_langgraph(...)`

7. **TaskRunner — LangGraph Wrapper**
   - File: `app/orchestrator/task_runner.py:97`, function `run()`
   - **Capability Classification** (line 115): `capability_router.classify(query, str(task_id))`
   - **Feasibility Check** (line 135): `feasibility_engine.check(assessment, config)`
   - **Environment Selection** (line 164): `feasibility_engine.select_environment(...)`
   - **Graph Compilation** (line 191): `get_cached_graph(mode, checkpointer=checkpointer)`
   - **Graph Invocation** (line 213): `await asyncio.wait_for(graph.ainvoke(state, config=thread_config), timeout=workflow_timeout)`

8. **LangGraph Task Graph Execution**
   - File: `app/langgraph/graphs.py:63`, function `compile_task_graph()`
   - Nodes: `planner` → `executor` → `verifier` → `approval` (optional) → `summarizer`
   - Conditional edges from executor: `_should_continue` routes back to `executor` or forward to `verifier`
   - Conditional edges from verifier: `_should_approve` routes to `approval` or `summarizer`

9. **Planner Node**
   - File: `app/langgraph/nodes.py:166`, function `planner_node()`
   - Calls `workflow_decomposer.decompose(query)` (line 181)
   - If >1 phases: builds deterministic plan without LLM
   - Else: calls LLM `complete_json()` with partial response schema
   - On exception: falls back to single-step plan with `tool: None`

10. **Executor Node**
    - File: `app/langgraph/nodes.py:327`, function `executor_node()`
    - Dependency gate: checks prior required steps for success
    - Tool selection hierarchy: explicit `allowed_tools` → `fallback_tools` → grounding layer
    - Inner loop: up to `max_tool_rounds` (default 5) LLM completions per step
    - Calls `tool_registry.execute()` for each tool call

11. **Verifier Node**
    - File: `app/langgraph/nodes.py:840`, function `verifier_node()`
    - Deterministic verification first (`verification_engine.verify_plan()`)
    - LLM semantic verification fallback
    - Environment-specific checks (browser, cloud)
    - Final verdict: `verified = det_pass and llm_verified and env_verified`

12. **Summarizer Node**
    - File: `app/langgraph/nodes.py:988`, function `summarizer_node()`
    - Combines all step outputs
    - Calls LLM for summary; falls back to `combined[:1000]` on failure

### Phase D: Result Delivery & Persistence

13. **TaskRunner Returns**
    - File: `app/orchestrator/task_runner.py:221`
    - Extracts `final_state.get("result", {})`
    - Returns `AgentOutput(status=AgentStatus.SUCCESS|FAILURE, ...)`

14. **Celery Finalization (if Celery path)**
    - File: `app/queue/tasks.py:189`
    - If success: `task_repo.update(task_id, status=TaskStatus.COMPLETED.value, result=result.output_data)`
    - If failure: updates to `FAILED`, publishes `task.failed` event
    - Retries with exponential backoff: `countdown=60 * (2 ** retries)`

15. **Real-Time Updates to Clients**
    - Worker publishes events via `event_bus.publish(f"task:{task_id}", ...)`
    - Redis PubSub channel: `agentos:task:{task_id}`
    - WebSocket subscribers receive via `ConnectionManager.broadcast()`
    - File: `app/api/ws.py:96-109`, function `_subscribe()`

---

## 3. File-by-File Responsibility Map

### Backend (`app/`)

| File | Lines | Responsibility | Key Classes/Functions |
|------|-------|---------------|----------------------|
| `app/main.py` | 312 | FastAPI app setup, lifespan bootstrap, middleware, exception handlers, route inclusion | `app`, `lifespan()`, `metrics_middleware()` |
| `app/api/__init__.py` | 30 | Router registration (CRITICAL: order matters) | `api_router` |
| `app/api/deps.py` | 67 | FastAPI dependency injection (current user, DB session) | `get_current_user()` |
| `app/api/ws.py` | 145 | WebSocket endpoint for real-time task updates | `ConnectionManager`, `websocket_endpoint()` |
| `app/api/routes/tasks.py` | 510 | Task CRUD, execution dispatch, approval workflow | `create_task()`, `approve_task()` |
| `app/api/routes/tools.py` | 249 | Tool listing, registration, execution (v1) | `execute_tool()`, `list_tools()` |
| `app/api/routes/tools_v2.py` | 129 | Tool v2 API (separate registry, partial implementation) | `execute_tool_v2()` |
| `app/api/routes/agents.py` | 227 | Agent CRUD and configuration | — |
| `app/api/routes/agents_v2.py` | 82 | Agent v2 API | — |
| `app/api/routes/workflows.py` | 97 | Workflow v1 CRUD | — |
| `app/api/routes/workflows_v2.py` | 141 | Workflow v2 CRUD and execution | — |
| `app/api/routes/chat.py` | 198 | Chat endpoint | — |
| `app/api/routes/analytics.py` | 238 | Analytics and metrics (contains fake/random data!) | `get_analytics_time_series()` |
| `app/api/routes/health.py` | 59 | Health checks (/health, /health/ready, /health/live) | — |
| `app/auth/utils.py` | 105 | JWT creation and verification | `create_access_token()`, `verify_access_token()` |
| `app/auth/rbac.py` | 82 | Role-based access control | — |
| `app/middleware/auth.py` | 80 | Auth middleware | `APIKeyMiddleware` |
| `app/middleware/rate_limit.py` | 134 | Rate limiting middleware | `RateLimitMiddleware` |
| `app/config/settings.py` | 109 | Pydantic settings singleton | `Settings()` |
| `app/memory/models.py` | 448 | SQLAlchemy ORM models (23 models in one file) | `TaskModel`, `StepModel`, `CheckpointModel`, `ToolV2Model`, ... |
| `app/memory/long_term.py` | 990 | Database connection + repository pattern | `Database`, `TaskRepository`, `AgentRepository`, ... |
| `app/memory/short_term.py` | 121 | Redis KV client | `RedisClient` |
| `app/memory/redis_pubsub.py` | 113 | Redis Pub/Sub client | `RedisPubSubClient` |
| `app/memory/session_memory.py` | 38 | Session-scoped memory | — |
| `app/memory/task_memory.py` | 36 | Task-scoped memory | — |
| `app/memory/user_memory.py` | 31 | User-scoped memory | — |
| `app/memory/workflow_memory.py` | 55 | Workflow-scoped memory | — |
| `app/runtime/runtime.py` | 275 | **AgentRuntime singleton** — the ONLY execution entry point | `AgentRuntime.__new__()`, `initialize()`, `get()` |
| `app/runtime/factory.py` | 36 | Agent factory | `AgentFactory` |
| `app/runtime/pool.py` | 42 | Runtime pool (stub) | — |
| `app/runtime/worker.py` | 114 | Worker runtime management | — |
| `app/agents/base.py` | 51 | Base agent class | `BaseAgent` |
| `app/agents/planner.py` | 311 | Legacy planner agent | `PlannerAgent.plan()` |
| `app/agents/executor.py` | 309 | Legacy executor agent | `ExecutorAgent.execute()` |
| `app/agents/verifier.py` | 71 | Legacy verifier agent | `VerifierAgent.verify()` |
| `app/agents/llm_client.py` | 220 | LLM client wrapper | `LLMClient.complete_json()` |
| `app/agents/types.py` | 21 | Agent type definitions | — |
| `app/agents/v2/registry.py` | 133 | Agent v2 registry | `agent_registry_v2` |
| `app/agents/v2/schemas.py` | 30 | Agent v2 schemas | — |
| `app/orchestrator/core.py` | 284 | **Orchestrator god object** — primary execution coordinator | `Orchestrator.execute_task()`, `_execute_with_langgraph()` |
| `app/orchestrator/task_runner.py` | 250 | LangGraph task runner wrapper | `TaskRunner.run()` |
| `app/orchestrator/builder.py` | 152 | Workflow builder | `WorkflowBuilder` |
| `app/orchestrator/pipeline.py` | 338 | Legacy pipeline executor | `PipelineExecutor` |
| `app/orchestrator/workflow.py` | 342 | Legacy workflow engine | `WorkflowEngine` |
| `app/orchestrator/executor.py` | 143 | Legacy step executor | `StepExecutor` |
| `app/orchestrator/router.py` | 52 | Orchestrator router | `AgentRouter` |
| `app/orchestrator/context.py` | 37 | Execution context | — |
| `app/orchestrator/retry.py` | 86 | Retry configuration | — |
| `app/orchestrator/errors.py` | 95 | Exception hierarchy | `AgentOSError`, `RetryableError`, `UnrecoverableError` |
| `app/orchestrator/modes/factory.py` | 32 | Mode strategy factory | `ModeStrategyFactory` |
| `app/orchestrator/modes/autonomous.py` | 157 | Autonomous mode strategy | `AutonomousMode` |
| `app/orchestrator/modes/collaboration.py` | 164 | Collaboration mode strategy | `CollaborationMode` |
| `app/orchestrator/v2/engine.py` | 109 | Workflow v2 engine (contains `eval()`) | `WorkflowV2Engine.execute()` |
| `app/orchestrator/v2/event_bus.py` | 71 | Redis-backed event bus | `RedisEventBus` |
| `app/orchestrator/v2/schemas.py` | 49 | V2 schemas | — |
| `app/langgraph/state.py` | 65 | LangGraph state schema | `AgentState` (TypedDict, total=False) |
| `app/langgraph/graphs.py` | 327 | Graph compilation and caching | `compile_task_graph()`, `get_cached_graph()` |
| `app/langgraph/nodes.py` | 1051 | **LangGraph node implementations** — largest file | `planner_node()`, `executor_node()`, `verifier_node()`, `summarizer_node()`, `approval_node()` |
| `app/langgraph/checkpointer.py` | 247 | PostgreSQL checkpoint saver | `PostgresCheckpointSaver` |
| `app/capabilities/router.py` | 215 | Capability classification and routing | `CapabilityRouter.classify()`, `.route()` |
| `app/capabilities/feasibility.py` | 165 | Feasibility engine | `FeasibilityEngine.check()` |
| `app/capabilities/environment_selector.py` | 70 | Execution environment selection | `ExecutionEnvironmentSelector.select()` |
| `app/capabilities/environment.py` | 118 | Environment configuration | — |
| `app/capabilities/models.py` | 114 | Capability data models | — |
| `app/capabilities/verification.py` | 311 | Verification engine | `VerificationEngine.verify_plan()` |
| `app/capabilities/recovery.py` | 270 | Recovery logic | — |
| `app/tools/registry.py` | 382 | **ToolRegistry singleton** — unified in-memory tool registry | `ToolRegistry.__new__()`, `register()`, `execute()`, `discover_mcp_tools()` |
| `app/tools/base.py` | 32 | Base tool interface | `BaseTool`, `ToolInput`, `ToolOutput` |
| `app/tools/builder.py` | 229 | Dynamic tool factory | `DynamicToolFactory` |
| `app/tools/grounding.py` | 281 | Tool grounding / capability-to-tool mapping | `ToolGroundingLayer` |
| `app/tools/parser.py` | 42 | Tool call parser from LLM output | `ToolCallParser` |
| `app/tools/search.py` | 125 | Search, calculator, text processor tools | `SearchTool`, `CalculatorTool` |
| `app/tools/sandbox.py` | 132 | Restricted Python sandbox | `ToolSandbox` |
| `app/tools/file_discovery.py` | 265 | File discovery tool | — |
| `app/tools/builtin/__init__.py` | 23 | Built-in tool registration | `register_builtin_tools()` |
| `app/tools/builtin/code_executor.py` | 26 | Code execution built-in | `CodeExecutorRunPythonTool` |
| `app/tools/builtin/github.py` | 93 | GitHub built-in | `GitHubGetRepoTool` |
| `app/tools/builtin/slack.py` | 28 | Slack built-in | `SlackSendMessageTool` |
| `app/tools/builtin/notion.py` | 27 | Notion built-in | `NotionSearchPagesTool` |
| `app/tools/builtin/web_scraper.py` | 45 | Web scraper built-in | `WebScraperExtractTextTool` |
| `app/tools/v2/registry.py` | 134 | Tool v2 registry (SQLAlchemy-backed) | `tool_registry_v2` |
| `app/tools/v2/schemas.py` | 41 | Tool v2 schemas | `ToolV2`, `ImplementationType` |
| `app/tools/v2/health_monitor.py` | 57 | V2 health monitor (dummy) | `ToolHealthMonitor` |
| `app/mcp/client_manager.py` | 264 | **MCPClientManager singleton** — stdio transport | `MCPClientManager`, `mcp_client_manager` |
| `app/mcp/registry.py` | 154 | MCP server DB registry | `mcp_registry` |
| `app/mcp/monitor.py` | 61 | MCP health monitor (HTTP only) | `mcp_health_monitor` |
| `app/mcp/protocol.py` | 108 | Inter-agent message protocol | `MCPProtocol` |
| `app/mcp/bus.py` | 77 | MCP message bus | `MemoryMCPBus`, `RedisMCPBus` |
| `app/mcp/router.py` | 56 | MCP message router | `MessageRouter` |
| `app/mcp/message.py` | 48 | MCP message models | `MCPMessage` |
| `app/mcp/server_export.py` | 49 | Workflow-to-MCP export stub | — |
| `app/mcp/servers/filesystem.py` | 145 | Filesystem MCP server | `read_file`, `write_file`, `list_directory`, `search_files` |
| `app/mcp/servers/shell.py` | 134 | Shell MCP server | `execute_command`, `run_script`, `get_process_status` |
| `app/mcp/servers/cloud_api.py` | 129 | Cloud API MCP server | `http_request`, `scrape_page`, `search_web` |
| `app/mcp/servers/desktop.py` | 193 | Desktop MCP server | `desktop__screenshot`, `desktop__click`, `desktop__type_text`, ... |
| `app/environments/browser_env.py` | 612 | Browser environment (Playwright) | `browser_session_manager` |
| `app/environments/desktop_env.py` | 881 | Desktop environment (pyautogui + mss) | `desktop_session_manager` |
| `app/environments/base.py` | 14 | Environment base class | — |
| `app/workflows/decomposer.py` | 238 | Workflow decomposer | `WorkflowDecomposer.decompose()` |
| `app/queue/tasks.py` | 263 | Celery task definitions + worker init | `execute_task()`, `on_worker_process_init()` |
| `app/recovery/checkpoint_service.py` | 40 | Checkpoint recovery service | `CheckpointRecoveryService.resume_task()` |
| `app/logs/logger.py` | 47 | Plain-text logger | `AgentOSLogger` |
| `app/logs/tracing.py` | 143 | Custom tracing (in-memory span buffer) | `TraceManager` |
| `app/logs/metrics.py` | 80 | In-memory metrics collector | `MetricsCollector` |
| `app/observability/bus.py` | 82 | Observability event bus | `ObservabilityBus` |
| `app/observability/models.py` | 49 | Observability event models | `ObservabilityEvent` |
| `app/safety/gate.py` | 74 | Safety gate | `SafetyGate` |
| `app/safety/models.py` | 7 | Safety models | — |
| `app/guardrails/schema.py` | 178 | Guardrails schema | — |
| `app/guardrails/validator.py` | 96 | Guardrails validator | — |
| `app/knowledge/store.py` | 113 | Knowledge base store | — |
| `app/knowledge/rag.py` | 18 | RAG stub | — |
| `app/knowledge/parser.py` | 50 | Document parser | — |
| `app/knowledge/schemas.py` | 30 | Knowledge schemas | — |
| `app/llm/providers/registry.py` | 222 | LLM provider registry | `LLMProviderRegistry` |
| `app/llm/providers/schemas.py` | 23 | LLM provider schemas | — |
| `app/migrations/runner.py` | 168 | Migration runner (executed at startup) | `run_pending_migrations()` |

### Frontend (`frontend/src/`)

| File | Lines | Responsibility |
|------|-------|---------------|
| `frontend/src/main.tsx` | 10 | React root render |
| `frontend/src/App.tsx` | 92 | React Router setup |
| `frontend/src/api/client.ts` | 760 | Axios API client (all endpoints) |
| `frontend/src/hooks/useWebSocket.ts` | 144 | WebSocket connection hook |
| `frontend/src/hooks/useTaskResults.ts` | 26 | Task result polling hook |
| `frontend/src/context/AuthContext.tsx` | 210 | JWT auth context |
| `frontend/src/pages/Dashboard.tsx` | 658 | Main dashboard |
| `frontend/src/pages/Chat.tsx` | 587 | Chat interface |
| `frontend/src/pages/AgentBuilderV2.tsx` | 842 | Agent builder v2 |
| `frontend/src/pages/WorkflowBuilderV2.tsx` | 755 | Workflow builder v2 |
| `frontend/src/pages/Tools.tsx` | 625 | Tool management UI |
| `frontend/src/pages/Monitor.tsx` | 545 | Monitoring dashboard |

---

## 4. Agent Responsibility Map

The term "agent" is overloaded in AgentOS. It refers to:

1. **LangGraph Nodes** (primary execution units)
2. **Legacy Agent Classes** (planner, executor, verifier)
3. **Runtime-Registered Agents** (singleton-held instances)
4. **User-Configured Agents** (DB-persisted agent definitions)

### LangGraph Nodes (Primary Execution Agents)

| Node | File | Function | Responsibility |
|------|------|----------|--------------|
| Planner | `app/langgraph/nodes.py:166` | `planner_node()` | Decomposes query into execution plan (deterministic or LLM) |
| Executor | `app/langgraph/nodes.py:327` | `executor_node()` | Executes plan steps by calling tools (up to 5 rounds per step) |
| Verifier | `app/langgraph/nodes.py:840` | `verifier_node()` | Verifies execution results (deterministic + LLM checks) |
| Approval | `app/langgraph/nodes.py:930` | `approval_node()` | Human-in-the-loop interrupt node |
| Summarizer | `app/langgraph/nodes.py:988` | `summarizer_node()` | Produces final user-facing summary |
| Distributor | `app/langgraph/nodes.py` | `distributor_node()` | Collaboration graph: distributes work to workers |
| Worker | `app/langgraph/nodes.py` | `worker_node()` | Collaboration graph: executes sub-task |
| Aggregator | `app/langgraph/nodes.py` | `aggregator_node()` | Collaboration graph: merges worker results |

### Legacy Agents (Fallback Pipeline)

| Agent | File | Class | Responsibility |
|-------|------|-------|--------------|
| Planner | `app/agents/planner.py` | `PlannerAgent` | Legacy plan generation with path normalization |
| Executor | `app/agents/executor.py` | `ExecutorAgent` | Legacy tool execution with path remapping |
| Verifier | `app/agents/verifier.py` | `VerifierAgent` | Legacy result verification |

### Runtime-Registered Agents

| Agent Key | Instantiated In | Purpose |
|-----------|-----------------|---------|
| `core_planner` | `AgentRuntime.initialize()` | Primary planner (legacy path) |
| `core_executor` | `AgentRuntime.initialize()` | Primary executor (legacy path) |
| `core_verifier` | `AgentRuntime.initialize()` | Primary verifier (legacy path) |
| `router` | `AgentRuntime.initialize()` | Capability router |

---

## 5. Tool Registry Flow

### Unified Tool Registry Architecture

AgentOS maintains a single in-memory `ToolRegistry` singleton (`app/tools/registry.py`) that merges:
1. **Built-in tools** (Python classes: SearchTool, GitHubGetRepoTool, etc.)
2. **Browser environment tools** (proxies to `browser_session_manager`)
3. **Desktop environment tools** (proxies to `desktop_session_manager`)
4. **MCP-wrapped tools** (stdio JSON-RPC to child processes)
5. **Dynamically constructed tools** (fallback factory)

### Startup Registration Sequence

```
FastAPI Lifespan (app/main.py:33)
  ├─> register_builtin_tools(tool_registry)
  │     ├─> SearchTool, CalculatorTool, TextProcessorTool
  │     ├─> GitHubGetRepoTool, SlackSendMessageTool, NotionSearchPagesTool
  │     ├─> WebScraperExtractTextTool, CodeExecutorRunPythonTool
  │     └─> DocumentParseTool (lazy import inside function)
  │
  ├─> mcp_client_manager.start_system_servers()
  │     ├─> Spawn "filesystem" server (stdio)
  │     ├─> Spawn "shell" server (stdio)
  │     ├─> Spawn "cloud_api" server (stdio)
  │     └─> Spawn "desktop" server (stdio)
  │
  ├─> tool_registry.discover_mcp_tools()
  │     ├─> mcp_client_manager.list_tools()
  │     └─> Wrap each in MCPWrappedTool → register in tool_registry.tools
  │
  └─> (Celery worker repeats this entire sequence per process)
```

### Tool Execution Flow

```
Executor Node / API Route
  └─> tool_registry.execute(tool_name, parameters)
        └─> app/tools/registry.py:324  ToolRegistry.execute()
            ├─> Find RegisteredTool in self.tools dict
            ├─> Enforce timeout (parameters.get("_timeout", 60))
            ├─> await asyncio.wait_for(registered.tool.execute(tool_input), timeout=...)
            │
            │   MCPWrappedTool.execute() (app/tools/registry.py:41)
            │     ├─> Strip keys starting with "_" (e.g., _task_id)
            │     ├─> mcp_client_manager.call_tool(self.name, arguments)
            │     │       └─> Lookup server_name in _tool_to_server
            │     │       └─> await conn.session.call_tool(original_name, arguments)
            │     │       └─> JSON-RPC over stdio
            │     └─> Convert CallToolResult → ToolOutput
            │
            │   NativeTool.execute()
            │     └─> Direct Python call
            │
            └─> observability_bus.emit_safe(TOOL_RESULT, ...)
```

### Tool Name Namespacing

- **Built-in**: `web_search`, `calculator`, `github_get_repo`, etc.
- **Browser env**: `browser_env__launch`, `browser_env__navigate`, etc.
- **Desktop env**: `desktop_env__screenshot`, `desktop_env__click`, `desktop_env__type_text`, etc.
- **MCP tools**: `{server_name}__{tool_name}` → e.g., `filesystem__read_file`, `shell__execute_command`, `desktop__screenshot`

### Critical Tool Registry Findings

1. **Name Collision**: `desktop__screenshot` exists as both native `DesktopEnvTool` and MCP-wrapped tool. MCP registration overwrites native because `discover_mcp_tools()` runs after `_register_desktop_env_tools()`.
2. **Empty Schemas**: `DesktopEnvTool.get_schema()` and `BrowserEnvTool.get_schema()` return `{"parameters": {}}`. The LLM receives zero parameter information, causing hallucinated or empty parameters.
3. **Double-Prefix Bug**: `app/tools/grounding.py:75-80` lists `desktop__desktop__screenshot` (double prefix), so semantic desktop tools are never matched by the grounding layer.
4. **v2 Execution Gap**: `app/api/routes/tools_v2.py:100-118` — OpenAPI tools return mock responses; MCP/PYTHON/DOCKER types fall through to v1 registry.
5. **No Auto-Restart**: If an MCP child process dies, `mcp_client_manager` has no restart logic. Subsequent calls raise `ValueError("Tool not found")`.

---

## 6. LangGraph Flow

### State Schema

File: `app/langgraph/state.py`

```python
class AgentState(TypedDict, total=False):
    task_id: str
    user_id: str
    trace_id: str
    query: str
    config: Dict[str, Any]
    messages: Annotated[List[BaseMessage], add_messages]
    plan: List[Dict[str, Any]]
    current_step_index: int
    steps: List[Dict[str, Any]]
    step_results: Dict[str, Any]
    collaboration_results: Annotated[Dict[str, Any], merge_dicts]
    tool_calls: List[Dict[str, Any]]
    verified: bool
    verification_notes: Optional[str]
    approved: Optional[bool]
    approval_reason: Optional[str]
    result: Dict[str, Any]
    error: Optional[str]
    capability_assessment: Optional[Dict[str, Any]]
    feasibility_report: Optional[Dict[str, Any]]
    environment_config: Optional[Dict[str, Any]]
    verification_reports: List[Dict[str, Any]]
    recovery_decisions: List[Dict[str, Any]]
    created_at: str
    mode: str
    status: str
    max_tool_rounds: int
```

**Critical**: `total=False` means NO runtime validation. Nodes can silently omit keys.

### Task Graph (Primary)

File: `app/langgraph/graphs.py:63`, function `compile_task_graph()`

```
[ENTRY] → planner → executor → (conditional)
                              │
                              ├─ "execute" → executor (loop)
                              └─ "verify" → verifier → (conditional)
                                                          │
                                                          ├─ "approve" → approval → (conditional)
                                                          │                                    │
                                                          │                                    ├─ "summarize" → summarizer → [END]
                                                          │                                    └─ "reject" → [END]
                                                          └─ "summarize" → summarizer → [END]
```

### Graph Compilation & Caching

File: `app/langgraph/graphs.py`

```python
_graph_cache: Dict[str, Any] = {}

def get_cached_graph(mode: str, **kwargs) -> Any:
    cache_key = f"{mode}:{hash(str(sorted(kwargs.items())))}"
    if cache_key in _graph_cache:
        return _graph_cache[cache_key]
    # ... compile and cache
```

- Graphs compiled ONCE per process and cached forever.
- Cache key uses `hash(str(sorted(kwargs.items())))` — fragile with unhashable nested dicts.
- Workflow mode includes `workflow_definition` in kwargs, causing per-workflow compilation.

### Node-by-Node Deep Dive

#### Planner Node (`app/langgraph/nodes.py:166`)

1. Calls `workflow_decomposer.decompose(query)` (line 181)
2. If phases > 1: builds deterministic plan from phases (bypasses LLM)
3. Else: calls LLM with partial schema:
   ```python
   response_schema = {
       "type": "object",
       "properties": {
           "plan": {
               "type": "array",
               "items": {
                   "type": "object",
                   "properties": {
                       "step_number": {"type": "integer"},
                       "description": {"type": "string"},
                       "tool": {"type": ["string", "null"]},
                       "expected_output": {"type": "string"},
                   },
                   "required": ["step_number", "description", "tool", "expected_output"]
               }
           }
       }
   }
   ```
   **Partial schema does NOT enforce**: `allowed_tools`, `fallback_tools`, `depends_on`, `required`, `step_type`.
4. On exception: single-step fallback plan with `tool: None`

#### Executor Node (`app/langgraph/nodes.py:327`)

1. Gets current step from `plan[current_step_index]`
2. **Dependency Gate** (lines 363-381):
   - Checks prior steps marked `required: True`
   - If any required prior step failed: sets `current_step_index = len(plan)` to force END
   - **BUG**: This tricks the graph into termination but the error is not checked by conditional edge logic
3. **Tool Selection** (lines 382-398):
   - Hierarchy: `step["allowed_tools"]` → `step["fallback_tools"]` → `tool_grounding_layer.filter_tools_for_step()`
4. **Deterministic Shortcut** (lines 402-426):
   - Calls `_build_default_params(tool_name, description)`
   - If returns non-None dict, skips LLM and executes directly
   - **BUG**: Returns `{}` for all `desktop_env__*` tools, causing execution with empty params
5. **LLM Execution Loop** (lines 428-680):
   - For `round_num in range(MAX_ROUNDS)` where `MAX_ROUNDS = state.get("max_tool_rounds", 5)`
   - Each loop calls `llm.complete_json()` with NO response schema
   - Grounding guard: rejects tool if not in `grounded_tool_names`
   - Duplicate guard: hashes `{name, params}` with `_task_id`
   - Safety gate check (line 575)
   - Calls `tool_registry.execute()` (line 605)
6. On exception in loop: breaks with `final_answer = f"Error during execution: {e}"`

#### Verifier Node (`app/langgraph/nodes.py:840`)

1. **Deterministic verification** (line 862):
   - `verification_engine.verify_plan(task_id, plan)`
   - `det_pass = all(r.result != VerificationResult.FAIL for r in det_reports)`
2. **LLM semantic verification** (lines 878-904):
   - Calls LLM with verification prompt
   - `llm_verified = raw.get("verified", False)`
3. **Environment-specific verification** (lines 907-924):
   - Checks browser calls if `env_type == "browser_ui"`
   - **No desktop environment verification exists**
4. **Final verdict** (line 927):
   - `verified = det_pass and llm_verified and env_verified`
   - All three must be true

#### Approval Node (`app/langgraph/nodes.py:930`)

1. Uses LangGraph `interrupt()` (line 961):
   ```python
   value = interrupt({
       "task_id": task_id,
       "step": step,
       "message": "Approval required before proceeding",
   })
   ```
2. `approved = value.get("approved", False)`
3. Returns state update with `approved` value

#### Summarizer Node (`app/langgraph/nodes.py:988`)

1. Combines all step outputs into context string
2. Calls LLM for final summary
3. On failure: falls back to `combined[:1000]`

### Checkpoint & Recovery

File: `app/langgraph/checkpointer.py`

```python
class PostgresCheckpointSaver(BaseCheckpointSaver):
    async def aput(self, config, checkpoint, metadata, new_versions=None):
        # Upsert to CheckpointModel table (thread_id, checkpoint_ns, checkpoint_id)
        # Stores checkpoint as JSON TEXT (not JSONB)

    async def aget_tuple(self, config):
        # Returns latest checkpoint for thread_id + checkpoint_ns

    async def aput_writes(self, config, writes, task_id, task_path=""):
        # NO-OP — writes are logged but not persisted
```

**Recovery Flow** (`app/recovery/checkpoint_service.py:11`):
```python
async def resume_task(self, task_id, mode, state):
    checkpointer = get_checkpointer()
    config = {"configurable": {"thread_id": task_id, "checkpoint_ns": mode}}
    checkpoint_tuple = await checkpointer.aget_tuple(config)
    if checkpoint_tuple is None:
        return None
    return checkpoint_tuple.checkpoint.get("channel_values", {})
```

**Critical flaw**: Recovery returns `channel_values` dict only. It does NOT return a `CheckpointTuple` or `Command(resume=...)`. The orchestrator passes this as `resume_state` to `_build_initial_state()`, which starts a **NEW** graph run with old state values. If the graph failed at an `interrupt()`, the recovery path will NOT resume the interrupt correctly.

---

## 7. Verification Flow

### Three-Layer Verification Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    VERIFIER NODE (LangGraph)                     │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │  Deterministic  │  │  LLM Semantic   │  │   Environment   │ │
│  │   Verification  │  │  Verification   │  │    Specific     │ │
│  │                 │  │                 │  │                 │ │
│  │ Checks based on │  │ Asks LLM "Was   │  │ Validates that  │ │
│  │ step keywords:  │  │ task completed  │  │ expected tools  │ │
│  │ - file_exists   │  │ correctly?"     │  │ were invoked    │ │
│  │ - deployment_   │  │                 │  │ for the chosen  │ │
│  │   healthy       │  │                 │  │ environment     │ │
│  │ - web_content   │  │                 │  │                 │ │
│  │ - browser_opened│  │                 │  │                 │ │
│  │ - html_rendered │  │                 │  │                 │ │
│  │ - summary_gen   │  │                 │  │                 │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
│                         │
│                         ▼
│              verified = det_pass AND llm_verified AND env_verified
└─────────────────────────────────────────────────────────────────┘
```

### Deterministic Verification Engine

File: `app/capabilities/verification.py:82`, function `verify_plan()`

Auto-generates checks based on step description keywords:

| Keyword Pattern | Verification Type | Actual Check |
|-----------------|-------------------|--------------|
| `file_*` | `file_exists` | File system existence check |
| `deploy` / `host` / `publish` | `deployment_healthy` | HTTP health check |
| `scrape` / `fetch` / `download` | `web_content` | HTTP content check |
| `open chrome` / `browser` | `browser_opened` | Browser tool invocation check |
| `create html` | `html_rendered` | HTML file existence |
| `summarize` | `summary_generated` | Summary text presence |

**Critical Gap**: There is NO verifier for desktop UI actions. `workflow_decomposer.py` declares `desktop_action_completed` (line 109), but `verification_engine.verify_plan()` does not implement it. Desktop tasks rely entirely on LLM semantic verification, which is easily fooled by success status of empty operations.

### LangGraph Verifier Node Logic

File: `app/langgraph/nodes.py:840`

```python
async def verifier_node(state: AgentState) -> Dict[str, Any]:
    # 1. Deterministic
    det_reports = await verification_engine.verify_plan(task_id, plan)
    det_pass = all(r.result != VerificationResult.FAIL for r in det_reports)

    # 2. LLM Semantic
    raw = await llm.complete_json(...)
    llm_verified = raw.get("verified", False)

    # 3. Environment-specific
    env_verified = True
    if env_type == "browser_ui":
        browser_calls = [t for t in tool_calls if t.get("tool", "").startswith("browser_env__")]
        env_verified = bool(browser_calls)
    # NOTE: No "desktop" env check!

    verified = det_pass and llm_verified and env_verified
```

**Flaw**: If `det_pass = False` but recovery already handled the issue, the old failed report is never re-evaluated because `verification_reports` are appended but never removed.

---

## 8. Current Bottlenecks

### B1. LLM Call Amplification in Executor

- Each step can trigger up to `max_tool_rounds` (default 5) LLM completions.
- A 10-step plan = up to 50 LLM calls.
- No caching of LLM responses for identical tool selection contexts.
- **Files**: `app/langgraph/nodes.py:428-680`

### B2. Synchronous Graph Compilation Cache

- `_graph_cache` is a module-level dict with no eviction.
- Workflow mode creates a new compiled graph per unique workflow definition.
- Long-running processes with many workflow definitions leak memory.
- **File**: `app/langgraph/graphs.py`

### B3. Database Blocking in Checkpointer

- `aput()` and `aget_tuple()` use SQLAlchemy async, but checkpoint serialization uses `json.dumps` synchronously on potentially large state objects.
- No streaming or chunked writes.
- **File**: `app/langgraph/checkpointer.py`

### B4. No Parallel Step Execution

- The task graph is strictly sequential.
- Even steps with no `depends_on` relationships execute one-at-a-time.
- The collaboration graph supports parallelism but is only used in `collaboration` mode.
- **File**: `app/langgraph/graphs.py:63`

### B5. Event Bus Fire-and-Forget

```python
try:
    await event_bus.publish(...)
except Exception:
    pass
```
- Observability failures are silently swallowed.
- **Files**: `app/observability/bus.py`, `app/langgraph/nodes.py`

### B6. In-Memory Metrics Volatility

- `MetricsCollector` stores all counters/histograms in memory.
- Process restart wipes all metrics.
- No Prometheus pushgateway or remote write.
- **File**: `app/logs/metrics.py`

### B7. API Key Middleware DB Write on Every Request

- `APIKeyMiddleware` updates `last_used_at` synchronously on every API-key-authenticated request.
- Adds DB write latency to every request.
- **File**: `app/middleware/auth.py`

### B8. N+1 Query in Task Listing

- `list_tasks()` iterates over all tasks and calls `_task_scoped_workflow_state()` for each.
- Issues multiple DB queries per task.
- **File**: `app/api/routes/tasks.py:303-304`

### B9. Redis Pub/Sub Message Loss

- Redis pub/sub is fire-and-forget with no replay buffer.
- WebSocket clients that disconnect and reconnect miss events published during the gap.
- **Files**: `app/api/ws.py`, `app/memory/redis_pubsub.py`

### B10. Celery Result Backend Shares Broker Redis

- Broker and result backend use the same Redis instance.
- Under load, result backend I/O can starve the broker.
- **File**: `app/queue/tasks.py:14-35`

---

## 9. Dangerous Architectural Flaws

### F1. Pervasive Singleton Proliferation (CRITICAL)

**Evidence**: ~20+ module-level singletons create a global state soup.

| File | Singleton | Pattern |
|------|-----------|---------|
| `app/runtime/runtime.py` | `AgentRuntime` | `__new__` with `_instance` |
| `app/tools/registry.py` | `ToolRegistry` | `__new__` with `_instance` |
| `app/mcp/client_manager.py` | `MCPClientManager` | module-level `mcp_client_manager` |
| `app/memory/long_term.py` | `db` + 15 repos | module-level instantiation |
| `app/memory/short_term.py` | `redis_client`, `short_term_memory` | module-level |
| `app/memory/redis_pubsub.py` | `redis_pubsub_client` | module-level |
| `app/orchestrator/core.py` | `orchestrator` | module-level |
| `app/orchestrator/v2/event_bus.py` | `event_bus` | module-level |
| `app/observability/bus.py` | `observability_bus` | module-level |
| `app/logs/metrics.py` | `metrics_collector` | module-level |
| `app/logs/logger.py` | `logger` | module-level |
| `app/langgraph/graphs.py` | `_graph_cache`, `get_checkpointer()` | module-level + global |
| `app/api/ws.py` | `manager` | module-level |
| `app/agents/v2/registry.py` | `agent_registry_v2` | module-level |
| `app/tools/v2/registry.py` | `tool_registry_v2` | module-level |

**Impact**:
- Unit testing requires `reset()` methods that don't exist on most objects.
- Horizontal scaling (multiple runtime instances per process) is impossible.
- Cannot run isolated tenants or sandboxed executions.

### F2. God Object: Orchestrator (CRITICAL)

**File**: `app/orchestrator/core.py` (284 lines)

The `Orchestrator` class knows about:
- Runtime, router, workflow engine, builder, step executor, task runner
- Pipeline executor, retry config, guardrails, DB repositories, short-term memory
- Checkpoint recovery, legacy mode fallback

**Violations**:
- 35+ attributes/methods
- Imports from 15+ modules
- Direct instantiation of `WorkflowEngine`, `WorkflowBuilder`, `StepExecutor`, `TaskRunner`, `PipelineExecutor`, `AgentRouter`
- API routes call private methods: `orchestrator._get_workflow_state()`, `orchestrator._execute_with_langgraph()`

### F3. Circular Dependency Graph & Lazy Import Workarounds (CRITICAL)

**Evidence**: At least 12 instances of inside-function imports across core modules.

| File | Line | Lazy Import |
|------|------|-------------|
| `app/tools/registry.py` | 42 | `from ..mcp.client_manager import mcp_client_manager` |
| `app/tools/registry.py` | 100 | `from ..pipelines.document_ingestion import DocumentParseTool` |
| `app/tools/registry.py` | 107 | `from ..environments.browser_env import browser_session_manager` |
| `app/tools/registry.py` | 150 | `from ..environments.desktop_env import desktop_session_manager` |
| `app/tools/registry.py` | 243 | `from ..mcp.client_manager import mcp_client_manager` |
| `app/tools/registry.py` | 358-359 | `from ..observability.bus import observability_bus` |
| `app/observability/bus.py` | 31 | `from ..orchestrator.v2.event_bus import event_bus` |
| `app/orchestrator/core.py` | 240 | `from ..recovery.checkpoint_service import CheckpointRecoveryService` |
| `app/orchestrator/core.py` | 251 | `from .modes import ModeStrategyFactory` |
| `app/api/routes/tasks.py` | 128 | `from ...orchestrator.core import orchestrator` |
| `app/api/routes/tasks.py` | 371, 414 | `from ...orchestrator.core import orchestrator` |
| `app/middleware/rate_limit.py` | 49 | `from ..auth.utils import verify_access_token` |

**Impact**:
- Hides true dependency structure
- Breaks IDE/static analysis
- Runtime failures if imports fail mid-execution
- Strong signal of broken module boundaries

### F4. No Service Layer / Routes Directly Touch Repositories (HIGH)

**Primary offender**: `app/api/routes/tasks.py` (510 lines)

Contains business logic:
- Task execution dispatch
- Celery enqueue decisions
- Approval/rejection workflows
- Workflow state serialization
- Defines helper functions `_parallel_groups()`, `_task_scoped_workflow_state()`

Directly calls:
- `task_repo.create()`, `task_repo.update()`, `task_repo.list_all()`
- `orchestrator.execute_task()`
- `workflow_node_repo.update()`

**Impact**: No encapsulation of business rules. Changes to execution logic require modifying API routes.

### F5. Missing Unit-of-Work / Transaction Boundaries (HIGH)

**File**: `app/memory/long_term.py`

Every repository method opens and closes its own database session:
```python
async with db.get_session() as session:
    ...
    await session.commit()
```

**Impact**:
- `AgentRuntime.initialize()` persists 3 core agents in 3 separate transactions.
- Task approval updates task + nodes in separate transactions.
- Crash midway leaves database inconsistent.

### F6. V1/V2 Duality Without Migration (HIGH)

**Files**: `app/tools/v2/registry.py`, `app/agents/v2/registry.py`, `app/api/routes/tools_v2.py`, `app/api/routes/agents_v2.py`, `app/memory/models.py`

- Separate DB tables: `tools` vs `tools_v2`, `agents` vs `agent_config_v2`
- Separate registries: `tool_registry` vs `tool_registry_v2`
- `AgentRuntime` and `AgentFactory` only know v1 agents.
- v2 tool execution falls back to v1 registry for native tools, returns mocks for OpenAPI.

**Impact**: Confuses users, corrupts data boundaries, blocks feature completion.

### F7. `eval()` in Workflow Engine (HIGH)

**File**: `app/orchestrator/v2/engine.py:84`

```python
result = eval(node.condition, {"context": context, "__builtins__": {}})
```

**Impact**: Code injection vector. User-provided workflow conditions execute arbitrary Python expressions.

### F8. Celery Worker Initialization Duplicates App Lifespan (HIGH)

**File**: `app/queue/tasks.py:42-100`

The `on_worker_process_init` handler duplicates the entire FastAPI startup sequence:
- DB connect, Redis connect, runtime init, tool registration, MCP server startup

**Impact**: Violates DRY. Any change to startup requires updating both places. Drift is guaranteed.

### F9. AgentRuntime Redis Mutex Expires After 1 Hour on Crash (MEDIUM-HIGH)

**File**: `app/runtime/runtime.py:47-65`

```python
await redis_client.client.set("agentos:runtime:init_mutex", mutex_value, nx=True, ex=3600)
```

**Impact**: If the process holding the mutex crashes without calling `reset()`, no other process can acquire the mutex for an hour. Blocks initialization across the fleet.

### F10. WebSocket Connection Manager Lacks TTL / Stale Connection Cleanup (MEDIUM)

**File**: `app/api/ws.py`

```python
self.active_connections: Dict[str, List[WebSocket]] = {}
```

**Impact**: No TTL, no garbage collection, no limit on total connections. Memory grows indefinitely.

### F11. Silent Desktop Typing Failure (CRITICAL — Execution Bug)

**Files**: `app/langgraph/nodes.py:56-93`, `app/langgraph/nodes.py:412-426`, `app/tools/registry.py:149-162`

For "open notepad and type hello":
1. `_build_default_params("desktop_env__type_text", ...)` returns `{}` (line 92)
2. Executor sees `{}` as valid default params and skips LLM parameter generation
3. `DesktopEnvTool.execute()` receives empty params, calls `session.type_text("")`
4. Step reports `success=True` but types nothing
5. Verifier has no desktop checks, LLM semantic verifier likely passes because Notepad is open

**Impact**: User tasks silently fail. The system reports success while accomplishing nothing.

### F12. Empty Tool Schemas Prevent LLM from Generating Correct Parameters (CRITICAL)

**Files**: `app/tools/registry.py:117` (BrowserEnvTool), `app/tools/registry.py:160` (DesktopEnvTool)

```python
def get_schema(self):
    return {"name": self.name, "description": self.description, "parameters": {}}
```

**Impact**: LLM has no schema for desktop/browser tools. Cannot generate correct parameter names or values.

### F13. Checkpoint Recovery Does Not Truly Resume LangGraph (HIGH)

**Files**: `app/recovery/checkpoint_service.py:11`, `app/orchestrator/core.py:230-247`

Recovery loads `channel_values` and starts a **new** graph run. If failure occurred at `interrupt()`, the interrupt is NOT resumed. The approval workflow is effectively broken for recovered tasks.

### F14. MCP System Servers Have Zero Health Monitoring (HIGH)

**File**: `app/mcp/monitor.py`

The `MCPHealthMonitor` only checks DB-registered HTTP endpoints. The 4 stdio system servers (filesystem, shell, cloud_api, desktop) are NEVER health-checked.

**Impact**: If a child process dies (OOM, segfault), the only symptom is a `ValueError` on the next tool call.

### F15. 16x Process Bloat in Celery (HIGH)

**File**: `app/queue/tasks.py`

With `--concurrency=4`, each Celery worker child spawns its own 4 MCP servers = 16 child processes total. No shared connection pooling.

---

## 10. Recommended Fix Priority Order

### Priority 1: Execution Correctness (Fix Silent Failures)

These bugs cause tasks to report success while failing to execute user intent.

| # | Fix | Files | Effort |
|---|-----|-------|--------|
| 1.1 | Fix `_build_default_params()` to NOT return `{}` for desktop tools | `app/langgraph/nodes.py:56-93` | Small |
| 1.2 | Implement proper parameter schemas for DesktopEnvTool and BrowserEnvTool | `app/tools/registry.py:117,160` | Small |
| 1.3 | Fix grounding layer double-prefix bug (`desktop__desktop__*`) | `app/tools/grounding.py:75-80` | Small |
| 1.4 | Add desktop verification checks to `verify_plan()` | `app/capabilities/verification.py:82` | Medium |
| 1.5 | Add shell→desktop prohibition to LangGraph executor prompt | `app/langgraph/nodes.py:461-492` | Small |

### Priority 2: Architectural Foundation (Prevent Catastrophic Failure)

| # | Fix | Files | Effort |
|---|-----|-------|--------|
| 2.1 | Replace `eval()` with `asteval` or JSON-based condition DSL | `app/orchestrator/v2/engine.py:84` | Medium |
| 2.2 | Add crash-safe Redis mutex (Redlock or watchdog pattern) | `app/runtime/runtime.py:47-65` | Medium |
| 2.3 | Implement MCP server auto-restart and health checks for stdio servers | `app/mcp/client_manager.py`, `app/mcp/monitor.py` | Medium |
| 2.4 | Fix checkpoint recovery to use `Command(resume=...)` properly | `app/recovery/checkpoint_service.py`, `app/orchestrator/core.py` | Medium |
| 2.5 | Extract service layer from `app/api/routes/tasks.py` | `app/api/routes/tasks.py` | Large |

### Priority 3: Structural Debt (Enable Scaling & Testing)

| # | Fix | Files | Effort |
|---|-----|-------|--------|
| 3.1 | Break `Orchestrator` god object into focused services | `app/orchestrator/core.py` | Large |
| 3.2 | Replace module-level singletons with dependency injection | `app/runtime/runtime.py`, `app/tools/registry.py`, etc. | Large |
| 3.3 | Resolve circular dependencies by restructuring module boundaries | `app/tools/registry.py`, `app/orchestrator/core.py`, etc. | Large |
| 3.4 | Introduce Unit-of-Work pattern for atomic transactions | `app/memory/long_term.py` | Medium |
| 3.5 | Consolidate V1/V2 duality or formally deprecate V1 | `app/tools/`, `app/agents/`, `app/memory/models.py` | Large |
| 3.6 | DRY: Extract shared bootstrap logic for FastAPI + Celery | `app/main.py`, `app/queue/tasks.py` | Medium |

### Priority 4: Observability & Reliability (Production Readiness)

| # | Fix | Files | Effort |
|---|-----|-------|--------|
| 4.1 | Implement structured JSON logging with correlation IDs | `app/logs/logger.py` | Medium |
| 4.2 | Add OpenTelemetry/Jaeger distributed tracing | `app/logs/tracing.py` | Medium |
| 4.3 | Fix WebSocket connection manager memory leak (TTL/cleanup) | `app/api/ws.py` | Small |
| 4.4 | Add message replay buffer for WebSocket/SSE disconnects | `app/api/ws.py`, `app/memory/redis_pubsub.py` | Medium |
| 4.5 | Separate Celery result backend from broker Redis | `app/queue/tasks.py` | Small |
| 4.6 | Fix duplicate /health and /metrics route registration | `app/main.py`, `app/api/routes/health.py` | Small |
| 4.7 | Add MCP server health to readiness probe | `app/api/routes/health.py` | Small |

### Priority 5: Performance Optimization

| # | Fix | Files | Effort |
|---|-----|-------|--------|
| 5.1 | Add LLM response caching for identical tool selection contexts | `app/langgraph/nodes.py` | Medium |
| 5.2 | Implement parallel step execution for independent steps | `app/langgraph/graphs.py` | Large |
| 5.3 | Add graph cache eviction / LRU policy | `app/langgraph/graphs.py` | Small |
| 5.4 | Fix N+1 query in task listing | `app/api/routes/tasks.py:303-304` | Small |
| 5.5 | Make API key `last_used_at` update asynchronous | `app/middleware/auth.py` | Small |

---

## Appendix: Desktop Execution Trace — "open notepad and type hello"

This appendix traces EXACTLY how the system handles the command "open notepad and type hello", citing every file and function involved, with identified failure points.

### Step 1: API Ingress

- **File**: `app/api/routes/tasks.py:132`
- **Function**: `create_task()`
- **Action**: Receives `POST /api/v1/tasks` with `{"query": "open notepad and type hello"}`
- **Auth**: `app/api/deps.py:22`, `get_current_user()` validates JWT

### Step 2: Task Persistence

- **File**: `app/api/routes/tasks.py:163`
- **Function**: `task_repo.create(task_id=str(task_id), query=request.query, ...)`
- **Action**: Inserts `TaskModel` with status `PENDING`
- **Event**: `task.status_changed` → `PENDING` published to event bus

### Step 3: Celery Dispatch

- **File**: `app/api/routes/tasks.py:178`
- **Action**: `celery_app.send_task("agent_os.execute_task", args=[str(task_id), "open notepad and type hello", config, user_id])`

### Step 4: Worker Initialization

- **File**: `app/queue/tasks.py:42`
- **Function**: `on_worker_process_init()`
- **Actions**:
  - Sets `ProactorEventLoopPolicy` (line 52)
  - Connects DB + Redis (lines 69-71)
  - Initializes `AgentRuntime` (line 73)
  - Registers built-in tools (line 76)
  - Starts MCP system servers (line 89): filesystem, shell, cloud_api, desktop
  - Discovers MCP tools (line 94)

### Step 5: Task Execution Entry

- **File**: `app/queue/tasks.py:127`
- **Function**: `execute_task(self, task_id, query, config, user_id)`
- **Action**: Calls `orchestrator.execute_task(query, config, task_id, user_id)` at line 186

### Step 6: Orchestrator → LangGraph

- **File**: `app/orchestrator/core.py:216`
- **Function**: `execute_task()`
- **Action**: Immediately delegates to `_execute_with_langgraph()` (line 231)

### Step 7: TaskRunner — Capability Classification

- **File**: `app/orchestrator/task_runner.py:97`
- **Function**: `run()`
- **Capability Classification** (line 115):
  - `capability_router.classify("open notepad and type hello", str(task_id))`
  - **File**: `app/capabilities/router.py:102`
  - **Function**: `CapabilityRouter.classify()`
  - Query contains `"open notepad"` and `"type"` → matches `Capability.DESKTOP` keywords (line 75)
  - Result: `primary_capability = DESKTOP`, `estimated_complexity = 1`, `safety_flags = []`

### Step 8: Feasibility Check

- **File**: `app/orchestrator/task_runner.py:135`
- **Function**: `feasibility_engine.check(assessment, config)`
- **File**: `app/capabilities/feasibility.py:38`
- **Function**: `FeasibilityEngine.check()`
- **Checks**:
  1. Required capabilities vs available (`_get_available_capabilities`, line 100)
  2. Required tools vs registered (`_get_available_tools`, line 111)
  3. Disk space > 100MB (line 115)
  4. Safety constraints (blocked patterns like `rm -rf /`, line 129)
- **Result**: `EXECUTABLE` (desktop capability always available, safety passes)

### Step 9: Environment Selection

- **File**: `app/orchestrator/task_runner.py:164`
- **Function**: `feasibility_engine.select_environment(...)`
- **File**: `app/capabilities/environment_selector.py:34`
- **Function**: `ExecutionEnvironmentSelector.select()`
- **Action**: Keyword matching falls through to `ExecutionEnvironment.DESKTOP` (line 65)
- **Action**: `execution_environment.configure(str(task_id), env_config)` (line 165)

### Step 10: Graph Compilation

- **File**: `app/orchestrator/task_runner.py:191`
- **Function**: `get_cached_graph("task", checkpointer=checkpointer)`
- **File**: `app/langgraph/graphs.py:63`
- **Function**: `compile_task_graph()`
- **Graph**: `planner → executor → verifier → (approval) → summarizer`

### Step 11: Graph Invocation

- **File**: `app/orchestrator/task_runner.py:213`
- **Action**: `await asyncio.wait_for(graph.ainvoke(state, config=thread_config), timeout=workflow_timeout)`
- **Thread config**: `{"configurable": {"thread_id": str(task_id), "checkpoint_ns": "task"}}`

### Step 12: Planner Node

- **File**: `app/langgraph/nodes.py:166`
- **Function**: `planner_node()`
- **Decomposer call** (line 181): `workflow_decomposer.decompose("open notepad and type hello")`
- **File**: `app/workflows/decomposer.py:142`
- **Function**: `WorkflowDecomposer.decompose()`
- **Action**: `_classify_query()` (line 129) detects `"notepad"` in `DESKTOP_APP_KEYWORDS` (line 26) → `has_desktop = True`
- **Result**: 1 phase → `[WorkflowPhase(name="desktop_automation", ...)]`

- **LLM Fallback** (line 182): `if len(phases) > 1:` is **FALSE**
- Falls through to LLM planner (lines 255-323)
- System prompt: `PLANNER_SYSTEM_PROMPT_TEMPLATE` (lines 113-156) with OS info injected
- **LLM call** (line 282): `llm.complete_json(...)` with partial schema
- **Likely LLM output**:
  ```json
  {
    "plan": [
      {"step_number": 1, "description": "Open Notepad", "tool": "shell__execute_command", "allowed_tools": ["shell__execute_command"]},
      {"step_number": 2, "description": "Type hello into Notepad", "tool": "desktop_env__type_text", "allowed_tools": ["desktop_env__type_text"]}
    ]
  }
  ```

### Step 13: Executor Node — Step 1 (Open Notepad)

- **File**: `app/langgraph/nodes.py:327`
- **Function**: `executor_node()`
- **State**: `idx=0`, `step = plan[0]`
- **Dependency gate**: Passes (no prior steps)
- **Tool grounding** (lines 382-398): `shell__execute_command` is in `allowed_tools`
- **Deterministic shortcut** (lines 402-426): `_build_default_params("shell__execute_command", "Open Notepad")` returns `None`
- **LLM generates params**: `{"tool_call": {"name": "shell__execute_command", "params": {"command": "notepad"}}}`
- **Grounding guard**: Passes (line 527)
- **Safety gate**: Passes (line 575)
- **Tool execution** (line 605): `tool_registry.execute("shell__execute_command", {"command": "notepad", "_task_id": task_id})`
- **Result**: Notepad process launches. Tool result = success.

### Step 14: Executor Node — Step 2 (Type Hello)

- **State**: `idx=1`, `step = plan[1]`
- **Dependency gate**: Passes (step 1 succeeded)
- **Tool grounding**: `desktop_env__type_text` is in `allowed_tools`
- **Deterministic shortcut TRIGGERED** (lines 412-426):
  - `_build_default_params("desktop_env__type_text", "Type hello into Notepad")` returns `{}`
  - **File**: `app/langgraph/nodes.py:92`
  - ```python
    if tool_name.startswith("desktop_env__"):
        return {}  # ← RETURNS EMPTY DICT
    ```
  - `det_tool = "desktop_env__type_text"` matches; `default_params = {}` is **not** `None`
  - Calls `_execute_tool_call(..., tool_name="desktop_env__type_text", tool_params={})` (line 417)
- **Execute tool call** (line 709): Injects `_task_id`, calls `tool_registry.execute(...)`
- **DesktopEnvTool.execute()** (`app/tools/registry.py:162`):
  - `params.get("text", "")` → **empty string** (because params dict was empty)
  - Calls `session.type_text("")` which types **nothing**
  - Returns `success=True` with `"message": "Typed text (length 0)"`
- **BUG**: Step appears successful but **"hello" was never typed**.

### Step 15: Graph Conditional Edge

- **File**: `app/langgraph/graphs.py:38`
- **Function**: `_should_continue()`
- **Check**: `idx < len(plan)` → false (2 steps done)
- **Route**: `"verify"` → `verifier_node`

### Step 16: Verifier Node

- **File**: `app/langgraph/nodes.py:840`
- **Function**: `verifier_node()`
- **Deterministic verification** (line 862): `verification_engine.verify_plan(task_id, plan)`
- **File**: `app/capabilities/verification.py:82`
- **Function**: `verify_plan()`
- **Action**: Auto-detects verification type from step description keywords
- **Result**: Neither step matches file/deploy/scrape/browser/html/summary keywords
- **Zero deterministic checks run**. `det_pass` remains `True` (line 860)
- **LLM semantic verification** (lines 878-904): Asks LLM "was the task completed?"
  - LLM sees Notepad opened → likely answers `verified: true`
- **Environment check** (lines 907-924): `env_type` is not `"browser_ui"` → `env_verified = True`
- **Final verdict**: `verified = True and True and True = True`

### Step 17: Summarizer Node

- **File**: `app/langgraph/nodes.py:988`
- **Function**: `summarizer_node()`
- **Action**: Compiles step outputs:
  - Step 1: "Notepad opened"
  - Step 2: "Typed text length 0"
- **LLM summary**: Likely says "Opened Notepad" with no mention of the failed typing
- **Result**: Final output with status "completed"

### Step 18: Completion & Persistence

- **File**: `app/queue/tasks.py:189`
- **Action**: `result.status.value == "success"` → true
- **DB update**: `task_repo.update(task_id, status=TaskStatus.COMPLETED.value, result=result.output_data)`
- **Event**: `task.completed` published
- **WebSocket**: Clients receive completion event

### Summary of the Silent Failure

For the command "open notepad and type hello":
1. Notepad **will** open (via shell)
2. **"hello" will NOT be typed** because `_build_default_params()` returns `{}` for all `desktop_env__*` tools, causing the executor to skip LLM parameter generation and call the tool with an empty `text` parameter.
3. The step reports `success=True` because `DesktopEnvTool` gracefully handles empty text.
4. Verification passes because:
   - No desktop-specific deterministic verifiers exist
   - LLM semantic verifier likely passes based on Notepad being open
5. The task completes with status `SUCCESS` while the user's actual intent was not fulfilled.

**Root cause chain**:
```
_build_default_params() returns {} for desktop_env__*
  → executor skips LLM param generation
  → DesktopEnvTool.execute() receives empty params
  → session.type_text("") is called
  → success=True with length 0
  → verifier has no desktop checks
  → task reports SUCCESS
```

---

*End of Audit Document*
