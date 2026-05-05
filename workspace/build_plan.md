# AgentOS Implementation Build Plan

**Goal:** Transform AgentOS from a partially-built 8-layer skeleton into a production-grade AI agent operating system with complete memory, multi-agent coordination, production reliability, and observability.

**Design:** Based on 13-section Q&A requirements covering Problem & Purpose, Core Explanation, Real-World Usage, System Architecture, Execution Flow, Production Behavior, Reliability & Safety, State & Memory, Tools & Integration, Scalability, Monitoring & Debugging, Product Thinking, and Advanced System Thinking.

---

## 1. SYSTEM BREAKDOWN

Maps the 13 Q&A sections to 8 concrete subsystems. Each subsystem declares responsibility, I/O boundaries, dependencies, and existing-vs-needed status.

### 1.1 Orchestrator & Routing Subsystem
- **Responsibility:** Central decision-maker that routes tasks, selects execution mode (simple vs complex), controls flow, manages fallback chains.
- **Input:** Task query + config dict (mode, max_steps, require_approval).
- **Output:** AgentOutput (SUCCESS/FAILURE) with result or error context.
- **Dependencies:** AgentRuntime, LangGraph engine, Action V1 runner, ModeStrategyFactory.
- **Existing:** `app/orchestrator/core.py` (Orchestrator with LangGraph delegation + legacy fallback), `app/orchestrator/task_runner.py`, `app/orchestrator/modes/`, `app/orchestrator/retry.py`, `app/orchestrator/errors.py`.
- **To Build:** Priority-based task routing, idempotency enforcement, execution lock management, dynamic mode selection based on task complexity scoring.

### 1.2 Agent System Subsystem
- **Responsibility:** Role-based reasoning units (planner, executor, verifier, reviewer, summarizer, coordinator), lifecycle management, inter-agent communication.
- **Input:** AgentInput (task_id, step_id, query, context, allowed_tools).
- **Output:** AgentOutput (status, output_data, error_message, recoverable).
- **Dependencies:** AgentRuntime, AgentFactory, AgentPool, LLM client, ToolRegistry.
- **Existing:** `app/agents/base.py` (BaseAgent, AgentInput, AgentOutput), `app/agents/planner.py`, `app/agents/executor.py`, `app/agents/verifier.py`, `app/agents/llm_client.py`, `app/runtime/runtime.py`, `app/runtime/factory.py`, `app/runtime/pool.py`, `app/runtime/worker.py`.
- **To Build:** ReviewerAgent, CoordinatorAgent, inter-agent handoff protocol, dynamic agent creation from AgentConfigV2Model, agent feedback loop (learn from past executions), multi-LLM provider abstraction.

### 1.3 Tool & MCP Subsystem
- **Responsibility:** Tool registry, discovery, input validation, permission model, failure classification, dynamic tool addition/removal, MCP server lifecycle.
- **Input:** ToolInput (name, arguments, agent_id).
- **Output:** ToolOutput (success, result, error, metadata).
- **Dependencies:** MCPClientManager, ToolSandbox, ToolGroundingLayer, SafetyGate.
- **Existing:** `app/tools/registry.py`, `app/tools/base.py`, `app/tools/sandbox.py`, `app/tools/grounding.py`, `app/mcp/client_manager.py`, `app/mcp/servers/` (filesystem, shell, browser), `app/safety/gate.py`.
- **To Build:** Tool permission model (agent-to-tool mapping), tool failure classification (retryable/fatal/fallback), dynamic tool addition/removal API, tool input validation pipeline (schema → type check → safety check → execution), tool cost tracking per invocation.

### 1.4 Memory & State Subsystem
- **Responsibility:** Temporary memory (active session), persistent memory (across tasks/sessions), state management, memory pruning/summarization/expiry, artifact storage.
- **Input:** task_id, memory_key, memory_value, expiry_ttl.
- **Output:** Retrieved memory value or None, pruned memory summary.
- **Dependencies:** PostgreSQL (long_term.py), Redis (short_term.py), AgentState TypedDict.
- **Existing:** `app/memory/long_term.py` (TaskRepository, TraceRepository, AgentRepository, etc.), `app/memory/short_term.py` (ShortTermMemory via Redis), `app/memory/models.py` (all SQLAlchemy models), `app/langgraph/state.py` (AgentState TypedDict), `app/langgraph/checkpointer.py` (PostgresCheckpointSaver).
- **To Build:** PersistentMemoryManager with pruning/expiry/summarization, user-level memory profiles, cross-task knowledge retrieval, artifact store for agent outputs, memory consistency layer (central state source), shared memory with access rules.

### 1.5 Execution Engine Subsystem
- **Responsibility:** Task lifecycle management, state transitions, checkpoint/resume, failure handling, infinite loop prevention, timeout enforcement.
- **Input:** Task execution request with config.
- **Output:** Execution result with full trace, checkpoints, and recovery context.
- **Dependencies:** LangGraph nodes, Action V1 runner, RecoveryEngine, VerificationEngine, ActionStabilizer.
- **Existing:** `app/langgraph/nodes.py`, `app/langgraph/graphs.py`, `app/action_v1/runner.py`, `app/action_v1/executor.py`, `app/action_v1/verifier.py`, `app/action_v1/fallback.py`, `app/capabilities/recovery.py`, `app/capabilities/verification.py`, `app/environments/execution_stabilizer.py`, `app/desktop/goal_loop.py`, `app/recovery/checkpoint_service.py`.
- **To Build:** Unified task state machine (PENDING → PLANNING → EXECUTING → VERIFYING → AWAITING_APPROVAL → COMPLETED/FAILED), per-agent/per-tool/per-workflow timeout enforcement, execution replay from stored checkpoints, idempotency key management.

### 1.6 Safety & Guardrails Subsystem
- **Responsibility:** Input/output validation, role restrictions, tool permissions, hallucination reduction, failure isolation, audit logging.
- **Input:** Query, tool parameters, agent output.
- **Output:** ValidationResult (valid, errors, warnings, confidence).
- **Dependencies:** GuardrailRuleRepository, SafetyGate, VerificationEngine.
- **Existing:** `app/guardrails/validator.py`, `app/guardrails/schema.py`, `app/safety/gate.py`, `app/memory/models.py` (GuardrailRuleModel).
- **To Build:** Role-based access control for agents, hallucination grounding layer (cross-reference tools/state/data), output schema validation per agent role, failure isolation boundaries (separate contexts per task/agent), comprehensive audit trail for every decision.

### 1.7 Observability Subsystem
- **Responsibility:** Structured logging, distributed tracing, metrics collection, anomaly detection, execution replay, dashboards, alerting.
- **Input:** Events from all subsystems (task start, tool call, state change, error).
- **Output:** Logs, traces, metrics, alerts, replay data.
- **Dependencies:** Prometheus client, PostgreSQL (traces, spans), Redis (event bus).
- **Existing:** `app/logs/logger.py`, `app/logs/tracing.py`, `app/logs/metrics.py`, `app/memory/models.py` (TraceModel, SpanModel, NodeTraceModel, TokenUsageModel).
- **To Build:** Complete trace schema with parent-child span relationships, anomaly detection engine (unusual errors/delays/loops), execution replay mechanism from checkpoints + traces, cost tracking dashboard, alert rules with severity levels, task-level end-to-end tracing by task ID.

### 1.8 Scalability & Concurrency Subsystem
- **Responsibility:** Task queue architecture, worker pools, resource limits, horizontal scaling, bottleneck mitigation, cost control.
- **Input:** Task submission requests, resource availability signals.
- **Output:** Scheduled task execution, resource allocation decisions.
- **Dependencies:** AgentPool semaphore, Redis event bus, Celery (optional), PostgreSQL.
- **Existing:** `app/runtime/pool.py` (AgentPool semaphore, default 100), `app/mcp/bus.py` (MemoryMCPBus + RedisMCPBus), `app/orchestrator/event_bus.py`.
- **To Build:** Priority task queue with scheduling, worker pool management across processes, resource limit enforcement (max concurrent agents, DB connections, Redis connections), horizontal scaling coordinator, cost control layer (limit unnecessary LLM calls, cache results, batch operations).

---

## 2. BUILD PHASES

Five sequential phases with clear objectives, entry/exit criteria, and deliverables.

### Phase 1 — MVP Hardening (Stabilize What Exists)
**Objective:** Ensure all existing components work reliably together with proper error handling, input validation, and test coverage.

**Entry Criteria:**
- All existing files compile without import errors
- PostgreSQL and Redis connections are functional
- `pytest -q` runs with no new failures beyond the known pre-existing one

**Exit Criteria:**
- All existing tests pass (except known pre-existing failure)
- Input validation covers all API endpoints
- Error handling is consistent across all modules (AgentOSError with structured fields)
- Orchestrator fallback chain works end-to-end (LangGraph → Action V1 → legacy)

**Deliverables:**
1. Unified error handling across all modules using `app/orchestrator/errors.py` (AgentOSError, RetryableError, UnrecoverableError, ErrorCode enum)
2. Input validation middleware for all API routes in `app/api/routes/`
3. Guardrails integration at orchestrator entry point (`app/orchestrator/core.py` `_validate_input`)
4. Output validation at every node exit point (planner_node, executor_node, verifier_node, summarizer_node)
5. Test coverage for orchestrator fallback chain
6. Consistent logging format across all modules using `app/logs/logger.py`

### Phase 2 — Core Stability (State, Memory, Recovery Completeness)
**Objective:** Build complete memory layer, state management, and recovery system.

**Entry Criteria:**
- Phase 1 exit criteria met
- PostgreSQL schema includes all models from `app/memory/models.py`
- Redis connection is stable with health checks

**Exit Criteria:**
- Persistent memory with pruning/expiry/summarization is operational
- Task state machine is fully implemented with all transitions
- Checkpoint resume works from any saved state
- Memory consistency is maintained across concurrent tasks

**Deliverables:**
1. PersistentMemoryManager (`app/memory/persistent.py`) with TTL-based expiry, size-based pruning, and summarization
2. UserMemoryProfile (`app/memory/user_profile.py`) for cross-task knowledge retrieval
3. ArtifactStore (`app/memory/artifact_store.py`) for structured agent output storage
4. TaskStateMachine (`app/orchestrator/state_machine.py`) with explicit state transitions
5. Memory consistency layer (`app/memory/consistency.py`) as central state source
6. Execution replay service (`app/recovery/replay.py`) from checkpoints + traces
7. Idempotency enforcement (`app/orchestrator/idempotency.py`) with Redis locks

