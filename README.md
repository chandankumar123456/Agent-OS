# Agent-OS Technical Documentation

Agent-OS is a multi-agent execution platform built around FastAPI, Celery, PostgreSQL, Redis, and a React control plane.

## 1. Purpose and Scope

Agent-OS provides:
- authenticated task submission and retrieval APIs,
- planner/executor/verifier agent orchestration,
- persisted workflow DAG execution state,
- runtime tool registry and custom tool execution,
- observability (metrics, traces, node-level execution records).

Primary implementation roots:
- `/home/runner/work/Agent-OS/Agent-OS/app`
- `/home/runner/work/Agent-OS/Agent-OS/frontend`

## 2. High-Level Architecture

### 2.1 Logical Layers
- **API Layer**: FastAPI app, route handlers, auth dependencies (`app/main.py`, `app/api/*`).
- **Orchestration Layer**: mode dispatch + pipeline execution (`app/orchestrator/*`).
- **Runtime Layer**: singleton agent runtime/worker lifecycle (`app/runtime/*`).
- **Agent Layer**: planner, executor, verifier (`app/agents/*`).
- **Tool Layer**: built-in tools + dynamic tools + sandbox (`app/tools/*`).
- **Persistence Layer**: SQLAlchemy repositories and models (`app/memory/*`).
- **Queue Layer**: Celery worker task (`app/queue/tasks.py`).
- **MCP Layer**: protocol/bus/router for inter-agent messaging (`app/mcp/*`).
- **Observability/Guardrails**: tracing, metrics, validation (`app/logs/*`, `app/guardrails/*`).
- **UI Layer**: React dashboard and admin pages (`frontend/src/*`).

### 2.2 Runtime Dependency Graph
- FastAPI startup requires `DATABASE_URL`, `REDIS_URL`, `OPENAI_API_KEY`.
- Startup sequence: DB connect -> migration runner -> Redis connect -> AgentRuntime initialize.
- Core runtime agents: `core_planner`, `core_executor`, `core_verifier`.

## 3. Backend Execution Model

### 3.1 Task Lifecycle
1. Client calls `POST /api/v1/tasks`.
2. Task row persisted (`tasks` table).
3. Work dispatched to Celery (`USE_CELERY=true`) or background task fallback.
4. Orchestrator executes mode strategy (`task|workflow|autonomous|collaboration`).
5. Planner returns steps; workflow DAG persisted (workflow + nodes + edges).
6. DAG executed with dependency and condition checks.
7. Verifier validates final output.
8. Task, trace, spans, and node traces persisted.

### 3.2 Mode Strategies
- `task`: plan -> execute -> verify pipeline.
- `workflow`: workflow semantics + optional predefined workflow name lookup.
- `autonomous`: iterative plan/execute loop with completion checks.
- `collaboration`: agent-type distribution + MCP message dispatch.

### 3.3 Workflow DAG Semantics
- Graph validation rejects missing dependencies and cycles.
- Deterministic condition expressions only (no lambda).
- Skipped dependencies are treated as terminal-satisfied for downstream nodes.
- Node status transitions persisted in `workflow_nodes` and `node_traces`.

## 4. API Contract Summary

Base API: `/api/v1`

- **Auth**: `POST /auth/signup`, `POST /auth/login`
- **Tasks**: `POST /tasks`, `GET /tasks`, `GET /tasks/{task_id}`, `DELETE /tasks/{task_id}`, `GET /tasks/{task_id}/trace`
- **Tools**: `GET /tools`, `GET /tools/{tool_name}`, `POST /tools`, `POST /tools/{tool_name}/execute`
- **Agents**: `GET /agents`, `GET /agents/{agent_id}`, `POST /agents`, `PUT /agents/{agent_id}`, `DELETE /agents/{agent_id}`
- **Config**: `GET /config`, `GET /config/{key}`, `POST /config`, `POST /config/reset`

Health/ops:
- `/health` (root)
- `/health`, `/health/ready`, `/health/live`, `/health/metrics`

## 5. Data Model and Persistence

Tables implemented in `app/memory/models.py` and SQL migrations:
- Core tasking: `tasks`, `steps`, `workflows`, `workflow_nodes`, `workflow_edges`
- Messaging/context: `context`, `messages`
- Observability: `traces`, `node_traces`, `spans`
- Control planes: `tools`, `agents`, `config`, `users`

Repositories in `app/memory/long_term.py` provide async CRUD/upsert access.

## 6. Security Model

- JWT bearer auth enforced by dependency and middleware.
- Signup/login endpoints exempt from bearer requirement.
- Admin role required for config writes, tool registration, and agent mutations.
- Rate limiting middleware uses Redis sorted sets by user/IP.
- Password hashing uses bcrypt with SHA-256 preprocessing for >72-byte input.

## 7. Configuration

Primary settings source: `app/config/settings.py`

Required:
- `DATABASE_URL`
- `REDIS_URL`
- `OPENAI_API_KEY`

Key runtime parameters:
- `OPENAI_MODEL`, `USE_CELERY`, `MAX_STEPS_DEFAULT`, `TIMEOUT_DEFAULT`, `MAX_RETRIES`
- `RATE_LIMIT_PER_MINUTE`, `MAX_ACTIVE_TASKS_PER_USER`, `MAX_TASK_EXECUTION_ATTEMPTS`
- `SECRET_KEY`, `ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`

## 8. Observability

- Structured app logger (`app/logs/logger.py`)
- In-memory Prometheus text metrics collector (`app/logs/metrics.py`)
- Span/trace persistence manager (`app/logs/tracing.py`)
- Task trace endpoint aggregates workflow state + node traces + spans.

## 9. Frontend Technical Overview

- React Router protected routes with auth context token lifecycle handling.
- API client centralizes typed fetch calls and auth-expiry event propagation.
- Main pages: Dashboard, Agent Builder, Tool Registry, Orchestrator, Monitor, Settings.
- Build/test/lint stack: Vite + TypeScript + Vitest + ESLint.

## 10. Local Development and Operations

### 10.1 Backend
- `pytest -q`

### 10.2 Frontend
- `npm run dev`
- `npm run lint`
- `npm run test`
- `npm run build`
- `npm run preview`

### 10.3 Docker Stack
`docker/docker-compose.yml` provisions:
- PostgreSQL 16
- Redis 7
- API container
- Celery worker container

## 11. Repository Documentation Map

Every directory now contains a technical `README.md` documenting module purpose, interfaces, and operational notes.
