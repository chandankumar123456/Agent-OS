# app/middleware/ Technical Documentation

## Purpose
Request-level cross-cutting controls.

## Components
- `auth.py` (`APIKeyMiddleware`): bearer token enforcement for API routes.
- `rate_limit.py` (`RateLimitMiddleware`): Redis-backed rate and burst limiting.

## Request Flow Position
Middleware is registered in `app/main.py` before route handling.

## Bypass Paths
- Auth middleware bypasses `/api/v1/auth/login` and `/api/v1/auth/signup`.
- Rate limit middleware bypasses `/health`, `/docs`, `/openapi.json`.
