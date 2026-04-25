# Browser Runtime Reliability Fixes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:dispatching-parallel-agents for independent tasks. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Make browser automation reliable: adaptive search, task-scoped sessions, page recovery, and robust WebSocket auth.

---

### Task A: Refactor BrowserEnvironment → BrowserSessionManager

**Files:**
- Modify: `app/environments/browser_env.py` (full rewrite)
- Modify: `app/tools/registry.py` (update tool registration to pass task_id)
- Test: `tests/test_browser_env.py`

**Step 1:** Read current `app/environments/browser_env.py` and `app/tools/registry.py`.

**Step 2:** Rewrite `browser_env.py` with two classes:

`BrowserSession`:
- `__init__(self, task_id: str)`
- `async launch(self, headless=False)` — start playwright, browser, context, page
- `async ensure_page(self)` — return page if alive, otherwise recover
- `async recover(self)` — create new page, restore current_url
- `is_alive(self)` — bool check
- `async search(self, query: str)` — domain-aware adaptive search
- `async navigate(self, url: str)` — goto url, update current_url
- `async click(self, selector: str)`
- `async type_text(self, selector: str, text: str)`
- `async screenshot(self, path: Optional[str])`
- `async get_text(self, selector: Optional[str])`
- `async close(self)`

`BrowserSessionManager`:
- `_sessions: Dict[str, BrowserSession]`
- `async get_or_create_session(task_id)`
- `async close_session(task_id)`
- `get_session(task_id)`

Domain-aware search logic:
```python
DOMAIN_SELECTORS = {
    "google.com": ['textarea[name="q"]', 'input[name="q"]', '#APjFqb'],
    "youtube.com": ['input[name="search_query"]', 'input#search', 'ytd-searchbox input'],
    "amazon.com": ['#twotabsearchtextbox', '#nav-bb-search input', '#nav-search-field input'],
}

FALLBACK_SELECTORS = [
    'input[type="search"]',
    'input[placeholder*="search" i]',
    '[role="searchbox"]',
    'input[name*="query" i]',
    'input[name*="search" i]',
    'input[name*="q" i]',
    'textarea[name*="q" i]',
    'form input',
    'input',
]
```

Search flow:
1. If not on search page, detect current domain from `page.url`
2. Try domain-specific selectors in order
3. Try fallback selectors in order
4. For each selector: `page.fill(selector, query)` then `page.press(selector, "Enter")`
5. If all fail: screenshot, list all input elements on page, return error

**Step 3:** Update `app/tools/registry.py` `_register_browser_env_tools`:
- Every tool action must pass `task_id` to `browser_session_manager`
- `BrowserEnvTool.execute` must receive `task_id` from context or state
- Since `ToolInput` only has `parameters`, add `task_id` extraction from `tool_input.parameters.get("task_id")` or use a default

Actually, looking at the executor, tool parameters come from LLM. The task_id is in the executor state. We need to modify the executor to inject `task_id` into browser env tool params.

**Simpler approach:** Store the current task_id in the global `browser_session_manager` via a method `set_active_task(task_id)` before executing browser tools. Or better: modify `BrowserEnvTool.execute` to accept `task_id` from a thread-local or explicit param.

The cleanest approach: modify the tool registration to look for `_task_id` in `tool_input.parameters` (injected by executor). And modify `executor_node` in `app/langgraph/nodes.py` to inject `task_id` into browser env tool params.

**Step 4:** Modify `executor_node` in `app/langgraph/nodes.py`:
After extracting `tool_params`, if tool_name starts with `browser_env__`, inject:
```python
if tool_name.startswith("browser_env__"):
    tool_params["_task_id"] = task_id
```

**Step 5:** Update tests `tests/test_browser_env.py`:
- Mock tests for BrowserSession
- Test domain-aware selector selection
- Test session reuse
- Test recovery

Run: `pytest tests/test_browser_env.py -v`

Commit: `git add app/environments/browser_env.py app/tools/registry.py app/langgraph/nodes.py tests/test_browser_env.py && git commit -m "feat: task-scoped browser sessions with adaptive search"`

---

### Task B: WebSocket Token Defensive Parsing

