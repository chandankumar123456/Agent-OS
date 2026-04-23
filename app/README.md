# app/ Backend Technical Documentation

## Purpose
Python backend package implementing API, orchestration, runtime, persistence, tooling, and observability.

## Entry Point
- `main.py`: FastAPI application lifecycle, middleware, exception handling, route mounting.

## Subsystem Map
- `api/`: route composition and request-layer contracts.
- `agents/`: planner/executor/verifier implementations.
- `runtime/`: agent worker lifecycle and singleton runtime.
- `orchestrator/`: mode strategies and workflow pipeline.
- `memory/`: database and redis state access.
- `tools/`: built-in/dynamic tool execution.
- `mcp/`: message protocol and routing.
- `queue/`: Celery worker execution hook.
- `middleware/`: auth and rate limiting.
- `guardrails/`: validation checks.
- `logs/`: metrics and tracing support.
- `config/`: settings model.
- `migrations/`: migration runner.

## Architectural Constraints
- Orchestrator delegates agent execution through `AgentRuntime` workers.
- Startup requires DB/Redis/OpenAI config to pass validation.
