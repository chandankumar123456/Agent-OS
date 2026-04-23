# tests/ Technical Documentation

## Purpose
Backend verification suite for auth, orchestration, workflows, and observability behaviors.

## Test Modules
- `test_auth_middleware.py`: middleware auth gate behavior.
- `test_auth_utils.py`: JWT round-trip behavior.
- `test_llm_mock_shapes.py`: LLM client API key requirement.
- `test_llm_normalization.py`: planner normalization safety.
- `test_orchestrator_task_identity.py`: task identity and mode defaults.
- `test_phase6_observability.py`: task/trace API auth and payload behavior.
- `test_task_steps_persisted.py`: DB persistence and worker failure handling.
- `test_workflow_engine_graph.py`: DAG validation and execution semantics.

## Dependencies
Some tests require DB/Redis availability or rely on monkeypatching internal modules.
