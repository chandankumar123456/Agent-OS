# app/orchestrator/ Technical Documentation

## Purpose
Implements task orchestration, workflow execution, retries, and mode strategies.

## Core Modules
- `core.py`: orchestrator facade and mode dispatch.
- `pipeline.py`: plan -> workflow build -> graph execute -> verify pipeline.
- `workflow.py`: DAG model/validation/condition evaluation/execution.
- `builder.py`: workflow persistence from planner steps.
- `executor.py`: persisted step execution + node trace generation.
- `retry.py`: retry config and backoff logic.
- `context.py`: per-task runtime context container.
- `errors.py`: domain error codes/types.

## Execution Guarantees
- Planner output normalized before persistence.
- Graph dependencies validated before node execution.
- Node statuses persisted and trace-linked.

## Extension Surface
Additional modes plug in through `modes/` strategy interface.
