# Agent-OS Technical Documentation

Agent-OS is a FastAPI + Celery + PostgreSQL/Redis multi-agent runtime that executes user tasks through planner/executor/verifier agents, persists workflow DAG state, and exposes operational APIs consumed by a React frontend.

## System Architecture

- **API Layer (`app/main.py`, `app/api/`)**: FastAPI app, middleware, auth, route handlers.
- **Orchestration Layer (`app/orchestrator/`)**: mode selection (`task`, `workflow`, `autonomous`, `collaboration`), plan→execute→verify pipeline, workflow DAG engine.
- **Runtime Layer (`app/runtime/`)**: singleton `AgentRuntime`, worker lifecycle, factory + pool.
- **Agent Layer (`app/agents/`)**: planner/executor/verifier implementations over OpenAI chat completions.
- **Tool Layer (`app/tools/`)**: built-in tools, dynamic custom tools, parser, sandbox.
- **Persistence Layer (`app/memory/`)**: SQLAlchemy models + repositories (tasks, workflows, traces, tools, agents, config, users) and Redis short-term context cache.
- **Queue Layer (`app/queue/tasks.py`)**: Celery task execution with retries.
- **Communication Layer (`app/mcp/`)**: in-memory/redis message bus and message router.
- **Guardrails & Observability (`app/guardrails/`, `app/logs/`)**: validation, logging, tracing spans, metrics.
- **Frontend (`frontend/`)**: React + Vite admin UI for tasks, tools, agents, config, monitoring.

## Runtime Flow

1. `POST /api/v1/tasks` creates a task row and enqueues Celery (or background execution).
2. Orchestrator picks execution mode and runs planner/executor/verifier.
3. Planner returns steps; `WorkflowBuilder` persists workflow/nodes/edges.
4. `WorkflowEngine` validates and executes DAG (dependency + condition aware).
5. Step execution updates workflow nodes + node traces + spans.
6. Final task result and trace state are persisted and exposed by API.

## API Surface

Base path: `/api/v1`

- `POST /auth/signup`, `POST /auth/login`
- `POST /tasks`, `GET /tasks`, `GET /tasks/{task_id}`, `DELETE /tasks/{task_id}`, `GET /tasks/{task_id}/trace`
- `GET /tools`, `GET /tools/{tool_name}`, `POST /tools`, `POST /tools/{tool_name}/execute`
- `GET /agents`, `GET /agents/{agent_id}`, `POST /agents`, `PUT /agents/{agent_id}`, `DELETE /agents/{agent_id}`
- `GET /config`, `GET /config/{key}`, `POST /config`, `POST /config/reset`

Health/ops endpoints:

- `/health` (root app)
- `/health`, `/health/ready`, `/health/live`, `/health/metrics` (health router)

## Data Model Summary

Core tables from `app/memory/models.py` and `migrations/*.sql`:

- Task execution: `tasks`, `workflows`, `workflow_nodes`, `workflow_edges`, `steps`
- Context/messaging: `context`, `messages`
- Observability: `traces`, `node_traces`, `spans`
- Control planes: `tools`, `agents`, `config`, `users`

## Configuration

Primary settings (`app/config/settings.py`):

- Required: `DATABASE_URL`, `REDIS_URL`, `OPENAI_API_KEY`
- Model/runtime: `OPENAI_MODEL`, `MAX_STEPS_DEFAULT`, `TIMEOUT_DEFAULT`, `MAX_RETRIES`, `USE_CELERY`
- Security: `SECRET_KEY`, `ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `API_KEYS`
- Rate/limits: `RATE_LIMIT_PER_MINUTE`, `MAX_ACTIVE_TASKS_PER_USER`, `MAX_TASK_EXECUTION_ATTEMPTS`

## Build/Test/Lint Commands

Backend (Python environment required):

- `pytest -q`

Frontend (`frontend/`):

- `npm run lint`
- `npm run test`
- `npm run build`

## Deployment/Local Infrastructure

`docker/docker-compose.yml` provisions:

- PostgreSQL 16
- Redis 7
- FastAPI API container
- Celery worker container

## Repository Directory Docs

Each directory now includes its own `README.md` with module-level technical details.
