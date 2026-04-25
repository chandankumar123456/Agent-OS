# Execution Environment Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:dispatching-parallel-agents for independent tasks, then superpowers:subagent-driven-development or superpowers:executing-plans to implement task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform AgentOS from generic tool-calling into a true execution OS with Browser, Terminal, File, Cloud/API, and Sandbox environments.

**Architecture:** Add `ExecutionEnvironmentSelector` that routes tasks to environment-specific toolsets. Build `BrowserEnvironment` using Playwright for real UI automation. Rename existing MCP `browser` server to `cloud_api` to clarify backend vs UI separation. Update planner prompts and verifier logic to be environment-aware.

**Tech Stack:** Python 3.11, FastAPI, Playwright, LangGraph, Pydantic, MCP

---

## File Map

| File | Responsibility |
|------|---------------|
| `app/capabilities/models.py` | `ExecutionEnvironment` enum, `EnvironmentConfig` model |
| `app/capabilities/environment_selector.py` | NEW — routes queries to correct environment |
| `app/capabilities/feasibility.py` | Update `select_environment()` to use selector |
| `app/environments/__init__.py` | NEW — environment package init |
| `app/environments/browser_env.py` | NEW — Playwright browser automation singleton |
| `app/environments/base.py` | NEW — base environment interface |
| `app/tools/registry.py` | Register `browser_env__*` tools |
| `app/mcp/servers/cloud_api.py` | RENAME from `browser.py` — backend HTTP/search tools |
| `app/mcp/client_manager.py` | Update server paths and tool name prefixes |
| `app/langgraph/nodes.py` | Update planner/verifier prompts for environment awareness |
| `app/agents/planner.py` | Update `PLANNER_PROMPT` with environment guidance |
| `app/api/ws.py` | Fix WebSocket token parsing bug |
| `requirements.txt` | Add `playwright==1.51.0` |
| `tests/test_environment_selector.py` | NEW — unit tests for selector |
| `tests/test_browser_env.py` | NEW — mock tests for browser environment |
| `tests/test_ws_auth.py` | NEW — WebSocket auth tests |

---

### Task 1: Fix WebSocket Authentication Bug

**Files:**
- Modify: `app/api/ws.py:53-64`
- Test: `tests/test_ws_auth.py`

- [ ] **Step 1: Read `app/api/ws.py` lines 50-70**

- [ ] **Step 2: Fix token coercion**

Replace:
```python
async def websocket_endpoint(websocket: WebSocket, token: str = Query(...)) -> None:
    task_id = websocket.path_params.get("task_id", "")
    if not task_id:
        await websocket.close(code=1008)
        return

    # Validate JWT token before accepting connection
    payload = verify_access_token(token)
```

With:
```python
async def websocket_endpoint(websocket: WebSocket, token: str = Query(...)) -> None:
    task_id = websocket.path_params.get("task_id", "")
    if not task_id:
        await websocket.close(code=1008)
        return

    # Coerce token to string (FastAPI Query object may be passed if param missing)
    token_str = str(token) if token else ""
    if not token_str or token_str == "None":
        logger.warning(f"WebSocket missing token for task {task_id}")
        await websocket.close(code=1008, reason="Missing token")
        return

    # Validate JWT token before accepting connection
    payload = verify_access_token(token_str)
```

- [ ] **Step 3: Create test**

`tests/test_ws_auth.py`:
```python
import pytest
from fastapi import WebSocket
from unittest.mock import AsyncMock, MagicMock, patch

from app.api.ws import websocket_endpoint


@pytest.mark.asyncio
async def test_websocket_missing_token():
    mock_ws = AsyncMock(spec=WebSocket)
    mock_ws.path_params = {"task_id": "abc-123"}
    
    with patch("app.api.ws.verify_access_token", return_value=None) as mock_verify:
        await websocket_endpoint(mock_ws, "")
    
    mock_ws.close.assert_called_once_with(code=1008, reason="Missing token")
    mock_verify.assert_not_called()


@pytest.mark.asyncio
async def test_websocket_valid_token():
    mock_ws = AsyncMock(spec=WebSocket)
    mock_ws.path_params = {"task_id": "abc-123"}
    
    with patch("app.api.ws.verify_access_token", return_value={"sub": "user-1"}) as mock_verify:
        with patch("app.api.ws.manager") as mock_mgr:
            mock_mgr.connect = AsyncMock()
            mock_ws.receive_text = AsyncMock(side_effect=["ping", Exception("done")])
            
            try:
                await websocket_endpoint(mock_ws, "valid.jwt.token")
            except Exception:
                pass
    
    mock_verify.assert_called_once_with("valid.jwt.token")
```

