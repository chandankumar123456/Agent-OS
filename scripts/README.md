# scripts/

Operational database maintenance scripts.

## Files

- `dedup_workflows.py`: removes duplicate workflows per `task_id` before adding uniqueness constraint.
- `migration_add_workflow_task_id_unique.sql`: manual SQL to add unique constraint on `workflows.task_id`.

## Usage Context

These scripts are intended for one-off maintenance/migration workflows.