### Phase 3 — Multi-Agent Coordination (Collaboration, Handoffs, Dynamic Routing)
**Objective:** Enable real inter-agent collaboration with structured handoffs and dynamic agent creation.

**Entry Criteria:**
- Phase 2 exit criteria met
- AgentRuntime can register and manage multiple agent types
- AgentConfigV2Model is populated with agent configurations

**Exit Criteria:**
- Agents can hand off work to each other via structured state passing
- Dynamic agent creation from configuration works
- ReviewerAgent validates outputs from other agents
- CoordinatorAgent manages multi-agent workflows

**Deliverables:**
1. InterAgentHandoff protocol (`app/agents/handoff.py`) with structured state transfer
2. ReviewerAgent (`app/agents/reviewer.py`) for output validation
3. CoordinatorAgent (`app/agents/coordinator.py`) for multi-agent workflow management
4. DynamicAgentFactory (`app/runtime/dynamic_factory.py`) extending existing AgentFactory
5. Agent feedback loop (`app/agents/feedback.py`) for learning from past executions
6. Multi-LLM provider abstraction (`app/agents/llm_router.py`) for model-agnostic execution
7. Collaboration graph compiler (`app/langgraph/collaboration.py`) extending existing graphs.py

### Phase 4 — Production Reliability (Distributed, Queued, Cost-Tracked)
**Objective:** Add task queuing, scheduling, cost tracking, and production-grade reliability features.

**Entry Criteria:**
- Phase 3 exit criteria met
- All agents and tools are registered and functional
- Memory and state systems are stable

**Exit Criteria:**
- Tasks are queued and scheduled with priority support
- Cost is tracked per task, per agent, per tool invocation
- Timeouts are enforced at agent, tool, and workflow levels
- Failure isolation prevents cascade failures between tasks

**Deliverables:**
1. TaskQueue (`app/orchestrator/queue.py`) with priority scheduling and worker assignment
2. CostTracker (`app/logs/cost_tracker.py`) integrating with existing TokenUsageModel
3. TimeoutEnforcer (`app/orchestrator/timeouts.py`) with per-agent/per-tool/per-workflow limits
4. FailureIsolator (`app/orchestrator/isolation.py`) with context separation per task
5. InfiniteLoopDetector (`app/orchestrator/loop_detector.py`) extending existing ActionStabilizer detection
6. ExecutionLock (`app/orchestrator/locks.py`) using Redis for distributed locking
7. WorkerPoolManager (`app/runtime/worker_pool.py`) for cross-process worker management

### Phase 5 — Scaling & Optimization (Advanced Features)
**Objective:** Add horizontal scaling, anomaly detection, advanced observability, and optimization features.

**Entry Criteria:**
- Phase 4 exit criteria met
- System handles concurrent tasks without degradation
- All metrics are being collected and exposed

**Exit Criteria:**
- System can scale horizontally across multiple instances
- Anomaly detection identifies unusual patterns automatically
- Execution replay works for any past task
- Cost optimization reduces unnecessary LLM calls

**Deliverables:**
1. HorizontalScalingCoordinator (`app/runtime/scaling.py`) for multi-instance coordination
2. AnomalyDetector (`app/logs/anomaly.py`) for unusual errors/delays/loops
3. AlertManager (`app/logs/alerts.py`) with severity levels and notification channels
4. CacheOptimizer (`app/tools/cache.py`) for tool result caching and batching
5. ResourceLimitEnforcer (`app/runtime/resource_limits.py`) for DB/Redis/agent limits
6. Dashboard API (`app/api/routes/observability.py`) for metrics, traces, and cost data
7. PerformanceProfiler (`app/logs/profiler.py`) for bottleneck identification

---

## 3. COMPONENT-LEVEL TASKS

### 3.1 Orchestrator & Routing Tasks

**Task 3.1.1: Priority-Based Task Router**
- **Description:** Extend `app/orchestrator/core.py` to route tasks based on priority level and complexity score.
- **Input Contract:** `route_task(query: str, config: dict, priority: str) -> RoutingDecision`
- **Output Contract:** RoutingDecision with target execution path (action_v1, langgraph, legacy), priority queue position, estimated cost.
- **Dependencies:** Task 3.1.2 (complexity scorer), Task 3.4.1 (task queue).
- **Verification:** Submit tasks with different priorities; verify high-priority tasks execute before low-priority ones.
- **Relevant Files:** `app/orchestrator/core.py`, `app/orchestrator/task_runner.py`.

**Task 3.1.2: Task Complexity Scorer**
- **Description:** Analyze query complexity to determine execution path (simple → Action V1, complex → LangGraph).
- **Input Contract:** `score_complexity(query: str, config: dict) -> ComplexityScore`
- **Output Contract:** ComplexityScore (0.0-1.0) with reasoning and recommended execution path.
- **Dependencies:** None (standalone utility).
- **Verification:** Score known simple queries (< 0.3) and complex queries (> 0.7); verify correct routing decisions.
- **Relevant Files:** `app/orchestrator/core.py`, `app/action_v1/selector.py`.

**Task 3.1.3: Idempotency Enforcement**
- **Description:** Prevent duplicate task execution using idempotency keys and Redis locks.
- **Input Contract:** `acquire_idempotency_lock(idempotency_key: str, ttl: int) -> bool`
- **Output Contract:** Boolean indicating lock acquisition success; raises IdempotencyConflictError if duplicate.
- **Dependencies:** Redis connection from `app/memory/short_term.py`.
- **Verification:** Submit same task twice with same idempotency key; verify second submission is rejected.
- **Relevant Files:** `app/orchestrator/core.py`, `app/memory/short_term.py`.

### 3.2 Agent System Tasks

**Task 3.2.1: ReviewerAgent**
- **Description:** New agent role that validates outputs from other agents against schemas and rules.
- **Input Contract:** `review(output: dict, schema: dict, rules: list) -> ReviewResult`
- **Output Contract:** ReviewResult (passed: bool, issues: list, confidence: float, recommendations: list).
- **Dependencies:** Task 3.6.1 (role-based access control), existing `app/guardrails/validator.py`.
- **Verification:** Feed known-good and known-bad outputs; verify correct pass/fail decisions with actionable issues.
- **Relevant Files:** `app/agents/reviewer.py` (new), `app/agents/base.py`, `app/guardrails/validator.py`.

**Task 3.2.2: CoordinatorAgent**
- **Description:** Manages multi-agent workflows, assigns tasks to agents, collects results, handles handoffs.
- **Input Contract:** `coordinate(workflow: WorkflowDefinition, agents: list) -> CoordinationResult`
- **Output Contract:** CoordinationResult with per-agent results, handoff log, overall status.
- **Dependencies:** Task 3.2.3 (inter-agent handoff), AgentRuntime.
- **Verification:** Run a multi-step workflow with 3 agents; verify correct task assignment and result collection.
- **Relevant Files:** `app/agents/coordinator.py` (new), `app/runtime/runtime.py`, `app/agents/handoff.py`.

**Task 3.2.3: Inter-Agent Handoff Protocol**
- **Description:** Structured state passing between agents (not chat-based). Defines handoff message format, validation, and state transfer.
- **Input Contract:** `handoff(from_agent: str, to_agent: str, state: dict, context: dict) -> HandoffReceipt`
- **Output Contract:** HandoffReceipt (accepted: bool, state_snapshot: dict, timestamp: str).
- **Dependencies:** AgentState TypedDict from `app/langgraph/state.py`.
- **Verification:** Hand off state between two agents; verify state integrity is preserved and receipt is logged.
- **Relevant Files:** `app/agents/handoff.py` (new), `app/langgraph/state.py`, `app/agents/base.py`.

**Task 3.2.4: Dynamic Agent Factory**
- **Description:** Extend `app/runtime/factory.py` to create agents dynamically from AgentConfigV2Model configurations.
- **Input Contract:** `create_from_config(config_id: str) -> AgentWorker`
- **Output Contract:** AgentWorker with configured agent instance, or raises ConfigNotFoundError.
- **Dependencies:** AgentConfigV2Model from `app/memory/models.py`, existing AgentFactory.
- **Verification:** Create agent from DB config; verify agent has correct model, tools, and system prompt.
- **Relevant Files:** `app/runtime/factory.py`, `app/runtime/dynamic_factory.py` (new), `app/memory/models.py`.

**Task 3.2.5: Agent Feedback Loop**
- **Description:** Agents learn from past executions by analyzing success/failure patterns and adjusting behavior.
- **Input Contract:** `record_feedback(agent_id: str, execution_result: dict) -> None`
- **Output Contract:** Updated agent behavior profile stored in persistent memory.
- **Dependencies:** Task 3.4.1 (persistent memory), TraceRepository.
- **Verification:** Run agent with known failure pattern; verify feedback is recorded and subsequent behavior adjusts.
- **Relevant Files:** `app/agents/feedback.py` (new), `app/memory/long_term.py`, `app/agents/base.py`.

**Task 3.2.6: Multi-LLM Provider Abstraction**
- **Description:** Model-agnostic LLM client that supports OpenAI, Anthropic, and other providers.
- **Input Contract:** `complete(messages: list, provider: str, model: str) -> LLMResponse`
- **Output Contract:** LLMResponse (content: str, usage: dict, provider: str, latency_ms: float).
- **Dependencies:** Existing `app/agents/llm_client.py`.
- **Verification:** Run same prompt through two providers; verify consistent output format and correct provider attribution.
- **Relevant Files:** `app/agents/llm_router.py` (new), `app/agents/llm_client.py`, `app/config/settings.py`.

### 3.3 Tool & MCP Tasks

**Task 3.3.1: Tool Permission Model**
- **Description:** Define which agents can use which tools. Enforce permissions at tool execution time.
- **Input Contract:** `check_permission(agent_id: str, tool_name: str) -> PermissionResult`
- **Output Contract:** PermissionResult (allowed: bool, reason: str, required_role: str).
- **Dependencies:** AgentModel and ToolModel from `app/memory/models.py`.
- **Verification:** Attempt tool execution with unauthorized agent; verify permission denied with clear reason.
- **Relevant Files:** `app/tools/permissions.py` (new), `app/tools/registry.py`, `app/memory/models.py`.