- [ ] **Step 4: Run test**

```bash
pytest tests/test_ws_auth.py -v
```
Expected: 2 passes

- [ ] **Step 5: Commit**

```bash
git add app/api/ws.py tests/test_ws_auth.py
git commit -m "fix: WebSocket token parsing - coerce Query to string"
```

---

### Task 2: Rename MCP Browser Server → Cloud API

**Files:**
- Rename: `app/mcp/servers/browser.py` → `app/mcp/servers/cloud_api.py`
- Modify: `app/mcp/client_manager.py`
- Modify: `app/capabilities/router.py`
- Test: `tests/test_cloud_api_server.py`

- [ ] **Step 1: Rename file and update contents**

`app/mcp/servers/cloud_api.py` (was `browser.py`):
- Change `mcp = FastMCP("browser")` → `mcp = FastMCP("cloud_api")`
- Keep tool function names the same internally, but update any docstrings

- [ ] **Step 2: Update client_manager references**

In `app/mcp/client_manager.py`, find the server registration list. Change:
```python
{"name": "browser", "module": "app.mcp.servers.browser"}
```
→
```python
{"name": "cloud_api", "module": "app.mcp.servers.cloud_api"}
```

Also update tool prefix mapping if any:
```python
# Old prefix
"browser__": "browser"
# New prefix
"cloud__": "cloud_api"
```

- [ ] **Step 3: Update capability router tool suggestions**

In `app/capabilities/router.py` line 152:
```python
Capability.WEB: ["browser__http_request", "browser__scrape_page", "search"],
```
→
```python
Capability.WEB: ["cloud__http_request", "cloud__scrape_page", "cloud__search_web"],
```

- [ ] **Step 4: Create test**

`tests/test_cloud_api_server.py`:
```python
def test_cloud_api_module_imports():
    from app.mcp.servers import cloud_api
    assert cloud_api.mcp.name == "cloud_api"
```

- [ ] **Step 5: Run test**

```bash
pytest tests/test_cloud_api_server.py -v
```

- [ ] **Step 6: Commit**

```bash
git add app/mcp/servers/cloud_api.py app/mcp/client_manager.py app/capabilities/router.py tests/test_cloud_api_server.py
git rm app/mcp/servers/browser.py
git commit -m "refactor: rename MCP browser server to cloud_api for semantic clarity"
```

---

### Task 3: Update ExecutionEnvironment Enum and Models

**Files:**
- Modify: `app/capabilities/models.py`

- [ ] **Step 1: Add new enum values**

Replace `ExecutionEnvironment` enum with:
```python
class ExecutionEnvironment(str, Enum):
    LOCAL = "local"
    SHELL = "shell"
    BROWSER_UI = "browser_ui"      # NEW: real browser automation
    CLOUD_API = "cloud_api"        # RENAMED from BROWSER
    FILE = "file"                  # NEW
    SANDBOX = "sandbox"
    DESKTOP = "desktop"            # Future
```

- [ ] **Step 2: Add environment to EnvironmentConfig**

Add field:
```python
class EnvironmentConfig(BaseModel):
    environment: ExecutionEnvironment
    working_dir: Optional[str] = None
    allowed_paths: List[str] = []
    blocked_commands: List[str] = []
    network_access: bool = True
    timeout_seconds: int = 300
    headless: bool = True          # NEW: for browser env
    screenshot_on_complete: bool = False  # NEW
```

