# AgentOS — Production-Grade AI Agent Operating System

> **AgentOS is NOT a chatbot.** It is a structured, stateful agent execution system where AI agents reason via LangGraph state machines and act on the system via the Model Context Protocol (MCP). Every execution is traceable, checkpointed, and observable.

## Overview

AgentOS executes complex AI workflows through a **closed-loop execution model**: observe → decide → act → verify → recover. The system receives user queries, classifies task capabilities, routes to appropriate execution paths, and manages the entire agent lifecycle with production-grade reliability.

For simple, deterministic tasks (browser navigation, file operations, desktop automation), **Action V1** bypasses the full LangGraph overhead and executes directly via MCP tools. Complex or ambiguous tasks flow through the full **LangGraph StateGraph** (planner → executor → verifier → approval → summarizer). Human approval gates pause execution via LangGraph `interrupt()`. Every LangGraph step is checkpointed to PostgreSQL for resume across restarts.

## Architecture

AgentOS is organized into 8 layers, each with strict single responsibility:

### 8-Layer Architecture Stack

```
┌─────────────────────────────────────────────────────────────┐
│ Layer 1 — Frontend (React 19 + Vite + Tailwind CSS)          │
├─────────────────────────────────────────────────────────────┤
│ Layer 2 — API Gateway (FastAPI + JWT + Rate Limiting)        │
├─────────────────────────────────────────────────────────────┤
│ Layer 3 — Orchestration (Orchestrator + Mode Strategy)       │
├─────────────────────────────────────────────────────────────┤
│ Layer 4 — LangGraph Engine (plan→exec→verify→summarize)      │
├─────────────────────────────────────────────────────────────┤
│ Layer 5 — Agent Runtime (Singleton + Pool + Factory)         │
├─────────────────────────────────────────────────────────────┤
│ Layer 6 — MCP + Tools (7 MCP servers + ToolRegistry)        │
├─────────────────────────────────────────────────────────────┤
│ Layer 7 — Safety + Observability (Guardrails + Metrics)     │
├─────────────────────────────────────────────────────────────┤
│ Layer 8 — Persistence (PostgreSQL + Redis + Checkpoints)     │
└─────────────────────────────────────────────────────────────┘
```

| Layer | Responsibility | Technology |
|-------|---------------|------------|
| Frontend | Structured agent interface | React 19, Vite 8, Tailwind CSS 3.4, TypeScript |
| API Gateway | Request routing, validation, auth | FastAPI 0.121+, Uvicorn, Pydantic 2.12+ |
| Orchestration | Mode selection, LangGraph compilation, fallback | LangGraph 1.1+, LangChain |
| LangGraph Engine | Graph-native execution: plan → execute → verify → summarize | LangGraph StateGraph |
| Agent Runtime | Singleton worker registry, lifecycle, concurrency | Asyncio, Semaphore (max 100) |
| MCP + Tools | System-level tools via MCP protocol | FastMCP, stdio transport |
| Safety + Observability | Validation, tracing, metrics, structured logging | Pydantic, Prometheus |
| Memory + Persistence | PostgreSQL long-term, Redis short-term, checkpoints | SQLAlchemy async 2.0+, Redis 7+ |

## Execution Flow

Two execution paths exist:

### 1. Action V1 Fast Path (Deterministic)
- **For simple tasks**: file operations, browser navigation, desktop automation
- **Flow**: CapabilitySelector → DeterministicExecutor → DeterministicVerifier → Result
- **States**: PENDING → EXECUTING → VERIFYING → COMPLETED
- **Bypass**: Skips LangGraph entirely for speed and reliability

### 2. LangGraph Full Path (Complex Tasks)
- **For complex tasks**: multi-step workflows, ambiguous queries, collaboration
- **Flow**: planner_node → executor_node → verifier_node → approval_node → summarizer_node
- **States**: PENDING → PLANNING → EXECUTING → VERIFYING → AWAITING_APPROVAL → COMPLETED
- **Interrupt**: Human approval gates via `interrupt()` with checkpoint resume

### State Machine

