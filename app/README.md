# app/

Backend application package.

## Subsystems

- `main.py`: FastAPI app creation, lifespan startup/shutdown, middleware wiring, exception handlers.
- `api/`: HTTP routes and dependencies.
- `orchestrator/`: execution engine and mode strategies.
- `runtime/`: agent worker lifecycle and registry.
- `agents/`: planner/executor/verifier implementations.
- `tools/`: built-in and dynamic tools.
- `memory/`: database/redis abstractions and repositories.
- `mcp/`: inter-agent protocol + router + bus.
- `middleware/`: auth + rate limiting.
- `guardrails/`: output/input validation helpers.
- `logs/`: logger, tracing, and metrics collectors.
- `queue/`: Celery task entrypoint.
- `config/`: environment and runtime config.