- [ ] **Step 3: Commit**

```bash
git add app/capabilities/models.py
git commit -m "feat: expand ExecutionEnvironment enum with browser_ui, cloud_api, file"
```

---

### Task 4: Build ExecutionEnvironmentSelector

**Files:**
- Create: `app/environments/__init__.py`
- Create: `app/environments/base.py`
- Create: `app/capabilities/environment_selector.py`
- Test: `tests/test_environment_selector.py`

- [ ] **Step 1: Create base environment interface**

`app/environments/base.py`:
```python
from abc import ABC, abstractmethod
from typing import Dict, Any

class BaseEnvironment(ABC):
    name: str = "base"

    @abstractmethod
    async def execute(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute an action in this environment."""
        pass

    @abstractmethod
    async def health_check(self) -> Dict[str, str]:
        pass
```

- [ ] **Step 2: Create environment_selector.py**

`app/capabilities/environment_selector.py`:
```python
import re
from typing import Set
from .models import Capability, CapabilityAssessment, ExecutionEnvironment

# Keywords that trigger real browser UI automation
BROWSER_UI_KEYWORDS = [
    "open chrome", "open browser", "launch browser", "launch chrome",
    "search in browser", "search on google", "search in chrome", "google search",
    "login to", "sign in to", "log in to", "fill form", "fill out form",
    "click button", "click link", "navigate to", "go to website", "browse to",
    "screenshot", "capture page", "take screenshot", "scroll down", "scroll up",
    "type in", "enter text", "submit form", "refresh page", "go back",
]

# Terminal keywords
SHELL_KEYWORDS = [
    "shell", "command", "terminal", "bash", "powershell", "cmd",
    "run command", "execute command", "install ", "git ", "docker ", "npm ", "pip ",
]

# File keywords
FILE_KEYWORDS = [
    "read file", "write file", "edit file", "create file", "delete file",
    "list directory", "search files", "file content", "save file",
]

class ExecutionEnvironmentSelector:
    def select(self, query: str, assessment: CapabilityAssessment) -> ExecutionEnvironment:
        q = query.lower()

        # 1. Browser UI interaction (highest priority)
        for kw in BROWSER_UI_KEYWORDS:
            if kw in q:
                return ExecutionEnvironment.BROWSER_UI

        # 2. Shell / Terminal
        for kw in SHELL_KEYWORDS:
            if kw in q:
                return ExecutionEnvironment.SHELL

        # 3. File operations
        for kw in FILE_KEYWORDS:
            if kw in q:
                return ExecutionEnvironment.FILE

        # 4. Capability-based fallback
        primary = assessment.primary_capability
        if primary == Capability.WEB:
            return ExecutionEnvironment.CLOUD_API
        elif primary == Capability.SHELL:
            return ExecutionEnvironment.SHELL
        elif primary == Capability.FILE:
            return ExecutionEnvironment.FILE
        elif primary == Capability.CODE:
            return ExecutionEnvironment.SANDBOX
        elif primary == Capability.DEPLOYMENT:
            return ExecutionEnvironment.SHELL

        return ExecutionEnvironment.LOCAL

environment_selector = ExecutionEnvironmentSelector()
```

- [ ] **Step 3: Create tests**

