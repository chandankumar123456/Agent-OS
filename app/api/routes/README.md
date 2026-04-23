# app/api/routes/

HTTP endpoint implementations.

## Route Modules

- `auth.py`: signup/login, password validation, JWT issuance.
- `tasks.py`: task creation, listing, status, cancellation, trace retrieval.
- `tools.py`: list/get/register/execute tools (admin checks for registration).
- `agents.py`: list/get/create/update/delete agents (admin checks for mutation).
- `config.py`: read/update/reset runtime config keys (admin-only).
- `health.py`: liveness/readiness/metrics endpoints.

## Security Model

All `/api/v1/*` endpoints require bearer auth except signup/login; route modules additionally enforce role-based checks for admin actions.
