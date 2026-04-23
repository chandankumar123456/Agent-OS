# app/memory/

Persistence and state storage.

## Files

- `models.py`: SQLAlchemy table models.
- `long_term.py`: async DB engine and repositories.
- `short_term.py`: Redis client + task context cache helper.

## Repository Coverage

Repositories exist for tasks, workflows, workflow nodes/edges, users, traces, node traces, spans, tools, agents, and runtime config.
