# migrations/ Technical Documentation

## Purpose
SQL migration source files for database schema evolution.

## Files
- `001_initial_schema.sql`: creates base schema and indexes.
- `002_add_user_id_to_tasks.sql`: introduces multi-user task ownership field/indexes.
- `003_fix_schema_mismatches.sql`: schema alignment fixes.

## Execution
Applied by `app/migrations/runner.py` in numeric order.

## Operational Guidance
Keep migrations idempotent and forward-only; add new numbered files for future changes.
