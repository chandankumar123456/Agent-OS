# app/orchestrator/ Technical Documentation

## Purpose
Implements task orchestration, workflow execution, retries, and mode strategies.

## Pipeline Architecture

```mermaid
flowchart LR
    Input[Task Input] --> Core[core.py]
    Core --> ModeFactory[modes/factory.py]
    ModeFactory --> Strategy[Mode Strategy]
    Strategy --> Pipeline[pipeline.py]

    Pipeline --> Planner[AgentRuntime planner]
    Planner --> Builder[builder.py]
    Builder --> Workflow[(workflows + nodes + edges)]

    Pipeline --> Executor[executor.py + workflow.py]
    Executor --> NodeTrace[(node_traces)]
    Executor --> Result[Execution Result]

    Pipeline --> Verifier[AgentRuntime verifier]
    Verifier --> Output[Final Task Output]
```

## Core Modules
- `core.py`: orchestrator facade and mode dispatch.
- `pipeline.py`: plan -> workflow build -> graph execute -> verify pipeline.
- `workflow.py`: DAG model/validation/condition evaluation/execution.
- `builder.py`: workflow persistence from planner steps.
- `executor.py`: persisted step execution + node trace generation.
- `retry.py`: retry config and backoff logic.
- `context.py`: per-task runtime context container.
- `errors.py`: domain error codes/types.

## Workflow Execution Semantics
- Planner output is normalized before persistence.
- Graph dependencies are validated before node execution.
- Node statuses are persisted and trace-linked.
- Condition expressions are deterministic and constrained.

## Retry Model
- Retry decisions rely on retry configuration and current attempt counts.
- Worker-level failures can trigger Celery retry behavior with backoff.

## Extension Surface
Additional modes plug in through `modes/` strategy interface.
