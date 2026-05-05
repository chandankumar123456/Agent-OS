# AgentOS — Architecture

## Overview

AgentOS is a structured, stateful agent execution system where AI agents reason via LangGraph state machines and act on the system via the Model Context Protocol (MCP). It is **not a chatbot** — every execution is traceable, checkpointed, and observable. The system executes desktop automation tasks through a closed-loop model: observe → decide → act → verify → recover.

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Frontend | React 19, Vite 8, Tailwind CSS 3.4, TypeScript | UI |
| Backend | Python 3.11+, FastAPI 0.121+, Uvicorn | REST API |
| Orchestration | LangGraph 1.1+, LangChain | StateGraph execution |
| LLM | OpenAI SDK (gpt-4o default) | Agent reasoning |
| Validation | Pydantic 2.12+ | Request/response schemas |
| Auth | python-jose (JWT), passlib (bcrypt) | Authentication |
| Desktop | uiautomation, pyautogui, pyperclip, mss, OpenCV | UI automation |
| Browser | Playwright 1.51+ | Browser automation |
| MCP | mcp SDK 1.0+ | Model Context Protocol |
| DB | PostgreSQL 14+ (SQLAlchemy async 2.0+) | Persistence |
| Cache | Redis 7+ | Short-term memory, pub/sub |
| Queue | Celery 5.3+ | Background tasks |
| Monitoring | Prometheus client | Metrics |

## Directory Structure

```
AgentOS/
├── app/                          # Backend (Python/FastAPI)
│   ├── main.py                   # FastAPI app entry, lifespan, middleware
│   ├── config/settings.py       # Pydantic Settings (env validation)
│   ├── api/                      # HTTP + WebSocket layer
│   │   ├── deps.py               # Dependency injection (singletons)
│   │   ├── ws.py                 # WebSocket connection manager
│   │   └── routes/               # auth, agents, tasks, tools, config, health
│   ├── action_v1/                # Deterministic fast-path (bypasses LangGraph)
│   │   ├── selector.py           # Capability classification
│   │   ├── executor.py           # Direct MCP tool execution
│   │   ├── verifier.py           # Deterministic verification
│   │   ├── fallback.py           # Vision/human fallback
│   │   └── runner.py             # Action V1 pipeline orchestrator
│   ├── langgraph/                # LangGraph execution engine (primary)
│   │   ├── state.py              # AgentState TypedDict
│   │   ├── nodes.py              # planner, executor, verifier, approval, summarizer
│   │   ├── graphs.py             # Graph compilers per mode (LRU cache)
│   │   └── checkpointer.py      # PostgreSQL checkpoint saver
│   ├── orchestrator/             # Mode selection, LangGraph compilation, fallback
│   │   ├── core.py               # Orchestrator singleton
│   │   ├── task_runner.py        # Task runner with recovery + perception
│   │   ├── pipeline.py           # Legacy plan→execute→verify pipeline
│   │   └── modes/                # Mode strategy implementations
│   ├── desktop/                  # Desktop automation core
│   │   └── goal_loop.py          # DesktopGoalLoop (observe-decide-act-verify)
│   ├── agents/                   # Agent implementations
│   │   ├── base.py               # BaseAgent, AgentInput, AgentOutput
│   │   ├── planner.py            # PlannerAgent
│   │   ├── executor.py            # ExecutorAgent (tool loop + path remapping)
│   │   ├── verifier.py           # VerifierAgent
│   │   └── llm_client.py         # OpenAI async client
│   ├── runtime/                  # Agent lifecycle management
│   │   ├── runtime.py            # AgentRuntime singleton (Redis mutex init)
│   │   ├── worker.py             # AgentWorker (inbox queue)
│   │   ├── factory.py            # AgentFactory
│   │   └── pool.py                # AgentPool (semaphore, max 100)
│   ├── environments/             # Execution environments
│   │   ├── desktop_env.py        # DesktopSession (UIA, vision, stabilizer)
│   │   ├── execution_stabilizer.py # ActionStabilizer + StabilizerConfig
│   │   ├── vision_fallback.py    # HybridVisionParser (DPI-aware)
│   │   └── window_registry.py   # WindowRegistry
│   ├── capabilities/             # Recovery + verification engines
│   │   ├── recovery.py           # RecoveryEngine + RecoveryStrategy enum
│   │   └── verification.py       # VerificationEngine
│   ├── safety/gate.py            # SafetyGate (credential regex blocking)
│   ├── mcp/                       # Model Context Protocol layer
│   │   ├── client_manager.py     # MCPClientManager (server lifecycle)
│   │   ├── servers/              # filesystem, shell, browser, cloud_api, desktop, document, code
│   │   ├── bus.py                # MCPBus (Memory + Redis)
│   │   ├── router.py             # MessageRouter
│   │   └── protocol.py           # MCPProtocol
│   ├── tools/                     # Tool registry + built-in tools
│   │   ├── registry.py            # ToolRegistry singleton
│   │   ├── sandbox.py             # ToolSandbox (AST validation)
│   │   ├── grounding.py           # ToolGroundingLayer
│   │   └── base.py                # BaseTool, ToolInput, ToolOutput
│   ├── guardrails/                # Input/output validation
│   ├── logs/                      # Structured logging, tracing, metrics
│   ├── memory/                    # PostgreSQL + Redis persistence
│   └── middleware/               # Auth middleware, rate limiting
├── frontend/                      # Frontend (React/TypeScript/Vite)
│   └── src/
│       ├── api/client.ts          # API client with auto-refresh
│       ├── context/AuthContext.tsx # Auth state management
│       ├── hooks/useWebSocket.ts  # WebSocket hook with reconnect
│       ├── pages/                 # Dashboard, Builder, Tools, Chat, etc.
│       └── components/            # Layout, Toast, Onboarding, UI primitives
├── tests/                         # Test suite (pytest)
│   ├── conftest.py                # Shared fixtures
│   ├── unit/                      # Unit tests
│   ├── integration/               # Integration tests
│   ├── stress/                    # Stress tests
│   └── benchmarks/                # Benchmark tests
├── docker/                         # Docker Compose
│   ├── Dockerfile
│   └── docker-compose.yml
├── scripts/                        # Utility scripts
├── migrations/                      # Database migrations
└── requirements.txt                 # Python dependencies
```

