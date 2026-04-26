# AgentOS Infrastructure Overhaul — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:dispatching-parallel-agents to implement independent subsystems concurrently. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix AgentOS production issues: invisible execution results, blank browser pages, slow task startup, and incorrect task routing.

**Architecture:** Surgical backend fixes (precompiled graphs, persistent browser, single MCP discovery, enriched tool outputs) + new frontend result renderer components. No heavy abstractions.

**Tech Stack:** Python 3.11, FastAPI, Playwright, LangGraph, Redis, PostgreSQL, React 18, TypeScript, Tailwind

---

## File Ownership Map

| File | Owner | Subsystem |
|------|-------|-----------|
| `app/langgraph/graphs.py` | Perf | Precompiled graph cache |
| `app/orchestrator/task_runner.py` | Perf | Remove per-task graph compile, remove per-task MCP discovery |
| `app/main.py` | Perf | Startup sequence: discover MCP tools once |
| `app/mcp/client_manager.py` | Perf | `discover_mcp_tools` lock, health monitor wiring |
| `app/tools/registry.py` | UI + Perf | `ToolOutput.visibility`, single emission, MCP discovery lock |
| `app/tools/base.py` | UI | Add `visibility` field to `ToolOutput` |
| `app/environments/browser_env.py` | Browser | Persistent browser process, context pool, content guards, window guards |
| `app/observability/bus.py` | UI | Use `visibility` from tool results |
| `app/orchestrator/executor.py` | UI | Remove duplicate emissions, rely on registry |
| `frontend/src/components/results/` | Frontend | ResultCard components |
| `frontend/src/hooks/useTaskResults.ts` | Frontend | Result consumption hook |

---

## Subsystem A: Performance & Warm Infrastructure

**Goal:** Eliminate per-task reconnects, duplicate launches, and graph recompilation.

### Task A1: Precompile LangGraph Graphs Once

**Files:**
- Modify: `app/langgraph/graphs.py`
- Modify: `app/orchestrator/task_runner.py`
- Test: `tests/test_langgraph_graphs.py`

- [ ] **Step A1.1: Add graph cache to graphs.py**

At module level in `app/langgraph/graphs.py`, add:
```python
_graph_cache: Dict[str, Any] = {}

def get_cached_graph(mode: str, **kwargs) -> Any:
    """Return a pre-compiled graph for the given mode."""
    cache_key = mode
    if cache_key in _graph_cache:
        return _graph_cache[cache_key]
    # Compile and cache
    if mode == "task":
        graph = compile_task_graph(**kwargs)
    elif mode == "autonomous":
        graph = compile_autonomous_graph(**kwargs)
    elif mode == "workflow":
        graph = compile_workflow_graph(**kwargs)
    elif mode == "collaboration":
        graph = compile_collaboration_graph(**kwargs)
    else:
        graph = compile_task_graph(**kwargs)
    _graph_cache[cache_key] = graph
    return graph
```

- [ ] **Step A1.2: Update task_runner.py to use cached graphs**

Replace lines 184-197 in `app/orchestrator/task_runner.py`:
```python
# OLD:
if mode == "task":
    graph = compile_task_graph(checkpointer=checkpointer)
# etc...

# NEW:
from ..langgraph.graphs import get_cached_graph
graph = get_cached_graph(mode, checkpointer=checkpointer)
```

For workflow mode, still compute `workflow_def` but pass it to `get_cached_graph`:
```python
if mode == "workflow":
    workflow_def = None
    workflow = await workflow_repo.get_by_task(str(task_id))
    if workflow and workflow.definition:
        workflow_def = workflow.definition
    graph = get_cached_graph("workflow", checkpointer=checkpointer, workflow_definition=workflow_def)
else:
    graph = get_cached_graph(mode, checkpointer=checkpointer)
```

- [ ] **Step A1.3: Write test for graph caching**

```python
def test_graph_cache_reuses_instances():
    from app.langgraph.graphs import get_cached_graph, _graph_cache
    _graph_cache.clear()
    g1 = get_cached_graph("task")
    g2 = get_cached_graph("task")
    assert g1 is g2
```

