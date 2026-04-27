# Desktop Goal-Driven Execution Loop Implementation Plan

> For agentic workers: REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development.

**Goal:** Make desktop tasks execute in a state-driven loop (observe -> act -> verify -> repeat) until the goal state is reached, instead of stopping after the first successful tool call.

**Architecture:** Add a desktop-specific goal loop inside executor_node that observes desktop state, prompts the LLM with current state + goal, executes the chosen action, runs deterministic goal verification, and repeats. Fix task_runner to respect verified=False. Fix verifier_node to check desktop environment.

**Tech Stack:** Python 3.11, LangGraph, FastAPI, pytest

---

## File Map

| File | Responsibility |
|------|---------------|
| app/langgraph/nodes.py | Contains executor_node and verifier_node. Add desktop loop and env check. |
| app/langgraph/state.py | Add desktop_iterations field to AgentState. |
| app/orchestrator/task_runner.py | Return FAILURE when verified=False after execution. |
| tests/test_desktop_loop.py | New tests proving the loop behavior. |

---

## Task 1: Add desktop loop state to AgentState

**Files:**
- Modify: app/langgraph/state.py
- Test: tests/test_desktop_loop.py

- [ ] **Step 1: Add desktop_iterations field**

Add a new field to AgentState:

```python
    # Desktop goal-driven loop tracking
    desktop_iterations: int
```

- [ ] **Step 2: Commit**

Run: git add app/langgraph/state.py && git commit -m "feat: add desktop loop state fields"

---

## Task 2: Implement desktop goal-driven execution loop in executor_node

**Files:**
- Modify: app/langgraph/nodes.py
- Test: tests/test_desktop_loop.py

### Step 1: Add helper functions before executor_node

- [ ] **Add _observe_desktop_state(task_id)**

This helper calls desktop_env__get_window_list and desktop__get_ui_tree to capture current desktop state. Log each observation at INFO level. Wrap each tool call in try/except so partial failures still yield useful state.

- [ ] **Add _check_desktop_goal(task_id, step_description)**

This helper calls verification_engine.verify_plan() with the step description to check if the goal is reached. Returns (bool, str).

- [ ] **Add _run_desktop_goal_loop(...)**

This is the core loop. Signature:

```python
async def _run_desktop_goal_loop(
    task_id: str,
    query: str,
    description: str,
    grounded_tools: List[Dict[str, Any]],
    grounded_tool_names: Set[str],
    max_iterations: int,
    state: AgentState,
) -> Dict[str, Any]:
```

Loop logic:
1. iteration = 0
2. While iteration < max_iterations:
   a. iteration += 1
   b. Log: [desktop-loop] iteration X/Y
   c. desktop_state = await _observe_desktop_state(task_id)
   d. Log observed state at INFO level
   e. goal_reached, notes = await _check_desktop_goal(task_id, description)
   f. Log goal check result at INFO level
   g. If goal_reached: set final_answer, break
   h. Build system prompt including desktop_state, query, description, grounded_tools
   i. The prompt MUST instruct the LLM: "Do NOT say the task is complete unless the goal state is actually true."
   j. Call LLM for next action
   k. If LLM returns answer (not tool_call): log warning, treat as early termination attempt, append warning to messages, continue loop
   l. Execute the chosen tool (same grounding guard, safety gate, and observability as existing code)
   m. Log tool result at INFO level
   n. Append tool result to messages for next iteration context
3. If loop exits without goal_reached: final_answer = "Reached max iterations without achieving goal"
4. Return dict with steps, tool_calls, verification_reports, status

- [ ] **Step 2: Integrate desktop loop into executor_node**

In executor_node, after grounding tools are determined, detect if this is a desktop step:

```python
is_desktop_step = bool(
    any(t.get("name", "").startswith(("desktop_env__", "desktop__")) for t in grounded_tools)
    or step.get("step_type", "").lower() == "desktop_automation"
)
```

If is_desktop_step:
- Call _run_desktop_goal_loop(...) instead of the normal LLM loop
- Set max_iterations = state.get("max_tool_rounds", 5) (reuse existing config)
- Return the result dict directly

If NOT desktop:
- Keep existing behavior exactly as-is

- [ ] **Step 3: Commit**

Run: git add app/langgraph/nodes.py && git commit -m "feat: add desktop goal-driven execution loop"

---

## Task 3: Fix verifier_node missing desktop env check

**Files:**
- Modify: app/langgraph/nodes.py (verifier_node section)
- Test: tests/test_desktop_loop.py

- [ ] **Step 1: Add desktop environment verification**

