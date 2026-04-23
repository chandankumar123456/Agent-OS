# app/agents/ Technical Documentation

## Purpose
Defines agent contracts and concrete role agents used by orchestration.

## Components
- `base.py`: `AgentInput`, `AgentOutput`, `AgentRole`, `AgentStatus`, `BaseAgent` protocol.
- `types.py`: task/step status enums used across APIs and repositories.
- `llm_client.py`: OpenAI async wrapper for text/json completions.
- `planner.py`: prompt + normalization to DAG-safe step format.
- `executor.py`: step execution, iterative tool-calling loop (`MAX_TOOL_ROUNDS`).
- `verifier.py`: output validation scoring/issue reporting.

## Contracts
Agents are async and return `AgentOutput`; failures are encoded as structured failure output rather than uncaught exceptions.

## Dependencies
- `app/tools` (executor)
- `app/config/settings.py` (llm model/key)
- `app/logs/logger.py`
