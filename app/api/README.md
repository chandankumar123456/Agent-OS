# app/api/

FastAPI routing composition and request dependencies.

## Files

- `__init__.py`: mounts `auth`, `tasks`, `tools`, `agents`, `config` routers.
- `deps.py`: orchestrator singleton dependency and bearer-token user resolution.
- `routes/`: endpoint implementations.
- `schemas/`: API request/response models.
