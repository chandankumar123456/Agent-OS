# AgentOS Grounding Layer & Tool Injection Fix

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development

**Goal:** Fix desktop tool injection, grounding, and verification so desktop tasks receive desktop tools, execute for real, and fail if execution fails.

**Architecture:** Surgical fixes to planner schema, executor fallback logic, grounding intent maps, tool registry refresh, and verifier env checks. No rewrites.

**Tech Stack:** Python 3.11, FastAPI, LangGraph

---

## File Structure

- `app/langgraph/nodes.py` — planner_node schema + prompt, executor_node fallback, verifier_node desktop gate + failure checks
- `app/tools/grounding.py` — CAPABILITY_TOOL_MAP, STEP_INTENT_MAP, classify_intent
- `app/tools/registry.py` — MCP discovery stale-cache guard
- `app/capabilities/verification.py` — verify_plan schema fix, desktop verifiers
- `tests/test_grounding_desktop.py` — regression tests

---

### Task 1: Fix Planner Schema and Executor Fallback (debugger)

**Files:**
- Modify: `app/langgraph/nodes.py`

**Context:** Single-phase desktop tasks fall back to LLM planner which omits `allowed_tools`, causing executor to fall back to brittle keyword grounding that defaults to `general` → generic tools.

- [ ] **Step 1: Expand LLM planner schema to include constraints**

In `planner_node`, update the `response_schema` passed to `llm.complete_json` (lines 284-302) to include `allowed_tools`, `fallback_tools`, `step_type`, `required`, and `depends_on`.

```python
response_schema={
    "type": "object",
    "properties": {
        "plan": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "step_number": {"type": "integer"},
                    "description": {"type": "string"},
                    "tool": {"type": ["string", "null"]},
                    "expected_output": {"type": "string"},
                    "step_type": {"type": "string"},
                    "allowed_tools": {"type": "array", "items": {"type": "string"}},
                    "fallback_tools": {"type": "array", "items": {"type": "string"}},
                    "required": {"type": "boolean"},
                    "depends_on": {"type": "array", "items": {"type": "integer"}},
                },
                "required": ["step_number", "description", "tool", "expected_output"],
            },
        }
    },
    "required": ["plan"],
},
```

- [ ] **Step 2: Update planner system prompt for desktop tool naming**

In `PLANNER_SYSTEM_PROMPT_TEMPLATE` (lines 113-156), update the desktop_automation rule to include all desktop prefixes:

Replace:
```
- desktop_automation steps: ONLY desktop_env__* tools.
```
With:
```
- desktop_automation steps: ONLY desktop_env__*, desktop__*, and desktop__desktop__* tools.
```

- [ ] **Step 3: Fix executor_node fallback to use step_type instead of generic description filtering**

In `executor_node` around lines 390-397:

```python
grounded_tools = []
if explicit_allowed:
    grounded_tools = [available_tool_map[name] for name in explicit_allowed if name in available_tool_map]
if not grounded_tools and explicit_fallback:
    grounded_tools = [available_tool_map[name] for name in explicit_fallback if name in available_tool_map]
if not grounded_tools:
    step_type = step.get("step_type")
    if step_type:
        grounded_tools = tool_grounding_layer.get_allowed_tools(step_type, available_tools)
    else:
        grounded_tools = tool_grounding_layer.filter_tools_for_step(description, available_tools)
    if not grounded_tools:
        logger.warning(f"[executor_node] No tools grounded for step {step_number}; using all available")
        grounded_tools = available_tools
```

- [ ] **Step 4: Add capability context logging in executor_node**

After line 400, add:
```python
rejected_tools = [t["name"] for t in available_tools if t["name"] not in grounded_tool_names]
logger.info(f"[executor_node] Step {step_number} step_type={step.get('step_type')} capability={state.get('capability_assessment', {}).get('primary_capability')}")
logger.info(f"[executor_node] Selected tools: {grounded_tool_names}")
if rejected_tools:
    logger.info(f"[executor_node] Rejected tools: {set(rejected_tools)}")
```

- [ ] **Step 5: Commit**

```bash
git add app/langgraph/nodes.py
git commit -m "fix(langgraph): include allowed_tools in LLM planner schema and capability-aware executor fallback"
```

---

### Task 2: Fix Tool Registry Stale Cache (mcp-builder)

**Files:**
- Modify: `app/tools/registry.py`

**Context:** `discover_mcp_tools` bails early if `_mcp_tools_registered` is True, preventing refresh.

- [ ] **Step 1: Allow MCP tool rediscovery**

Replace lines 237-241:
```python
    async def discover_mcp_tools(self) -> None:
        """Discover and register tools from connected MCP servers."""
        async with self._discovery_lock:
            if self._mcp_tools_registered:
                return
```

With:
```python
    async def discover_mcp_tools(self, force: bool = False) -> None:
        """Discover and register tools from connected MCP servers."""
        async with self._discovery_lock:
            if self._mcp_tools_registered and not force:
                return
```

- [ ] **Step 2: Commit**

