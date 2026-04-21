# Agent-OS

MCP-based multi-agent operating system for structured AI workflow execution.

## 1) Project purpose

Agent-OS is designed as a layered runtime for AI agents, not a single-model chatbot.

Core goals:
- Centralized orchestration (orchestrator controls flow end-to-end)
- Structured communication (MCP message contract)
- Composable agents (planner, executor, verifier)
- Recoverable failures (retry/fallback patterns)
- Observable execution (logs + traces)

This README is implementation-accurate for the code currently in this repository and aligned with the design documents in `Details/`.

## 2) Architecture

Locked logical architecture (from `Details/Implementation_Plan.md`):

```text
User -> API Layer -> Orchestrator -> Agent Layer -> Tool Layer
                          |
                       MCP Layer
                          |
                  Memory + State Layer
                          |
                   Observability Layer
                          |
                  Queue / Execution Layer
```

Current runtime flow in code:

```text
Client -> FastAPI (/api/v1/tasks)
       -> in-process background task
       -> Orchestrator
       -> Planner -> Executor (loop) -> Verifier
       -> result returned via GET /api/v1/tasks/{task_id}
```

## 3) Repository structure

```text
AgentOS/
  app/
    main.py
    api/
      deps.py
      routes/
        tasks.py
    orchestrator/
      core.py
      workflow.py
      retry.py
      fallback.py
      errors.py
    agents/
      base.py
      llm_client.py
      planner.py
      executor.py
      verifier.py
      dummy_agent.py
      types.py
    mcp/
      message.py
      protocol.py
    memory/
      models.py
      long_term.py
      short_term.py
    guardrails/
      schema.py
      validator.py
    tools/
      base.py
      search.py
      registry.py
    logs/
      logger.py
      tracing.py
    queue/
      tasks.py
  docker/
    Dockerfile
    docker-compose.yml
  frontend/
    src/api/client.ts
  Details/
    Complete_Project_Documentation.md
    Core_Design_Specification.md
    Implementation_Plan.md
    Ultra-detailed-implementation-plan.md
  requirements.txt
```

## 4) Core module documentation

### 4.1 API Layer (`app/api`)

Entry points:
- `POST /api/v1/tasks` creates an async task and returns `task_id`
- `GET /api/v1/tasks/{task_id}` returns current task state
- `GET /api/v1/tasks` lists all in-memory tasks
- `DELETE /api/v1/tasks/{task_id}` deletes in-memory task metadata
- `GET /health` returns service health/version

Implementation notes:
- Task registry is currently in-memory (`TASKS` dict in `app/api/routes/tasks.py`).
- Execution is triggered via FastAPI `BackgroundTasks`.

### 4.2 Orchestrator (`app/orchestrator`)

Main class: `Orchestrator` in `app/orchestrator/core.py`.

Responsibilities:
- Create per-task context (`TaskContext`)
- Call planner to produce steps
- Execute each step through executor
- Verify combined output through verifier
- Return normalized `AgentOutput`

Related utilities:
- Retry utility: `app/orchestrator/retry.py`
- Fallback manager: `app/orchestrator/fallback.py`
- Error taxonomy: `app/orchestrator/errors.py`

### 4.3 Agent runtime (`app/agents`)

Contract defined in `app/agents/base.py`:
- Input model: `AgentInput`
- Output model: `AgentOutput`
- Roles: `planner`, `executor`, `verifier`, `researcher`

Concrete agents:
- `PlannerAgent` (`app/agents/planner.py`)
- `ExecutorAgent` (`app/agents/executor.py`)
- `VerifierAgent` (`app/agents/verifier.py`)

LLM adapter:
- `LLMClient` in `app/agents/llm_client.py`
- Uses OpenAI `AsyncOpenAI`
- Falls back to mock behavior when `OPENAI_API_KEY` is missing/placeholder

### 4.4 MCP layer (`app/mcp`)

Message schema:
- `MCPMessage` with `message_id`, `task_id`, `step_id`, `sender_agent`, `receiver_agent`, `timestamp`, `payload`, `metadata`
- `payload` includes `input_data`, `output_data`, `context_snapshot`
- `metadata` includes `status`, `priority`, `retry_count`, `execution_time`

Protocol helper:
- `MCPProtocol` in `app/mcp/protocol.py`
- Supports message creation, router registration, routing, and message history

### 4.5 Memory and state (`app/memory`)

Long-term (PostgreSQL):
- SQLAlchemy models in `app/memory/models.py`
  - `tasks`
  - `steps`
  - `context`
  - `messages`
- DB/session/repositories in `app/memory/long_term.py`

Short-term (Redis):
- Redis client + context helpers in `app/memory/short_term.py`
- Context key format: `agentos:context:{task_id}`

Lifecycle hookup:
- `app/main.py` connects/disconnects DB and Redis in app lifespan hooks

### 4.6 Guardrails (`app/guardrails`)

Validation models/rules:
- `ValidationResult`, `GuardrailSchema` in `app/guardrails/schema.py`

Validator entry points:
- `OutputValidator` and `Guardrails` in `app/guardrails/validator.py`

### 4.7 Tool layer (`app/tools`)

Tool contract:
- `ToolInput`, `ToolOutput`, `BaseTool` in `app/tools/base.py`

Registry:
- `ToolRegistry` in `app/tools/registry.py`

Default tools:
- `web_search`
- `calculator`
- `text_processor`

### 4.8 Observability (`app/logs`)

Logging:
- Structured logger wrapper in `app/logs/logger.py`

Tracing:
- Span/trace manager in `app/logs/tracing.py`

### 4.9 Queue and async workers (`app/queue`)