## 8-Layer Architecture

```
┌─────────────────────────────────────────────────────────┐
│ Layer 1 — Frontend (React 19 + Vite + Tailwind CSS)    │
├─────────────────────────────────────────────────────────┤
│ Layer 2 — API Gateway (FastAPI + JWT + Rate Limiting)   │
├─────────────────────────────────────────────────────────┤
│ Layer 3 — Orchestration (Orchestrator + ModeStrategy)   │
├─────────────────────────────────────────────────────────┤
│ Layer 4 — LangGraph Engine (plan→exec→verify→summarize) │
├─────────────────────────────────────────────────────────┤
│ Layer 5 — Agent Runtime (Singleton + Pool + Factory)    │
├─────────────────────────────────────────────────────────┤
│ Layer 6 — MCP + Tools (7 MCP servers + ToolRegistry)   │
├─────────────────────────────────────────────────────────┤
│ Layer 7 — Safety + Observability (Guardrails + Metrics) │
├─────────────────────────────────────────────────────────┤
│ Layer 8 — Persistence (PostgreSQL + Redis + Checkpoint) │
└─────────────────────────────────────────────────────────┘
```

## Core Components

### Orchestration Flow

Two execution paths exist:

1. **Action V1 Fast Path** — For simple, deterministic tasks (browser, desktop, filesystem). Bypasses LangGraph entirely: `CapabilitySelector` → `DeterministicExecutor` → `DeterministicVerifier` → result.

2. **LangGraph Full Path** — For complex/ambiguous tasks. StateGraph: `planner_node` → `executor_node` → `verifier_node` → `approval_node` (interrupt) → `summarizer_node`. Autonomous mode adds a `replanner_node`.

### Key Singletons

