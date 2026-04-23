# app/guardrails/

Validation layer for output, steps, and context.

## Files

- `schema.py`: validation result schema + static validation rules.
- `validator.py`: async wrappers (`OutputValidator`, `Guardrails`) used by orchestrator.

## Integration

`Orchestrator` validates input payload and final output before persistence.
