# app/queue/

Asynchronous task execution integration.

## File

- `tasks.py`: Celery app configuration and `agent_os.execute_task` worker task.

## Execution Contract

- Worker marks task running, executes orchestrator, then writes completed/failed state.
- Retries with exponential delay until `MAX_RETRIES`.