In verifier_node, around line 950-967, add:

```python
elif env_type == "desktop":
    tool_calls = state.get("tool_calls", [])
    desktop_calls = [t for t in tool_calls if t.get("tool", "").startswith(("desktop_env__", "desktop__"))]
    if not desktop_calls:
        env_verified = False
        env_notes = "Desktop environment selected but no desktop tools were invoked."
    else:
        env_notes = f"Desktop automation verified: {len(desktop_calls)} desktop actions performed."
```

- [ ] **Step 2: Commit**

Run: git add app/langgraph/nodes.py && git commit -m "fix: add desktop env verification to verifier_node"

---

## Task 4: Fix task_runner to respect verified=False

**Files:**
- Modify: app/orchestrator/task_runner.py
- Test: tests/test_desktop_loop.py

- [ ] **Step 1: Return FAILURE when verified is False**

Change the final return logic in task_runner.run():

```python
if error or status == "rejected":
    return AgentOutput(...FAILURE...)

if not verified:
    return AgentOutput(
        task_id=str(task_id),
        step_id=uuid4(),
        status=AgentStatus.FAILURE,
        error_type="verification_failed",
        error_message="Task execution completed but verification failed. The goal state was not reached.",
        output_data=result,
    )

return AgentOutput(...SUCCESS...)
```

- [ ] **Step 2: Commit**

Run: git add app/orchestrator/task_runner.py && git commit -m "fix: task_runner returns FAILURE when verified=False"

---

## Task 5: Write failing tests first (TDD)

**Files:**
- Create: tests/test_desktop_loop.py

- [ ] **Step 1: Test desktop loop does not stop after first action**

Write a test that mocks the LLM to return a tool call on first invocation and an answer on second. Verify that _run_desktop_goal_loop calls the tool twice before accepting completion.

- [ ] **Step 2: Test goal check drives continuation**

Mock _check_desktop_goal to return False on first two calls, True on third. Mock tool execution. Verify the loop runs 3 iterations.

- [ ] **Step 3: Test max iterations bounds the loop**

Mock _check_desktop_goal to always return False. Set max_iterations=3. Verify the loop stops at 3 and returns appropriate status.

- [ ] **Step 4: Test task_runner returns FAILURE on unverified desktop task**

Mock graph.ainvoke to return a state with verified=False, error=None, status="completed". Verify task_runner.run() returns AgentStatus.FAILURE.

- [ ] **Step 5: Test verifier_node catches missing desktop calls**

Mock state with env_type="desktop" and empty tool_calls. Verify verifier_node returns verified=False.

- [ ] **Step 6: Run tests and confirm they fail**

Run: .venv\\Scripts\\python -m pytest tests/test_desktop_loop.py -v

Expected: all tests FAIL because the implementation does not exist yet.

- [ ] **Step 7: Commit**

Run: git add tests/test_desktop_loop.py && git commit -m "test: add failing tests for desktop goal-driven loop"

---

## Task 6: Implement to make tests pass

**Files:**
- Modify: app/langgraph/nodes.py
- Modify: app/langgraph/state.py
- Modify: app/orchestrator/task_runner.py

- [ ] **Step 1: Implement all changes from Tasks 1-4**

Follow the plan details above. Keep changes minimal and focused.

- [ ] **Step 2: Run tests**

Run: .venv\\Scripts\\python -m pytest tests/test_desktop_loop.py -v

Expected: all tests PASS.

- [ ] **Step 3: Run regression tests**

Run: .venv\\Scripts\\python -m pytest tests/ -v --ignore=tests/integration

Expected: no new failures.

- [ ] **Step 4: Commit**

Run: git add -A && git commit -m "feat: desktop goal-driven execution loop"

---

## Spec Coverage Checklist

| Requirement | Task |
|-------------|------|
| FR1 - Desktop execution loop | Task 2 |
| FR2 - State observation | Task 2 (_observe_desktop_state) |
| FR3 - Goal completion checker | Task 2 (_check_desktop_goal) |
| FR4 - Iterative action selection | Task 2 (_run_desktop_goal_loop) |
| FR5 - Bounded execution | Task 2 (max_iterations) |
| FR6 - No false success | Task 4 (task_runner verified check) |
| FR7 - Traceability | Task 2 (logging in loop) |

---

## Logging Strategy

Every iteration must log at INFO level:
- Iteration X/Y started
- Observed state: ... (truncated to avoid spam)
- Goal check: reached=X notes=...
- Executing tool: name=X params=...
- Tool result: success=X ...

This satisfies FR7 without adding new infrastructure.
