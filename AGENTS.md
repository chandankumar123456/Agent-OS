# AgentOS — Agent Instructions

Compact reference for working in this repo. If a fact is obvious from filenames, it is omitted.

## Architecture

- **Backend**: FastAPI (Python 3.11+), entry at `app/main.py`.
- **Frontend**: React 18 + Vite + TypeScript, entry at `frontend/`.
- **Execution engine**: LangGraph StateGraph is primary; legacy pipeline is fallback on exception only.
- **Runtime**: `AgentRuntime` is a singleton and the **only** execution entry point. No module may instantiate agents directly.
- **Tooling**: MCP servers (filesystem, shell, browser) run as child processes; built-in tools register as singletons.

## Prerequisites

- Python 3.11+, Node 20+
- PostgreSQL 14+, Redis 7+
- `playwright install chromium` (browser automation)

## Environment

Create `.env` at repo root. Strictly required on startup (lifespan raises `RuntimeError` if missing):

```env
DATABASE_URL=postgresql+asyncpg://...
REDIS_URL=redis://...
OPENAI_API_KEY=sk-...
SECRET_KEY=minimum-32-byte-secret-shared-across-processes
```

> **Critical**: `SECRET_KEY` must be identical across FastAPI, Celery workers, and runtime instances.

Frontend `.env` (in `frontend/`):
```env
VITE_API_URL=http://localhost:8000/api/v1
VITE_WS_URL=ws://localhost:8000
```

## Running Locally

**Backend**
```bash
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**Frontend**
```bash
cd frontend
npm install
npm run dev        # http://localhost:5173
```

**Docker (full stack)**
```bash
cd docker
docker compose up --build
```

## Testing & Validation

```bash
# Priority 1 validation (touches DB + Redis; requires services running)
python validate_fixes.py

# Backend full suite
pytest -q

# Frontend
npm run test       # vitest
npm run lint       # eslint
```

## Key Code Facts

### Lifespan Bootstrap (`app/main.py`)
Startup sequence (all must succeed or raise):
1. Validate `DATABASE_URL`, `REDIS_URL`, `OPENAI_API_KEY`
2. Connect PostgreSQL + run pending migrations
3. Connect Redis (cache + PubSub clients)
4. Initialize `AgentRuntime` (idempotent via Redis mutex)
5. Start MCP health monitor
6. Register built-in tools
7. Start MCP system servers
8. Discover MCP tools

Shutdown reverses the above gracefully.

### Router Registration Order (`app/api/__init__.py`)
`tools_v2` **must** be registered **before** `tools`. If reversed, `/tools/{tool_name}` shadows `/tools/v2`.

### Orchestrator Fallback (`app/orchestrator/core.py`)
- `execute_task()` always calls `_execute_with_langgraph()` first.
- If LangGraph fails, it attempts checkpoint recovery via `CheckpointRecoveryService`.
- Only if recovery also fails does it fall back to legacy `ModeStrategyFactory`.

### WebSocket Auth
Endpoint: `/ws/tasks/{task_id}?token={access_token}`  
Auth is via **query parameter**, not header. Invalid/expired tokens close the connection with code 1008.

### Path Handling
The planner and executor are OS-aware. The executor remaps hallucinated foreign paths (e.g., Unix paths on Windows) to the current user's home/desktop. See `app/agents/executor.py`.

### FastAPI Docs
Explicitly disabled: `docs_url=None`, `redoc_url=None`, `openapi_url=None`. Do not rely on auto-generated Swagger UI.

## Where to Add Features

| Feature type | Location | Registration point |
|---|---|---|
| API routes | `app/api/routes/` | `app/api/__init__.py` (mind order) |
| LangGraph nodes | `app/langgraph/nodes.py` | `app/langgraph/graphs.py` |
| Graph compilers | `app/langgraph/graphs.py` | — |
| Execution modes | `app/orchestrator/modes/` | `ModeStrategyFactory` |
| Built-in tools | `app/tools/` | `app/tools/builtin.py` (lifespan calls this) |
| MCP servers | `app/mcp/servers/` | `app/mcp/client_manager.py` |

## Operational Notes

- Migrations and checkpoints table are auto-created on startup.
- CORS avoids wildcard + credentials combination; `CORS_ORIGINS=*` disables credentials.
- Celery worker entry (Docker): `celery -A app.queue.tasks worker --loglevel=info --concurrency=4 --prefetch-multiplier=1`.
- `tests/conftest.py` injects repo root into `sys.path`.
