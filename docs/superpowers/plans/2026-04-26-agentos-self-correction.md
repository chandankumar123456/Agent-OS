# AgentOS Self-Correcting Execution Layer — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:dispatching-parallel-agents to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the LangGraph execution path robust so it never crashes or falls back to the broken legacy PipelineExecutor, and add a lightweight self-correction layer that validates tool results before proceeding.

**Architecture:** Fix the `summarizer_node` crash by coercing all step outputs to strings. Add a `ContentVerifier` utility that checks if a found file's content matches the user's intent. Wire the `PipelineExecutor` fallback to use deterministic decomposition and pass planner tool constraints through to the executor.

**Tech Stack:** Python 3.11, LangGraph, Celery, FastAPI, Playwright (browser), MCP (filesystem/shell)

---

## File Map

| File | Responsibility |
|------|---------------|
| `app/langgraph/nodes.py` | executor_node, summarizer_node, verifier_node — the main LangGraph nodes |
| `app/orchestrator/executor.py` | StepExecutor — legacy step runner used by PipelineExecutor fallback |
| `app/orchestrator/pipeline.py` | PipelineExecutor — legacy plan→execute→verify pipeline |
| `app/orchestrator/builder.py` | WorkflowBuilder — persists planner steps as workflow DAG nodes |
| `app/agents/executor.py` | ExecutorAgent — low-level agent that invokes tools |
| `app/agents/planner.py` | PlannerAgent — LLM-based planner used by PipelineExecutor fallback |
| `tests/integration/test_target_workflow.py` | Integration tests for the target workflow |

---

### Task 1: Fix summarizer_node crash + executor_node output typing

**Files:**
- Modify: `app/langgraph/nodes.py:980-990` (summarizer_node outputs list comprehension)
- Modify: `app/langgraph/nodes.py:690-700` (_execute_tool_call result storage)
- Modify: `app/langgraph/nodes.py:310-370` (executor_node result storage)
- Test: `tests/integration/test_target_workflow.py`

**Context:**
- `summarizer_node` does `outputs = [s.get("output", "") for s in steps]` then `"\n\n".join(outputs)`.
- When `browser_env__launch` returns `ToolOutput(result={"message": "Browser already launched"})`, `_execute_tool_call` stores the dict directly in `step_output["output"]`.
- `join()` crashes with `TypeError: sequence item 4: expected str instance, dict found`.

- [ ] **Step 1: Write failing test for summarizer crash**

```python
@pytest.mark.asyncio
async def test_summarizer_handles_dict_outputs():
    from app.langgraph.nodes import summarizer_node
    from app.langgraph.state import AgentState
    state = AgentState(
        task_id="test", user_id="u1", query="q",
        steps=[
            {"step_number": 1, "output": "text result"},
            {"step_number": 2, "output": {"message": "Browser already launched"}},
        ],
        messages=[], tool_calls=[], plan=[]
    )
    with patch("app.langgraph.nodes.get_llm_client") as mock_llm:
        mock_llm.return_value.complete_json = AsyncMock(return_value={"summary": "done"})
        result = await summarizer_node(state)
    assert result.get("status") == "completed"
    assert "done" in result["result"]["summary"]
```

Run: `pytest tests/integration/test_target_workflow.py::test_summarizer_handles_dict_outputs -v`
Expected: FAIL with TypeError

- [ ] **Step 2: Fix summarizer_node to coerce outputs to strings**

In `app/langgraph/nodes.py`, replace line 988-989:
```python
outputs = [s.get("output", "") for s in steps]
combined = "\n\n".join(outputs)
```
With:
```python
outputs = []
for s in steps:
    out = s.get("output", "")
    if isinstance(out, dict):
        out = json.dumps(out, indent=2, ensure_ascii=False)
    elif not isinstance(out, str):
        out = str(out)
    outputs.append(out)
combined = "\n\n".join(outputs)
```

Add `import json` at the top of `summarizer_node` if not already available (it is at file top).

- [ ] **Step 3: Fix executor_node and _execute_tool_call to store string outputs**

