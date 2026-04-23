# app/queue/ Technical Documentation

## Purpose
Asynchronous task execution using Celery.

## Module
- `tasks.py`:
  - Celery app configuration (broker/backend/timeouts/retry behavior).
  - `agent_os.execute_task` worker function.

## Worker Responsibilities
- connect DB and Redis for execution context,
- mark task running/completed/failed,
- invoke orchestrator with explicit `task_id` and `user_id`,
- retry with exponential backoff when retry budget remains.
