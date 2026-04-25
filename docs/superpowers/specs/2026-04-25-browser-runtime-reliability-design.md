# Browser Runtime Reliability Fixes — Design Spec

> **Date:** 2026-04-25  
> **Status:** Approved for implementation  
> **Scope:** Browser execution layer only — no architecture changes  

## 1. Problem Summary

The Execution Environment Layer correctly routes browser UI tasks to `ExecutionEnvironment.BROWSER_UI` and invokes `browser_env__*` tools. However, the browser runtime itself is fragile:

| # | Failure | Root Cause |
|---|---------|-----------|
| 1 | `Page.fill: Timeout` on YouTube | `search()` hardcodes Google selector `textarea[name="q"]` |
| 2 | Browser relaunched every step | Global singleton `BrowserEnvironment` — no task-scoped sessions |
| 3 | "Target page has been closed" | Executor uses stale page references across steps |
| 4 | WebSocket 403 "Not enough segments" | Token may contain URL-encoded chars or `Bearer` prefix |

## 2. Fix 1: Adaptive Website Search

**File:** `app/environments/browser_env.py`

**Current:** `search()` always navigates to Google and uses `textarea[name="q"]`.

**New behavior:**
1. Detect current domain from `page.url`
2. Use domain-specific search selector:
   - `google.com` → `textarea[name="q"]`
   - `youtube.com` → `input[name="search_query"]`
   - `amazon.com` → `#twotabsearchtextbox`
3. Generic fallback chain:
   - `input[type="search"]`
   - `input[placeholder*="search" i]`
   - `[role="searchbox"]`
   - `input[name*="query" i]`
   - `input[name*="search" i]`
4. If all fail → screenshot + return error with available inputs list

## 3. Fix 2: Task-Scoped Browser Session Manager

**File:** `app/environments/browser_env.py` (refactored)

**Current:** Single global `browser_environment = BrowserEnvironment()`.

**New:** `BrowserSessionManager` class:
```python
class BrowserSessionManager:
    def __init__(self):
        self._sessions: Dict[str, BrowserSession] = {}
    
    async def get_or_create_session(self, task_id: str) -> BrowserSession:
        if task_id in self._sessions:
            session = self._sessions[task_id]
            if session.is_alive():
                return session
        session = BrowserSession()
        await session.launch()
        self._sessions[task_id] = session
        return session
    
    async def close_session(self, task_id: str):
        session = self._sessions.pop(task_id, None)
        if session:
            await session.close()
    
    def get_session(self, task_id: str) -> Optional[BrowserSession]:
        return self._sessions.get(task_id)
```

`BrowserSession` encapsulates:
- `_playwright`, `_browser`, `_context`, `_page`
- `current_url`
- `is_alive()` — checks page exists and not closed
- `recover()` — reopen page, restore URL

## 4. Fix 3: Page State Validation & Recovery

**File:** `app/environments/browser_env.py`

Before every action:
```python
async def _ensure_page(self):
    if self._page and not self._page.is_closed():
        return self._page
    # Recovery
    logger.warning("BrowserSession: page closed, attempting recovery")
    self._page = await self._context.new_page()
    if self._current_url:
        await self._page.goto(self._current_url, wait_until="domcontentloaded")
    return self._page
```

After navigation actions, update `self._current_url`.

## 5. Fix 4: WebSocket Token Defensive Parsing

**File:** `app/api/ws.py`

Add before `verify_access_token`:
```python
import urllib.parse

token_str = str(token) if token else ""
token_str = urllib.parse.unquote(token_str)
token_str = token_str.replace("Bearer ", "").replace("bearer ", "").strip()

# Validate JWT structure (3 dot-separated segments)
segments = token_str.split(".")
if len(segments) != 3:
    logger.warning(f"WebSocket malformed token for task {task_id}: {len(segments)} segments, length={len(token_str)}")
    await websocket.close(code=1008, reason="Malformed token")
    return
```

## 6. Testing

- `test_browser_env.py` — adaptive search for Google, YouTube, unknown domain
- `test_browser_session.py` — session reuse, recovery, close
- `test_ws_auth.py` — URL-encoded token, Bearer prefix, malformed token

---
*Spec approved. Proceed to implementation plan.*
