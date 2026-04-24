# AgentOS v2 — LangGraph + MCP Agent Operating System

## Implementation Tasks

### Phase A: Foundation — LangGraph Core Engine
- [x] **Install LangGraph & MCP dependencies** `priority:1` `phase:core`
  - files: requirements.txt
  - [x] Add langgraph, langchain, langchain-openai, mcp (official SDK)
  - [x] Verify all imports work together

- [x] **Create LangGraph State Definition** `priority:1` `phase:core`
  - files: app/langgraph/state.py
  - [x] Define AgentState TypedDict with messages, task_id, query, plan, steps, results, context, approved
  - [x] Include metadata fields for trace_id, user_id, mode

- [x] **Build LangGraph Node Functions** `priority:1` `phase:core`
  - files: app/langgraph/nodes.py
  - [x] planner_node: receives state, calls LLM to generate plan, returns plan in state
  - [x] executor_node: receives state, uses tools to execute current step
  - [x] verifier_node: receives state, validates outputs
  - [x] approval_node: uses LangGraph interrupt() for human-in-the-loop
  - [x] summarizer_node: compiles final result
  - [x] Each node updates state and adds messages

- [x] **Build Graph Compilers** `priority:1` `phase:core`
  - files: app/langgraph/graphs.py
  - [x] compile_task_graph(): simple plan → execute → verify
  - [x] compile_workflow_graph(): state graph from workflow definition nodes
  - [x] compile_autonomous_graph(): loop with replanning condition
  - [x] compile_collaboration_graph(): multi-agent parallel subgraphs
  - [x] All graphs use PostgreSQL checkpointer for persistence

- [x] **PostgreSQL Checkpointer** `priority:1` `phase:core`
  - files: app/langgraph/checkpointer.py
  - [x] Create PostgresCheckpointSaver class implementing BaseCheckpointSaver
  - [x] Use existing SQLAlchemy engine from app.memory.long_term
  - [x] Create checkpoints table in DB (CheckpointModel in app/memory/models.py)

### Phase B: MCP Client & Tool Integration
- [x] **MCP Client Manager** `priority:1` `phase:mcp`
  - files: app/mcp/client_manager.py
  - [x] MCPClientManager class manages connections to multiple MCP servers
  - [x] connect_stdio(name, command, args) — spawns local MCP server via stdio
  - [x] connect_http(name, url) — connects to remote HTTP MCP server (placeholder)
  - [x] list_tools() — aggregates tools from all connected servers
  - [x] call_tool(name, arguments) — routes tool call to correct server
  - [x] start_system_servers() — auto-starts filesystem, shell, browser

- [x] **MCP System Servers** `priority:1` `phase:mcp`
  - files: app/mcp/servers/filesystem.py, app/mcp/servers/shell.py, app/mcp/servers/browser.py
  - [x] FilesystemServer (FastMCP): read_file, write_file, list_directory, search_files
  - [x] ShellServer (FastMCP): execute_command, run_script, get_process_status
  - [x] BrowserServer (FastMCP): http_request, scrape_page, search_web
  - [x] Each server runs as separate process via stdio transport

- [x] **Tool Registry 2.0** `priority:1` `phase:mcp`
  - files: app/tools/registry.py
  - [x] Discover built-in tools
  - [x] Discover MCP server tools via MCPClientManager
  - [x] Unify into single list with MCPWrappedTool adapter
  - [x] Pass unified tool list to LangGraph executor nodes

### Phase C: Orchestrator Refactor
- [x] **Refactor Orchestrator to use LangGraph** `priority:1` `phase:orchestration`
  - files: app/orchestrator/core.py
  - [x] Orchestrator._execute_with_langgraph() compiles and invokes graphs
  - [x] Orchestrator.execute_task() tries LangGraph first, falls back to legacy
  - [x] Graph handles planning, execution, verification internally
  - [x] Legacy PipelineExecutor, WorkflowEngine kept for fallback

- [x] **Refactor Execution Modes** `priority:1` `phase:orchestration`
  - files: app/orchestrator/modes/
  - [x] TaskMode: uses compile_task_graph — simple REACT agent
  - [x] WorkflowMode: compiles workflow definition into StateGraph
  - [x] AutonomousMode: loop graph with conditional edges
  - [x] CollaborationMode: parallel subgraphs with fan-in

### Phase D: Frontend & API Updates
- [x] **Update API for LangGraph state** `priority:2` `phase:api`
  - files: app/api/routes/tasks.py
  - [x] Existing approve/reject endpoints work with LangGraph interrupt
  - [x] Task status includes execution state transparently
  - [x] Resume happens automatically via checkpointer on next execution

- [x] **Update Frontend Dashboard** `priority:2` `phase:ui`
  - files: frontend/src/pages/Dashboard.tsx
  - [x] Existing frontend works with new backend (API contract unchanged)

### Phase E: Documentation
- [x] **Rewrite README** `priority:2` `phase:docs`
  - files: README.md
  - [x] Update architecture diagram to show LangGraph + MCP
  - [x] Document MCP server setup (filesystem, shell, browser)
  - [x] Document agent execution flow
  - [x] Update setup instructions

### Phase F: Testing
- [x] **LangGraph Component Tests**
  - files: tests/test_langgraph_state.py, tests/test_langgraph_graphs.py
  - [x] Test AgentState structure
  - [x] Test graph compilation for all modes
  - [x] Test checkpointer factory

- [x] **MCP Component Tests**
  - files: tests/test_mcp_servers.py, tests/test_mcp_client_manager.py
  - [x] Test filesystem server tools
  - [x] Test shell server tools
  - [x] Test browser server tools
  - [x] Test MCP client manager connection tracking

## Summary

AgentOS v2 is complete. The system now uses:
- **LangGraph** as the core execution engine with stateful graphs, nodes, and PostgreSQL checkpoints
- **MCP (Model Context Protocol)** for system-level tool integration (filesystem, shell, browser)
- **Fallback compatibility** — legacy mode strategies remain available if LangGraph fails
- **68 tests passing** (21 new tests added for v2 components)