- [ ] **Step A1.4: Run tests**

```bash
pytest tests/test_langgraph_graphs.py -v
```

### Task A2: Single-Time MCP Tool Discovery

**Files:**
- Modify: `app/main.py`
- Modify: `app/orchestrator/task_runner.py`
- Modify: `app/capabilities/feasibility.py`
- Modify: `app/tools/registry.py`

- [ ] **Step A2.1: Add MCP discovery to startup in main.py**

After `await mcp_client_manager.start_system_servers()` in `app/main.py` (around line 102), add:
```python
try:
    from .tools.registry import tool_registry
    await tool_registry.discover_mcp_tools()
    logger.info("MCP tools discovered at startup")
    initialized.append("mcp_tools_discovered")
except Exception as e:
    logger.error(f"MCP tool discovery failed at startup: {e}")
```

- [ ] **Step A2.2: Remove per-task MCP discovery from task_runner.py**

Remove line 173: `await tool_registry.discover_mcp_tools()`

- [ ] **Step A2.3: Remove MCP discovery from feasibility.py**

Find and remove any `await tool_registry.discover_mcp_tools()` calls in `app/capabilities/feasibility.py`.

- [ ] **Step A2.4: Add concurrency lock to discover_mcp_tools**

In `app/tools/registry.py`, modify `discover_mcp_tools`:
```python
import asyncio

class ToolRegistry:
    def __init__(self):
        # ... existing ...
        self._discovery_lock = asyncio.Lock()

    async def discover_mcp_tools(self) -> None:
        async with self._discovery_lock:
            if self._mcp_tools_registered:
                return
            # ... existing logic ...
```

### Task A3: Browser Process Reuse with Context Pooling

**Files:**
- Modify: `app/environments/browser_env.py`
- Modify: `app/main.py`
- Test: `tests/test_browser_env.py`

- [ ] **Step A3.1: Add persistent Playwright + Browser to BrowserSessionManager**

In `app/environments/browser_env.py`, modify `BrowserSessionManager`:
```python
class BrowserSessionManager:
    def __init__(self):
        self._sessions: Dict[str, BrowserSession] = {}
        self._playwright = None
        self._browser = None
        self._lock = asyncio.Lock()

    async def _ensure_browser(self):
        if self._browser and self._browser.is_connected():
            return
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"]
        )
        logger.info("BrowserSessionManager: launched persistent browser process")

    async def get_or_create_session(self, task_id: str) -> BrowserSession:
        session = self._sessions.get(task_id)
        if session and session.is_alive():
            logger.info(f"BrowserSessionManager: reusing session for task {task_id}")
            return session
        if session:
            logger.warning(f"BrowserSessionManager: session dead for task {task_id}, recreating")
            await session.close()

        await self._ensure_browser()
        session = BrowserSession(task_id)
        # Bind to persistent browser
        await session.bind_to_browser(self._browser)
        self._sessions[task_id] = session
        return session

    async def close_all(self):
        for task_id, session in list(self._sessions.items()):
            await session.close_context_only()
        self._sessions.clear()
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
```

- [ ] **Step A3.2: Modify BrowserSession to support context-only lifecycle**

```python
class BrowserSession:
    def __init__(self, task_id: str):
        self.task_id = task_id
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._headless = False
        self._current_url: Optional[str] = None

    async def bind_to_browser(self, browser: Browser):
        """Bind to an existing browser instance (context-only mode)."""
        self._browser = browser
        self._context = await browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        self._page = await self._context.new_page()
        logger.info(f"BrowserSession[{self.task_id}]: created new context in persistent browser")

    async def launch(self, headless: bool = False) -> ToolOutput:
        """Legacy standalone launch — delegates to manager's persistent browser."""
        from .browser_env import browser_session_manager
        session = await browser_session_manager.get_or_create_session(self.task_id)
        self._browser = session._browser
        self._context = session._context
        self._page = session._page
        return ToolOutput(success=True, result={"message": "Browser bound to persistent instance"})

    async def close_context_only(self) -> ToolOutput:
        """Close only the context, not the shared browser."""
        try:
            if self._context:
                await self._context.close()
                self._context = None
            self._page = None
            logger.info(f"BrowserSession[{self.task_id}]: context closed")
            return ToolOutput(success=True, result={"message": "Browser context closed"})
        except Exception as e:
            return ToolOutput(success=False, error=str(e))
```

