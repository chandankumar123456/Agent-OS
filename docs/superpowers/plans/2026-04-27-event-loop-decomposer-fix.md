# AgentOS Windows Event Loop & Decomposer Fix Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix the Windows Celery event loop crash (Playwright `NotImplementedError`) and prevent the Executor from using shell shortcuts to bypass Desktop/Browser automation tools.

**Architecture:** Add `WindowsProactorEventLoopPolicy` at Celery worker startup (gated by `sys.platform == 'win32'`). Add deterministic keyword-based routing heuristics in `WorkflowDecomposer` to classify desktop vs browser tasks. Update Executor prompt to explicitly forbid `shell__execute_command` for GUI app interaction.

**Tech Stack:** Python 3.11+, Celery, Playwright, asyncio

---

## Task 1: TDD — Write failing tests

**Files:**
- Create: `tests/test_queue_tasks.py`
- Create: `tests/test_decomposer_routing.py`

- [ ] **Step 1: Write test for Windows event loop policy**

In `tests/test_queue_tasks.py`:
```python
import sys
import pytest
import asyncio
from unittest.mock import patch, MagicMock

class TestCeleryWorkerEventLoop:
    def test_worker_init_sets_proactor_policy_on_windows(self):
        """On Windows, Celery worker must use ProactorEventLoop for subprocess support."""
        if sys.platform != "win32":
            pytest.skip("Windows-only test")
        
        from app.queue.tasks import on_worker_process_init
        
        with patch("asyncio.set_event_loop_policy") as mock_set_policy:
            with patch("asyncio.get_running_loop", side_effect=RuntimeError):
                with patch("asyncio.new_event_loop") as mock_new_loop:
                    mock_loop = MagicMock()
                    mock_new_loop.return_value = mock_loop
                    
                    # Mock DB/Redis connections
                    with patch("app.queue.tasks.db") as mock_db:
                        with patch("app.queue.tasks.redis_client") as mock_redis:
                            with patch("app.queue.tasks.redis_pubsub_client") as mock_pubsub:
                                with patch("app.queue.tasks._ensure_runtime_initialized") as mock_runtime:
                                    with patch("app.queue.tasks.register_builtin_tools"):
                                        with patch("app.queue.tasks.mcp_client_manager"):
                                            on_worker_process_init()
                    
                    # Assert ProactorEventLoopPolicy was set
                    from asyncio import WindowsProactorEventLoopPolicy
                    mock_set_policy.assert_called_once()
                    args, _ = mock_set_policy.call_args
                    assert isinstance(args[0], WindowsProactorEventLoopPolicy)
```

- [ ] **Step 2: Write test for decomposer deterministic routing**

In `tests/test_decomposer_routing.py`:
```python
import pytest
from app.workflows.decomposer import WorkflowDecomposer

class TestDecomposerRouting:
    def setup_method(self):
        self.decomposer = WorkflowDecomposer()
    
    def test_desktop_app_notepad_routes_to_desktop(self):
        query = "open notepad and write hello world"
        phases = self.decomposer.decompose(query)
        names = [p.name for p in phases]
        assert "desktop_automation" in names, f"Expected desktop_automation in {names}"
        assert "shell_execution" not in names, f"Shell shortcut should not appear for GUI apps"
    
    def test_desktop_app_calculator_routes_to_desktop(self):
        query = "open calculator and click 1 + 1"
        phases = self.decomposer.decompose(query)
        names = [p.name for p in phases]
        assert "desktop_automation" in names
    
    def test_browser_search_routes_to_browser(self):
        query = "search google for python tutorials"
        phases = self.decomposer.decompose(query)
        names = [p.name for p in phases]
        assert "browser_navigation" in names
        assert "desktop_automation" not in names
    
    def test_mixed_prompt_splits_sequentially(self):
        query = "open notepad write hello then open chrome and search python"
        phases = self.decomposer.decompose(query)
        names = [p.name for p in phases]
        # Desktop should come before browser
        if "desktop_automation" in names and "browser_navigation" in names:
            desktop_idx = names.index("desktop_automation")
            browser_idx = names.index("browser_navigation")
            assert desktop_idx < browser_idx, "Desktop phases must precede browser phases"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_queue_tasks.py tests/test_decomposer_routing.py -v`
