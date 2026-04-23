# app/tools/

Tooling subsystem for agent tool use.

## Files

- `base.py`: tool input/output contracts.
- `registry.py`: in-memory registry with execute/list/get operations.
- `search.py`: built-in `web_search`, `calculator`, `text_processor` tools.
- `parser.py`: extracts `tool_call` from agent output JSON.
- `sandbox.py`: restricted execution environment for dynamic tool templates.

## Dynamic Tools

Custom tools can be registered via API and executed through `DynamicTool` + sandbox.
