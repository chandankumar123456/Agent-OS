# app/tools/ Technical Documentation

## Purpose
Defines tool contracts, registration, execution, parsing, and sandboxing.

## Modules
- `base.py`: tool input/output base classes.
- `registry.py`: global tool registry singleton.
- `search.py`: built-in tools (`web_search`, `calculator`, `text_processor`).
- `parser.py`: tool call extraction from agent JSON output.
- `sandbox.py`: restricted execution of dynamic tool templates.

## Dynamic Tool Path
1. Tool registered via API and persisted.
2. `DynamicTool` wraps template and executes through `ToolSandbox`.
3. Sandbox validates AST and blocks dangerous constructs.