Expected: FAIL (event loop policy not set, decomposer doesn't detect notepad/calculator)

---

## Task 2: Fix Windows Event Loop (Playwright Celery Fix)

**Files:**
- Modify: `app/queue/tasks.py`

- [ ] **Step 1: Add Windows event loop policy at worker startup**

At the very top of `on_worker_process_init` in `app/queue/tasks.py`, before any asyncio calls:

```python
@worker_process_init.connect
def on_worker_process_init(**kwargs):
    """Initialize AgentRuntime in each Celery worker child process."""
    global _worker_event_loop
    
    # Windows: Force ProactorEventLoop to support asyncio subprocess (required by Playwright)
    if sys.platform == "win32":
        import asyncio
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        logger.info("Celery worker: set WindowsProactorEventLoopPolicy for subprocess support")
    
    try:
        ...
```

Also add `import sys` at the top of the file if not already present.

- [ ] **Step 2: Verify syntax**

Run: `python -m py_compile app/queue/tasks.py`

- [ ] **Step 3: Run event loop test**

Run: `pytest tests/test_queue_tasks.py -v`
Expected: PASS

---

## Task 3: Add deterministic routing heuristics to decomposer

**Files:**
- Modify: `app/workflows/decomposer.py`

- [ ] **Step 1: Add keyword-based classification dictionaries**

After the `PHASE_PATTERNS` list, add:

```python
    # Deterministic routing: native desktop app keywords
    DESKTOP_APP_KEYWORDS: set = {
        "notepad", "calculator", "calc", "paint", "mspaint",
        "file explorer", "explorer", "vscode", "code.exe",
        "settings", "control panel", "wordpad", "cmd", "terminal",
        "powershell", "command prompt",
    }
    
    # Deterministic routing: browser/web keywords
    BROWSER_WEB_KEYWORDS: set = {
        "chrome", "google", "browser", "website", "web", "search",
        "youtube", "bing", "duckduckgo", "yahoo", "amazon",
        "url", "http", "https", "online", "internet",
    }
    
    # Deterministic routing: desktop UI action keywords
    DESKTOP_UI_ACTIONS: set = {
        "click", "type", "write text", "enter text", "fill",
        "press button", "check box", "select menu",
    }
```

- [ ] **Step 2: Add helper method `_classify_query`**

Add before `decompose`:

```python
    def _classify_query(self, query: str) -> tuple[bool, bool]:
        """Return (has_desktop, has_browser) based on keyword presence."""
        q = query.lower()
        has_desktop = any(kw in q for kw in self.DESKTOP_APP_KEYWORDS)
        has_browser = any(kw in q for kw in self.BROWSER_WEB_KEYWORDS)
        has_ui_action = any(kw in q for kw in self.DESKTOP_UI_ACTIONS)
        
        # If UI actions present but no browser keyword, assume desktop
        if has_ui_action and not has_browser:
            has_desktop = True
        
        return has_desktop, has_browser
```

- [ ] **Step 3: Rewrite `decompose` method with deterministic routing**

Replace the entire `decompose` method with:

```python
    def decompose(self, query: str) -> List[WorkflowPhase]:
        """Decompose a user query into ordered workflow phases.
        
        Uses deterministic keyword heuristics to separate desktop UI
        tasks from browser/web tasks. Mixed prompts are split sequentially
        (desktop first, browser later).
        """
        query_lower = query.lower()
        phases: List[WorkflowPhase] = []
        
        # Phase 1: Deterministic keyword-based classification
        has_desktop, has_browser = self._classify_query(query)
        
        # Phase 2: Pattern matching for additional context
        matched_patterns: List[str] = []
        for pattern in self.PHASE_PATTERNS:
            matched = False
            for regex in pattern.get("regexes", []):
                if re.search(regex, query_lower):
                    matched = True
                    break
            if not matched:
                for intent_keyword in pattern["intents"]:
                    if intent_keyword in query_lower:
                        matched = True
                        break
            if matched:
                matched_patterns.append(pattern["name"])
        
        # Phase 3: Build phase list with deterministic overrides
        # If native desktop apps detected, ALWAYS add desktop_automation first
        if has_desktop:
            phases.append(WorkflowPhase(
                phase_id="phase_1",
                name="desktop_automation",
                description="Interact with native desktop applications using UI automation",
                intent="desktop_automation",
                verification_criteria=[{"type": "desktop_action_completed"}],
            ))
        
        # If browser/web detected, add browser_navigation AFTER desktop
        if has_browser:
            phase_id = f"phase_{len(phases) + 1}"
            phases.append(WorkflowPhase(
                phase_id=phase_id,
                name="browser_navigation",
                description="Navigate browser and perform web UI actions",
                intent="browser_navigation",
                verification_criteria=[{"type": "browser_navigated"}],
            ))
        
        # Phase 4: Fallback to pattern-based decomposition if no deterministic match
        if not phases:
            for pattern_name in matched_patterns:
                phase_id = f"phase_{len(phases) + 1}"
                pattern = next(p for p in self.PHASE_PATTERNS if p["name"] == pattern_name)
                phases.append(WorkflowPhase(
                    phase_id=phase_id,
                    name=pattern_name,
                    description=pattern.get("description", f"Execute {pattern_name}"),
                    intent=pattern_name,
                    verification_criteria=pattern.get("verification", []),
                ))
        
        # Phase 5: Ultimate fallback
        if not phases:
            phases.append(WorkflowPhase(
                phase_id="phase_1",
                name="general_execution",
                description="Execute the user request",
                intent="general",
            ))
        
        # Phase 6: Set dependencies (sequential execution)
        for i, phase in enumerate(phases):
            if i > 0:
                phase.depends_on = [phases[i - 1].phase_id]
        
        logger.info(f"[WorkflowDecomposer] Decomposed query into {len(phases)} phases: {[p.name for p in phases]}")
        return phases
```

- [ ] **Step 4: Verify syntax**

Run: `python -m py_compile app/workflows/decomposer.py`

- [ ] **Step 5: Run decomposer tests**

Run: `pytest tests/test_decomposer_routing.py -v`
Expected: PASS

---

## Task 4: Update Executor prompt to forbid shell shortcuts for GUI apps

**Files:**
- Modify: `app/agents/executor.py`

- [ ] **Step 1: Add shell shortcut prohibition rule**

In `EXECUTOR_PROMPT`, after the existing DESKTOP GUI AUTOMATION rules and before the tool_call JSON example, add:

```
SHELL SHORTCUT PROHIBITION:
11. You MUST NEVER use shell__execute_command to open, launch, or interact with GUI applications (e.g., Notepad, Calculator, Chrome, VS Code) if the task requires further interaction within that app (typing, clicking, navigating).
    a. Opening a GUI app via PowerShell/batch and then trying to interact with it will FAIL because the shell tool cannot see or control the UI.
    b. Desktop apps MUST use desktop__get_ui_tree → desktop__click_element / desktop__type_element.
    c. Browser apps MUST use browser_env__launch → browser_env__navigate / browser_env__type / browser_env__click.
    d. The ONLY exception: if the task is purely to launch an app with no follow-up interaction, shell__execute_command is acceptable.
```

- [ ] **Step 2: Verify syntax**

Run: `python -m py_compile app/agents/executor.py`

---

## Task 5: Final verification

- [ ] **Step 1: Run all new and existing tests**

Run: `pytest tests/test_queue_tasks.py tests/test_decomposer_routing.py tests/test_desktop_env.py -v`
Expected: All PASS

- [ ] **Step 2: Check cross-platform compatibility**

- The event loop fix is gated behind `if sys.platform == "win32"` — Linux/macOS unaffected
- The decomposer heuristics use string matching — cross-platform by design
- No platform-specific imports added outside the Windows guard

- [ ] **Step 3: Check for infinite loop risk in executor**

- The new prompt rules are static instructions, not runtime logic
- No loops introduced in decomposer (sequential phase building)
- `_classify_query` is O(n) over keyword sets — bounded and fast