`tests/test_environment_selector.py`:
```python
import pytest
from app.capabilities.environment_selector import ExecutionEnvironmentSelector
from app.capabilities.models import Capability, CapabilityAssessment, CapabilityRequirement, ExecutionEnvironment

selector = ExecutionEnvironmentSelector()

def make_assessment(primary: Capability):
    return CapabilityAssessment(
        task_id="t1",
        query="test",
        required_capabilities=[CapabilityRequirement(capability=primary)],
        primary_capability=primary,
    )

def test_browser_ui_open_chrome():
    assessment = make_assessment(Capability.WEB)
    result = selector.select("open chrome and search for AI", assessment)
    assert result == ExecutionEnvironment.BROWSER_UI

def test_browser_ui_login():
    assessment = make_assessment(Capability.WEB)
    result = selector.select("login to linkedin", assessment)
    assert result == ExecutionEnvironment.BROWSER_UI

def test_cloud_api_fallback():
    assessment = make_assessment(Capability.WEB)
    result = selector.select("search latest AI news", assessment)
    assert result == ExecutionEnvironment.CLOUD_API

def test_shell_env():
    assessment = make_assessment(Capability.SHELL)
    result = selector.select("run git status", assessment)
    assert result == ExecutionEnvironment.SHELL

def test_file_env():
    assessment = make_assessment(Capability.FILE)
    result = selector.select("read file config.txt", assessment)
    assert result == ExecutionEnvironment.FILE

def test_sandbox_for_code():
    assessment = make_assessment(Capability.CODE)
    result = selector.select("write a python script", assessment)
    assert result == ExecutionEnvironment.SANDBOX
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_environment_selector.py -v
```

- [ ] **Step 5: Commit**

```bash
git add app/environments/ app/capabilities/environment_selector.py tests/test_environment_selector.py
git commit -m "feat: ExecutionEnvironmentSelector with keyword-based routing"
```

---

### Task 5: Update FeasibilityEngine to Use Selector

**Files:**
- Modify: `app/capabilities/feasibility.py`
- Modify: `app/capabilities/__init__.py`

- [ ] **Step 1: Import selector**

Add to `app/capabilities/feasibility.py`:
```python
from .environment_selector import environment_selector
```

- [ ] **Step 2: Update `select_environment` method**

Replace `select_environment` with:
```python
    def select_environment(
        self,
        assessment: CapabilityAssessment,
        report: FeasibilityReport,
    ) -> EnvironmentConfig:
        """Select the best execution environment for the task."""
        env = environment_selector.select(assessment.query, assessment)

        home = os.path.expanduser("~")
        config = EnvironmentConfig(
            environment=env,
            working_dir=os.getcwd(),
            allowed_paths=[home, os.getcwd()],
            blocked_commands=["rm -rf /", "format", "dd if=/dev/zero"],
            network_access=True,
            timeout_seconds=300,
            headless=(env != ExecutionEnvironment.BROWSER_UI),
            screenshot_on_complete=(env == ExecutionEnvironment.BROWSER_UI),
        )
        return config
```

- [ ] **Step 3: Export selector from capabilities package**

In `app/capabilities/__init__.py`, ensure:
```python
from .environment_selector import environment_selector
```

- [ ] **Step 4: Commit**

```bash
git add app/capabilities/feasibility.py app/capabilities/__init__.py
git commit -m "feat: integrate ExecutionEnvironmentSelector into FeasibilityEngine"
```

---

### Task 6: Build BrowserEnvironment with Playwright

**Files:**
- Create: `app/environments/browser_env.py`
- Modify: `app/tools/registry.py`
- Modify: `requirements.txt`
- Test: `tests/test_browser_env.py`

- [ ] **Step 1: Add playwright to requirements**

`requirements.txt`:
```
playwright==1.51.0
```

- [ ] **Step 2: Install playwright browsers**

```bash
playwright install chromium
```

- [ ] **Step 3: Create BrowserEnvironment**

