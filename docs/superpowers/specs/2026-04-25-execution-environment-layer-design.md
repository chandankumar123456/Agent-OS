# Execution Environment Layer — AgentOS v2 Design Spec

> **Date:** 2026-04-25  
> **Status:** Approved for implementation  
> **Author:** AgentOS Team  

## 1. Problem Statement

AgentOS currently treats all "search" and "web" tasks as backend API calls. When a user says:

> "open chrome and search for what is agentic ai"

The system:
1. Classifies the task as `Capability.WEB`
2. Selects `ExecutionEnvironment.BROWSER`
3. But the **executor** still calls backend `browser__search_web` (DuckDuckGo HTTP scraping)
4. Chrome is opened via `shell__execute_command`, but the actual search happens in the backend logs

**Result:** Chrome opens to a blank page. The user sees no search results in the browser UI.

## 2. Root Cause

- The `CapabilityRouter` maps `WEB` capability to generic web tools (`browser__http_request`, `browser__scrape_page`, `search`).
- The `FeasibilityEngine.select_environment()` chooses `BROWSER` environment based on capability, but there is **no actual browser automation runtime**.
- The `executor_node` uses `ToolRegistry` which only contains MCP-wrapped HTTP tools, not real browser UI drivers.
- There is no distinction between:
  - **UI/browser interaction** (open Chrome, click, type, fill forms)
  - **Information retrieval** (backend web search, API calls, scraping)

## 3. Goal

Transform AgentOS into a true execution operating system that dynamically selects execution environments based on task intent, then uses the correct runtime for that environment.

## 4. Execution Environments

### 4.1 Browser Environment (NEW)
**Purpose:** Real browser UI automation.

**Triggers (keywords in query):**
- "open chrome", "open browser", "launch browser"
- "search in browser", "search on google", "search in chrome"
- "login to", "sign in to", "fill form", "click button"
- "navigate to", "go to website", "browse to"
- "screenshot", "capture page"

**Runtime:** Playwright (primary), Selenium (fallback).

**Tools:**
- `browser_env__launch(url)` — launch browser to URL
- `browser_env__navigate(url)` — navigate current tab
- `browser_env__search(query)` — focus address bar, type query, press enter
- `browser_env__click(selector)` — click element
- `browser_env__type(selector, text)` — type into input
- `browser_env__screenshot(path)` — capture screenshot
- `browser_env__get_text(selector)` — extract text from element
- `browser_env__close()` — close browser

**Expected behavior:**
- Launch visible (non-headless) browser when user explicitly requests UI interaction
- Perform actions in the real browser window
- Return screenshot or page text as evidence

### 4.2 Terminal Environment
**Purpose:** Shell/command execution.

**Triggers:** `shell`, `command`, `terminal`, `run script`, `git`, `install`, `docker`, `npm`, `pip`

**Runtime:** Existing `shell__execute_command` / `shell__run_script` MCP tools.

**No changes needed** — already works.

### 4.3 File Environment
**Purpose:** File system operations.

**Triggers:** `read file`, `write file`, `edit file`, `create file`, `list directory`, `search files`

**Runtime:** Existing `filesystem__*` MCP tools.

**No changes needed** — already works.

### 4.4 Cloud/API Environment (RENAMED from current "Browser" MCP server)
**Purpose:** Backend web search, HTTP requests, API calls, scraping without UI.

**Triggers:** `search latest`, `find research`, `summarize topic`, `fetch data`, `API call`, `scrape website`

**Runtime:** Existing `browser__http_request`, `browser__scrape_page`, `browser__search_web` MCP tools.

**Changes:**
- Rename MCP server from `browser` → `cloud_api` to avoid semantic confusion
- Rename tools from `browser__*` → `cloud__*` (e.g., `cloud__search_web`)
- Keep same implementation (urllib, BeautifulSoup, DuckDuckGo)

### 4.5 Sandbox Environment
**Purpose:** Isolated execution of untrusted code.

**Triggers:** `run untrusted code`, `execute generated script`, `test in isolation`

**Runtime:** Placeholder for Docker / E2B / Daytona.

**Current behavior:** Delegates to shell with restricted paths.

**Future:** Add Docker container execution.

## 5. Execution Environment Selector

New component: `ExecutionEnvironmentSelector`

Located in: `app/capabilities/environment_selector.py`

