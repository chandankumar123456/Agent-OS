# Data & State Design + Agent System Design Implementation Plan

## Overview
Implement Sections 5 (Data & State Design) and 6 (Agent System Design) from the build plan.

## Phase 1: Extend AgentState TypedDict (Section 5.1)
**Goal:** Add new fields to `app/langgraph/state.py` AgentState

**Tasks:**
1. Add task_state field (str) - Current state machine state
2. Add idempotency_key field (str) - Duplicate detection
3. Add priority field (str) - Task priority level
4. Add complexity_score field (float) - 0.0-1.0 rating
5. Add execution_lock_id field (str) - Redis lock identifier
6. Add cost_estimate_usd field (float) - Estimated cost
7. Add actual_cost_usd field (float) - Actual cost
8. Add memory_profile_id field (str) - User memory profile link
9. Add artifact_refs field (List[str]) - Artifact references
10. Add handoff_log field (List[Dict]) - Inter-agent handoffs
11. Add feedback_records field (List[Dict]) - Past execution feedback
12. Add timeout_config field (Dict) - Timeout configuration
13. Add isolation_context field (Dict) - Isolation boundaries
14. Add audit_trail field (List[Dict]) - Complete audit log

## Phase 2: Create Database Models (Section 5.2, 5.3, 5.5)
**Goal:** Extend `app/memory/models.py` with new models

**Tasks:**
1. **CheckpointMetadataModel** - Checkpoint metadata with node_name, step_index, decision_context
2. **UserMemoryProfileModel** - User-level memory profiles for cross-task knowledge
3. **ArtifactModel** - Artifact storage metadata
4. **AuditModel** - Complete audit trail for compliance
5. **Update TokenUsageModel** - Add cost fields if missing

## Phase 3: Implement Agent Lifecycle (Section 6.2)
**Goal:** Create agent lifecycle management

**Tasks:**
1. Create `app/agents/lifecycle.py` with AgentLifecycle class
2. Define AgentState enum: CREATED, REGISTERED, ACTIVE, EXECUTING, IDLE, DECOMMISSIONED
3. Implement state transition validation
4. Create `app/runtime/dynamic_factory.py` for dynamic agent creation
5. Implement health check mechanism in `app/runtime/worker.py`

## Phase 4: Create New Agent Roles (Section 6.1)
**Goal:** Implement ReviewerAgent and CoordinatorAgent

**Tasks:**
1. Create `app/agents/reviewer.py` - ReviewerAgent for output validation
2. Create `app/agents/coordinator.py` - CoordinatorAgent for multi-agent workflows
3. Create `app/agents/handoff.py` - InterAgentHandoff protocol
4. Create `app/agents/feedback.py` - Agent feedback loop

## Phase 5: Implement Supporting Services
**Goal:** Create services for cost tracking, timeouts, isolation

**Tasks:**
1. Create `app/logs/cost_tracker.py` - CostTracker for per-task/agent/tool cost tracking
2. Create `app/orchestrator/timeouts.py` - TimeoutEnforcer
3. Create `app/orchestrator/isolation.py` - FailureIsolator
4. Create `app/memory/artifact_store.py` - ArtifactStore
5. Create `app/memory/persistent.py` enhancements for UserMemoryProfile

## Phase 6: Implement Checkpoint Enhancements (Section 5.3)
**Goal:** Extend checkpoint functionality

**Tasks:**
1. Create `app/recovery/checkpoint_service.py` - CheckpointNavigator for chain traversal
2. Create `app/recovery/checkpoint_cleanup.py` - CheckpointCleanupJob
3. Enhance `app/langgraph/checkpointer.py` with metadata support

## Phase 7: Testing & Validation
**Goal:** Verify all implementations

**Tasks:**
1. Run `pytest -q` to ensure no regressions
2. Create tests for new models
3. Create tests for agent lifecycle
4. Validate AgentState fields work in LangGraph nodes

## Execution Order
1. Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5 → Phase 6 → Phase 7
2. Each phase is independent enough to be implemented separately
3. Some phases can be parallelized (Phase 4 and Phase 5)