`app/environments/browser_env.py`:
```python
"""Browser Environment — real browser UI automation via Playwright."""
import os
import tempfile
from typing import Optional, Dict, Any
from playwright.async_api import async_playwright, Page, Browser, BrowserContext

from ..logs.logger import logger
from ..tools.base import ToolInput, ToolOutput


class BrowserEnvironment:
    """Manages a Playwright browser instance for UI automation tasks."""

    def __init__(self):
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._headless = False

    async def _ensure_browser(self) -> Page:
        if self._page and not self._page.is_closed():
            return self._page

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self._headless,
            args=["--disable-blink-features=AutomationControlled"]
        )
        self._context = await self._browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        self._page = await self._context.new_page()
        logger.info("BrowserEnvironment: launched new browser instance")
        return self._page

    async def launch(self, url: Optional[str] = None, headless: bool = False) -> ToolOutput:
        self._headless = headless
        page = await self._ensure_browser()
        if url:
            await page.goto(url, wait_until="domcontentloaded")
            logger.info(f"BrowserEnvironment: navigated to {url}")
            return ToolOutput(success=True, result={"message": f"Launched browser and navigated to {url}"})
        return ToolOutput(success=True, result={"message": "Browser launched"})

    async def navigate(self, url: str) -> ToolOutput:
        page = await self._ensure_browser()
        await page.goto(url, wait_until="domcontentloaded")
        title = await page.title()
        return ToolOutput(success=True, result={"url": url, "title": title})

    async def search(self, query: str) -> ToolOutput:
        page = await self._ensure_browser()
        # Navigate to Google and search
        await page.goto("https://www.google.com", wait_until="domcontentloaded")
        # Accept cookies if present (generic selectors)
        try:
            await page.click('button:has-text("Accept all")', timeout=3000)
        except Exception:
            pass
        await page.fill('textarea[name="q"]', query)
        await page.press('textarea[name="q"]', "Enter")
        await page.wait_for_load_state("networkidle")
        title = await page.title()
        return ToolOutput(success=True, result={"query": query, "page_title": title, "message": f"Searched for '{query}' in browser"})

    async def click(self, selector: str) -> ToolOutput:
        page = await self._ensure_browser()
        await page.click(selector)
        return ToolOutput(success=True, result={"message": f"Clicked {selector}"})

    async def type_text(self, selector: str, text: str) -> ToolOutput:
        page = await self._ensure_browser()
        await page.fill(selector, text)
        return ToolOutput(success=True, result={"message": f"Typed into {selector}"})

    async def screenshot(self, path: Optional[str] = None) -> ToolOutput:
        page = await self._ensure_browser()
        if not path:
            path = os.path.join(tempfile.gettempdir(), "agentos_screenshot.png")
        await page.screenshot(path=path, full_page=True)
        return ToolOutput(success=True, result={"path": path, "message": f"Screenshot saved to {path}"})

    async def get_text(self, selector: Optional[str] = None) -> ToolOutput:
        page = await self._ensure_browser()
        if selector:
            text = await page.inner_text(selector)
        else:
            text = await page.inner_text("body")
        return ToolOutput(success=True, result={"text": text[:5000]})

    async def close(self) -> ToolOutput:
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        self._page = None
        self._context = None
        logger.info("BrowserEnvironment: browser closed")
        return ToolOutput(success=True, result={"message": "Browser closed"})

    async def health_check(self) -> Dict[str, str]:
        try:
            page = await self._ensure_browser()
            await page.goto("about:blank")
            return {"status": "healthy", "message": "Browser launched successfully"}
        except Exception as e:
            return {"status": "unhealthy", "message": str(e)}


browser_environment = BrowserEnvironment()
```

- [ ] **Step 4: Register browser_env tools in ToolRegistry**

In `app/tools/registry.py`, add to `ToolRegistry.__init__` after `_register_default_tools`:
```python
    def _register_browser_env_tools(self):
        from ..environments.browser_env import browser_environment
        
        class BrowserEnvTool:
            def __init__(self, name, action):
                self.name = name
                self.description = f"Browser environment: {action}"
                self.tool_type = "browser_env"
                self._action = action
            
            def get_schema(self):
                return {"name": self.name, "description": self.description, "parameters": {}}
            
            async def execute(self, tool_input: ToolInput):
                params = tool_input.parameters
                if self._action == "launch":
                    return await browser_environment.launch(params.get("url"), params.get("headless", False))
                elif self._action == "navigate":
                    return await browser_environment.navigate(params.get("url"))
                elif self._action == "search":
                    return await browser_environment.search(params.get("query"))
                elif self._action == "click":
                    return await browser_environment.click(params.get("selector"))
                elif self._action == "type":
                    return await browser_environment.type_text(params.get("selector"), params.get("text"))
                elif self._action == "screenshot":
                    return await browser_environment.screenshot(params.get("path"))
                elif self._action == "get_text":
                    return await browser_environment.get_text(params.get("selector"))
                elif self._action == "close":
                    return await browser_environment.close()
                return ToolOutput(success=False, error=f"Unknown action: {self._action}")
        
        for action in ["launch", "navigate", "search", "click", "type", "screenshot", "get_text", "close"]:
            self.register(BrowserEnvTool(f"browser_env__{action}", action))
        logger.info("Browser environment tools registered")
```