| Singleton | Location | Purpose |
|-----------|----------|---------|
| `AgentRuntime` | `app/runtime/runtime.py` | Agent lifecycle, Redis mutex init |
| `MCPClientManager` | `app/mcp/client_manager.py` | MCP server lifecycle |
| `ToolRegistry` | `app/tools/registry.py` | Built-in + MCP tool registration |
| `Orchestrator` | `app/orchestrator/core.py` | Mode selection, LangGraph compilation |

### AgentState (TypedDict)

Central state dict flowing through LangGraph nodes. Key fields: `task_id`, `query`, `config`, `messages` (add_messages reducer), `plan`, `steps`, `tool_calls`, `verified`, `approved`, `result`, `error`, `execution_state`. Written by different nodes, reduced via `add_messages` and `merge_dicts`.

### Desktop Automation Pipeline

`DesktopGoalLoop` encapsulates observe-decide-act-verify:
- **Observe**: Screenshot + UIA tree + window list
- **Decide**: LLM selects grounded tool action
- **Act**: `ActionStabilizer` with retry + popup detection
- **Verify**: `verify_plan()` checks structural + semantic correctness
- **Recover**: `RecoveryEngine` selects strategy (re-focus, rebuild, vision escalate, dismiss popup)

### MCP Tool Naming

All MCP tools follow `{server_name}__{tool_name}` convention. Examples: `filesystem__read_file`, `shell__execute_command`, `browser_env__launch`.

## Data Flow

```
User → Frontend → FastAPI → Orchestrator
                              ├── Action V1 (simple tasks)
                              │     → CapabilitySelector → DeterministicExecutor → DeterministicVerifier
                              └── LangGraph (complex tasks)
                                    → planner_node → executor_node → verifier_node
                                    → approval_node (interrupt) → summarizer_node
                                    → DesktopGoalLoop (desktop tasks)
                                          → ToolRegistry → MCPClientManager → MCP Servers
                                          → ActionStabilizer → SafetyGate → RecoveryEngine
```

## External Integrations

| Service | Purpose | Config |
|---------|---------|--------|
| PostgreSQL | Long-term state, checkpoints, user data | `DATABASE_URL` |
| Redis | Short-term cache, pub/sub event bus, MCP bus | `REDIS_URL` |
| OpenAI | LLM completions for agent reasoning | `OPENAI_API_KEY`, `OPENAI_MODEL` |
| Playwright | Browser automation | Installed via `playwright install chromium` |

## Configuration

All settings in `app/config/settings.py` (Pydantic BaseSettings). Required env vars:
- `DATABASE_URL` — PostgreSQL connection string
- `REDIS_URL` — Redis connection string
- `OPENAI_API_KEY` — OpenAI API key
- `SECRET_KEY` — JWT signing key (32+ bytes)

Key settings: `MAX_STEPS_DEFAULT` (1-100), `TIMEOUT_DEFAULT` (1-3600s), `MAX_RETRIES` (0-10), `CORS_ORIGINS`, `ACCESS_TOKEN_EXPIRE_MINUTES` (default 30).

## Build & Deploy

```bash
# Backend
pip install -r requirements.txt
playwright install chromium
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Frontend
cd frontend && npm install && npm run dev

# Docker
cd docker && docker compose up --build

# Tests
pytest -q                                    # Full suite
pytest tests/test_action_v1_benchmarks.py -v # Action V1 benchmarks
python validate_fixes.py                     # Validation suite
```

## API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/v1/auth/signup` | Public | Register |
| POST | `/api/v1/auth/login` | Public | Login |
| POST | `/api/v1/auth/refresh` | Public | Refresh token |
| POST | `/api/v1/tasks` | Bearer | Create task |
| GET | `/api/v1/tasks/{id}` | Bearer | Get task |
| POST | `/api/v1/tasks/{id}/approve` | Bearer | Approve task |
| POST | `/api/v1/tasks/{id}/reject` | Bearer | Reject task |
| GET | `/api/v1/agents` | Bearer | List agents |
| GET | `/api/v1/tools` | Bearer | List tools |
| GET | `/ws/tasks/{id}` | Query token | WebSocket events |
| GET | `/health` | Public | Health check |
| GET | `/health/ready` | Public | Readiness probe |
| GET | `/health/metrics` | Public | Prometheus metrics |