```
PENDING → PLANNING → EXECUTING → VERIFYING → AWAITING_APPROVAL → COMPLETED
   ↓          ↓           ↓           ↓              ↓
FAILED ←─── FAILED ←─── FAILED ←─── FAILED ←───── REJECTED
```

| From | To | Trigger | Failure Mode |
|------|-----|---------|--------------|
| PENDING | PLANNING | Orchestrator accepts task | Validation failure → FAILED |
| PLANNING | EXECUTING | Planner generates plan | Planning timeout → FAILED |
| EXECUTING | VERIFYING | All steps executed | Step failure → retry → FAILED |
| VERIFYING | AWAITING_APPROVAL | Verification passes + approval required | Verification fails → replan or FAILED |
| VERIFYING | COMPLETED | Verification passes + no approval | Verification fails → replan or FAILED |
| AWAITING_APPROVAL | COMPLETED | User approves | User rejects → REJECTED, Timeout → FAILED |
| Any | FAILED | Unrecoverable error | N/A |

## Core Components

### AgentState TypedDict

Central state dict flowing through LangGraph nodes with 40+ fields:

| Category | Key Fields |
|----------|------------|
| Identity | `task_id`, `user_id`, `trace_id` |
| Input | `query`, `config` |
| Conversation | `messages` (add_messages reducer) |
| Planning | `plan`, `current_step_index` |
| Execution | `steps`, `step_results`, `tool_calls`, `execution_state` |
| Verification | `verified`, `verification_notes` |
| Approval | `approved`, `approval_reason` |
| Extended | `task_state`, `idempotency_key`, `priority`, `complexity_score`, `cost_estimate_usd`, `actual_cost_usd`, `memory_profile_id`, `artifact_refs`, `handoff_log`, `feedback_records`, `audit_trail` |

### Key Singletons

| Singleton | Location | Purpose |
|-----------|----------|---------|
| `AgentRuntime` | `app/runtime/runtime.py` | Agent lifecycle, Redis mutex init |
| `MCPClientManager` | `app/mcp/client_manager.py` | MCP server lifecycle, tool discovery |
| `ToolRegistry` | `app/tools/registry.py` | Built-in + MCP tool registration |
| `Orchestrator` | `app/orchestrator/core.py` | Mode selection, LangGraph compilation |

## MCP Integration (Model Context Protocol)

AgentOS uses MCP for system-level tool access with **7 stdio-based MCP servers** providing **60+ tools**:

### Available MCP Servers

| Server | Tools | Purpose |
|--------|-------|---------|
| **filesystem** | 4 tools | File read, write, list, search with path normalization |
| **shell** | 3 tools | Command execution with blocked command detection |
| **cloud_api** | 5 tools | HTTP requests, web scraping, DuckDuckGo search |
| **browser_env** | 10 tools | Playwright-based browser automation |
| **desktop** | 22 tools | Windows UI automation (uiautomation, pyautogui) |
| **document** | 8 tools | PDF/DOCX/TXT/Markdown parsing and chunking |
| **code_executor** | 1 tool | Sandboxed Python execution with AST validation |

### Tool Naming Convention

All MCP tools follow `{server_name}__{tool_name}`:
- `filesystem__read_file`
- `shell__execute_command`
- `browser_env__navigate`
- `desktop__screenshot`
- `cloud_api__search_web`

## Agents

### Core Agents

| Agent | Location | Responsibility |
|-------|----------|---------------|
| **PlannerAgent** | `app/agents/planner.py` | Decomposes queries into execution plans with DAG validation |
| **ExecutorAgent** | `app/agents/executor.py` | Executes steps with tool grounding and path remapping |
| **VerifierAgent** | `app/agents/verifier.py` | Validates outputs with quality scoring |

### Multi-Agent Coordination (Phase 3)

| Component | Location | Purpose |
|-----------|----------|---------|
| **CoordinatorAgent** | `app/agents/coordinator.py` | Fan-out/fan-in workflows with DAG execution |
| **ReviewerAgent** | `app/agents/reviewer.py` | Schema/quality validation with strict mode |
| **InterAgentHandoff** | `app/agents/handoff.py` | State transfer with SHA-256 signatures |
| **AgentFeedbackLoop** | `app/agents/feedback.py` | Pattern analysis and learning insights |
| **ConsensusEngine** | `app/agents/consensus.py` | Multi-agent agreement (majority, weighted, unanimous) |
| **AgentRouter** | `app/agents/router.py` | Capability-based routing with complexity scoring |
| **LLMRouter** | `app/agents/llm_router.py` | Multi-provider routing (OpenAI, Anthropic, Google, Local) |

