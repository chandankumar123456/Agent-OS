# app/migrations/

Application-level migration runner.

## File

- `runner.py`: tracks migration versions in `schema_migrations`, discovers `migrations/*.sql`, applies pending migrations in order.

## Behavior

- Splits SQL files into executable statements.
- Inserts applied migration records idempotently.
- Exposes schema status reporting.
