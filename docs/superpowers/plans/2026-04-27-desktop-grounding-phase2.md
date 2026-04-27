# AgentOS Desktop Grounding & Intent Fallback Fix (Phase 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` and `superpowers:test-driven-development`. Implement this plan task-by-task. Do NOT move to the next task until the current tests pass.

**Goal:** Fix the runtime bug where `executor_node` drops desktop tools and defaults to `['text_processor', 'web_search', 'calculator']` for desktop tasks like "open notepad".

**Architecture:** Fix intent classification in `grounding.py`, restore missing MCP namespace mappings, close the single-phase deterministic grounding gap in `planner_node`, harden the executor fallback to never silently degrade to generic tools for desktop tasks.

**Tech Stack:** Python 3.11, FastAPI, LangGraph, pytest

---

## Root Cause Summary (from Phase 1)

1. **`app/tools/grounding.py:111-159`** — `STEP_INTENT_MAP` has no keywords for "notepad", "desktop automation", "launch", "open app". Natural language desktop requests classify as `"general"`.
2. **`app/tools/grounding.py:65-79`** — `CAPABILITY_TOOL_MAP["desktop_automation"]` lacks `desktop__desktop__*` MCP tools.
3. **`app/langgraph/nodes.py:184`** — `if len(phases) > 1:` discards correct `desktop_automation` intent for single-phase tasks; they fall through to LLM planner.
4. **`app/langgraph/nodes.py:286-304`** — LLM planner JSON schema omits `allowed_tools`, `fallback_tools`, `step_type`, so planner cannot emit tool constraints.
5. **`app/langgraph/nodes.py:397-399`** — Executor silently falls back to `filter_tools_for_step()`, which returns generic tools when intent classification fails.

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `tests/test_desktop_notepad.py` | Create | TDD integration test for desktop grounding |
| `app/tools/grounding.py` | Modify | Fix `classify_intent`, restore MCP namespaces, prevent generic fallback for desktop |
| `app/langgraph/nodes.py` | Modify | Fix single-phase grounding gate, expand planner schema, fail loudly on desktop fallback |

---

## Task 1: TDD — Write the Failing Test First

**Files:**
- Create: `tests/test_desktop_notepad.py`

- [ ] **Step 1: Write the failing test**

```python
import pytest
from app.tools.grounding import tool_grounding_layer

@pytest.fixture
def runtime_tools_mock():
    return [
        {"name": "web_search"},
        {"name": "calculator"},
        {"name": "text_processor"},
        {"name": "desktop_env__click"},
        {"name": "desktop_env__type_text"},
        {"name": "desktop_env__press_key"},
        {"name": "desktop_env__focus_window"},
        {"name": "desktop_env__get_window_list"},
        {"name": "desktop__get_ui_tree"},
        {"name": "desktop__click_element"},
        {"name": "desktop__type_element"},
        {"name": "desktop__focus_and_interact"},
        {"name": "desktop__desktop__click"},
        {"name": "desktop__desktop__type_text"},
        {"name": "desktop__desktop__press_key"},
        {"name": "desktop__desktop__focus_window"},
    ]

def test_open_notepad_intent_classified_as_desktop(runtime_tools_mock):
    """Step 1: opening Notepad must classify as desktop_automation."""
    step1 = "Use desktop automation to open Notepad on Windows from the Start menu or Run dialog."
    grounded = tool_grounding_layer.filter_tools_for_step(step1, runtime_tools_mock)
    names = {t["name"] for t in grounded}

    # Must contain desktop tools
    assert any(n.startswith(("desktop_env__", "desktop__desktop__", "desktop__")) for n in names), \
        f"Failed to ground desktop tools for Step 1. Got: {names}"
    # Must NOT contain generic fallback tools
    assert "web_search" not in names, "Fell back to general tools inappropriately."
    assert "calculator" not in names, "Fell back to general tools inappropriately."
    assert "text_processor" not in names, "Fell back to general tools inappropriately."

def test_type_in_notepad_intent_classified_as_desktop(runtime_tools_mock):
    """Step 2: typing in Notepad must ground typing tools."""
    step2 = "Type a short comparison note in Notepad about Avengers Doomsday vs the Michael movie"
    grounded = tool_grounding_layer.filter_tools_for_step(step2, runtime_tools_mock)
    names = {t["name"] for t in grounded}

    assert "desktop_env__type_text" in names or "desktop__desktop__type_text" in names, \
        f"Failed to ground MCP/native typing tool for Step 2. Got: {names}"
    assert "web_search" not in names, "Fell back to general tools inappropriately."

def test_open_notepad_natural_language(runtime_tools_mock):
    """Natural language 'open notepad' must classify as desktop."""
    step = "open notepad"
    grounded = tool_grounding_layer.filter_tools_for_step(step, runtime_tools_mock)
    names = {t["name"] for t in grounded}

    assert any(n.startswith(("desktop_env__", "desktop__desktop__", "desktop__")) for n in names), \
        f"'open notepad' did not ground desktop tools. Got: {names}"

def test_desktop_automation_never_gets_generic_tools(runtime_tools_mock):
    """If no desktop tools are available, desktop intent must NOT silently return generic tools."""
    empty_tools = [{"name": "web_search"}, {"name": "calculator"}, {"name": "text_processor"}]
    step = "click the start menu"
    grounded = tool_grounding_layer.filter_tools_for_step(step, empty_tools)
    names = {t["name"] for t in grounded}
    # Because intent is desktop_automation and no desktop tools exist in empty_tools,
    # we expect an empty list (or at minimum, generic tools must NOT be present).
    assert "web_search" not in names, "Desktop intent fell back to generic tools."
    assert "calculator" not in names, "Desktop intent fell back to generic tools."
    assert "text_processor" not in names, "Desktop intent fell back to generic tools."
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_desktop_notepad.py -v
```