## Agent Runtime

The **AgentRuntime** singleton manages agent lifecycle with production features:

### Components

| Component | File | Purpose |
|-----------|------|---------|
| **AgentRuntime** | `runtime.py` | Singleton with Redis mutex init, worker registry |
| **AgentWorker** | `worker.py` | Inbox queue, execution loop |
| **AgentFactory** | `factory.py` | Static agent creation |
| **DynamicAgentFactory** | `dynamic_factory.py` | Runtime agent creation from config |
| **AgentPool** | `pool.py` | Semaphore-based concurrency (max 100) |
| **AgentLifecycleManager** | `agent_lifecycle.py` | FSM with 6 states (CREATED → REGISTERED → ACTIVE → EXECUTING → IDLE → DECOMMISSIONED) |
| **WorkerPoolManager** | `worker_pool.py` | Health checks, scaling, task assignment |
| **HorizontalScalingCoordinator** | `scaling.py` | Multi-instance coordination with distributed locks |
| **ResourceLimitEnforcer** | `resource_limits.py` | Agent/DB/Redis/memory limits |

## Safety & Observability

### Safety Layer

| Component | Location | Features |
|-----------|----------|----------|
| **SafetyGate** | `app/safety/gate.py` | Irreversible tool registry (29 tools), credential pattern blocking |
| **Guardrails** | `app/guardrails/` | Input/output validation, schema enforcement |
| **RBAC** | `app/safety/rbac.py` | 6 roles (planner, executor, verifier, reviewer, coordinator, system) |
| **AuditTrail** | `app/safety/audit.py` | Cryptographic hash chaining, 24 event types, compliance reports |

### Observability

| Component | Location | Purpose |
|-----------|----------|---------|
| **MetricsCollector** | `app/logs/metrics.py` | Prometheus metrics, dashboard summaries |
| **TraceManager** | `app/logs/tracing.py` | Distributed tracing with spans |
| **AnomalyDetector** | `app/logs/anomaly.py` | Statistical anomaly detection (error rate, latency, cost) |
| **AlertManager** | `app/logs/alerts.py` | 4 channels (log, webhook, email, slack) with cooldowns |
| **PerformanceProfiler** | `app/logs/profiler.py` | Step-level latency, bottleneck detection |
| **CostTracker** | `app/logs/cost_tracker.py` | Per-task/agent/tool cost tracking |

## Memory & Persistence

### Dual-Layer Architecture

| Layer | Technology | Purpose |
|-------|------------|---------|
| **Short-term** | Redis | Task contexts, session states, pub/sub, rate limiting |
| **Long-term** | PostgreSQL | Tasks, workflows, agents, traces, checkpoints, audit logs |

### Key Models (27 tables)

| Category | Models |
|----------|--------|
| Task & Workflow | TaskModel, StepModel, WorkflowModel, WorkflowNodeModel, WorkflowEdgeModel, ContextModel |
| Agent & Tool | AgentModel, AgentVersionModel, ToolModel, ToolV2Model, MCPServerModel |
| User & Auth | UserModel, WorkspaceModel, WorkspaceMemberModel, APIKeyModel, UserOnboardingState, UserMemoryProfileModel |
| Observability | TraceModel, NodeTraceModel, SpanModel, TokenUsageModel, MessageModel |
| Safety | GuardrailRuleModel, AuditModel |
| LangGraph | CheckpointModel, CheckpointWriteModel, CheckpointMetadataModel |
| Extended | AgentConfigV2Model, AgentStateTransitionModel, ArtifactModel, TaskQueueEntryModel, ChatSessionModel, ChatMessageModel, KnowledgeSourceModel, KnowledgeChunkModel, DeploymentModel, ConfigModel |

### Memory Managers

