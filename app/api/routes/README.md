# app/api/routes/ Technical Documentation

## Purpose
Implements externally exposed backend behavior.

## Modules
- `auth.py`: signup/login and token response.
- `tasks.py`: task creation, listing, retrieval, cancellation, and trace aggregation.
- `tools.py`: tool discovery/registration/execution APIs.
- `agents.py`: runtime agent config CRUD APIs.
- `config.py`: runtime config read/write/reset APIs.
- `health.py`: readiness/liveness/metrics endpoints.

## Common Patterns
- Uses `Depends(get_current_user)` for authentication.
- Uses admin role checks for privileged mutations.
- Returns structured error payloads aligned to `ErrorCode` enums.

## Cross-Cutting Dependencies
- Repositories in `app/memory/long_term.py`
- Orchestrator APIs and settings
- Logger and tracing/metrics data providers