- [ ] **Step A3.3: Startup browser warm in main.py**

In `app/main.py` lifespan, after MCP servers start, optionally warm the browser:
```python
try:
    from .environments.browser_env import browser_session_manager
    await browser_session_manager._ensure_browser()
    logger.info("Browser process warmed at startup")
    initialized.append("browser_warmed")
except Exception as e:
    logger.warning(f"Browser warm failed (will lazy-load): {e}")
```

- [ ] **Step A3.4: Update tests for context pooling**

```python
@pytest.mark.asyncio
async def test_browser_session_manager_persistent_browser():
    mgr = BrowserSessionManager()
    # First session creates browser
    s1 = await mgr.get_or_create_session("task-a")
    assert s1._browser is not None
    # Second session reuses same browser
    s2 = await mgr.get_or_create_session("task-b")
    assert s2._browser is s1._browser
    await mgr.close_all()
```

### Task A4: Planner Cache (Optional)

**Files:**
- Modify: `app/orchestrator/task_runner.py` or `app/langgraph/nodes.py`
- Test: `tests/test_langgraph_state.py`

- [ ] **Step A4.1: Add planner cache decorator**

In `app/langgraph/nodes.py` or a new `app/cache/planner_cache.py`:
```python
import hashlib
from ..memory.short_term import redis_client

async def get_cached_plan(query: str, capability_hash: str) -> Optional[Dict]:
    key = f"agentos:plan:{hashlib.sha256(f'{query}:{capability_hash}'.encode()).hexdigest()}"
    data = await redis_client.client.get(key)
    if data:
        import json
        return json.loads(data)
    return None

async def set_cached_plan(query: str, capability_hash: str, plan: Dict, ttl: int = 300):
    key = f"agentos:plan:{hashlib.sha256(f'{query}:{capability_hash}'.encode()).hexdigest()}"
    import json
    await redis_client.client.setex(key, ttl, json.dumps(plan))
```

- [ ] **Step A4.2: Integrate cache into planner node**

Before invoking the LLM planner, check cache. After successful planning, store in cache.

---

## Subsystem B: Browser Visibility & Reliability

**Goal:** Eliminate blank browser pages, ensure visible execution, detect failures.

### Task B1: Content Guard — Fix is_alive() and navigate()

**Files:**
- Modify: `app/environments/browser_env.py`
- Test: `tests/test_browser_reliability.py`

- [ ] **Step B1.1: Fix is_alive() to detect blank pages**

```python
def is_alive(self) -> bool:
    if self._page is None or self._page.is_closed():
        return False
    if self._browser is not None:
        try:
            if not self._browser.is_connected():
                return False
        except Exception:
            return False
    # Content guard: verify page is not about:blank and has substance
    try:
        url = self._page.url
        if url in ("about:blank", "", None):
            return False
        html_len = self._page.evaluate("document.body ? document.body.innerHTML.length : 0")
        if html_len < 50:
            return False
    except Exception:
        return False
    return True
```

- [ ] **Step B1.2: Add navigation verification to navigate()**

After `page.goto()` in `navigate()`, add:
```python
# Content verification after navigation
await asyncio.sleep(0.5)  # Brief pause for initial render
try:
    url = page.url
    title = await page.title()
    html_len = await page.evaluate("document.body ? document.body.innerHTML.length : 0")
    if url in ("about:blank", "", None) or html_len < 50:
        # Try screenshot for diagnostics
        screenshot_path = os.path.join(tempfile.gettempdir(), f"agentos_blank_{self.task_id}.png")
        await page.screenshot(path=screenshot_path, full_page=True)
        logger.error(f"BrowserSession[{self.task_id}]: blank page detected after navigate to {url}. Screenshot: {screenshot_path}")
        return ToolOutput(success=False, error=f"Browser page remained blank after navigating to {url}. Screenshot: {screenshot_path}")
except Exception as e:
    logger.warning(f"BrowserSession[{self.task_id}]: content verification error: {e}")
```