**Task 3.3.2: Tool Failure Classification**
- **Description:** Classify tool failures as retryable, fatal, or fallback-available. Drive recovery behavior.
- **Input Contract:** `classify_failure(tool_name: str, error: Exception) -> FailureClassification`
- **Output Contract:** FailureClassification (type: enum, retryable: bool, fallback_tools: list, max_retries: int).
- **Dependencies:** Existing `app/orchestrator/errors.py`, `app/orchestrator/retry.py`.
- **Verification:** Trigger known failure types; verify correct classification and recovery behavior.
- **Relevant Files:** `app/tools/failure_classifier.py` (new), `app/orchestrator/errors.py`, `app/orchestrator/retry.py`.

**Task 3.3.3: Tool Input Validation Pipeline**
- **Description:** Schema → type check → safety check → execution pipeline for all tool invocations.
- **Input Contract:** `validate_tool_input(tool_name: str, arguments: dict) -> ValidationResult`
- **Output Contract:** ValidationResult (valid: bool, errors: list, sanitized_args: dict).
- **Dependencies:** ToolModel parameters_schema, `app/safety/gate.py`, `app/tools/sandbox.py`.
- **Verification:** Submit malformed tool arguments; verify validation catches errors before execution.
- **Relevant Files:** `app/tools/validation.py` (new), `app/tools/sandbox.py`, `app/safety/gate.py`.

**Task 3.3.4: Dynamic Tool Addition/Removal API**
- **Description:** API endpoints to register and unregister tools at runtime without restart.
- **Input Contract:** `register_tool(tool_def: ToolDefinition) -> ToolRegistrationResult`
- **Output Contract:** ToolRegistrationResult (success: bool, tool_id: str, error: str).
- **Dependencies:** ToolRegistry singleton, MCPServerRepository.
- **Verification:** Register new tool via API; verify it appears in tool list and is executable.
- **Relevant Files:** `app/api/routes/tools.py`, `app/tools/registry.py`, `app/memory/long_term.py`.

**Task 3.3.5: Tool Cost Tracking**
- **Description:** Track cost per tool invocation (LLM calls, API calls, compute time).
- **Input Contract:** `record_tool_cost(tool_name: str, cost_usd: float, tokens: int) -> None`
- **Output Contract:** Cost record stored in TokenUsageModel with tool_name label.
- **Dependencies:** TokenUsageModel from `app/memory/models.py`.
- **Verification:** Execute tools with known costs; verify cost records are accurate and queryable.
- **Relevant Files:** `app/tools/cost_tracker.py` (new), `app/memory/models.py`, `app/memory/long_term.py`.

### 3.4 Memory & State Tasks

**Task 3.4.1: Persistent Memory Manager**
- **Description:** Manage persistent memory with TTL-based expiry, size-based pruning, and summarization.
- **Input Contract:** `store(key: str, value: dict, ttl: int, scope: str) -> bool`
- **Output Contract:** Boolean indicating store success; automatic pruning when size limits exceeded.
- **Dependencies:** PostgreSQL (long_term.py), Redis (short_term.py), existing memory models.
- **Verification:** Store memory with 60s TTL; verify it expires automatically. Store beyond size limit; verify oldest entries are pruned.
- **Relevant Files:** `app/memory/persistent.py` (new), `app/memory/long_term.py`, `app/memory/short_term.py`.

**Task 3.4.2: User Memory Profile**
- **Description:** Cross-task knowledge retrieval for individual users. Stores preferences, past patterns, and context.
- **Input Contract:** `get_user_profile(user_id: str) -> UserProfile`
- **Output Contract:** UserProfile with preferences, recent_tasks, learned_patterns, context_summary.
- **Dependencies:** UserModel, TaskRepository, PersistentMemoryManager.
- **Verification:** Complete multiple tasks as same user; verify profile accumulates relevant context.
- **Relevant Files:** `app/memory/user_profile.py` (new), `app/memory/long_term.py`, `app/memory/models.py`.

**Task 3.4.3: Artifact Store**
- **Description:** Structured storage for agent outputs (files, images, data) with metadata and retrieval.
- **Input Contract:** `store_artifact(task_id: str, artifact_type: str, content: bytes, metadata: dict) -> ArtifactRef`
- **Output Contract:** ArtifactRef (id: str, uri: str, metadata: dict, created_at: str).
- **Dependencies:** PostgreSQL for metadata, filesystem or S3 for content storage.
- **Verification:** Store artifact; verify it can be retrieved by ID with correct metadata.
- **Relevant Files:** `app/memory/artifact_store.py` (new), `app/memory/models.py`.

**Task 3.4.4: Task State Machine**
- **Description:** Explicit state machine for task lifecycle: PENDING → PLANNING → EXECUTING → VERIFYING → AWAITING_APPROVAL → COMPLETED/FAILED.
- **Input Contract:** `transition(task_id: str, from_state: str, to_state: str, context: dict) -> StateTransition`
- **Output Contract:** StateTransition (success: bool, new_state: str, timestamp: str, validation_errors: list).
- **Dependencies:** TaskModel, existing state fields in AgentState.
- **Verification:** Run task through all state transitions; verify invalid transitions are rejected.
- **Relevant Files:** `app/orchestrator/state_machine.py` (new), `app/langgraph/state.py`, `app/memory/models.py`.

**Task 3.4.5: Memory Consistency Layer**
- **Description:** Central state source ensuring all components see consistent task state. Resolves conflicts between Redis cache and PostgreSQL.
- **Input Contract:** `get_consistent_state(task_id: str) -> ConsistentState`
- **Output Contract:** ConsistentState with resolved conflicts, source_of_truth indicator, last_updated timestamp.
- **Dependencies:** Redis client, PostgreSQL session, TaskStateMachine.
- **Verification:** Modify state in Redis; verify consistency layer detects conflict and resolves correctly.
- **Relevant Files:** `app/memory/consistency.py` (new), `app/memory/long_term.py`, `app/memory/short_term.py`.

**Task 3.4.6: Execution Replay Service**
- **Description:** Replay any past task execution from stored checkpoints and traces.
- **Input Contract:** `replay(task_id: str, from_checkpoint: str) -> ReplayResult`
- **Output Contract:** ReplayResult (success: bool, replay_log: list, final_state: dict, duration_ms: float).
- **Dependencies:** PostgresCheckpointSaver, TraceRepository, TaskStateMachine.
- **Verification:** Replay a completed task; verify it produces the same final state.
- **Relevant Files:** `app/recovery/replay.py` (new), `app/langgraph/checkpointer.py`, `app/memory/long_term.py`.

### 3.5 Safety & Guardrails Tasks

**Task 3.5.1: Role-Based Access Control**
- **Description:** Enforce role restrictions for agents. Each role has defined permissions for tools, memory access, and actions.
- **Input Contract:** `check_role_permission(role: str, action: str, resource: str) -> bool`
- **Output Contract:** Boolean indicating permission granted or denied.
- **Dependencies:** AgentModel role field, ToolPermission model.
- **Verification:** Attempt action with restricted role; verify access denied.
- **Relevant Files:** `app/safety/rbac.py` (new), `app/memory/models.py`, `app/agents/base.py`.

**Task 3.5.2: Hallucination Grounding Layer**
- **Description:** Cross-reference agent outputs with tools, state, and real data to reduce hallucinations.
- **Input Contract:** `ground_claim(claim: str, available_tools: list, state: dict) -> GroundingResult`
- **Output Contract:** GroundingResult (grounded: bool, evidence: list, confidence: float, ungrounded_parts: list).
- **Dependencies:** ToolRegistry, AgentState, VerificationEngine.
- **Verification:** Feed hallucinated claim; verify grounding layer identifies ungrounded parts.
- **Relevant Files:** `app/safety/grounding.py` (new), `app/capabilities/verification.py`, `app/tools/registry.py`.

**Task 3.5.3: Output Schema Validation**
- **Description:** Validate agent outputs against role-specific schemas before persistence.
- **Input Contract:** `validate_output(agent_role: str, output: dict) -> ValidationResult`
- **Output Contract:** ValidationResult (valid: bool, errors: list, warnings: list).
- **Dependencies:** Existing `app/guardrails/schema.py`, GuardrailRuleRepository.
- **Verification:** Submit output violating schema; verify validation catches all violations.
- **Relevant Files:** `app/guardrails/schema.py`, `app/guardrails/validator.py`, `app/memory/long_term.py`.

**Task 3.5.4: Failure Isolation Boundaries**
- **Description:** Ensure failures in one agent/task don't cascade to others. Separate contexts, independent error handling.
- **Input Contract:** `isolate_context(task_id: str) -> IsolationContext`
- **Output Contract:** IsolationContext with isolated state, independent error handler, resource limits.
- **Dependencies:** TaskStateMachine, AgentPool, Redis locks.
- **Verification:** Cause failure in one task; verify other concurrent tasks continue unaffected.
- **Relevant Files:** `app/orchestrator/isolation.py` (new), `app/runtime/pool.py`, `app/orchestrator/state_machine.py`.

**Task 3.5.5: Audit Trail**
- **Description:** Comprehensive audit log for every decision: routing, tool selection, state transitions, approvals.
- **Input Contract:** `record_audit(event_type: str, actor: str, decision: dict, context: dict) -> AuditRecord`
- **Output Contract:** AuditRecord (id: str, timestamp: str, event_type: str, actor: str, decision: dict).
- **Dependencies:** PostgreSQL for persistent storage, existing TraceModel.
- **Verification:** Execute task; verify all decisions are logged with timestamps and context.
- **Relevant Files:** `app/safety/audit.py` (new), `app/memory/models.py`, `app/memory/long_term.py`.

### 3.6 Observability Tasks

**Task 3.6.1: Complete Trace Schema**
- **Description:** Define trace schema with span types, attributes, and parent-child relationships for end-to-end task tracing.
- **Input Contract:** `create_span(trace_id: str, parent_span_id: str, operation: str, attributes: dict) -> Span`
- **Output Contract:** Span (span_id: str, trace_id: str, parent_span_id: str, operation: str, attributes: dict, start_time: str).
- **Dependencies:** Existing SpanModel, TraceManager in `app/logs/tracing.py`.
- **Verification:** Create parent-child span hierarchy; verify relationships are queryable and correct.
- **Relevant Files:** `app/logs/tracing.py`, `app/memory/models.py`, `app/logs/trace_schema.py` (new).

