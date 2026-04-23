# frontend/src/api/ Technical Documentation

## Purpose
Centralized typed API client for backend communication.

## Module
- `client.ts`

## Responsibilities
- Build base URL from `VITE_API_URL` fallback.
- Attach bearer token from localStorage.
- Handle non-2xx responses and auth expiration.
- Expose typed methods for tasks, traces, tools, agents, config, and health/metrics.

## Error Handling
401/403 responses clear auth storage and dispatch `auth:expired` browser event.