```bash
git add app/tools/registry.py
git commit -m "fix(tools): allow forced MCP tool rediscovery to prevent stale cache"
```

---

### Task 3: Fix Grounding Intent and Capability Map (capability-builder)

**Files:**
- Modify: `app/tools/grounding.py`

**Context:** STEP_INTENT_MAP misses common desktop phrasing; CAPABILITY_TOOL_MAP omits local `desktop__*` semantic tools; `classify_intent` defaults to `general` too aggressively.

- [ ] **Step 1: Expand STEP_INTENT_MAP with desktop keywords**

In `STEP_INTENT_MAP` (lines 113-161), add after existing desktop entries:

```python
    "open notepad": "desktop_automation",
    "open app": "desktop_automation",
    "open application": "desktop_automation",
    "launch app": "desktop_automation",
    "launch application": "desktop_automation",
    "get ui tree": "desktop_automation",
    "click element": "desktop_automation",
    "type element": "desktop_automation",
    "ui automation": "desktop_automation",
    "focus app": "desktop_automation",
```

- [ ] **Step 2: Add local desktop semantic tools to CAPABILITY_TOOL_MAP**

In `CAPABILITY_TOOL_MAP["desktop_automation"]` (lines 65-81), append:

```python
        "desktop__get_ui_tree",
        "desktop__click_element",
        "desktop__type_element",
        "desktop__focus_and_interact",
```

- [ ] **Step 3: Harden classify_intent against generic fallback for desktop tasks**

In `classify_intent` (lines 167-178), add a pre-check for desktop environment indicator:

```python
    def classify_intent(self, step_description: str) -> str:
        """Classify a step description into a capability intent."""
        desc_lower = step_description.lower()
        
        # Fast-path: if description mentions desktop-specific nouns/verbs, never default to general
        desktop_indicators = ["notepad", "ui tree", "click element", "type element", "focus window", "get window list"]
        if any(ind in desc_lower for ind in desktop_indicators):
            return "desktop_automation"
        
        best_intent = "general"
        best_score = 0
        for keyword, intent in STEP_INTENT_MAP.items():
            if keyword in desc_lower:
                score = len(keyword)
                if score > best_score:
                    best_score = score
                    best_intent = intent
        return best_intent
```

- [ ] **Step 4: Commit**

```bash
git add app/tools/grounding.py
git commit -m "fix(tools): expand desktop intent keywords and capability tool map"
```

---

### Task 4: Fix Verification False Success (verification-builder)

**Files:**
- Modify: `app/capabilities/verification.py`
- Modify: `app/langgraph/nodes.py`

**Context:** `verify_plan` expects legacy `id`/`step` keys; no desktop env gate in `verifier_node`; failed tool executions don't fail verification.

- [ ] **Step 1: Fix verify_plan to read LangGraph plan schema**

In `verification.py` lines 91-92:

```python
step_id = str(step.get("step_number", step.get("id", "unknown")))
desc = step.get("description", step.get("step", "")).lower()
```

- [ ] **Step 2: Add desktop environment gate to verifier_node**

In `nodes.py` `verifier_node`, after the `cloud_api` block (lines 917-924), add:

```python
    elif env_type in ("desktop", "desktop_automation"):
        tool_calls = state.get("tool_calls", [])
        desktop_calls = [t for t in tool_calls if t.get("tool", "").startswith(("desktop_env__", "desktop__desktop__", "desktop__"))]
        if not desktop_calls:
            env_verified = False
            env_notes = "Desktop environment selected but no desktop tools were invoked."
        else:
            env_notes = f"Desktop automation verified: {len(desktop_calls)} desktop actions performed."
            # Additional deterministic check: if plan mentions typing, ensure type tool was called
            for pstep in plan:
                pdesc = pstep.get("description", "").lower()
                if any(k in pdesc for k in ("type text", "type hello", "type element")):
                    if not any(t.get("tool", "").endswith(("type_text", "type_element")) for t in desktop_calls):
                        env_verified = False
                        env_notes += " Plan step mentioned typing but no desktop type tool was invoked."
                        break
                if any(k in pdesc for k in ("click", "click element")):
                    if not any(t.get("tool", "").endswith(("click", "click_element")) for t in desktop_calls):
                        env_verified = False
                        env_notes += " Plan step mentioned clicking but no desktop click tool was invoked."
                        break
```

- [ ] **Step 3: Enforce execution failure fails verification**

In `nodes.py` `verifier_node`, before the final verdict (line 927), add:

```python
    # If any tool execution failed, verification must fail
    for step in steps:
        for tr in step.get("tool_results", []):
            if not tr.get("success"):
                det_pass = False
                notes = f"Execution failure in step {step.get('step_number')}: {tr.get('error', 'unknown error')}. {notes}"
                break
        if not det_pass:
            break
```

- [ ] **Step 4: Commit**

```bash
git add app/capabilities/verification.py app/langgraph/nodes.py
git commit -m "fix(verification): repair plan schema mismatch, add desktop env gate, and enforce execution-failure=verification-failure"
```

---

### Task 5: Improve Observability Logging (observability-agent)