**Logic:**
```python
def select(query: str, assessment: CapabilityAssessment) -> ExecutionEnvironment:
    q = query.lower()
    
    # Browser UI interaction takes highest priority
    if any(kw in q for kw in BROWSER_UI_KEYWORDS):
        return ExecutionEnvironment.BROWSER_UI
    
    # Terminal
    if assessment.primary_capability == Capability.SHELL:
        return ExecutionEnvironment.SHELL
    
    # File
    if assessment.primary_capability == Capability.FILE:
        return ExecutionEnvironment.FILE
    
    # Web / API (backend search, scraping)
    if assessment.primary_capability == Capability.WEB:
        return ExecutionEnvironment.CLOUD_API
    
    # Code execution
    if assessment.primary_capability == Capability.CODE:
        return ExecutionEnvironment.SANDBOX
    
    return ExecutionEnvironment.LOCAL
```

**New enum values in `ExecutionEnvironment`:**
- `BROWSER_UI` — real browser automation via Playwright
- `CLOUD_API` — backend HTTP/search APIs (renamed from BROWSER)
- `FILE` — file system operations
- `SHELL` — terminal commands
- `SANDBOX` — isolated execution
- `LOCAL` — direct Python

## 6. Planner Fix

Update `PLANNER_SYSTEM_PROMPT_TEMPLATE` in `app/langgraph/nodes.py` and `app/agents/planner.py`.

**New prompt section:**
```
Execution Environment Awareness:
- If the user asks to "open chrome", "open browser", "search in browser", "login to", "click", "fill form", or "navigate website", generate steps that use browser_env__* tools.
- If the user asks to "search for information", "find research", "summarize topic", or "fetch data", generate steps that use cloud__search_web or cloud__http_request tools.
- Do NOT use cloud__search_web when the user explicitly wants browser UI interaction.
```

## 7. Verifier Fix

Update `verifier_node` in `app/langgraph/nodes.py`.

**For Browser Environment tasks:**
- Check if a screenshot was captured
- Check if the browser actually navigated to the expected URL
- Verify page title or extracted text matches search intent

**For Cloud/API tasks:**
- Check if HTTP response or search results were returned
- Verify result quality

## 8. WebSocket Bug Fix

**File:** `app/api/ws.py`

**Error:** `AttributeError: 'Query' object has no attribute 'rsplit'`

**Root cause:** `token` parameter is declared as `token: str = Query(...)` but FastAPI passes the `Query` object itself when the parameter is not properly coerced (e.g., missing or malformed query string).

**Fix:**
```python
token_str = str(token) if token else ""
if not token_str:
    await websocket.close(code=1008, reason="Missing token")
    return
payload = verify_access_token(token_str)
```

## 9. Playwright Integration

**Add to `requirements.txt`:**
```
playwright==1.51.0
```

**New module:** `app/environments/browser_env.py`

**Singleton:** `browser_environment`

**Interface:**
```python
class BrowserEnvironment:
    async def launch(self, url: Optional[str] = None, headless: bool = False) -> str
    async def navigate(self, url: str) -> str
    async def search(self, query: str) -> str
    async def click(self, selector: str) -> str
    async def type(self, selector: str, text: str) -> str
    async def screenshot(self, path: Optional[str] = None) -> str
    async def get_text(self, selector: Optional[str] = None) -> str
    async def close(self) -> str
```

**Tool registration:** Register `browser_env__*` tools in `ToolRegistry` on startup.

## 10. MCP Server Rename

**File:** `app/mcp/servers/browser.py` → `app/mcp/servers/cloud_api.py`

**Changes:**
- Rename FastMCP instance from `browser` to `cloud_api`
- Rename tools from `browser__http_request` → `cloud__http_request`
- Rename tools from `browser__scrape_page` → `cloud__scrape_page`
- Rename tools from `browser__search_web` → `cloud__search_web`
- Update `app/main.py` or orchestrator startup to reference new module path

## 11. Data Flow

```
User Query
  ↓
CapabilityRouter.classify()
  ↓
ExecutionEnvironmentSelector.select()
  ↓
FeasibilityEngine.check()
  ↓
Planner (prompted with env context)
  ↓
Executor (uses env-specific tools)
  ↓
Verifier (env-specific validation)
  ↓
Summarizer
```

## 12. Testing Strategy

- **Unit:** `ExecutionEnvironmentSelector` keyword matching
- **Unit:** `BrowserEnvironment` mock Playwright page
- **Integration:** End-to-end task with "open chrome and search..."
- **Integration:** WebSocket connection with valid/missing token
- **Regression:** Cloud/API search still works for "search latest AI news"

## 13. Rollout Order

1. Fix WebSocket bug (`app/api/ws.py`)
2. Rename MCP browser server → cloud_api
3. Update `ExecutionEnvironment` enum and `FeasibilityEngine`
4. Build `BrowserEnvironment` with Playwright
5. Update planner prompts
6. Update verifier logic
7. Add `ExecutionEnvironmentSelector`
8. Test end-to-end

---
*Spec approved by user. Proceed to implementation plan.*
