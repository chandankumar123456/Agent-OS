# app/orchestrator/

Task orchestration core and workflow engine.

## Core Modules

- `core.py`: orchestrator facade, mode dispatch, persistence helpers.
- `pipeline.py`: task/workflow mode pipeline (plan → build workflow → execute DAG → verify).
- `workflow.py`: DAG model, validation, deterministic condition evaluation, graph execution.
- `builder.py`: persists planner steps into workflow/node/edge rows.
- `executor.py`: executes individual workflow nodes and records traces.
- `retry.py`: retry config, retryability rules, exponential backoff helper.
- `context.py`: per-task execution context object.
- `errors.py`: typed error taxonomy and codes.
- `modes/`: mode strategy implementations.