**Task 3.6.2: Anomaly Detection Engine**
- **Description:** Detect unusual patterns: error rate spikes, latency anomalies, infinite loops, cost outliers.
- **Input Contract:** `analyze_metrics(window: str, thresholds: dict) -> AnomalyReport`
- **Output Contract:** AnomalyReport (anomalies: list, severity: str, affected_tasks: list, recommendations: list).
- **Dependencies:** MetricsCollector, Prometheus metrics, TokenUsageRepository.
- **Verification:** Inject anomalous metrics; verify detection engine identifies them with correct severity.
- **Relevant Files:** `app/logs/anomaly.py` (new), `app/logs/metrics.py`, `app/memory/long_term.py`.

**Task 3.6.3: Alert Manager**
- **Description:** Manage alert rules with severity levels (info, warning, critical) and notification channels.
- **Input Contract:** `evaluate_alert_rules(metrics: dict) -> AlertList`
- **Output Contract:** AlertList with alerts (severity, message, triggered_rule, timestamp).
- **Dependencies:** AnomalyDetector, MetricsCollector.
- **Verification:** Trigger alert conditions; verify alerts are generated with correct severity and routed to channels.
- **Relevant Files:** `app/logs/alerts.py` (new), `app/logs/anomaly.py`, `app/logs/metrics.py`.

**Task 3.6.4: Cost Tracking Dashboard API**
- **Description:** API endpoints for cost data: per-task, per-agent, per-tool, per-user, time-series.
- **Input Contract:** `get_cost_breakdown(scope: str, period: str) -> CostBreakdown`
- **Output Contract:** CostBreakdown with totals, breakdowns, trends, and projections.
- **Dependencies:** TokenUsageRepository, ToolCostTracker, AgentFeedback.
- **Verification:** Query cost data for known executions; verify accuracy and completeness.
- **Relevant Files:** `app/api/routes/observability.py` (new), `app/memory/long_term.py`, `app/tools/cost_tracker.py`.

**Task 3.6.5: Performance Profiler**
- **Description:** Identify bottlenecks in execution: LLM latency, tool latency, orchestration overhead.
- **Input Contract:** `profile_execution(task_id: str) -> ProfileReport`
- **Output Contract:** ProfileReport with per-step latency, bottleneck identification, optimization suggestions.
- **Dependencies:** TraceManager, MetricsCollector, SpanRepository.
- **Verification:** Profile a slow task; verify bottleneck is correctly identified with actionable suggestions.
- **Relevant Files:** `app/logs/profiler.py` (new), `app/logs/tracing.py`, `app/logs/metrics.py`.

### 3.7 Scalability & Concurrency Tasks

**Task 3.7.1: Priority Task Queue**
- **Description:** Task queue with priority levels, scheduling, and worker assignment.
- **Input Contract:** `enqueue(task: Task, priority: int) -> QueuePosition`
- **Output Contract:** QueuePosition (position: int, estimated_wait: float, assigned_worker: str).
- **Dependencies:** Redis for queue storage, AgentPool, TaskStateMachine.
- **Verification:** Enqueue tasks with different priorities; verify execution order matches priority.
- **Relevant Files:** `app/orchestrator/queue.py` (new), `app/runtime/pool.py`, `app/memory/short_term.py`.

**Task 3.7.2: Worker Pool Manager**
- **Description:** Manage worker pools across processes with health checks, scaling, and load balancing.
- **Input Contract:** `manage_workers(target_count: int, health_check_interval: int) -> PoolStatus`
- **Output Contract:** PoolStatus (active_workers: int, healthy_workers: int, pending_tasks: int, load_factor: float).
- **Dependencies:** AgentPool, existing worker.py, Redis for coordination.
- **Verification:** Scale workers up and down; verify health checks detect unhealthy workers.
- **Relevant Files:** `app/runtime/worker_pool.py` (new), `app/runtime/pool.py`, `app/runtime/worker.py`.

**Task 3.7.3: Resource Limit Enforcer**
- **Description:** Enforce resource limits: max concurrent agents, DB connections, Redis connections, memory usage.
- **Input Contract:** `check_resource_availability(resource_type: str, requested: int) -> ResourceGrant`
- **Output Contract:** ResourceGrant (granted: bool, available: int, wait_time: float, reason: str).
- **Dependencies:** AgentPool semaphore, SQLAlchemy pool config, Redis connection pool.
- **Verification:** Request resources beyond limits; verify requests are queued or rejected appropriately.
- **Relevant Files:** `app/runtime/resource_limits.py` (new), `app/runtime/pool.py`, `app/memory/long_term.py`.

**Task 3.7.4: Cache Optimizer**
- **Description:** Cache tool results, LLM responses, and intermediate states to reduce redundant calls.
- **Input Contract:** `cache_get(key: str) -> Optional[CachedResult]`
- **Output Contract:** CachedResult or None; automatic cache invalidation on state changes.
- **Dependencies:** Redis cache, ToolRegistry, LLM router.
- **Verification:** Execute same tool twice; verify second execution uses cached result.
- **Relevant Files:** `app/tools/cache.py` (new), `app/memory/short_term.py`, `app/tools/registry.py`.

**Task 3.7.5: Horizontal Scaling Coordinator**
- **Description:** Coordinate multiple AgentOS instances with shared state, distributed locks, and load balancing.
- **Input Contract:** `register_instance(instance_id: str, capabilities: list) -> InstanceRegistration`
- **Output Contract:** InstanceRegistration (accepted: bool, assigned_tasks: list, cluster_state: dict).
- **Dependencies:** Redis for distributed coordination, existing RedisMCPBus, TaskQueue.
- **Verification:** Start two instances; verify tasks are distributed and state is shared correctly.
- **Relevant Files:** `app/runtime/scaling.py` (new), `app/mcp/bus.py`, `app/orchestrator/queue.py`.

---

## 4. EXECUTION FLOW DESIGN

Complete task lifecycle with state transitions, triggers, data requirements, and failure modes.

### 4.1 State Machine

```
PENDING → PLANNING → EXECUTING → VERIFYING → AWAITING_APPROVAL → COMPLETED
   ↓          ↓           ↓           ↓              ↓
FAILED ←─── FAILED ←─── FAILED ←─── FAILED ←───── REJECTED
```

### 4.2 State Transitions

| From | To | Trigger | Required Data | Failure Mode |
|------|-----|---------|---------------|--------------|
| PENDING | PLANNING | Orchestrator accepts task | task_id, user_id, query, config, trace_id | Validation failure → FAILED |
| PLANNING | EXECUTING | Planner generates plan | plan (list of steps), current_step_index=0 | Planning timeout → FAILED |
| EXECUTING | VERIFYING | All steps executed | steps (list), step_results (dict), tool_calls (list) | Step failure → retry → FAILED after max retries |
| VERIFYING | AWAITING_APPROVAL | Verification passes + approval required | verified=true, verification_notes, approval_mode | Verification fails → replan or FAILED |
| VERIFYING | COMPLETED | Verification passes + no approval required | verified=true, verification_notes, result | Verification fails → replan or FAILED |
| AWAITING_APPROVAL | COMPLETED | User approves | approved=true, approval_reason | User rejects → REJECTED |
| AWAITING_APPROVAL | REJECTED | User rejects | approved=false, approval_reason | Timeout → FAILED |
| Any | FAILED | Unrecoverable error | error (str), error_type, recovery_context | N/A |

### 4.3 Existing Code Paths

**Action V1 Fast Path:**
- Entry: `app/orchestrator/core.py` → `app/action_v1/runner.py`
- Flow: Selector → DeterministicExecutor → DeterministicVerifier → Result
- States: PENDING → EXECUTING → VERIFYING → COMPLETED (skips PLANNING and AWAITING_APPROVAL for simple tasks)
- Failure: Falls back to LangGraph full path

**LangGraph Full Path:**
- Entry: `app/orchestrator/core.py` → `app/orchestrator/task_runner.py` → `app/langgraph/graphs.py`
- Flow: planner_node → executor_node → verifier_node → approval_node (optional) → summarizer_node
- States: PENDING → PLANNING → EXECUTING → VERIFYING → AWAITING_APPROVAL → COMPLETED
- Failure: Checkpoint recovery → retry → legacy fallback

### 4.4 Failure Modes at Each Transition

- **PENDING → PLANNING:** Input validation failure, guardrails block, resource unavailable → FAILED with error context
- **PLANNING → EXECUTING:** Planning timeout, plan generation failure, no feasible plan → FAILED with planning error
- **EXECUTING → VERIFYING:** Tool failure (retryable → retry, fatal → FAILED), step timeout, infinite loop detected → FAILED
- **VERIFYING → AWAITING_APPROVAL:** Verification failure → replan (autonomous mode) or FAILED (task mode)
- **AWAITING_APPROVAL → COMPLETED:** Approval timeout → FAILED, user rejection → REJECTED
- **Any → FAILED:** Unrecoverable error, system crash, resource exhaustion → FAILED with recovery context for resume

---

## 5. DATA & STATE DESIGN

### 5.1 Complete State Schema (Extending AgentState TypedDict)

Extend `app/langgraph/state.py` AgentState with new fields:

| Field | Type | Written By | Description |
|-------|------|-----------|-------------|
| `task_state` | str | TaskStateMachine | Current state machine state (PENDING, PLANNING, etc.) |
| `idempotency_key` | str | Orchestrator | Unique key for duplicate detection |
| `priority` | str | Orchestrator | Task priority level (critical, high, normal, low) |
| `complexity_score` | float | ComplexityScorer | 0.0-1.0 complexity rating |
| `execution_lock_id` | str | ExecutionLock | Redis lock identifier for this task |
| `cost_estimate_usd` | float | CostTracker | Estimated cost before execution |
| `actual_cost_usd` | float | CostTracker | Actual cost after execution |
| `memory_profile_id` | str | UserMemoryProfile | Link to user's memory profile |
| `artifact_refs` | list | ArtifactStore | List of artifact references produced |
| `handoff_log` | list | InterAgentHandoff | Log of all inter-agent handoffs |
| `feedback_records` | list | AgentFeedback | Feedback from past executions |
| `timeout_config` | dict | TimeoutEnforcer | Per-agent/per-tool/per-workflow timeouts |
| `isolation_context` | dict | FailureIsolator | Isolation boundary configuration |
| `audit_trail` | list | AuditTrail | Complete audit log for this task |

### 5.2 Persistence Strategy

