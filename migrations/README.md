# migrations/

SQL schema migrations consumed by `app/migrations/runner.py`.

## Files

- `001_initial_schema.sql`: creates base tables and indexes.
- `002_add_user_id_to_tasks.sql`: adds `tasks.user_id` and related indexes.
- `003_fix_schema_mismatches.sql`: fixes steps/users schema drift.

## Ordering

Migrations are applied in numeric prefix order.