- [ ] **Step B1.3: Add bring_to_front after navigation and recovery**

In `navigate()` after `page.goto()`:
```python
await page.bring_to_front()
```

In `_ensure_page()` after creating a new page:
```python
if self._context:
    self._page = await self._context.new_page()
    await self._page.bring_to_front()
```

### Task B2: Window Visibility Guard (Windows)

**Files:**
- Modify: `app/environments/browser_env.py`

- [ ] **Step B2.1: Add Windows window foregrounding**

In `BrowserSessionManager._ensure_browser()` or `BrowserSession.bind_to_browser()`, after creating the page:
```python
import sys
if sys.platform == "win32":
    try:
        import pygetwindow as gw
        # Find the Chromium window by title pattern
        windows = [w for w in gw.getAllWindows() if "Chromium" in w.title or "chrome" in w.title.lower()]
        if windows:
            win = windows[0]
            if win.isMinimized:
                win.restore()
            win.activate()
            logger.info(f"BrowserSessionManager: brought Chromium window to foreground")
    except Exception as e:
        logger.warning(f"BrowserSessionManager: could not foreground window: {e}")
```

### Task B3: Non-Destructive Health Check

**Files:**
- Modify: `app/environments/browser_env.py`

- [ ] **Step B3.1: Fix health_check()**

```python
async def health_check(self) -> Dict[str, str]:
    try:
        page = await self._ensure_page()
        url = page.url
        title = await page.title()
        html_len = await page.evaluate("document.body ? document.body.innerHTML.length : 0")
        if url in ("about:blank", "", None) or html_len < 50:
            return {"status": "unhealthy", "message": f"Page appears blank (url={url}, html_len={html_len})"}
        return {"status": "healthy", "message": f"Browser active (url={url}, title={title})"}
    except Exception as e:
        return {"status": "unhealthy", "message": str(e)}
```

---

## Subsystem C: UI Visibility Layer

**Goal:** Every tool output is surfaced to the user in real-time.

### Task C1: Extend ToolOutput with visibility Metadata

**Files:**
- Modify: `app/tools/base.py`
- Modify: `app/environments/browser_env.py`
- Modify: `app/environments/desktop_env.py`

- [ ] **Step C1.1: Add visibility field to ToolOutput**

```python
@dataclass
class ToolOutput:
    success: bool
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    visibility: Optional[Dict[str, Any]] = None  # NEW
```

- [ ] **Step C1.2: Populate visibility in browser tools**

In `BrowserSession.navigate()`:
```python
return ToolOutput(
    success=True,
    result={"url": self._current_url, "title": title},
    visibility={"type": "browser_navigated", "url": self._current_url, "title": title}
)
```

In `BrowserSession.screenshot()`:
```python
return ToolOutput(
    success=True,
    result={"path": path},
    visibility={"type": "browser_screenshot", "path": path}
)
```

In `BrowserSession.search()`:
```python
return ToolOutput(
    success=True,
    result={...},
    visibility={"type": "browser_search", "query": query, "domain": domain, "page_title": title}
)
```

- [ ] **Step C1.3: Populate visibility in desktop tools**

In `DesktopSession.screenshot()`:
```python
return ToolOutput(
    success=True,
    result={"path": path},
    visibility={"type": "desktop_screenshot", "path": path}
)
```

In `DesktopSession.click()`:
```python
return ToolOutput(
    success=True,
    result={"message": f"Clicked at ({x}, {y})"},
    visibility={"type": "desktop_click", "x": x, "y": y}
)
```

### Task C2: Single Emission Point in ToolRegistry

