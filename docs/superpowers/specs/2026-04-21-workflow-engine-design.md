# Workflow Engine Design

## Goal
Replace linear step batching with graph-based workflow execution in the orchestrator.

## Scope
Phase 3 covers workflow modeling, graph execution, conditional skips, parallel execution, persistence, and orchestrator integration.

## Workflow Schema

### WorkflowModel
- `id`: workflow identifier
- `task_id`: owning task
- `name`: optional template or generated workflow name
- `definition_json`: full workflow snapshot
- `status`: workflow runtime status
- `created_at`, `updated_at`

### WorkflowNodeModel
- `id`: node identifier
- `workflow_id`: parent workflow
- `step_number`: stable ordering field for display/debugging
- `agent_type`: `agent`, `tool`, or `system`
- `input_data`: node input payload
- `condition_code`: optional Python callable source for conditional execution
- `status`: `PENDING`, `RUNNING`, `COMPLETED`, `FAILED`, `SKIPPED`
- `output_data`: execution result
- `confidence`: optional result confidence

### WorkflowEdgeModel
- `id`: edge identifier
- `workflow_id`: parent workflow
- `from_node_id`: dependency source
- `to_node_id`: dependency target

## Execution Flow
1. Orchestrator receives either a simple task or a workflow definition.
2. Planner output is normalized into a workflow graph when the input is not already a workflow.
3. Workflow is persisted to the DB with nodes, edges, and a JSON snapshot.
4. Engine resolves ready nodes by checking dependency completion.
5. Ready nodes execute in parallel.
6. Engine continues until all nodes reach a terminal state.
7. Verifier runs after workflow completion.

## Graph Rules
- A node is runnable only when all inbound dependencies are `COMPLETED`.
- Independent nodes may run in parallel.
- Linear workflows are represented as a chain of edges.
- Branching workflows are represented by multiple outgoing edges.
- Conditional workflows are represented by a node with a condition and alternative downstream branches.

## Condition Handling
- Conditions are evaluated as Python callables against the runtime context.
- The persisted form is `condition_code`.
- If the condition evaluates to false, the node is marked `SKIPPED` and is not executed.
- Skipped nodes are terminal and are recorded in DB.

## Node Lifecycle
- Allowed transitions:
  - `PENDING -> RUNNING -> COMPLETED`
  - `PENDING -> RUNNING -> FAILED`
  - `PENDING -> SKIPPED`
- No direct transition into `COMPLETED`, `FAILED`, or `SKIPPED` without a prior valid state.

## Persistence
- Persist workflow header, node rows, and edge rows.
- Store a JSON snapshot of the workflow on the workflow record.
- Link every workflow to its task.
- Update node state in DB during execution.

## Orchestrator Integration
- Replace `_batch_steps` with graph readiness resolution.
- Replace step-plan persistence with workflow persistence.
- Update task result payloads to include workflow and node outcomes.
- Keep planner, executor, and verifier phases intact, but route execution through the workflow engine.

## Reusable Workflows
- Support predefined workflow templates.
- Support planner-generated dynamic workflows.
- Both forms use the same persisted workflow schema.

## Validation
- Reject graphs with circular dependencies.
- Reject edges that reference missing nodes.
- Reject malformed planner output.
- Ensure condition skips do not violate dependency constraints.

## Known Risks
- Inline Python condition storage is flexible but trusted-only.
- Condition safety and sandboxing are out of scope for this phase.
- Existing step APIs may need follow-up cleanup after workflow rollout.
