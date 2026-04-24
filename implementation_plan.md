# Agent-OS PRD Alignment Implementation Plan

## Implementation Tasks

- [ ] **Add Agent Versioning Support** `priority:1` `phase:model`
  - files: app/memory/models.py, app/memory/long_term.py, app/api/routes/agents.py
  - [ ] Add `version` field to AgentModel and create AgentVersionModel table
  - [ ] Update AgentRepository to support version history (list_versions, get_version)
  - [ ] Add API endpoints: GET /agents/{id}/versions, POST /agents/{id}/versions
  - [ ] Ensure runtime loads correct version on execution

- [ ] **Implement Dynamic Agent Router** `priority:1` `phase:orchestration`
  - files: app/orchestrator/router.py, app/orchestrator/core.py, app/orchestrator/pipeline.py
  - [ ] Create AgentRouter class that maps agent_type/role to registered runtime workers
  - [ ] Support fallback agent selection when primary agent is unavailable
  - [ ] Integrate router into PipelineExecutor and mode strategies
  - [ ] Route planner output steps to correct agent types dynamically

- [ ] **Enforce Per-Agent Tool Access Control** `priority:1` `phase:agent`
  - files: app/agents/executor.py, app/agents/base.py, app/tools/registry.py, app/orchestrator/executor.py
  - [ ] Pass agent's allowed tools list into ExecutorAgent.execute()
  - [ ] Reject unauthorized tool calls before tool_registry.execute()
  - [ ] Return clear error in AgentOutput when tool access denied
  - [ ] Update StepExecutor to pass agent config tools to executor

- [ ] **Persist MCP Messages to Database** `priority:1` `phase:mcp`
  - files: app/mcp/protocol.py, app/mcp/router.py, app/memory/long_term.py
  - [ ] Create MessageRepository with create/get_by_task methods
  - [ ] Wire MCPProtocol.send_message() to persist messages to DB
  - [ ] Wire MessageRouter.route() to log routing decisions
  - [ ] Ensure message persistence includes sender, receiver, payload, timestamp

- [ ] **Fix Custom Agent Prompt Injection** `priority:1` `phase:agent`
  - files: app/agents/executor.py, app/runtime/factory.py
  - [ ] Update ExecutorAgent to check for _custom_prompt and inject into system message
  - [ ] Ensure custom prompt replaces or prepends to EXECUTOR_PROMPT
  - [ ] Test that custom agents use their configured system_prompt

- [ ] **Build MCP Broker / Server Registry** `priority:1` `phase:mcp`
  - files: app/mcp/registry.py, app/memory/models.py, app/memory/long_term.py, app/api/routes/tools.py
  - [ ] Create MCPServerModel table (id, name, endpoint, tools_list, health_status, version)
  - [ ] Implement MCPServerRegistry with register/discover/health_check
  - [ ] Add API endpoints: POST /tools/mcp-servers, GET /tools/mcp-servers, GET /tools/mcp-servers/{id}/health
  - [ ] Integrate registry with tool discovery in ExecutorAgent

- [ ] **Implement Fallback Agent Recovery** `priority:2` `phase:orchestration`
  - files: app/orchestrator/retry.py, app/orchestrator/core.py
  - [ ] Extend retry logic to support fallback agent switching
  - [ ] Define fallback agent mappings (executor -> custom_executor, etc.)
  - [ ] Update _execute_with_retry to try fallback after retries exhausted
  - [ ] Log fallback decisions in traces

- [ ] **Add Approval/Wait Node Types to Workflow Engine** `priority:2` `phase:workflow`
  - files: app/memory/models.py, app/orchestrator/workflow.py, app/orchestrator/executor.py, app/api/routes/tasks.py
  - [ ] Add node_type enum to WorkflowNodeModel (agent, tool, decision, wait)
  - [ ] Extend WorkflowEngine to pause on wait/approval nodes
  - [ ] Add resume/approve endpoints for paused workflows
  - [ ] Update frontend to show approval UI for waiting tasks

- [ ] **Enhance Guardrails with Custom Constraint Rules** `priority:2` `phase:safety`
  - files: app/guardrails/schema.py, app/guardrails/validator.py, app/memory/models.py
  - [ ] Create GuardrailRule model (rule_type, condition, action)
  - [ ] Add configurable constraint validation to GuardrailSchema
  - [ ] Support rules: blocked_keywords, max_length, required_fields, allowed_tools
  - [ ] Integrate custom rules into orchestrator input/output validation

- [ ] **Add Frontend Workflow Visual Builder** `priority:3` `phase:ui`
  - files: frontend/src/pages/WorkflowBuilder.tsx, frontend/src/api/client.ts
  - [ ] Install and configure React Flow dependency
  - [ ] Create drag-and-drop canvas with node palette (Agent, Tool, Decision, Wait)
  - [ ] Implement node connection and property editing
  - [ ] Add save/load workflow definition to backend API

- [ ] **Add MCP Server Health Monitoring** `priority:3` `phase:mcp`
  - files: app/mcp/registry.py, app/api/routes/tools.py, frontend/src/pages/Tools.tsx
  - [ ] Implement periodic health checks for registered MCP servers
  - [ ] Store health status in MCPServerModel
  - [ ] Expose health status in API and frontend
  - [ ] Auto-disable tools from unhealthy servers

- [ ] **Verify All Changes and Run Tests** `priority:1` `phase:test`
  - files: tests/
  - [ ] Update existing tests for new schema changes
  - [ ] Add tests for agent versioning API
  - [ ] Add tests for tool access control enforcement
  - [ ] Add tests for MCP message persistence
  - [ ] Add tests for dynamic agent routing
  - [ ] Add tests for workflow approval nodes
  - [ ] Run full test suite and fix regressions
