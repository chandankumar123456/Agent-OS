-- Manual SQL migration to add unique constraint on workflows.task_id
-- RUN THIS ONLY AFTER RUNNING scripts/dedup_workflows.py

-- Step 1: Verify no duplicates remain
-- SELECT task_id, COUNT(*) FROM workflows GROUP BY task_id HAVING COUNT(*) > 1;
-- Should return 0 rows.

-- Step 2: Add unique constraint
ALTER TABLE workflows ADD CONSTRAINT uq_workflows_task_id UNIQUE (task_id);

-- Step 3: Verify constraint exists
-- \d workflows
-- Should show: "uq_workflows_task_id" UNIQUE CONSTRAINT, btree (task_id)