| Manager | Location | Purpose |
|---------|----------|---------|
| **PersistentMemoryManager** | `app/memory/persistent.py` | Dual-tier Redis + PostgreSQL with LRU pruning |
| **UserMemoryProfile** | `app/memory/user_profile.py` | Cross-task knowledge with fact deduplication |
| **ArtifactStore** | `app/memory/artifact_store.py` | Filesystem sharding with metadata indexing |
| **MemoryConsistencyLayer** | `app/memory/consistency.py` | 3 consistency levels (eventual, strong, read-through) |

## Frontend

### Technology Stack

- **Framework**: React 19 with TypeScript
- **Build Tool**: Vite 8
- **Styling**: Tailwind CSS 3.4 with pixel-art aesthetic
- **State Management**: Zustand + React Context
- **Animations**: Framer Motion
- **Workflow Builder**: XYFlow/ReactFlow

### Key Pages

| Page | File | Features |
|------|------|----------|
| **Dashboard** | `pages/Dashboard.tsx` | Task execution, metrics, task log sidebar |
| **Agent Builder** | `pages/AgentBuilder.tsx` | Agent templates, configuration, testing |
| **Tools** | `pages/Tools.tsx` | Tool registry V2, testing, OpenAPI import |
| **Chat** | `pages/Chat.tsx` | Session management, streaming messages |
| **Workflow Builder** | `pages/WorkflowBuilder.tsx` | Visual workflow editor with XYFlow |
| **Monitor** | `pages/Monitor.tsx` | Analytics, traces, metrics console |

### Frontend-Backend Integration

- **API Client**: JWT auto-refresh, exponential backoff, rate limit tracking
- **WebSocket**: `/ws/tasks/{id}?token={jwt}` with auto-reconnect
- **Authentication**: Bearer tokens with refresh flow
- **Real-time**: WebSocket events for task status updates

## API Endpoints

### Authentication

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/v1/auth/signup` | Public | User registration |
| POST | `/api/v1/auth/login` | Public | Login with JWT |
| POST | `/api/v1/auth/refresh` | Public | Token refresh |

### Tasks

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/v1/tasks` | Bearer | Create and execute task |
| GET | `/api/v1/tasks` | Bearer | List user tasks |
| GET | `/api/v1/tasks/{id}` | Bearer | Get task status |
| POST | `/api/v1/tasks/{id}/approve` | Bearer | Approve pending task |
| POST | `/api/v1/tasks/{id}/reject` | Bearer | Reject pending task |

### Agents & Tools

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/v1/agents` | Bearer | List agents |
| POST | `/api/v1/agents` | Bearer | Create agent |
| GET | `/api/v1/tools` | Bearer | List tools |
| POST | `/api/v1/tools/{name}/execute` | Bearer | Execute tool |
| GET | `/api/v1/tools/mcp-servers` | Bearer | List MCP servers |

### Observability

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | Public | Health check |
| GET | `/health/ready` | Public | Readiness probe |
| GET | `/health/metrics` | Public | Prometheus metrics |
| GET | `/observability/metrics` | Bearer | System metrics |
| GET | `/observability/traces/{task_id}` | Bearer | Task traces |
| GET | `/observability/anomalies` | Bearer | Anomaly reports |

### WebSocket

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/ws/tasks/{id}` | Query token | Real-time task events |

## Testing

### Test Suite Overview

| Category | Files | Tests | Focus |
|----------|-------|-------|-------|
| **Unit** | 9 | ~100 | Isolated component tests |
| **Integration** | 5 | ~50 | Cross-component validation |
| **Action V1** | 1 | 6 | Fast path benchmarks |
| **Desktop** | 8 | ~80 | Desktop automation |
| **LangGraph** | 4 | ~30 | Graph execution |
| **Safety** | 3 | ~40 | RBAC, guardrails, audit |
| **Stress** | 4 | 5 | Load testing |
| **Benchmarks** | 4 | 5 | Performance benchmarks |
| **Total** | **87** | **413+** | **Comprehensive coverage** |

### Key Test Files