**Files:**
- Modify: `app/tools/registry.py`
- Modify: `app/orchestrator/executor.py`
- Modify: `app/langgraph/nodes.py`

- [ ] **Step C2.1: Emit TOOL_RESULT from ToolRegistry.execute()**

```python
async def execute(self, tool_name: str, parameters: Dict[str, Any]) -> ToolOutput:
    # ... existing lookup logic ...
    result = await registered.tool.execute(tool_input)
    
    # SINGLE EMISSION POINT
    try:
        from ..observability.bus import observability_bus
        from ..observability.models import ObservabilityEventType
        task_id = parameters.get("_task_id", "unknown")
        await observability_bus.emit_safe(
            ObservabilityEventType.TOOL_RESULT,
            task_id=task_id,
            payload={
                "tool_name": tool_name,
                "success": result.success,
                "result": result.result,
                "visibility": result.visibility,
                "error": result.error,
            },
            source="tool_registry",
        )
    except Exception as e:
        logger.warning(f"Failed to emit tool result visibility: {e}")
    
    if result.success:
        registered.use_count += 1
        registered.last_used = datetime.utcnow().isoformat()
    return result
```

- [ ] **Step C2.2: Remove duplicate emissions from executor.py**

Find and remove any `observability_bus.emit_safe(ObservabilityEventType.TOOL_RESULT, ...)` calls in `app/orchestrator/executor.py` that duplicate the registry emission.

- [ ] **Step C2.3: Remove duplicate emissions from langgraph/nodes.py**

Find and remove any duplicate `TOOL_RESULT` emissions in `app/langgraph/nodes.py`.

### Task C3: Fix MCPWrappedTool Result Flattening

**Files:**
- Modify: `app/tools/registry.py`

- [ ] **Step C3.1: Parse MCP content for visibility**

```python
async def execute(self, tool_input: ToolInput) -> ToolOutput:
    from ..mcp.client_manager import mcp_client_manager
    try:
        result = await mcp_client_manager.call_tool(self.name, tool_input.parameters)
        content = ""
        if hasattr(result, "content"):
            content = "\n".join(
                str(c.text if hasattr(c, "text") else c)
                for c in result.content
            )
        else:
            content = str(result)
        
        # Detect visibility metadata
        visibility = None
        if self.name.startswith("filesystem__"):
            path = tool_input.parameters.get("path", "")
            visibility = {"type": "file_operation", "path": path, "operation": self.name}
        elif self.name.startswith("shell__"):
            cmd = tool_input.parameters.get("command", "")
            visibility = {"type": "shell_output", "command": cmd}
        
        return ToolOutput(success=True, result={"output": content}, visibility=visibility)
    except Exception as e:
        return ToolOutput(success=False, error=str(e))
```

---

## Subsystem D: Frontend Result Renderer

**Goal:** Render tool results visibly in the UI.

### Task D1: Create Result Type Definitions

**Files:**
- Create: `frontend/src/types/results.ts`

```typescript
export interface VisibilityEvent {
  type: string;
  task_id: string;
  tool_name: string;
  success: boolean;
  result?: any;
  visibility?: VisibilityPayload;
  error?: string;
  timestamp: string;
}

export interface VisibilityPayload {
  type: 'browser_navigated' | 'browser_screenshot' | 'browser_search' | 'desktop_screenshot' | 'desktop_click' | 'file_operation' | 'shell_output' | string;
  [key: string]: any;
}
```

### Task D2: Create Result Card Components

**Files:**
- Create: `frontend/src/components/results/BrowserResultCard.tsx`
- Create: `frontend/src/components/results/FileResultCard.tsx`
- Create: `frontend/src/components/results/DesktopResultCard.tsx`
- Create: `frontend/src/components/results/ShellResultCard.tsx`
- Create: `frontend/src/components/results/ResultCard.tsx`
- Create: `frontend/src/components/results/index.ts`

- [ ] **Step D2.1: BrowserResultCard**