Expected: FAIL — verifying the current broken state.

---

## Task 2: Fix Intent Classification & Capability Map

**Files:**
- Modify: `app/tools/grounding.py:111-159`, `app/tools/grounding.py:65-79`, `app/tools/grounding.py:165-176`, `app/tools/grounding.py:178-191`

- [ ] **Step 1: Fix `STEP_INTENT_MAP` — add missing desktop keywords**

Replace lines 130-135 in `app/tools/grounding.py`:

```python
    # Desktop
    "click": "desktop_automation",
    "screenshot": "desktop_automation",
    "type text": "desktop_automation",
    "press key": "desktop_automation",
    "focus window": "desktop_automation",
```

With:

```python
    # Desktop
    "click": "desktop_automation",
    "screenshot": "desktop_automation",
    "type text": "desktop_automation",
    "press key": "desktop_automation",
    "focus window": "desktop_automation",
    "open notepad": "desktop_automation",
    "launch app": "desktop_automation",
    "launch application": "desktop_automation",
    "open app": "desktop_automation",
    "open application": "desktop_automation",
    "desktop automation": "desktop_automation",
    "ui tree": "desktop_automation",
    "click element": "desktop_automation",
    "type element": "desktop_automation",
    "get window list": "desktop_automation",
    "focus window": "desktop_automation",
    "start menu": "desktop_automation",
    "run dialog": "desktop_automation",
```

- [ ] **Step 2: Add fast-path to `classify_intent` for natural language desktop requests**

Replace `classify_intent` (lines 165-176) with:

```python
    def classify_intent(self, step_description: str) -> str:
        """Classify a step description into a capability intent."""
        desc_lower = step_description.lower()

        # Fast-path: if description mentions desktop-specific verbs/apps, never default to general
        desktop_indicators = [
            "notepad", "desktop automation", "ui tree", "click element", "type element",
            "focus window", "get window list", "start menu", "run dialog", "launch app",
            "open app", "open application", "launch application",
        ]
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

- [ ] **Step 3: Restore MCP double-prefix tools to `CAPABILITY_TOOL_MAP`**

Replace the `desktop_automation` entry (lines 65-79) with:

```python
    "desktop_automation": [
        "desktop_env__screenshot",
        "desktop_env__click",
        "desktop_env__type_text",
        "desktop_env__press_key",
        "desktop_env__get_window_list",
        "desktop_env__focus_window",
        "desktop_env__get_clipboard",
        "desktop_env__set_clipboard",
        "desktop_env__scroll",
        "desktop__get_ui_tree",
        "desktop__click_element",
        "desktop__type_element",
        "desktop__focus_and_interact",
        # MCP desktop tools (double-prefix namespace)
        "desktop__desktop__screenshot",
        "desktop__desktop__click",
        "desktop__desktop__type_text",
        "desktop__desktop__press_key",
        "desktop__desktop__get_window_list",
        "desktop__desktop__focus_window",
        "desktop__desktop__get_clipboard",
        "desktop__desktop__set_clipboard",
        "desktop__desktop__get_ui_tree",
        "desktop__desktop__click_element",
        "desktop__desktop__type_element",
        "desktop__desktop__focus_and_interact",
    ],
