# frontend/src/api/

Typed HTTP client for backend API.

## File

- `client.ts`: request wrapper, auth header injection, 401/403 handling, typed methods for tasks/tools/agents/config/health endpoints.

## Notable Behavior

On auth failure, client clears local auth storage and emits `auth:expired` browser event.