```tsx
import React from 'react';
import { VisibilityPayload } from '../../types/results';

interface Props {
  visibility: VisibilityPayload;
}

export const BrowserResultCard: React.FC<Props> = ({ visibility }) => {
  const { url, title, path, query, domain } = visibility;
  return (
    <div className="rounded-lg border border-blue-200 bg-blue-50 p-4 shadow-sm">
      <div className="flex items-center gap-2 mb-2">
        <span className="text-blue-600 font-semibold text-sm">Browser</span>
        {url && (
          <a href={url} target="_blank" rel="noopener noreferrer" className="text-blue-700 hover:underline text-sm truncate">
            {title || url}
          </a>
        )}
      </div>
      {query && <p className="text-sm text-gray-700">Searched: "{query}" on {domain}</p>}
      {path && (
        <div className="mt-2">
          <img src={`file://${path}`} alt="Screenshot" className="max-w-full rounded border" />
        </div>
      )}
    </div>
  );
};
```

- [ ] **Step D2.2: FileResultCard**

```tsx
import React from 'react';
import { VisibilityPayload } from '../../types/results';

interface Props {
  visibility: VisibilityPayload;
}

export const FileResultCard: React.FC<Props> = ({ visibility }) => {
  const { path, operation } = visibility;
  return (
    <div className="rounded-lg border border-green-200 bg-green-50 p-4 shadow-sm">
      <div className="flex items-center gap-2 mb-2">
        <span className="text-green-600 font-semibold text-sm">File</span>
        <span className="text-xs text-gray-500">{operation}</span>
      </div>
      <code className="block bg-white rounded px-3 py-2 text-sm text-gray-800 break-all">{path}</code>
      <button
        onClick={() => window.open(`file://${path}`, '_blank')}
        className="mt-2 text-sm text-green-700 hover:text-green-900 font-medium"
      >
        Open file/folder
      </button>
    </div>
  );
};
```

- [ ] **Step D2.3: DesktopResultCard**

```tsx
import React from 'react';
import { VisibilityPayload } from '../../types/results';

interface Props {
  visibility: VisibilityPayload;
}

export const DesktopResultCard: React.FC<Props> = ({ visibility }) => {
  const { path, x, y } = visibility;
  return (
    <div className="rounded-lg border border-purple-200 bg-purple-50 p-4 shadow-sm">
      <div className="flex items-center gap-2 mb-2">
        <span className="text-purple-600 font-semibold text-sm">Desktop</span>
      </div>
      {x !== undefined && y !== undefined && (
        <p className="text-sm text-gray-700">Clicked at ({x}, {y})</p>
      )}
      {path && (
        <div className="mt-2">
          <img src={`file://${path}`} alt="Screenshot" className="max-w-full rounded border" />
        </div>
      )}
    </div>
  );
};
```

- [ ] **Step D2.4: ShellResultCard**

```tsx
import React from 'react';
import { VisibilityPayload } from '../../types/results';

interface Props {
  visibility: VisibilityPayload;
  output?: string;
}

export const ShellResultCard: React.FC<Props> = ({ visibility, output }) => {
  const { command } = visibility;
  return (
    <div className="rounded-lg border border-gray-200 bg-gray-50 p-4 shadow-sm font-mono">
      <div className="flex items-center gap-2 mb-2">
        <span className="text-gray-600 font-semibold text-sm">Shell</span>
        <code className="text-xs text-gray-500">{command}</code>
      </div>
      {output && (
        <pre className="bg-black text-green-400 rounded px-3 py-2 text-xs overflow-auto max-h-48">
          {output}
        </pre>
      )}
    </div>
  );
};
```

- [ ] **Step D2.5: ResultCard dispatcher**

```tsx
import React from 'react';
import { VisibilityEvent } from '../../types/results';
import { BrowserResultCard } from './BrowserResultCard';
import { FileResultCard } from './FileResultCard';
import { DesktopResultCard } from './DesktopResultCard';
import { ShellResultCard } from './ShellResultCard';

interface Props {
  event: VisibilityEvent;
}