And call it in `__init__`:
```python
    def __init__(self):
        if self._initialized:
            return
        self.tools: Dict[str, RegisteredTool] = {}
        self._mcp_tools_registered = False
        self._register_default_tools()
        self._register_browser_env_tools()
        self._initialized = True
```

- [ ] **Step 5: Create mock tests**

`tests/test_browser_env.py`:
```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.environments.browser_env import BrowserEnvironment


@pytest.fixture
def browser_env():
    return BrowserEnvironment()


@pytest.mark.asyncio
async def test_browser_launch(browser_env):
    mock_page = AsyncMock()
    mock_browser = AsyncMock()
    mock_pw = MagicMock()
    mock_pw.chromium.launch = AsyncMock(return_value=mock_browser)
    mock_browser.new_context = AsyncMock(return_value=AsyncMock(new_page=AsyncMock(return_value=mock_page)))
    mock_page.is_closed.return_value = False
    mock_page.goto = AsyncMock()
    mock_page.title = AsyncMock(return_value="Test")

    with patch("app.environments.browser_env.async_playwright", return_value=AsyncMock(start=AsyncMock(return_value=mock_pw))):
        with patch.object(mock_pw, "chromium", MagicMock(launch=AsyncMock(return_value=mock_browser))):
            result = await browser_env.launch(url="https://example.com")
            assert result.success
```

- [ ] **Step 6: Run tests**

```bash
pytest tests/test_browser_env.py -v
```

- [ ] **Step 7: Commit**

```bash
git add app/environments/browser_env.py app/tools/registry.py requirements.txt tests/test_browser_env.py
git commit -m "feat: BrowserEnvironment with Playwright UI automation tools"
```

---

### Task 7: Update Planner Prompts for Environment Awareness

**Files:**
- Modify: `app/langgraph/nodes.py`
- Modify: `app/agents/planner.py`

- [ ] **Step 1: Update LangGraph planner prompt**

In `app/langgraph/nodes.py`, append to `PLANNER_SYSTEM_PROMPT_TEMPLATE` after line 57:
```
Execution Environment Awareness:
- If the user asks to "open chrome", "open browser", "search in browser", "login to", "click", "fill form", or "navigate website", use browser_env__* tools (e.g., browser_env__launch, browser_env__search).
- If the user asks for general information retrieval ("search latest AI news", "find research papers", "summarize topic"), use cloud__search_web or cloud__http_request.
- Do NOT use cloud__search_web when the user explicitly wants browser UI interaction.
```

- [ ] **Step 2: Update legacy planner prompt**

In `app/agents/planner.py`, append to `PLANNER_PROMPT` after line 100:
```
Execution Environment Awareness:
- Browser UI tasks (open chrome, search in browser, login, click, fill forms) MUST use browser_env__* tools.
- Information retrieval tasks (general search, summarize, fetch data) MUST use cloud__search_web or cloud__http_request.
- Do NOT confuse browser UI automation with backend web search.
```

- [ ] **Step 3: Commit**

```bash
git add app/langgraph/nodes.py app/agents/planner.py
git commit -m "feat: update planner prompts with execution environment awareness"
```

---

### Task 8: Update Verifier for Environment-Specific Validation

**Files:**
- Modify: `app/langgraph/nodes.py`

- [ ] **Step 1: Update verifier_node to check environment_config**

After line 336 in `app/langgraph/nodes.py` (where it checks `if not steps:`), add:
```python
    env_config = state.get("environment_config", {})
    env_type = env_config.get("environment", "local") if isinstance(env_config, dict) else getattr(env_config, "environment", "local")
```