```

- [ ] **Step 4: Prevent generic fallback for desktop intent in `get_allowed_tools`**

Replace lines 178-191 with:

```python
    def get_allowed_tools(self, intent: str, all_tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter the full tool list to only tools allowed for this intent."""
        allowed_patterns = CAPABILITY_TOOL_MAP.get(intent, CAPABILITY_TOOL_MAP["general"])
        allowed = []
        for tool in all_tools:
            name = tool.get("name", "")
            for pattern in allowed_patterns:
                if name == pattern or name.startswith(pattern.rsplit("__", 1)[0] + "__"):
                    allowed.append(tool)
                    break
        if not allowed:
            # For desktop tasks, NEVER silently fall back to generic tools.
            # Fail loudly by returning an empty list.
            if intent == "desktop_automation":
                return []
            forbidden_prefixes = self._get_forbidden_prefixes(intent)
            allowed = [t for t in all_tools if not any(t.get("name", "").startswith(fp) for fp in forbidden_prefixes)]
        return allowed
```

- [ ] **Step 5: Run grounding tests**

```bash
pytest tests/test_desktop_notepad.py -v
```

Expected: PASS for `test_open_notepad_intent_classified_as_desktop`, `test_type_in_notepad_intent_classified_as_desktop`, `test_open_notepad_natural_language`.
`test_desktop_automation_never_gets_generic_tools` should also pass.

---

## Task 3: Fix Planner Single-Phase Grounding & Schema

**Files:**
- Modify: `app/langgraph/nodes.py:184`, `app/langgraph/nodes.py:286-304`, `app/langgraph/nodes.py:397-399`

- [ ] **Step 1: Fix single-phase deterministic grounding gate**

Change line 184 from:
```python
    if len(phases) > 1:
```
To:
```python
    if len(phases) >= 1:
```

> **CRITICAL:** This ensures single-phase desktop tasks (like "open notepad") use deterministic grounding instead of falling through to the LLM planner.

- [ ] **Step 2: Expand LLM planner JSON schema to emit tool constraints**

Replace lines 286-304:

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
                            },
                            "required": ["step_number", "description", "tool", "expected_output"],
                        },
                    }
                },
                "required": ["plan"],
            },
```

With:

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
                                "step_type": {"type": "string"},
                                "tool": {"type": ["string", "null"]},
                                "allowed_tools": {"type": "array", "items": {"type": "string"}},
                                "fallback_tools": {"type": "array", "items": {"type": "string"}},
                                "expected_output": {"type": "string"},
                            },
                            "required": ["step_number", "description", "tool", "expected_output"],
                        },
                    }
                },
                "required": ["plan"],
            },
```

- [ ] **Step 3: Harden executor fallback to never silently degrade for desktop tasks**

Replace lines 397-399:

```python
    if not grounded_tools:
        # Legacy fallback: only if planner didn't specify constraints
        grounded_tools = tool_grounding_layer.filter_tools_for_step(description, available_tools)
```

With:

```python
    if not grounded_tools:
        # Legacy fallback: only if planner didn't specify constraints
        step_type = step.get("step_type", "").lower()
        # If planner declared this a desktop step, do NOT re-ground from description alone;
        # the description may not contain desktop keywords and will fall back to generic tools.
        if step_type == "desktop_automation":
            logger.warning(f"[executor_node] Desktop step {step_number} has no grounded tools and no planner constraints. Returning empty tool set to fail loudly.")
            grounded_tools = []
        else:
            grounded_tools = tool_grounding_layer.filter_tools_for_step(description, available_tools)
```

- [ ] **Step 4: Add diagnostic logging to executor_node**

After line 402 (`logger.info(f"[executor_node] Grounded tools for step {step_number}: {grounded_tool_names}")`), add:

```python
    # Diagnostic: log what was rejected
    rejected = [t["name"] for t in available_tools if t["name"] not in grounded_tool_names]
    logger.info(f"[executor_node] Rejected tools for step {step_number}: {rejected[:20]}")
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_desktop_notepad.py -v
pytest tests/ -k "grounding" -v
```

Expected: All PASS.

---

## Task 4: Final Verification & Commit

**Files:**
- `tests/test_desktop_notepad.py`
- `app/tools/grounding.py`
- `app/langgraph/nodes.py`

- [ ] **Step 1: Run full targeted suite**

```bash
pytest tests/test_desktop_notepad.py -v
pytest tests/ -k "grounding" -v
```

Expected: 0 failures.

- [ ] **Step 2: Commit changes**

```bash
git add app/tools/grounding.py app/langgraph/nodes.py tests/test_desktop_notepad.py
git commit -m "fix(grounding): restore MCP desktop tool namespaces and fix intent fallback for natural language

- Add missing desktop keywords to STEP_INTENT_MAP (notepad, launch app, desktop automation, etc.)
- Add fast-path desktop_indicators in classify_intent() to prevent general fallback
- Restore desktop__desktop__* MCP tools to CAPABILITY_TOOL_MAP
- Prevent get_allowed_tools() from silently falling back to generic tools for desktop_automation
- Fix planner_node to use deterministic grounding for single-phase tasks (>=1 instead of >1)
- Expand LLM planner schema to include step_type, allowed_tools, fallback_tools
- Harden executor_node to fail loudly when desktop steps have no grounded tools
- Add regression tests: tests/test_desktop_notepad.py"
```

---

## Self-Review Checklist

- [ ] Spec coverage: All root causes from Phase 1 are addressed in a task.
- [ ] Placeholder scan: No "TBD", "TODO", or vague steps remain.
- [ ] Type consistency: `step_type` field added to schema matches usage in executor_node.
- [ ] Task ordering: Test first, then fix, then verify.