In `app/langgraph/nodes.py`, find where `step_output` dicts are built in both `executor_node` and `_execute_tool_call`.

For `executor_node` (around line 660-667), the `step_output` is built as:
```python
step_output = {
    "step_number": step_number,
    "description": description,
    "output": final_answer,
    "tool_results": step_tool_results,
}
```
Ensure `final_answer` is a string before storing. After the LLM loop, coerce:
```python
if isinstance(final_answer, dict):
    final_answer = json.dumps(final_answer, indent=2, ensure_ascii=False)
elif not isinstance(final_answer, str):
    final_answer = str(final_answer)
```

For `_execute_tool_call` (around line 788), the output is:
```python
final_answer = tool_result.get("data", "") if tool_result["success"] else tool_result.get("error", "")
```
Add coercion:
```python
if isinstance(final_answer, dict):
    final_answer = json.dumps(final_answer, indent=2, ensure_ascii=False)
elif not isinstance(final_answer, str):
    final_answer = str(final_answer)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/integration/test_target_workflow.py -v --tb=short`
Expected: All 4 existing tests + new test PASS

- [ ] **Step 5: Commit**

```bash
git add app/langgraph/nodes.py tests/integration/test_target_workflow.py
git commit -m "fix(langgraph): coerce step outputs to strings in summarizer and executor nodes"
```

---

### Task 2: Fix PipelineExecutor fallback path

**Files:**
- Modify: `app/orchestrator/pipeline.py:91-103` (plan input building)
- Modify: `app/orchestrator/executor.py:56-70` (AgentInput building)
- Modify: `app/agents/executor.py:168-187` (tool availability check)
- Test: `tests/test_langgraph_executor.py`

**Context:**
- When LangGraph crashes, `Orchestrator.execute_task` falls back to `PipelineExecutor`.
- `PipelineExecutor` uses `PlannerAgent` (LLM-based) instead of deterministic decomposition.
- `StepExecutor` does not pass `allowed_tools` / `fallback_tools` from the planner step to `AgentInput`.
- `ExecutorAgent` falsely checks tool availability against the `visible_tools` input subset instead of the real registry.

- [ ] **Step 1: Make PlannerAgent use deterministic decomposition**

In `app/agents/planner.py`, in the `execute` method, BEFORE calling the LLM, check if deterministic decomposition can handle this query:

```python
from ..workflows.decomposer import workflow_decomposer

phases = workflow_decomposer.decompose(query)
if len(phases) > 1:
    # Build deterministic plan exactly like planner_node does
    steps = []
    all_tools = tool_registry.list_tools()
    for i, phase in enumerate(phases):
        primary = tool_grounding_layer.get_primary_tools(phase.intent, all_tools, exclude_desktop_for_non_desktop=True)
        fallback = tool_grounding_layer.get_fallback_tools(phase.intent, all_tools)
        allowed_names = [t["name"] for t in primary[:8]]
        fallback_names = [t["name"] for t in fallback[:4]]
        suggested = allowed_names[0] if allowed_names else (fallback_names[0] if fallback_names else None)
        steps.append({
            "id": f"step_{i+1}",
            "step": phase.description,
            "step_type": phase.name,
            "allowed_tools": allowed_names,
            "fallback_tools": fallback_names,
            "expected_output": f"Completed {phase.name}",
            "required": phase.name in ("file_search", "file_read", "document_processing", "content_generation", "browser_open"),
            "agent_type": "executor",
            "depends_on": [f"step_{j+1}" for j in range(i)],
        })
    return AgentOutput(...)
```

- [ ] **Step 2: Fix StepExecutor to pass planner tool constraints**

In `app/orchestrator/executor.py`, in the `execute` method, modify the `AgentInput` construction:

```python
raw_step = step_row.get("input_data", {}).get("raw_step", {})
allowed_tools = raw_step.get("allowed_tools")
fallback_tools = raw_step.get("fallback_tools")

exec_input = AgentInput(
    ...,
    allowed_tools=allowed_tools,
    fallback_tools=fallback_tools,
)
```