| Data Type | Storage | Rationale |
|-----------|---------|-----------|
| Task metadata | PostgreSQL (TaskModel) | Durable, queryable, relational |
| LangGraph checkpoints | PostgreSQL (CheckpointModel) | Required for resume, already implemented |
| Agent state (active) | Redis (ShortTermMemory) | Fast access, TTL-based expiry |
| Agent state (completed) | PostgreSQL (TaskModel.result) | Long-term storage, audit |
| Traces and spans | PostgreSQL (TraceModel, SpanModel) | Queryable, relational, already modeled |
| Metrics | Prometheus (in-memory) + PostgreSQL (aggregated) | Real-time + historical |
| User memory profiles | PostgreSQL (new UserMemoryProfileModel) | Persistent across sessions |
| Artifacts | Filesystem/S3 + PostgreSQL metadata | Large binary data separate from metadata |
| Tool cache | Redis | Fast access, TTL-based invalidation |
| Execution locks | Redis | Distributed coordination, TTL-based |
| Task queue | Redis | Fast enqueue/dequeue, priority support |
| Audit trail | PostgreSQL (new AuditModel) | Immutable, queryable, compliance |

### 5.3 Checkpoint Approach

**Existing:** `app/langgraph/checkpointer.py` PostgresCheckpointSaver saves LangGraph state at each node transition. Handles IntegrityError recovery with savepoint-based duplicate handling.

**Missing:**
- Checkpoint metadata (which node, which step, what was the decision)
- Checkpoint chain traversal (navigate between checkpoints for replay)
- Checkpoint cleanup (remove old checkpoints for completed tasks)
- Cross-process checkpoint access (for horizontal scaling)

**To Build:**
- CheckpointMetadata model in `app/memory/models.py` with node_name, step_index, decision_context
- CheckpointNavigator in `app/recovery/checkpoint_service.py` for chain traversal
- CheckpointCleanupJob for periodic cleanup of completed task checkpoints
- CheckpointReplication for cross-process access in horizontal scaling

### 5.4 Memory Separation

| Memory Type | Scope | Storage | TTL | Access Pattern |
|-------------|-------|---------|-----|----------------|
| Session memory | Single task execution | Redis | Task duration | Read/write during execution |
| Task memory | Single task lifecycle | PostgreSQL | Permanent (with cleanup policy) | Read/write during execution, read-only after |
| User memory | All tasks for a user | PostgreSQL | Permanent (with pruning) | Read during planning, write after completion |
| Shared memory | All tasks, all users | PostgreSQL + Redis | Configurable per key | Read-heavy, write-once |
| Agent memory | Agent-specific learned patterns | PostgreSQL | Permanent (with feedback updates) | Read during execution, write after feedback |

### 5.5 Artifact Storage

- **Location:** Filesystem (local) or S3 (production) for content; PostgreSQL for metadata
- **Schema:** ArtifactModel with id, task_id, agent_id, artifact_type, uri, metadata, created_at
- **Access:** Via ArtifactStore API with task_id and artifact_id lookup
- **Cleanup:** Artifacts older than configurable retention period are archived or deleted

### 5.6 Cleanup/Pruning Rules

| Data Type | Rule | Trigger |
|-----------|------|---------|
| Session memory | Delete on task completion | Task transitions to COMPLETED/FAILED |
| Completed task checkpoints | Keep for 30 days, then archive | Scheduled job (daily) |
| User memory profiles | Prune entries older than 90 days | Scheduled job (weekly) |
| Trace records | Keep for 90 days, then archive | Scheduled job (daily) |
| Audit trail | Keep permanently (compliance) | N/A |
| Tool cache | TTL-based expiry (default 1 hour) | Redis TTL |
| Artifacts | Archive after 30 days, delete after 90 days | Scheduled job (daily) |
| Failed task state | Keep for 7 days for debugging | Scheduled job (daily) |

---

## 6. AGENT SYSTEM DESIGN

### 6.1 Agent Role Taxonomy

| Role | Responsibility | Existing | To Build |
|------|---------------|----------|----------|
| Planner | Generate execution plans from queries | `app/agents/planner.py` | Enhance with complexity-aware planning |
| Executor | Execute plan steps using tools | `app/agents/executor.py` | Enhance with tool permission checks |
| Verifier | Validate execution results | `app/agents/verifier.py` | Enhance with hallucination grounding |
| Reviewer | Review outputs against schemas/rules | No | New: `app/agents/reviewer.py` |
| Summarizer | Compile results into final output | `app/langgraph/nodes.py` (summarizer_node) | Enhance with cost/feedback inclusion |
| Coordinator | Manage multi-agent workflows | No | New: `app/agents/coordinator.py` |

### 6.2 Agent Lifecycle

```
CREATED → REGISTERED → ACTIVE → EXECUTING → IDLE → DECOMMISSIONED
```

1. **CREATED:** Agent instance created from config (AgentConfigV2Model or dynamic config)
2. **REGISTERED:** Agent registered with AgentRuntime via `runtime.register()`
3. **ACTIVE:** Agent available for task assignment, health check passing
4. **EXECUTING:** Agent actively processing a task
5. **IDLE:** Agent finished task, waiting for next assignment
6. **DECOMMISSIONED:** Agent removed from runtime (config change, error, scaling down)

**Lifecycle Management:**
- Creation: `app/runtime/dynamic_factory.py` creates from config
- Registration: `app/runtime/runtime.py` registers with Redis mutex for cross-process safety
- Health check: Periodic ping via `app/runtime/worker.py` inbox queue
- Decommission: Graceful shutdown with task completion before removal

### 6.3 Inter-Agent Communication Protocol

**Not chat-based.** Structured state passing via HandoffMessage:

```
HandoffMessage:
  from_agent: str
  to_agent: str
  task_id: str
  state_snapshot: dict (subset of AgentState)
  context: dict (additional context for receiving agent)
  timestamp: str
  signature: str (integrity verification)
```

**Flow:**
1. Sending agent creates HandoffMessage with relevant state
2. Message validated against schema
3. Message stored in receiving agent's inbox (AgentWorker inbox queue)
4. Receiving agent processes message, updates its state
5. HandoffReceipt returned to sender confirming receipt

**Existing:** `app/runtime/worker.py` has inbox queue mechanism. Extend for inter-agent handoffs.

### 6.4 Agent Constraints and Permissions Model

| Constraint | Description | Enforcement Point |
|------------|-------------|-------------------|
| Tool permissions | Which tools each agent can use | Tool execution in ToolRegistry |
| Memory access | Which memory scopes each agent can read/write | Memory manager access check |
| Action restrictions | Which actions each agent can perform | Orchestrator routing |
| Resource limits | Max tokens, max steps, max time per agent | TimeoutEnforcer, AgentPool |
| Output schema | Required output format per agent role | OutputValidator |

**Implementation:** RBAC system in `app/safety/rbac.py` with role-to-permission mappings stored in PostgreSQL.

### 6.5 Dynamic Agent Creation Rules

1. Agent config must exist in AgentConfigV2Model
2. Config must specify: name, role, model, tools, system_prompt
3. AgentFactory validates config against schema
4. Agent instance created and registered with AgentRuntime
5. Agent health check passes before accepting tasks
6. Agent version tracked for rollback capability

### 6.6 Existing Agent Mapping

| Existing Agent | Maps To | Enhancement Needed |
|----------------|---------|-------------------|
| PlannerAgent | Planner role | Complexity-aware planning, multi-LLM support |
| ExecutorAgent | Executor role | Tool permission checks, cost tracking |
| VerifierAgent | Verifier role | Hallucination grounding, schema validation |
| summarizer_node | Summarizer role | Cost/feedback inclusion in summary |
| core_planner | Planner (runtime) | Already registered via AgentRuntime |
| core_executor | Executor (runtime) | Already registered via AgentRuntime |
| core_verifier | Verifier (runtime) | Already registered via AgentRuntime |

---

## 7. TOOL SYSTEM DESIGN

### 7.1 Complete Tool Registration Lifecycle

1. **Discovery:** Tool discovered via MCP server startup or manual registration
2. **Validation:** Tool definition validated against ToolModel schema
3. **Registration:** Tool registered with ToolRegistry singleton (idempotent)
4. **Permission Assignment:** Tool assigned to agent roles via RBAC
5. **Activation:** Tool marked active and available for execution
6. **Monitoring:** Tool invocations tracked for cost, latency, error rate
7. **Deprecation:** Tool marked deprecated, existing tasks complete, no new assignments
8. **Removal:** Tool removed from registry after all dependent tasks complete

### 7.2 Tool Discovery Mechanism

- **MCP servers:** Auto-discovered on startup via `app/mcp/client_manager.py`
- **Built-in tools:** Registered at startup via ToolRegistry singleton
- **Dynamic tools:** Registered via API endpoint (`POST /api/v1/tools`)
- **External tools:** Discovered via tool catalog API (future)

### 7.3 Input Validation Pipeline

```
Tool Input → Schema Validation → Type Check → Safety Check → Permission Check → Execution
```

1. **Schema Validation:** Arguments match ToolModel.parameters_schema (JSON Schema)
2. **Type Check:** Argument types match expected types (string, number, boolean, etc.)
3. **Safety Check:** `app/safety/gate.py` blocks credential patterns, dangerous operations
4. **Permission Check:** `app/tools/permissions.py` verifies agent has tool access
5. **Execution:** Tool executed via ToolRegistry → MCPWrappedTool or built-in tool

### 7.4 Tool Permission Model

| Agent Role | Allowed Tools | Denied Tools |
|------------|--------------|--------------|
| Planner | read-only tools (filesystem__read_file, cloud_api__search_web) | write tools, shell execution |
| Executor | All tools assigned to task | Tools not in task config |
| Verifier | read-only tools, verification tools | write tools, shell execution |
| Reviewer | read-only tools | All write tools |
| Coordinator | All tools (workflow management) | None |

**Enforcement:** `app/tools/permissions.py` checked before every tool invocation.

### 7.5 Tool Failure Classification

| Classification | Description | Recovery | Max Retries |
|----------------|-------------|----------|-------------|
| RETRYABLE | Transient error (timeout, connection) | Retry with backoff | 3 |
| FATAL | Permanent error (invalid input, permission denied) | No retry, fail immediately | 0 |
| FALLBACK_AVAILABLE | Tool unavailable but alternative exists | Switch to fallback tool | 1 per fallback |

**Implementation:** `app/tools/failure_classifier.py` analyzes error type and tool context.

### 7.6 Dynamic Tool Addition/Removal Procedure

**Addition:**
1. POST `/api/v1/tools` with tool definition
2. Tool validated against schema
3. Tool registered with ToolRegistry (idempotent)
4. Tool persisted to ToolModel in PostgreSQL
5. Tool available for immediate use