export const ResultCard: React.FC<Props> = ({ event }) => {
  const v = event.visibility;
  if (!v) return null;

  const type = v.type;
  if (type.startsWith('browser_')) return <BrowserResultCard visibility={v} />;
  if (type === 'file_operation') return <FileResultCard visibility={v} />;
  if (type.startsWith('desktop_')) return <DesktopResultCard visibility={v} />;
  if (type === 'shell_output') return <ShellResultCard visibility={v} output={event.result?.output} />;

  return (
    <div className="rounded-lg border border-gray-200 p-4">
      <pre className="text-xs">{JSON.stringify(v, null, 2)}</pre>
    </div>
  );
};
```

### Task D3: Create useTaskResults Hook

**Files:**
- Create: `frontend/src/hooks/useTaskResults.ts`

```typescript
import { useState, useCallback } from 'react';
import { VisibilityEvent } from '../types/results';

export function useTaskResults() {
  const [results, setResults] = useState<VisibilityEvent[]>([]);

  const addResult = useCallback((event: any) => {
    if (event.type === 'tool.result' && event.payload?.visibility) {
      const visibilityEvent: VisibilityEvent = {
        type: event.payload.visibility.type,
        task_id: event.payload.task_id || 'unknown',
        tool_name: event.payload.tool_name,
        success: event.payload.success,
        result: event.payload.result,
        visibility: event.payload.visibility,
        error: event.payload.error,
        timestamp: event.timestamp || new Date().toISOString(),
      };
      setResults((prev) => [...prev, visibilityEvent]);
    }
  }, []);

  const clearResults = useCallback(() => setResults([]), []);

  return { results, addResult, clearResults };
}
```

### Task D4: Integrate into Task View

**Files:**
- Modify: `frontend/src/pages/TaskDetail.tsx` (or wherever task view lives)

- [ ] **Step D4.1: Wire useTaskResults into WebSocket consumer**

```typescript
import { useTaskResults } from '../hooks/useTaskResults';
import { ResultCard } from '../components/results';

function TaskDetail({ taskId }: { taskId: string }) {
  const { results, addResult, clearResults } = useTaskResults();
  const { messages } = useWebSocket({ taskId, onMessage: addResult });

  return (
    <div>
      {/* existing task UI */}
      <div className="space-y-3 mt-4">
        <h3 className="text-sm font-semibold text-gray-700">Execution Results</h3>
        {results.length === 0 && (
          <p className="text-sm text-gray-400 italic">No visible results yet...</p>
        )}
        {results.map((r, i) => (
          <ResultCard key={i} event={r} />
        ))}
      </div>
    </div>
  );
}
```

---

## Cross-Cutting: Testing & Verification

### Task E1: Run All Tests

```bash
pytest tests/ -v --tb=short
```

### Task E2: Frontend Build Check

```bash
cd frontend && npm run build
```

### Task E3: Integration Verification

1. Create a file search task → verify FileResultCard appears with path
2. Create a browser navigate task → verify BrowserResultCard appears with URL
3. Create a desktop click task → verify DesktopResultCard appears with coordinates
4. Verify no duplicate events in WebSocket messages

---

## Self-Review Checklist

- [ ] Spec coverage: All 4 subsystems have tasks
- [ ] Placeholder scan: No TBD/TODO/"implement later"
- [ ] Type consistency: `ToolOutput.visibility`, `VisibilityPayload`, `VisibilityEvent` all match
- [ ] File paths: All paths are exact and exist in the codebase
- [ ] Test coverage: Each subsystem has test steps
- [ ] No over-engineering: WarmRuntime, CachedToolRegistry, etc. are NOT in this plan

---

**Plan complete and saved to `docs/superpowers/plans/2026-04-26-agentos-infrastructure.md`.**

**Execution choice:**
1. **Subagent-Driven** — dispatch fresh subagent per subsystem
2. **Parallel Agents** — dispatch 4 subagents concurrently (recommended for independent subsystems)

**Recommendation:** Use dispatching-parallel-agents for the 4 independent subsystems, with a final integration subagent.
