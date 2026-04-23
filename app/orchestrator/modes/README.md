# app/orchestrator/modes/ Technical Documentation

## Purpose
Strategy implementations for execution-mode-specific orchestration behavior.

## Modules
- `base.py`: abstract `ModeStrategy` contract.
- `factory.py`: mode-to-strategy mapping.
- `task.py`: standard pipeline execution.
- `workflow.py`: workflow semantics wrapper around pipeline.
- `autonomous.py`: iterative self-directed loop mode.
- `collaboration.py`: multi-agent collaboration with MCP dispatch.

## Mode Registry
Valid modes:
- `task`
- `workflow`
- `autonomous`
- `collaboration`