**Removal:**
1. POST `/api/v1/tools/{name}/deactivate`
2. Tool marked inactive in ToolRegistry
3. Existing tasks using tool complete normally
4. Tool removed from ToolRegistry after no active references
5. Tool marked deprecated in PostgreSQL (soft delete)

### 7.7 MCP Server Extension

Existing MCP servers (filesystem, shell, browser) extend the tool system via:
- `app/mcp/client_manager.py` manages server lifecycle
- `app/tools/registry.py` wraps MCP tools as MCPWrappedTool
- Tool naming: `{server_name}__{tool_name}` convention
- New MCP servers follow same pattern: create server module, register with client_manager, tools auto-discovered

---

## 8. FAILURE HANDLING PLAN

### 8.1 Failure Type Classification

| Failure Type | Scope | Detection | Examples |
|--------------|-------|-----------|----------|
| Input Validation | Task entry | Guardrails validator | Malformed query, blocked keywords |
| Planning Failure | Planning phase | Planner timeout, no plan | Complex query, no feasible plan |
| Tool Failure | Tool execution | ToolOutput.success=false | API down, permission denied, timeout |
| Agent Failure | Agent execution | AgentOutput.status=FAILURE | LLM error, context overflow |
| State Transition | State machine | Invalid transition | Concurrent state conflict |
| System Failure | Infrastructure | Health check failure | DB down, Redis down, OOM |
| Timeout | Any phase | Timer expiration | LLM slow, tool slow, orchestration slow |
| Infinite Loop | Execution loop | ActionStabilizer detection | Same action repeated 3x with no state change |

### 8.2 Detection Mechanisms

| Failure Type | Detection Mechanism | Existing | To Build |
|--------------|--------------------|----------|----------|
| Input Validation | Guardrails validator | `app/guardrails/validator.py` | Enhanced with role-specific rules |
| Planning Failure | Timeout + plan quality check | Partial (timeout in settings) | Plan quality scoring |
| Tool Failure | ToolOutput.success flag | `app/tools/base.py` | Failure classifier |
| Agent Failure | AgentOutput.status check | `app/agents/base.py` | Agent health monitoring |
| State Transition | State machine validation | No | TaskStateMachine |
| System Failure | Health check endpoints | `/health/ready`, `/health/live` | Component-level health checks |
| Timeout | Timer comparison | `app/orchestrator/retry.py` | Per-phase timeout enforcement |
| Infinite Loop | ActionStabilizer no-change detection | `app/environments/execution_stabilizer.py` | Extend to non-desktop tasks |

### 8.3 Recovery Strategies

| Failure Type | Strategy | Max Retries | Backoff |
|--------------|----------|-------------|---------|
| Input Validation | Reject with clear error | 0 | N/A |
| Planning Failure | Replan with simplified scope | 2 | Exponential (1s, 2s) |
| Tool Failure (RETRYABLE) | Retry same tool | 3 | Exponential (1s, 2s, 4s) |
| Tool Failure (FALLBACK) | Switch to fallback tool | 1 per fallback | Linear (2s) |
| Tool Failure (FATAL) | Fail immediately, log | 0 | N/A |
| Agent Failure | Retry with fallback agent | 2 | Exponential (2s, 4s) |
| State Transition | Rollback to last valid state | 1 | N/A |
| System Failure | Wait for recovery, resume from checkpoint | 3 | Exponential (5s, 10s, 20s) |
| Timeout | Abort current phase, replan or fail | 1 | N/A |
| Infinite Loop | Abort, escalate to human | 0 | N/A |

### 8.4 Maximum Retry Counts and Backoff Strategy

**Global defaults** (from `app/config/settings.py`):
- MAX_RETRIES=3
- TIMEOUT_DEFAULT=300s
- MAX_STEPS_DEFAULT=10

**Per-component overrides:**
- Tool retries: ToolModel.max_retries (default 2)
- Agent retries: AgentConfigV2Model.max_retry_limit (default 2)
- Orchestrator retries: RetryConfig.max_retries (default 3)
- Backoff: exponential_base=2.0, base_delay=1.0, max_delay=30.0 (from `app/orchestrator/retry.py`)

### 8.5 Failure Isolation Boundaries

| Boundary | Isolation Mechanism | Scope |
|----------|--------------------|-------|
| Task isolation | Separate AgentState per task | Per task |
| Agent isolation | Separate AgentWorker per agent | Per agent |
| Tool isolation | Separate execution context per tool call | Per tool invocation |
| Memory isolation | Separate Redis keys per task | Per task |
| Error isolation | Try/catch at every node boundary | Per node |

**Implementation:** `app/orchestrator/isolation.py` with context managers for each boundary.

### 8.6 Existing vs Gaps

| Component | Existing | Gap |
|-----------|----------|-----|
| ActionStabilizer | Retry with backoff, infinite loop detection, popup dismissal | Desktop-only, needs generalization |
| RecoveryEngine | RecoveryStrategy.DESKTOP (re-focus, rebuild, vision escalate, popup dismiss) | Desktop-only, needs general task recovery |
| RetryConfig | Exponential backoff with configurable params | No per-component overrides |
| Error types | AgentOSError, RetryableError, UnrecoverableError, ErrorCode | No failure classification for tools |
| Checkpoint recovery | PostgresCheckpointSaver with IntegrityError recovery | No cross-process checkpoint access |
| Orchestrator fallback | LangGraph → checkpoint recovery → legacy fallback | No priority-based fallback |

---

## 9. CONCURRENCY & SCALING PLAN

### 9.1 Task Queue Architecture

**Priority Levels:** critical (0) > high (1) > normal (2) > low (3)

**Queue Implementation:** Redis sorted sets with priority scores.

**Components:**
- **Enqueue:** Task submitted → assigned priority → added to Redis sorted set
- **Dequeue:** Worker polls queue → pops highest priority task → acquires execution lock
- **Scheduling:** Delayed tasks stored with future timestamp → moved to active queue when ready
- **Worker Assignment:** Tasks assigned to available workers based on capability match

**Existing:** No task queue. Tasks execute immediately via `orchestrator.execute_task()`.

**To Build:** `app/orchestrator/queue.py` with Redis-backed priority queue.

### 9.2 Concurrency Model

| Level | Mechanism | Limit |
|-------|-----------|-------|
| Within process | Asyncio event loop | 10,000+ coroutines (limited by DB connections) |
| Across processes | Worker pool with Redis coordination | Configurable (default 100 via AgentPool) |
| Per task | Single-threaded execution (LangGraph) | 1 task = 1 execution thread |
| Per agent | AgentPool semaphore | 100 concurrent agents (configurable) |
| Per tool | Tool-level semaphore | Configurable per tool |

**Existing:** `app/runtime/pool.py` AgentPool with semaphore(100). Asyncio for within-process concurrency.

**To Build:** Worker pool manager for cross-process coordination, tool-level semaphores.

### 9.3 Resource Limits

| Resource | Limit | Enforcement | Configuration |
|----------|-------|-------------|---------------|
| Concurrent agents | 100 | AgentPool semaphore | settings.MAX_CONCURRENT_AGENTS |
| DB connections | 20 pool + 40 overflow | SQLAlchemy pool config | settings.DATABASE_URL pool params |
| Redis connections | 50 | Redis connection pool | `app/memory/short_term.py` max_connections |
| Memory per task | 100MB | TaskStateMachine check | Configurable per task |
| LLM calls per minute | 60 | Rate limiter | settings.RATE_LIMIT |
| Tool invocations per task | 50 | ToolRegistry counter | Configurable per tool |

### 9.4 Bottleneck Identification and Mitigation

| Bottleneck | Impact | Mitigation |
|------------|--------|------------|
| LLM latency | High (seconds per call) | Caching, parallel execution, smaller models for simple tasks |
| Tool latency | Medium (varies by tool) | Timeout enforcement, fallback tools, result caching |
| Orchestration overhead | Low (milliseconds) | Action V1 fast path for simple tasks, graph cache |
| DB connection pool | Medium (connection exhaustion) | Connection pooling, query optimization, read replicas |
| Redis connection pool | Low (50 connections sufficient) | Connection reuse, pipeline commands |
| Memory usage | Medium (large contexts) | Context pruning, summarization, streaming |

### 9.5 Horizontal Scaling Approach

**When single instance isn't enough:**
- Task throughput > 100 tasks/minute
- Concurrent users > 50
- Memory usage > 80% of available RAM
- LLM API rate limits reached

**Scaling strategy:**
1. Multiple AgentOS instances share PostgreSQL and Redis
2. Redis coordinates task distribution via priority queue
3. Each instance registers with HorizontalScalingCoordinator
4. Tasks distributed based on instance capacity and capability
5. State shared via PostgreSQL (checkpoints, task state, memory)
6. Real-time events via Redis pub/sub (RedisMCPBus, RedisEventBus)

**Existing:** `app/mcp/bus.py` has RedisMCPBus for multi-instance. `app/orchestrator/event_bus.py` has event bus.

**To Build:** `app/runtime/scaling.py` for instance coordination and load balancing.

### 9.6 AgentPool Integration

**Existing:** `app/runtime/pool.py` AgentPool with semaphore(100) limits concurrent agent executions.

**Enhancement:**
- Add per-agent-type limits (e.g., max 10 planners, max 50 executors)
- Add health check integration (unhealthy agents removed from pool)
- Add dynamic scaling (pool size adjusts based on load)
- Add priority-based agent assignment (critical tasks get agents first)

---

## 10. OBSERVABILITY DESIGN

### 10.1 Complete Log Structure

**Format:** JSON structured logging via `app/logs/logger.py`.

| Field | Type | Description |
|-------|------|-------------|
| timestamp | str | ISO 8601 timestamp |
| level | str | DEBUG, INFO, WARNING, ERROR, CRITICAL |
| message | str | Human-readable message |
| task_id | str | Task identifier (if applicable) |
| trace_id | str | Trace identifier for correlation |
| span_id | str | Span identifier for nested operations |
| agent_id | str | Agent identifier (if applicable) |
| tool_name | str | Tool name (if applicable) |
| duration_ms | float | Operation duration |
| error | str | Error message (if applicable) |
| metadata | dict | Additional context |

**Log Levels:**
- DEBUG: Detailed execution steps (tool calls, state changes)
- INFO: Task lifecycle events (start, complete, fail)
- WARNING: Recoverable issues (retries, fallbacks, degraded performance)
- ERROR: Unrecoverable failures (tool fatal errors, system crashes)
- CRITICAL: System-wide issues (DB down, Redis down, OOM)