**Files:**
- Modify: `app/api/ws.py`
- Test: `tests/test_ws_auth.py`

**Step 1:** Read `app/api/ws.py`.

**Step 2:** Add imports:
```python
import urllib.parse
```

**Step 3:** Replace token parsing block (lines 59-64):
```python
    # Coerce token to string (FastAPI Query object may be passed if param missing)
    token_str = str(token) if token else ""
    if not token_str or token_str == "None":
        logger.warning(f"WebSocket missing token for task {task_id}")
        await websocket.close(code=1008, reason="Missing token")
        return
```

With:
```python
    # Coerce token to string and sanitize
    token_str = str(token) if token else ""
    if not token_str or token_str == "None":
        logger.warning(f"WebSocket missing token for task {task_id}")
        await websocket.close(code=1008, reason="Missing token")
        return

    # URL-decode and strip Bearer prefix
    token_str = urllib.parse.unquote(token_str)
    token_str = token_str.replace("Bearer ", "").replace("bearer ", "").strip()

    # Validate JWT structure (3 dot-separated segments)
    segments = token_str.split(".")
    if len(segments) != 3:
        logger.warning(
            f"WebSocket malformed token for task {task_id}: "
            f"{len(segments)} segments, length={len(token_str)}, "
            f"preview={token_str[:20]}..."
        )
        await websocket.close(code=1008, reason="Malformed token")
        return
```

**Step 4:** Add tests to `tests/test_ws_auth.py`:
```python
@pytest.mark.asyncio
async def test_websocket_url_encoded_token():
    mock_ws = AsyncMock(spec=WebSocket)
    mock_ws.path_params = {"task_id": "abc-123"}
    encoded_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIn0.rTCH8cLoGxAm_xw68z-zXVKi9ie6xJn9tnVWjd_9ftE"
    url_encoded = encoded_token.replace(".", "%2E")  # simulate partial encoding
    
    with patch("app.api.ws.verify_access_token", return_value={"sub": "user-1"}) as mock_verify:
        await websocket_endpoint(mock_ws, url_encoded)
    
    mock_verify.assert_called_once()
    call_args = mock_verify.call_args[0][0]
    assert "." in call_args  # decoded back

@pytest.mark.asyncio
async def test_websocket_bearer_prefix_token():
    mock_ws = AsyncMock(spec=WebSocket)
    mock_ws.path_params = {"task_id": "abc-123"}
    
    with patch("app.api.ws.verify_access_token", return_value={"sub": "user-1"}) as mock_verify:
        await websocket_endpoint(mock_ws, "Bearer valid.jwt.token")
    
    mock_verify.assert_called_once_with("valid.jwt.token")

@pytest.mark.asyncio
async def test_websocket_malformed_token():
    mock_ws = AsyncMock(spec=WebSocket)
    mock_ws.path_params = {"task_id": "abc-123"}
    
    with patch("app.api.ws.verify_access_token") as mock_verify:
        await websocket_endpoint(mock_ws, "not.a.valid.jwt")
    
    mock_ws.close.assert_called_once_with(code=1008, reason="Malformed token")
    mock_verify.assert_not_called()
```

Run: `pytest tests/test_ws_auth.py -v`

Commit: `git add app/api/ws.py tests/test_ws_auth.py && git commit -m "fix: WebSocket token URL-decode, Bearer strip, segment validation"`

---

### Task C: Executor Browser Env Task ID Injection

**Files:**
- Modify: `app/langgraph/nodes.py`

**Step 1:** In `executor_node`, after extracting `tool_params` (around line 226), add:
```python
            # Inject task_id for browser environment tools to enable session reuse
            if tool_name.startswith("browser_env__"):
                tool_params["_task_id"] = task_id
```

This is included in Task A's Step 4, but can be done independently.

---

## Execution Order

1. **Task A** (browser_env.py refactor) — large change
2. **Task C** (executor_node task_id injection) — small change, depends on Task A
3. **Task B** (ws.py token parsing) — independent, can run in parallel with Task A

**Recommended:** Dispatch Task A + Task B in parallel. Task C is done as part of Task A.
