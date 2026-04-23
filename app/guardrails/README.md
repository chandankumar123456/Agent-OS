# app/guardrails/ Technical Documentation

## Purpose
Implements lightweight validation for orchestration inputs/outputs and workflow steps.

## Modules
- `schema.py`: validation result models and static validation rules.
- `validator.py`: async wrapper classes (`OutputValidator`, `Guardrails`).

## Integration Points
- `Orchestrator._validate_input` and `_validate_output` invoke guardrail validation.

## Limitations
Current checks are schema/logical heuristics and do not perform advanced semantic policy enforcement.
