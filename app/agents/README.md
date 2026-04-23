# app/agents/

LLM-driven agent implementations and shared contracts.

## Files

- `base.py`: `AgentInput`, `AgentOutput`, roles/status enums, protocol interface.
- `types.py`: task/step status enums.
- `llm_client.py`: OpenAI Async client wrapper (`complete`, `complete_json`).
- `planner.py`: generates normalized DAG-compatible steps with dependency sanitization.
- `executor.py`: executes steps, optionally calls tools through parser + registry.
- `verifier.py`: validates aggregate output quality.

## Runtime Use

Instantiated by `app/runtime/factory.py` and executed via `AgentRuntime` workers.
