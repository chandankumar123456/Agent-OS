# app/api/ Technical Documentation

## Purpose
Defines HTTP API composition and cross-route dependencies.

## Composition
- `__init__.py`: mounts route modules into a single API router.
- `deps.py`:
  - `get_orchestrator()` returns module-level singleton orchestrator.
  - `get_current_user()` validates bearer token and loads active user from DB.

## Route Packages
- `routes/`: endpoint handlers grouped by bounded context.
- `schemas/`: Pydantic request/response definitions.

## Security Boundary
All mounted `/api/v1/*` business endpoints require authenticated user context.