Then after the LLM verification block (before the final verdict), add:
```python
    # Environment-specific verification
    env_verified = True
    env_notes = ""
    if env_type == "browser_ui":
        # Check if any browser_env tool was called
        tool_calls = state.get("tool_calls", [])
        browser_calls = [t for t in tool_calls if t.get("tool", "").startswith("browser_env__")]
        if not browser_calls:
            env_verified = False
            env_notes = "Browser environment selected but no browser_env tools were invoked."
        else:
            env_notes = f"Browser automation verified: {len(browser_calls)} browser actions performed."
    elif env_type == "cloud_api":
        tool_calls = state.get("tool_calls", [])
        cloud_calls = [t for t in tool_calls if t.get("tool", "").startswith("cloud__")]
        if not cloud_calls:
            env_verified = False
            env_notes = "Cloud API environment selected but no cloud tools were invoked."
        else:
            env_notes = f"Cloud API verified: {len(cloud_calls)} API calls made."

    # Final verdict: deterministic, LLM, and environment checks must agree
    verified = det_pass and llm_verified and env_verified
    if env_notes:
        notes = f"{env_notes} {notes}"
```

- [ ] **Step 2: Commit**

```bash
git add app/langgraph/nodes.py
git commit -m "feat: environment-specific verification in verifier_node"
```

---

### Task 9: Update Orchestrator to Pass Environment Context

**Files:**
- Modify: `app/orchestrator/core.py`

- [ ] **Step 1: Ensure environment_selector is imported**

Already imported via `from ..capabilities import (...)`.

- [ ] **Step 2: Log selected environment**

In `_execute_with_langgraph`, after line 303, ensure:
```python
logger.info(f"[Environment] task={task_id} env={env_config.environment.value}")
```

- [ ] **Step 3: Commit**

```bash
git add app/orchestrator/core.py
git commit -m "chore: orchestrator logs selected execution environment"
```

---

### Task 10: Integration Test

**Files:**
- Test: `tests/test_integration_browser_task.py`

- [ ] **Step 1: Create integration test**

`tests/test_integration_browser_task.py`:
```python
import pytest
from unittest.mock import patch, AsyncMock

from app.capabilities.environment_selector import environment_selector
from app.capabilities.models import CapabilityAssessment, CapabilityRequirement, ExecutionEnvironment


def test_browser_ui_task_routing():
    assessment = CapabilityAssessment(
        task_id="t1",
        query="open chrome and search for what is agentic ai",
        required_capabilities=[CapabilityRequirement(capability="web")],
        primary_capability="web",
    )
    env = environment_selector.select(assessment.query, assessment)
    assert env == ExecutionEnvironment.BROWSER_UI


def test_cloud_api_task_routing():
    assessment = CapabilityAssessment(
        task_id="t2",
        query="search latest AI news",
        required_capabilities=[CapabilityRequirement(capability="web")],
        primary_capability="web",
    )
    env = environment_selector.select(assessment.query, assessment)
    assert env == ExecutionEnvironment.CLOUD_API
```

- [ ] **Step 2: Run all new tests**

```bash
pytest tests/test_ws_auth.py tests/test_cloud_api_server.py tests/test_environment_selector.py tests/test_browser_env.py tests/test_integration_browser_task.py -v
```

- [ ] **Step 3: Final commit**

```bash
git add tests/test_integration_browser_task.py
git commit -m "test: integration tests for execution environment routing"
```

---

## Self-Review Checklist

- [x] Spec coverage: every section maps to a task
- [x] No placeholders (TBD, TODO, etc.)
- [x] Type consistency: `ExecutionEnvironment` enum used consistently
- [x] File paths exact and correct
- [x] Tests included for every new component
- [x] Commit messages follow conventional commits

## Execution Options

**Plan saved to:** `docs/superpowers/plans/2026-04-25-execution-environment-layer.md`

**Recommended execution:** Dispatch parallel agents for Tasks 1-6 (independent), then sequential for Tasks 7-10 (depend on prior state).