| File | Coverage |
|------|----------|
| `test_action_v1_benchmarks.py` | Fast path validation (6 benchmarks) |
| `test_desktop_env.py` | Desktop session lifecycle (388 lines) |
| `test_desktop_loop.py` | Goal-driven execution (610 lines) |
| `test_langgraph_executor.py` | Node execution (166 lines) |
| `test_execution_stabilizer.py` | Stabilization/retry (518 lines) |
| `test_multi_agent.py` | Coordination (57 tests) |
| `test_phase5_scaling.py` | Scaling components (40 tests) |

### Running Tests

```bash
# Full test suite
pytest -q

# Action V1 benchmarks
pytest tests/test_action_v1_benchmarks.py -v

# Desktop automation
pytest tests/test_desktop_env.py tests/test_desktop_loop.py tests/test_execution_stabilizer.py -v

# Validation suite
python validate_fixes.py
```

## Tech Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| Frontend Framework | React | 19.x |
| Build Tool | Vite | 8.x+ |
| CSS | Tailwind CSS | 3.4+ |
| Backend Framework | FastAPI | 0.121+ |
| ASGI Server | Uvicorn | 0.34+ |
| Validation | Pydantic | 2.12+ |
| Auth | python-jose | 3.3+ |
| Password Hashing | passlib | 1.7+ |
| LLM Client | OpenAI SDK | 1.0+ |
| Orchestration | LangGraph | 1.1+ |
| LangChain | langchain-core | 1.3+ |
| MCP SDK | mcp | 1.0+ |
| Browser Automation | Playwright | 1.51+ |
| Desktop Automation | uiautomation, pyautogui | Latest |
| Database | PostgreSQL | 14+ |
| ORM | SQLAlchemy async | 2.0+ |
| Cache + PubSub | Redis | 7+ |
| Monitoring | Prometheus client | 0.19+ |

## Setup & Installation

### Prerequisites

- Python 3.11+
- Node.js 20+
- PostgreSQL 14+
- Redis 7+
- Playwright Chromium

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

Backend starts on `http://localhost:8000`.

### Frontend

```bash
cd AgentOS/frontend
npm install
npm run dev
```

Frontend starts on `http://localhost:5173`.

### Docker (Full Stack)

```bash
cd docker
docker compose up --build
```

## System Guarantees

1. **LangGraph is the primary execution engine** — orchestrator compiles mode-specific StateGraphs and falls back to legacy pipelines only on exception
2. **Every execution is checkpointed** — LangGraph state persisted to PostgreSQL via `PostgresCheckpointSaver` for resume across restarts
3. **Human-in-the-loop uses LangGraph interrupt** — approval gates pause execution via `interrupt()` and resume via API calls
4. **Runtime is the ONLY execution entry point** — no module may instantiate or call agents directly
5. **MCP tools are auto-discovered** — system servers start automatically and register tools via `MCPWrappedTool`
6. **Tool registration is idempotent** — built-in tools register once via singleton; MCP discovery skips if already registered
7. **Runtime initialization is idempotent** — Redis mutex prevents duplicate core agent registration across processes
8. **Paths are OS-aware** — planner generates OS-appropriate paths; executor remaps hallucinated foreign paths
9. **Authentication uses JWT with refresh tokens** — access tokens expire in 30 minutes; refresh tokens expire in 7 days
10. **WebSocket connections authenticate via query token** — invalid or expired tokens close connection with code 1008
11. **All data is strictly typed** — Pydantic models validate every request/response; no untyped dicts in core flow
12. **Output is validated before persistence** — guardrails validate pipeline output before database insertion
13. **Desktop actions are verified before success** — `verify_plan()` confirms structural and semantic correctness
14. **Desktop tool parameters are safety-checked** — credential patterns blocked by `SafetyGate` before execution
15. **Infinite loops are detected and aborted** — `ActionStabilizer` aborts after 3 identical no-change failures

## Project Structure

