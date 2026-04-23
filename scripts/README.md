# scripts/ Technical Documentation

## Purpose
One-off operational scripts for schema/data maintenance.

## Files
- `dedup_workflows.py`: removes duplicate workflows prior to unique-constraint enforcement.
- `migration_add_workflow_task_id_unique.sql`: adds unique constraint on `workflows.task_id`.

## Usage Sequence
1. Run dedup script.
2. Verify no duplicate workflow rows remain.
3. Apply unique-constraint SQL migration.