### 10.2 Trace Schema

**Span Types:**
- `task`: Root span for entire task execution
- `planning`: Planner node execution
- `execution`: Executor node execution (may contain child spans for tool calls)
- `tool_call`: Individual tool invocation
- `verification`: Verifier node execution
- `approval`: Approval node execution
- `summarization`: Summarizer node execution
- `recovery`: Recovery attempt
- `handoff`: Inter-agent handoff

**Attributes per Span:**
- span_id, trace_id, parent_span_id
- operation (span type)
- agent_name
- status (pending, success, failure)
- error (if failed)
- metadata (operation-specific data)
- start_time, end_time

**Parent-Child Relationships:**
- task span → planning span → execution span → tool_call span
- task span → verification span
- task span → approval span
- task span → summarization span
- execution span → recovery span (if recovery triggered)
- execution span → handoff span (if inter-agent handoff)

**Existing:** `app/logs/tracing.py` TraceManager with SpanModel. `app/memory/models.py` has TraceModel, SpanModel, NodeTraceModel.

**To Build:** Complete trace schema enforcement, parent-child relationship validation, trace query API.

### 10.3 Metrics Catalog

**Existing Metrics** (from `app/logs/metrics.py`):
| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| desktop_task_duration | Histogram | success | Total task execution time |
| desktop_task_total | Counter | success | Total tasks executed |
| desktop_action_count | Counter | action | Actions executed per type |
| desktop_retry_count | Counter | action | Retries per action type |
| desktop_perception_layer | Counter | layer | UIA or vision fallback usage |

**New Metrics to Add:**
| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| task_duration | Histogram | mode, success, priority | Task execution time by mode |
| task_total | Counter | mode, success | Total tasks by mode |
| tool_invocation_count | Counter | tool_name, success | Tool invocations |
| tool_latency | Histogram | tool_name | Tool execution latency |
| tool_error_rate | Gauge | tool_name | Tool error rate (last 5 min) |
| agent_execution_count | Counter | agent_role, success | Agent executions |
| agent_latency | Histogram | agent_role | Agent execution latency |
| llm_token_usage | Counter | model, task_id | Token usage per model |
| llm_cost_usd | Counter | model, task_id | Cost per model |
| memory_usage_bytes | Gauge | scope | Memory usage by scope |
| queue_depth | Gauge | priority | Tasks waiting in queue |
| active_agents | Gauge | agent_role | Currently active agents |
| checkpoint_count | Counter | task_id | Checkpoints saved per task |
| recovery_count | Counter | strategy, success | Recovery attempts |
| handoff_count | Counter | from_agent, to_agent | Inter-agent handoffs |
| anomaly_count | Counter | anomaly_type | Detected anomalies |

**Aggregation Rules:**
- Counters: cumulative, reset on restart
- Histograms: buckets at [0.1, 0.5, 1, 2.5, 5, 10, 25, 50, 100, 250, 500, 1000] seconds
- Gauges: current value, sampled every 10 seconds

### 10.4 Dashboard Requirements

**Operator Dashboard:**
- Active tasks count by status (PENDING, EXECUTING, VERIFYING, COMPLETED, FAILED)
- Task throughput (tasks/minute) over time
- Error rate over time
- Average task latency over time
- Agent utilization (active vs idle)
- Tool usage heatmap
- Queue depth by priority
- System resource usage (CPU, memory, DB connections, Redis connections)

**Cost Dashboard:**
- Total cost over time (daily, weekly, monthly)
- Cost breakdown by model, agent, tool
- Cost per task average
- Cost projection based on current rate
- Top cost-consuming tasks

**Debug Dashboard:**
- Task trace viewer (end-to-end span tree)
- Error log viewer with filtering
- Replay viewer for past tasks
- Anomaly timeline
- Agent decision log

### 10.5 Alert Rules

| Rule | Condition | Severity | Action |
|------|-----------|----------|--------|
| High error rate | Error rate > 10% in 5 min | Critical | Page on-call, auto-scale |
| Task latency spike | P99 latency > 2x baseline | Warning | Investigate, notify |
| Queue depth high | Queue depth > 100 | Warning | Scale workers |
| Agent pool exhausted | Active agents = max | Critical | Scale pool, notify |
| DB connection pool exhausted | Active connections = max | Critical | Investigate, notify |
| Memory usage high | Memory > 80% | Warning | Prune memory, notify |
| Cost spike | Cost > 2x daily average | Warning | Investigate, notify |
| Anomaly detected | Anomaly score > threshold | Warning | Investigate, notify |
| System health check failure | Health check fails | Critical | Auto-restart, page on-call |

### 10.6 Execution Replay Mechanism

**Process:**
1. Select task_id and checkpoint_id to replay from
2. Load checkpoint state from PostgresCheckpointSaver
3. Load trace data from TraceRepository
4. Reconstruct AgentState from checkpoint
5. Replay execution step by step, logging each step
6. Compare replay result with original result
7. Generate replay report with differences

**Existing:** `app/recovery/checkpoint_service.py` has CheckpointRecoveryService for resume.

**To Build:** `app/recovery/replay.py` with full replay capability, comparison engine, and report generation.

### 10.7 Anomaly Detection Approach

**Detection Methods:**
1. **Statistical:** Z-score analysis of metrics (latency, error rate, cost)
2. **Pattern-based:** Detect repeated failure patterns, infinite loops
3. **Threshold-based:** Metrics exceed configured thresholds
4. **Trend-based:** Metrics trending in concerning direction (increasing errors, increasing latency)

**Implementation:** `app/logs/anomaly.py` with sliding window analysis, configurable thresholds, and anomaly scoring.

### 10.8 Existing vs Missing

| Component | Existing | Missing |
|-----------|----------|---------|
| Structured logging | `app/logs/logger.py` | Complete log schema enforcement |
| Tracing | `app/logs/tracing.py`, SpanModel | Parent-child relationships, trace query API |
| Metrics | `app/logs/metrics.py`, Prometheus | Task/agent/tool metrics, cost metrics |
| Dashboards | None | Operator, cost, debug dashboards |
| Alerts | None | Alert rules, notification channels |
| Replay | CheckpointRecoveryService | Full execution replay with comparison |
| Anomaly detection | None | Statistical, pattern, threshold, trend detection |
| Cost tracking | TokenUsageModel | Per-task/agent/tool cost aggregation |

---

## 11. IMPLEMENTATION ORDER

Dependency-ordered list of files/modules to create or modify. Each entry specifies phase, dependencies, and dependents.

### Phase 1: MVP Hardening

| # | File Path | Action | Phase | Depends On | Depended By |
|---|-----------|--------|-------|------------|-------------|
| 1.1 | `app/orchestrator/errors.py` | Modify | Phase 1 | None | 1.2, 1.3, 1.4, 1.5 |
| 1.2 | `app/orchestrator/core.py` | Modify | Phase 1 | 1.1 | 1.3, 1.4 |
| 1.3 | `app/guardrails/validator.py` | Modify | Phase 1 | 1.1 | 1.4, 1.5 |
| 1.4 | `app/langgraph/nodes.py` | Modify | Phase 1 | 1.2, 1.3 | 1.5 |
| 1.5 | `app/logs/logger.py` | Modify | Phase 1 | 1.1 | 2.1, 2.2 |
| 1.6 | `app/api/routes/tasks.py` | Modify | Phase 1 | 1.2 | 2.1 |
| 1.7 | `tests/test_orchestrator_fallback.py` | Create | Phase 1 | 1.2 | None |
| 1.8 | `tests/test_guardrails_integration.py` | Create | Phase 1 | 1.3 | None |

### Phase 2: Core Stability

| # | File Path | Action | Phase | Depends On | Depended By |
|---|-----------|--------|-------|------------|-------------|
| 2.1 | `app/memory/models.py` | Modify | Phase 2 | 1.5 | 2.2, 2.3, 2.4, 2.5, 2.6 |
| 2.2 | `app/memory/persistent.py` | Create | Phase 2 | 2.1, 1.5 | 2.3, 2.4, 2.5 |
| 2.3 | `app/memory/user_profile.py` | Create | Phase 2 | 2.2 | 3.2.5 |
| 2.4 | `app/memory/artifact_store.py` | Create | Phase 2 | 2.1 | 3.4.3 |
| 2.5 | `app/memory/consistency.py` | Create | Phase 2 | 2.2, 1.5 | 3.4.5 |
| 2.6 | `app/orchestrator/state_machine.py` | Create | Phase 2 | 2.1 | 3.4.4, 4.1, 4.3 |
| 2.7 | `app/orchestrator/idempotency.py` | Create | Phase 2 | 1.5 | 3.1.3 |
| 2.8 | `app/recovery/replay.py` | Create | Phase 2 | 2.6, 1.5 | 3.6.2 |
| 2.9 | `app/recovery/checkpoint_service.py` | Modify | Phase 2 | 2.6 | 2.8 |
| 2.10 | `tests/test_state_machine.py` | Create | Phase 2 | 2.6 | None |
| 2.11 | `tests/test_persistent_memory.py` | Create | Phase 2 | 2.2 | None |
| 2.12 | `tests/test_idempotency.py` | Create | Phase 2 | 2.7 | None |

### Phase 3: Multi-Agent Coordination

| # | File Path | Action | Phase | Depends On | Depended By |
|---|-----------|--------|-------|------------|-------------|
| 3.1 | `app/agents/handoff.py` | Create | Phase 3 | 2.6 | 3.2, 3.3 |
| 3.2 | `app/agents/reviewer.py` | Create | Phase 3 | 3.1, 1.3 | 3.3 |
| 3.3 | `app/agents/coordinator.py` | Create | Phase 3 | 3.1, 3.2 | 3.4 |
| 3.4 | `app/runtime/dynamic_factory.py` | Create | Phase 3 | 2.1 | 3.5 |
| 3.5 | `app/agents/feedback.py` | Create | Phase 3 | 2.3, 2.2 | 3.6 |
| 3.6 | `app/agents/llm_router.py` | Create | Phase 3 | 1.5 | None |
| 3.7 | `app/langgraph/collaboration.py` | Create | Phase 3 | 3.1, 3.3 | None |
| 3.8 | `app/safety/rbac.py` | Create | Phase 3 | 2.1 | 3.9, 3.10 |
| 3.9 | `app/safety/grounding.py` | Create | Phase 3 | 3.8 | None |
| 3.10 | `app/safety/audit.py` | Create | Phase 3 | 2.1 | None |
| 3.11 | `tests/test_inter_agent_handoff.py` | Create | Phase 3 | 3.1 | None |
| 3.12 | `tests/test_reviewer_agent.py` | Create | Phase 3 | 3.2 | None |
| 3.13 | `tests/test_rbac.py` | Create | Phase 3 | 3.8 | None |

