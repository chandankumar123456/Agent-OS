# app/runtime/

Agent lifecycle runtime.

## Files

- `runtime.py`: singleton `AgentRuntime`, worker registry, init/shutdown, DB agent loading.
- `factory.py`: agent instance creation logic by role.
- `worker.py`: async worker with inbox loop + direct execution path.
- `pool.py`: semaphore-backed agent capacity control.

## Invariant

All agent execution should flow through runtime-managed workers.