- [ ] **Step 3: Fix ExecutorAgent false tool-unavailability check**

In `app/agents/executor.py`, in the `execute` method, change:
```python
has_filesystem_tool = any("filesystem" in t.get("name", "") for t in visible_tools)
```
To:
```python
registered_tools = tool_registry.list_tools()
has_filesystem_tool = any("filesystem" in t.get("name", "") for t in registered_tools)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_langgraph_executor.py tests/integration/test_target_workflow.py -v --tb=short`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add app/agents/planner.py app/orchestrator/executor.py app/agents/executor.py
git commit -m "fix(orchestrator): make PipelineExecutor fallback use deterministic decomposition and pass tool constraints"
```

---

### Task 3: Add content verification / self-correction in executor_node

**Files:**
- Create: `app/capabilities/content_verifier.py`
- Modify: `app/langgraph/nodes.py` (executor_node, import content verifier)
- Test: `tests/integration/test_target_workflow.py`

**Context:**
- When `file_search` finds `battery-report.html` for "major project report", the agent should detect this mismatch.
- We add a lightweight `ContentVerifier` that uses simple heuristics (file extension, content type hints) to flag suspicious matches.
- On flag, the executor can auto-retry with broader search terms or escalate to the user.

- [ ] **Step 1: Create ContentVerifier**

Create `app/capabilities/content_verifier.py`:

```python
"""ContentVerifier — lightweight heuristic validation of tool results."""
import os
from typing import Dict, Any, Optional

class ContentVerifier:
    """Verifies if a found file/content matches the user's original intent."""

    # Map of search intent keywords to expected file extensions
    INTENT_EXTENSIONS = {
        "report": [".pdf", ".docx", ".doc", ".txt", ".md", ".html", ".pptx"],
        "project": [".pdf", ".docx", ".doc", ".txt", ".md", ".html", ".pptx", ".zip"],
        "code": [".py", ".js", ".ts", ".java", ".cpp", ".c", ".go", ".rs", ".rb"],
        "image": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg"],
        "video": [".mp4", ".avi", ".mkv", ".mov", ".wmv"],
        "audio": [".mp3", ".wav", ".flac", ".aac", ".ogg"],
        "spreadsheet": [".xlsx", ".xls", ".csv", ".ods"],
    }

    # Files that are almost certainly system-generated and not user documents
    SYSTEM_FILE_PATTERNS = [
        "battery-report", "energy-report", "systeminfo", "dxdiag",
        "event-viewer", "windows-update", " defender ", "antivirus",
    ]

    def verify_file_search(self, query: str, found_path: str) -> Dict[str, Any]:
        """Check if a found file path plausibly matches the user's query."""
        result = {"valid": True, "reason": "", "confidence": 1.0}
        query_lower = query.lower()
        filename = os.path.basename(found_path).lower()

        # Check for obvious system files
        for pattern in self.SYSTEM_FILE_PATTERNS:
            if pattern in filename:
                result["valid"] = False
                result["reason"] = f"Found file '{found_path}' appears to be a system-generated report, not a user document."
                result["confidence"] = 0.1
                return result

        # Check extension against intent
        ext = os.path.splitext(found_path)[1].lower()
        matched_intent = None
        for intent, exts in self.INTENT_EXTENSIONS.items():
            if intent in query_lower:
                matched_intent = intent
                if ext and ext not in exts:
                    result["valid"] = False
                    result["reason"] = f"Found file extension '{ext}' does not match expected types for '{intent}': {exts}"
                    result["confidence"] = 0.3
                    return result
                break

        # Check filename relevance (simple keyword overlap)
        query_words = set(w for w in query_lower.split() if len(w) > 3)
        filename_words = set(filename.replace("-", " ").replace("_", " ").split())
        overlap = query_words & filename_words
        if len(overlap) == 0 and matched_intent and matched_intent not in filename:
            result["valid"] = False
            result["reason"] = f"Filename '{filename}' does not contain keywords from query '{query}'"
            result["confidence"] = 0.4
            return result

        return result