### Phase 4: Production Reliability

| # | File Path | Action | Phase | Depends On | Depended By |
|---|-----------|--------|-------|------------|-------------|
| 4.1 | `app/orchestrator/queue.py` | Create | Phase 4 | 2.6, 2.7 | 4.2, 4.6 |
| 4.2 | `app/orchestrator/timeouts.py` | Create | Phase 4 | 2.6 | 4.3 |
| 4.3 | `app/orchestrator/isolation.py` | Create | Phase 4 | 2.6, 4.2 | 4.4 |
| 4.4 | `app/orchestrator/loop_detector.py` | Create | Phase 4 | 4.3 | None |
| 4.5 | `app/orchestrator/locks.py` | Create | Phase 4 | 1.5 | 4.1 |
| 4.6 | `app/runtime/worker_pool.py` | Create | Phase 4 | 4.1 | 4.7 |
| 4.7 | `app/logs/cost_tracker.py` | Create | Phase 4 | 2.1 | 5.4 |
| 4.8 | `app/tools/permissions.py` | Create | Phase 4 | 3.8 | 4.9 |
| 4.9 | `app/tools/failure_classifier.py` | Create | Phase 4 | 1.1 | 4.10 |
| 4.10 | `app/tools/validation.py` | Create | Phase 4 | 4.8, 4.9 | None |
| 4.11 | `app/tools/cost_tracker.py` | Create | Phase 4 | 4.7 | None |
| 4.12 | `tests/test_task_queue.py` | Create | Phase 4 | 4.1 | None |
| 4.13 | `tests/test_timeout_enforcer.py` | Create | Phase 4 | 4.2 | None |
| 4.14 | `tests/test_tool_permissions.py` | Create | Phase 4 | 4.8 | None |

### Phase 5: Scaling & Optimization

| # | File Path | Action | Phase | Depends On | Depended By |
|---|-----------|--------|-------|------------|-------------|
| 5.1 | `app/runtime/scaling.py` | Create | Phase 5 | 4.1, 4.6 | 5.5 |
| 5.2 | `app/logs/anomaly.py` | Create | Phase 5 | 1.5, 4.7 | 5.3 |
| 5.3 | `app/logs/alerts.py` | Create | Phase 5 | 5.2 | None |
| 5.4 | `app/tools/cache.py` | Create | Phase 5 | 4.7, 1.5 | None |
| 5.5 | `app/runtime/resource_limits.py` | Create | Phase 5 | 5.1 | None |
| 5.6 | `app/api/routes/observability.py` | Create | Phase 5 | 4.7, 5.2, 5.3 | None |
| 5.7 | `app/logs/profiler.py` | Create | Phase 5 | 1.5, 4.7 | None |
| 5.8 | `tests/test_anomaly_detection.py` | Create | Phase 5 | 5.2 | None |
| 5.9 | `tests/test_horizontal_scaling.py` | Create | Phase 5 | 5.1 | None |
| 5.10 | `tests/test_cache_optimizer.py` | Create | Phase 5 | 5.4 | None |

---

## 12. RESUME STRATEGY

### 12.1 Checkpointing Work Mid-Build

**File-based progress tracking:**
- Maintain `workspace/build_progress.md` with phase completion status
- Each task marked as: NOT_STARTED, IN_PROGRESS, COMPLETED, BLOCKED
- Last completed task recorded with timestamp

**Git-based checkpointing:**
- Commit after each completed task with descriptive message
- Tag each phase completion: `phase-1-complete`, `phase-2-complete`, etc.
- Branch per phase: `phase-1-mvp-hardening`, `phase-2-core-stability`, etc.

**State persistence between sessions:**
- `workspace/build_state.json` with current phase, current task, completed tasks
- Environment variables for database/redis connection strings preserved in `.env`
- Test results logged to `workspace/test_results.log`

### 12.2 State Persisted Between Build Sessions

| State | Location | Format |
|-------|----------|--------|
| Build progress | `workspace/build_progress.md` | Markdown with checkboxes |
| Build state | `workspace/build_state.json` | JSON with phase/task/completed |
| Git state | Git repository | Commits, tags, branches |
| Test results | `workspace/test_results.log` | Text log |
| Database schema | PostgreSQL | Migrations via SQLAlchemy |
| Environment config | `.env` | Key-value pairs |
| Dependencies | `requirements.txt`, `package.json` | Package lists |

### 12.3 Detecting Partially-Built State

**Detection methods:**
1. Check `workspace/build_state.json` for current phase and task
2. Check git log for last commit message (contains task identifier)
3. Check if files listed in implementation order exist and have expected content
4. Run `pytest` to identify which tests pass/fail (indicates completion status)
5. Check database for new tables/models added by completed phases

**Recovery procedure:**
1. Read `workspace/build_state.json` to identify last completed task
2. Verify last completed task's files exist and tests pass
3. Resume from next task in implementation order
4. If last task was IN_PROGRESS, review changes and either complete or revert

### 12.4 Rolling Back Incomplete Work

**Rollback procedure:**
1. Identify the incomplete task from `workspace/build_state.json`
2. If files were created: delete them and remove from imports
3. If files were modified: `git checkout` to restore pre-modification state
4. If database models were added: create rollback migration
5. Update `workspace/build_state.json` to mark task as NOT_STARTED
6. Run `pytest` to verify system is in clean state

**Safety measures:**
- Commit before starting each task (easy rollback via `git reset`)
- Use feature branches per phase (isolate changes)
- Database migrations are reversible (define downgrade path)
- Test suite validates system integrity after rollback

### 12.5 Verification Checklist per Build Milestone

**Phase 1 Verification:**
- [ ] All existing tests pass (except known pre-existing failure)
- [ ] `app/orchestrator/errors.py` has unified error types
- [ ] Input validation covers all API endpoints
- [ ] Guardrails integrated at orchestrator entry point
- [ ] Output validation at every node exit point
- [ ] Orchestrator fallback chain tested end-to-end
- [ ] Consistent logging format across all modules

**Phase 2 Verification:**
- [ ] PersistentMemoryManager stores and retrieves with TTL
- [ ] Memory pruning works when size limits exceeded
- [ ] UserMemoryProfile accumulates context across tasks
- [ ] ArtifactStore stores and retrieves artifacts
- [ ] TaskStateMachine enforces valid transitions
- [ ] Memory consistency layer resolves conflicts
- [ ] Execution replay produces same final state
- [ ] Idempotency enforcement rejects duplicates

**Phase 3 Verification:**
- [ ] Inter-agent handoff preserves state integrity
- [ ] ReviewerAgent correctly validates outputs
- [ ] CoordinatorAgent manages multi-agent workflows
- [ ] Dynamic agent creation from config works
- [ ] Agent feedback loop records and applies feedback
- [ ] Multi-LLM provider abstraction works with 2+ providers
- [ ] RBAC enforces role restrictions
- [ ] Hallucination grounding identifies ungrounded claims
- [ ] Audit trail records all decisions

**Phase 4 Verification:**
- [ ] Task queue respects priority ordering
- [ ] Cost tracking records per-task/agent/tool costs
- [ ] Timeouts enforced at agent/tool/workflow levels
- [ ] Failure isolation prevents cascade failures
- [ ] Infinite loop detection works for non-desktop tasks
- [ ] Execution locks prevent duplicate processing
- [ ] Worker pool manages health and scaling
- [ ] Tool permissions enforced at execution time
- [ ] Tool failure classification drives correct recovery

**Phase 5 Verification:**
- [ ] Horizontal scaling distributes tasks across instances
- [ ] Anomaly detection identifies unusual patterns
- [ ] Alert rules trigger at correct thresholds
- [ ] Tool cache reduces redundant calls
- [ ] Resource limits enforced correctly
- [ ] Observability API returns accurate data
- [ ] Performance profiler identifies bottlenecks
- [ ] All metrics exposed via Prometheus endpoint
- [ ] Dashboards display accurate real-time data

---

## REQUIREMENT COVERAGE MATRIX

Maps every requirement from the 13 Q&A sections to at least one concrete build task.

| Q&A Section | Requirement | Build Task(s) |
|-------------|------------|---------------|
| 1. Problem & Purpose | Multi-step execution with planning, delegation, validation, retries | 3.1.1, 3.1.2, 3.4.4, 8.3 |
| 2. Core Explanation | OS for AI agents, not chatbot | 6.1, 6.3, 4.1 |
| 3. Real-World Usage | Long-running workflows, multiple users, cross-industry | 3.4.1, 3.4.2, 3.7.1, 3.7.5 |
| 4. System Architecture | Orchestrator, agents, tools, memory, state, observability | All 8 subsystems (1.1-1.8) |
| 5. Execution Flow | Planning before execution, step-by-step, validation, retry/replan | 4.1-4.4, 8.1-8.3 |
| 6. Production Behavior | Queued, scheduled, parallel, no duplicates, no infinite loops, timeouts, crash recovery, resume | 3.7.1, 3.1.3, 3.4.6, 4.2, 4.4, 4.5 |
| 7. Reliability & Safety | Role restrictions, input validation, tool permissions, output validation, hallucination reduction, failure isolation, audit | 3.5.1-3.5.5, 3.3.1, 3.3.3 |
| 8. State & Memory | Task status, temp memory, persistent memory, pruning, expiry, shared memory, consistency | 3.4.1-3.4.6, 5.4-5.6 |
| 9. Tools & Integration | Registry, discovery, input validation, failure handling, external integration | 3.3.1-3.3.5, 7.1-7.7 |
| 10. Scalability | Role separation, queues, scheduling, workers, checkpoints, bottleneck mitigation, cost control | 3.7.1-3.7.5, 9.1-9.6 |
| 11. Monitoring & Debugging | Logs, traces, metrics, task tracing, debug failures, success metrics, anomaly detection, replay | 3.6.1-3.6.5, 10.1-10.8 |
| 12. Product Thinking | MVP → core stability → multi-agent → production → scaling | Phases 1-5 |
| 13. Advanced | Autonomous systems, dynamic collaboration, multi-LLM, agent improvement, real-time, distributed workflows | 3.2.1-3.2.6, 3.6.2, 3.7.5 |