**Files:**
- Modify: `app/langgraph/nodes.py`

**Context:** Need visibility into capability routing, tool selection, and verification decisions.

- [ ] **Step 1: Add executor input/output logging**

In `executor_node`, after line 400 (grounded tools log), add:

```python
logger.info(f"[executor_node] Step {step_number} capability_assessment={state.get('capability_assessment', {})}")
logger.info(f"[executor_node] Step {step_number} explicit_allowed={explicit_allowed} explicit_fallback={explicit_fallback}")
```

Before the return at line 706, add:

```python
logger.info(f"[executor_node] Step {step_number} completed with {len(step_tool_results)} tool results, final_status={'success' if all(r.get('success') for r in step_tool_results) else 'failure'}")
```

- [ ] **Step 2: Add verification decision logging**

In `verifier_node`, after line 927 (final verdict), add:

```python
logger.info(f"[verifier_node] Final verdict for task {task_id}: verified={verified} det_pass={det_pass} llm_verified={llm_verified} env_verified={env_verified} env_type={env_type}")
```

In `verifier_node`, inside the LLM verification exception handler (line 903), add:

```python
logger.error(f"[verifier_node] LLM verification failed for task {task_id}: {e}")
```

- [ ] **Step 3: Commit**

```bash
git add app/langgraph/nodes.py
git commit -m "chore(observability): add capability, tool selection, and verification decision logs"
```

---

### Task 6: Add Regression Tests (test-engineer)

**Files:**
- Create: `tests/test_grounding_desktop.py`

**Context:** Need tests ensuring desktop tasks get desktop tools and never fall back to generic tools.

- [ ] **Step 1: Create regression test file**

```python
import pytest
from app.tools.grounding import tool_grounding_layer, CAPABILITY_TOOL_MAP


@pytest.fixture
def fake_available_tools():
    return [
        {"name": "web_search", "description": "Search the web"},
        {"name": "calculator", "description": "Calculate things"},
        {"name": "text_processor", "description": "Process text"},
        {"name": "desktop_env__screenshot", "description": "Screenshot"},
        {"name": "desktop_env__type_text", "description": "Type text"},
        {"name": "desktop__get_ui_tree", "description": "Get UI tree"},
        {"name": "desktop__click_element", "description": "Click element"},
        {"name": "desktop__type_element", "description": "Type element"},
        {"name": "desktop__desktop__click", "description": "MCP click"},
    ]


def test_open_notepad_gets_desktop_tools(fake_available_tools):
    grounded = tool_grounding_layer.filter_tools_for_step("open notepad and type hello", fake_available_tools)
    names = {t["name"] for t in grounded}
    assert any(n in names for n in ("desktop_env__type_text", "desktop__type_element", "desktop__desktop__click"))
    assert "web_search" not in names
    assert "calculator" not in names
    assert "text_processor" not in names


def test_type_hello_gets_desktop_tools(fake_available_tools):
    grounded = tool_grounding_layer.filter_tools_for_step("type hello into the search box", fake_available_tools)
    names = {t["name"] for t in grounded}
    assert any(n in names for n in ("desktop_env__type_text", "desktop__type_element"))
    assert "web_search" not in names
    assert "calculator" not in names
    assert "text_processor" not in names


def test_click_element_gets_desktop_tools(fake_available_tools):
    grounded = tool_grounding_layer.filter_tools_for_step("click element with id 5", fake_available_tools)
    names = {t["name"] for t in grounded}
    assert any(n in names for n in ("desktop__click_element", "desktop__desktop__click"))
    assert "web_search" not in names


def test_desktop_automation_capability_map_includes_local_tools():
    desktop_tools = CAPABILITY_TOOL_MAP["desktop_automation"]
    assert "desktop__get_ui_tree" in desktop_tools
    assert "desktop__click_element" in desktop_tools
    assert "desktop__type_element" in desktop_tools
    assert "desktop__focus_and_interact" in desktop_tools


def test_general_capability_does_not_include_desktop(fake_available_tools):
    grounded = tool_grounding_layer.get_allowed_tools("general", fake_available_tools)
    names = {t["name"] for t in grounded}
    assert not any(n.startswith(("desktop_env__", "desktop__")) for n in names)
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/test_grounding_desktop.py -v
```

Expected: All PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_grounding_desktop.py
git commit -m "test(grounding): add desktop tool selection regression tests"
```

---

## Spec Coverage Checklist

- [x] Planner emits `allowed_tools` for all tasks (LLM schema expanded)
- [x] Executor fallback uses `step_type` / capability instead of generic description → `general`
- [x] Grounding intent map recognizes desktop phrasing ("open notepad", etc.)
- [x] CAPABILITY_TOOL_MAP includes local `desktop__*` semantic tools
- [x] MCP registry allows refresh (stale cache removed)
- [x] Verifier `verify_plan` reads `step_number`/`description`
- [x] Verifier has desktop env gate
- [x] Execution failure forces verification failure
- [x] Observability logs capability, selected/rejected tools, verification decisions
- [x] Regression tests validate desktop grounding and prevent generic fallback