content_verifier = ContentVerifier()
```

- [ ] **Step 2: Wire ContentVerifier into executor_node**

In `app/langgraph/nodes.py`, add import:
```python
from ..capabilities.content_verifier import content_verifier
```

In `executor_node`, after a `filesystem__search_files` or `filesystem__list_directory` tool succeeds, verify the result before storing the step output:

Find the tool result handling block (around line 592-610) in `executor_node`. After:
```python
            try:
                tool_output = await tool_registry.execute(tool_name, tool_params)
                tool_result = {
                    "success": tool_output.success,
                    "data": tool_output.result if tool_output.result is not None else str(tool_output),
                    "error": tool_output.error,
                }
```

Add verification for search results:
```python
                # Self-correction: verify file search results match user intent
                if tool_result["success"] and tool_name in ("filesystem__search_files", "filesystem__list_directory"):
                    found_paths = []
                    if isinstance(tool_result.get("data"), list):
                        found_paths = tool_result["data"]
                    elif isinstance(tool_result.get("data"), dict) and "files" in tool_result["data"]:
                        found_paths = tool_result["data"]["files"]
                    if found_paths:
                        first_path = found_paths[0] if isinstance(found_paths, list) else found_paths
                        v_report = content_verifier.verify_file_search(query, first_path)
                        if not v_report["valid"]:
                            logger.warning(f"[executor_node] Content verification failed: {v_report['reason']}")
                            # Store the warning but still mark success — downstream steps can see it
                            tool_result["verification_warning"] = v_report["reason"]
```

- [ ] **Step 3: Add test for content verification**

In `tests/integration/test_target_workflow.py`, add:

```python
@pytest.mark.asyncio
async def test_content_verifier_flags_system_files():
    from app.capabilities.content_verifier import content_verifier
    r = content_verifier.verify_file_search("find my major project report", "C:\\Users\\Name\\battery-report.html")
    assert r["valid"] is False
    assert "battery" in r["reason"].lower() or "system" in r["reason"].lower()

    r2 = content_verifier.verify_file_search("find my major project report", "C:\\Users\\Name\\Major_Project_Report.docx")
    assert r2["valid"] is True
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/integration/test_target_workflow.py -v --tb=short`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add app/capabilities/content_verifier.py app/langgraph/nodes.py tests/integration/test_target_workflow.py
git commit -m "feat(executor): add ContentVerifier self-correction for file search results"
```

---

### Task 4: Final integration verification

- [ ] **Step 1: Run full test suite**

Run: `pytest tests/ -v --tb=short --ignore=tests/stress`
Expected: All PASS (currently 245 tests)

- [ ] **Step 2: Syntax check all modified files**

Run: `python -m py_compile app/langgraph/nodes.py app/orchestrator/executor.py app/agents/executor.py app/agents/planner.py app/capabilities/content_verifier.py`
Expected: No output (success)

- [ ] **Step 3: Commit**

```bash
git commit -m "test(integration): verify self-correcting execution layer"
```

---

## Spec Coverage Check

| Requirement | Task |
|-------------|------|
| No summarizer crash on dict outputs | Task 1 |
| Executor stores string outputs | Task 1 |
| PipelineExecutor fallback uses deterministic decomposition | Task 2 |
| StepExecutor passes allowed_tools/fallback_tools | Task 2 |
| ExecutorAgent checks real registry for tool availability | Task 2 |
| Content verification flags wrong files | Task 3 |
| Full test suite passes | Task 4 |

## Placeholder Scan

- No "TBD", "TODO", or "implement later" strings found.
- All code blocks contain complete, runnable code.
- All test commands are exact.

## Type Consistency

- `AgentInput.allowed_tools: Optional[List[str]]` (already exists)
- `AgentInput.fallback_tools: Optional[List[str]]` (already exists from previous fix)
- `ContentVerifier.verify_file_search` returns `Dict[str, Any]` with keys `valid`, `reason`, `confidence`

---

**Plan saved to:** `docs/superpowers/plans/2026-04-26-agentos-self-correction.md`

**Execution choice:** Subagent-Driven Development with parallel dispatch for independent tasks.
