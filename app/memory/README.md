# app/memory/ Technical Documentation

## Purpose
Long-term and short-term state management abstraction layer.

## Modules
- `models.py`: SQLAlchemy model definitions.
- `long_term.py`: async engine/session management + repositories.
- `short_term.py`: Redis client and task context cache.

## Repository Coverage
- Task/workflow/workflow node/workflow edge
- User/auth lookup
- Trace/node trace/span
- Tool registry persistence
- Agent registry persistence
- Runtime config key-value storage

## Persistence Strategy
- PostgreSQL via SQLAlchemy async for durable state.
- Redis for ephemeral task context and middleware rate-limit primitives.
