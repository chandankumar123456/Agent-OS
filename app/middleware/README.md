# app/middleware/

HTTP middleware.

## Components

- `auth.py`: bearer-token protection for API routes (exempts login/signup).
- `rate_limit.py`: Redis-backed rolling-window + burst limit checks by user/IP.

## Wiring

Both middleware are attached in `app/main.py`.