```
AgentOS/
├── README.md                          # This file
├── ARCHITECTURE.md                    # Detailed architecture documentation
├── AUDIT_REPORT_LEGACY_SYSTEMS.md     # Legacy system audit
├── validate_fixes.py                  # Priority 1 validation script
├── app/
│   ├── main.py                        # FastAPI application entry
│   ├── config/settings.py             # Pydantic Settings with env validation
│   ├── api/                           # HTTP + WebSocket layer
│   │   ├── deps.py                    # Dependency injection (orchestrator singleton)
│   │   ├── ws.py                      # WebSocket connection manager
│   │   └── routes/                    # 17 API route modules
│   ├── action_v1/                     # Deterministic fast-path execution
│   │   ├── selector.py                # Capability classification
│   │   ├── executor.py                # Direct MCP tool executor
│   │   ├── verifier.py                # Deterministic result verifier
│   │   ├── fallback.py                # Vision & human fallback layers
│   │   └── runner.py                  # Action V1 pipeline orchestrator
│   ├── langgraph/                     # LangGraph execution engine
│   │   ├── state.py                   # AgentState TypedDict (40+ fields)
│   │   ├── nodes.py                   # 5 nodes: planner, executor, verifier, approval, summarizer
│   │   ├── graphs.py                  # 4 graph compilers: task, workflow, autonomous, collaboration
│   │   ├── checkpointer.py            # PostgreSQL checkpoint saver
│   │   └── collaboration.py           # Multi-agent coordination
│   ├── orchestrator/                  # Orchestration layer (25 files, ~7,000 lines)
│   │   ├── core.py                    # Orchestrator singleton with LangGraph integration
│   │   ├── task_runner.py             # Task runner with adaptive routing
│   │   ├── state_machine.py           # Task state FSM with validation
│   │   ├── queue.py                   # Priority queue with Redis backing
│   │   ├── isolation.py               # Failure isolation with circuit breaker
│   │   ├── timeouts.py                # Scoped timeout enforcement
│   │   ├── locks.py                   # Distributed locks
│   │   └── modes/                     # 4 execution mode strategies
│   ├── runtime/                       # Agent runtime (10 files, ~2,300 lines)
│   │   ├── runtime.py                 # AgentRuntime singleton
│   │   ├── worker.py                  # AgentWorker with inbox queue
│   │   ├── factory.py                 # Static agent factory
│   │   ├── dynamic_factory.py         # Dynamic agent creation
│   │   ├── pool.py                    # Semaphore-based concurrency
│   │   ├── agent_lifecycle.py         # Lifecycle FSM with hooks
│   │   ├── worker_pool.py             # Worker pool with health checks
│   │   ├── scaling.py                 # Horizontal scaling coordinator
│   │   └── resource_limits.py         # Resource limit enforcer
│   ├── agents/                        # Agent implementations (14 files, ~4,500 lines)
│   │   ├── base.py                    # BaseAgent protocol
│   │   ├── planner.py                 # PlannerAgent with DAG validation
│   │   ├── executor.py                # ExecutorAgent with tool grounding
│   │   ├── verifier.py                # VerifierAgent with quality scoring
│   │   ├── reviewer.py                # ReviewerAgent with schema validation
│   │   ├── coordinator.py             # CoordinatorAgent for multi-agent
│   │   ├── handoff.py                 # InterAgentHandoff with signatures
│   │   ├── feedback.py                # AgentFeedbackLoop with learning
│   │   ├── consensus.py               # ConsensusEngine for agreement
│   │   ├── router.py                  # AgentRouter with complexity scoring
│   │   ├── llm_router.py              # LLMRouter for multi-provider
│   │   └── llm_client.py              # OpenAI async client
│   ├── mcp/                           # MCP layer (7 servers)
│   │   ├── client_manager.py          # MCPClientManager singleton
│   │   └── servers/                   # 7 stdio MCP servers
│   │       ├── filesystem.py          # File operations
│   │       ├── shell.py               # Command execution
│   │       ├── cloud_api.py           # HTTP/search
│   │       ├── browser.py             # Playwright automation
│   │       ├── desktop.py             # Windows UI automation
│   │       ├── document.py            # Document parsing
│   │       └── code.py                # Python execution
│   ├── tools/                         # Tool infrastructure (9 files, ~3,800 lines)
│   │   ├── registry.py                # ToolRegistry singleton
│   │   ├── sandbox.py                 # AST-based code validation
│   │   ├── grounding.py               # Capability-based tool filtering
│   │   ├── validation.py              # 4-stage validation pipeline
│   │   ├── permissions.py             # RBAC tool permissions
│   │   ├── failure_classifier.py      # Failure categorization
│   │   ├── cache.py                   # Two-tier caching
│   │   └── cost_tracker.py            # Per-tool cost tracking
│   ├── environments/                  # Execution environments
│   │   ├── desktop_env.py             # DesktopSession with UIA
│   │   ├── execution_stabilizer.py    # ActionStabilizer with retry
│   │   ├── vision_fallback.py         # HybridVisionParser with DPI scaling
│   │   └── window_registry.py         # Window tracking
│   ├── capabilities/                  # Recovery and verification
│   │   ├── recovery.py                # RecoveryEngine with strategies
│   │   └── verification.py            # VerificationEngine
│   ├── safety/                        # Safety layer
│   │   ├── gate.py                    # SafetyGate with credential blocking
│   │   ├── rbac.py                    # Role-based access control
│   │   └── audit.py                   # Audit trail with hash chaining
│   ├── guardrails/                    # Input/output validation
│   │   ├── validator.py               # Input/output validators
│   │   └── schema.py                  # Validation schemas
│   ├── logs/                          # Observability (8 files, ~1,500 lines)
│   │   ├── logger.py                  # Structured JSON logging
│   │   ├── metrics.py                 # Prometheus metrics
│   │   ├── tracing.py                 # Distributed tracing
│   │   ├── anomaly.py                 # Anomaly detection
│   │   ├── alerts.py                  # Alert management
│   │   ├── profiler.py                # Performance profiling
│   │   └── cost_tracker.py            # Cost tracking
│   ├── memory/                        # Persistence (13 files, ~3,150 lines)
│   │   ├── models.py                  # 27 SQLAlchemy models
│   │   ├── long_term.py               # PostgreSQL repositories
│   │   ├── short_term.py              # Redis client
│   │   ├── persistent.py              # PersistentMemoryManager
│   │   ├── user_profile.py            # UserMemoryProfile
│   │   ├── artifact_store.py          # ArtifactStore
│   │   └── consistency.py             # MemoryConsistencyLayer
│   └── middleware/                    # Auth middleware, rate limiting
├── frontend/                          # React frontend
│   ├── src/
│   │   ├── api/client.ts              # API client with auto-refresh
│   │   ├── context/AuthContext.tsx    # JWT authentication
│   │   ├── hooks/useWebSocket.ts      # WebSocket with reconnect
│   │   ├── pages/                     # 16 pages
│   │   └── components/                # Shared components
│   └── package.json
├── tests/                             # Test suite (87 files, 413+ tests)
│   ├── conftest.py                    # Shared fixtures
│   ├── test_action_v1_benchmarks.py   # Action V1 validation
│   ├── unit/                          # Unit tests
│   ├── integration/                   # Integration tests
│   ├── stress/                        # Load tests
│   └── benchmarks/                    # Performance benchmarks
├── docker/                            # Docker Compose
└── requirements.txt                   # Python dependencies
```

## Production Checklist

- [ ] Set `DATABASE_URL` with connection pooling (pool_size=20, max_overflow=40)
- [ ] Set `REDIS_URL` for MCP pub/sub and caching
- [ ] Set `SECRET_KEY` to persistent 32+ byte secret
- [ ] Configure `MAX_RETRIES`, `TIMEOUT_DEFAULT`, `MAX_STEPS_DEFAULT`
- [ ] Set `OPENAI_API_KEY` and `OPENAI_MODEL`
- [ ] Enable `RedisMCPBus` for multi-instance deployments
- [ ] Monitor `/health/ready` for load balancer health checks
- [ ] Scrape `/health/metrics` with Prometheus
- [ ] Review audit trail retention policies
- [ ] Configure alert channels (webhook, email, slack)
- [ ] Enable anomaly detection thresholds

## Contributing

1. Follow the existing test-first approach: write a failing test, implement the fix, verify the test passes
2. Ensure all tests pass: `pytest -q`
3. Run the validation suite: `python validate_fixes.py`
4. Update documentation if architecture changes
5. Keep commits focused and descriptive

## License

[Add license information here]