Celery app:
- `app/queue/tasks.py`
- Redis broker/backend
- Worker task `agent_os.execute_task`

Note:
- API route execution is currently in-process via FastAPI background tasks.
- Celery worker path exists and is containerized, but API routes are not yet wired to enqueue Celery tasks directly.

## 5) API specification

Base URL: `http://localhost:8000/api/v1`

### POST `/tasks`

Creates a task and starts background execution.

Request:

```json
{
  "query": "Find cheapest healthy breakfast ingredients",
  "config": {
    "max_steps": 10,
    "timeout": 300
  }
}
```

Response:

```json
{
  "task_id": "0f2d6b31-52fa-47f2-a31e-c41b0a31cdd1",
  "status": "pending",
  "created_at": "2026-04-20T10:10:10.100000"
}
```

### GET `/tasks/{task_id}`

Returns current state and output (if completed).

Response shape:

```json
{
  "task_id": "uuid",
  "status": "pending|running|completed|failed",
  "result": {},
  "steps": [],
  "error": {},
  "created_at": "datetime"
}
```

### GET `/tasks`

Returns all in-memory task records.

### DELETE `/tasks/{task_id}`

Deletes task from in-memory registry.

### GET `/health`

Health check endpoint:

```json
{
  "status": "healthy",
  "version": "0.1.0"
}
```

## 6) Execution lifecycle

Task status lifecycle:

```text
pending -> running -> completed
                 \-> failed
```

Orchestrator lifecycle:
1. Build `TaskContext`
2. Planner generates step list
3. Executor runs each step sequentially
4. Verifier validates aggregate output
5. Final `AgentOutput` is returned to API layer

## 7) Contracts

### 7.1 Agent input contract

Defined in `app/agents/base.py`:

```json
{
  "task_id": "uuid",
  "step_id": "uuid",
  "role": "planner|executor|verifier|researcher",
  "input_data": {},
  "context": {},
  "constraints": {}
}
```

### 7.2 Agent output contract

```json
{
  "task_id": "uuid",
  "step_id": "uuid",
  "status": "pending|running|success|failure",
  "output_data": {},
  "confidence": 0.0,
  "reasoning_trace": [],
  "error_type": "string|null",
  "error_message": "string|null",
  "recoverable": true
}
```

### 7.3 MCP contract

Defined in `app/mcp/message.py`:

```json
{
  "message_id": "uuid",
  "task_id": "uuid",
  "step_id": "uuid",
  "sender_agent": "orchestrator",
  "receiver_agent": "planner",
  "timestamp": "datetime",
  "payload": {
    "input_data": {},
    "output_data": {},
    "context_snapshot": {}
  },
  "metadata": {
    "status": "pending|sent",
    "priority": 0,
    "retry_count": 0,
    "execution_time": null
  }
}
```

## 8) Configuration

Primary configuration file: `.env`

Important variables:
- `OPENAI_API_KEY` - OpenAI key used by agent LLM client
- `OPENAI_MODEL` - model name used by OpenAI client
- `DATABASE_URL` - async SQLAlchemy DSN
- `REDIS_URL` - Redis DSN for cache/queue
- `MAX_STEPS_DEFAULT`, `TIMEOUT_DEFAULT`, `MAX_RETRIES`

Configuration model is defined in `app/config/settings.py`.

## 9) Running the system

### Option A: Full containerized stack (recommended)

```bash
cd docker
docker compose up --build
```

Services started by `docker/docker-compose.yml`:
- `postgres`
- `redis`
- `api`
- `worker`

### Option B: Local backend only

```bash
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend

Frontend API client is in `frontend/src/api/client.ts` and defaults to:
- `VITE_API_URL` env var if provided
- fallback: `http://localhost:8000/api/v1`

## 10) Security and production hardening

Current code includes scaffolding for production hardening but does not yet implement full auth/rate-limit/monitoring policy.

Planned/expected additions (per `Details/Implementation_Plan.md` phase 10):
- API authentication/authorization
- Rate limiting
- Metrics stack (Prometheus/Grafana)
- Hardened secret management

## 11) Known limitations (current code state)

- API task state is currently in-memory (`TASKS` dict) and not persisted by API routes.
- DB and Redis clients are connected at startup, but orchestration persistence wiring is partial.
- Celery worker exists and runs in Docker, but `/tasks` currently uses FastAPI background tasks instead of queue submission.
- OpenAI model defaults in code/config may differ from desired deployment model; set `OPENAI_MODEL` explicitly in `.env`.
- `app/guardrails/validator.py` currently contains a syntax issue in `validate_context` and should be fixed before strict runtime use.

## 12) Phase compliance matrix

Alignment against `Details/Implementation_Plan.md`:

| Phase | Name | Repo status |
|---|---|---|
| 1 | Core Skeleton | Implemented |
| 2 | Agent Execution | Implemented |
| 3 | MCP Protocol | Implemented |
| 4 | Memory System | Implemented (with partial route-level wiring) |
| 5 | Guardrails | Implemented (needs syntax fix in validator) |
| 6 | Failure Handling | Implemented |
| 7 | Tool Integration | Implemented |
| 8 | Observability | Implemented |
| 9 | Async & Queue | Implemented (API not fully Celery-wired) |
| 10 | Production Hardening | Scaffolded / partially implemented |

## 13) Design-source references

Project design sources in `Details/`:
- `Details/Complete_Project_Documentation.md`
- `Details/Core_Design_Specification.md`
- `Details/Implementation_Plan.md`
- `Details/Ultra-detailed-implementation-plan.md`

These documents define the architectural intent. This README documents the current implementation behavior and interface contracts.
