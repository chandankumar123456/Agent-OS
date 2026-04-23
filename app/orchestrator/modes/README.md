# app/orchestrator/modes/

Execution mode strategy implementations selected by `ModeStrategyFactory`.

## Modes

- `task.py`: standard pipeline mode.
- `workflow.py`: pipeline mode with workflow semantics and optional predefined workflow lookup.
- `autonomous.py`: iterative self-directed loop with completion checks.
- `collaboration.py`: planner assigns step agent types + MCP dispatch + direct execution.
- `base.py`: abstract strategy interface.
- `factory.py`: mode registry and lookup.
