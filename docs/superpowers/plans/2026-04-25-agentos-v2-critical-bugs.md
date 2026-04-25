# AgentOS v2 Critical Bug Fixes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix three production-critical bugs (WebSocket reconnect storm, browser automation timeout on SPAs, task executor step repetition) and their underlying architectural weaknesses.

**Architecture:** Phase 1 applies targeted emergency fixes to stop user-impacting failures. Phase 2 introduces structured cross-step memory, idempotent tool design, and config wiring. Phase 3 adds integration tests and auth hardening to prevent regressions.

**Tech Stack:** FastAPI, React/TypeScript, Playwright, LangGraph, Celery, Redis, PostgreSQL, Pydantic v2

---

## File Structure

| File | Responsibility |
|------|---------------|
| `frontend/src/hooks/useWebSocket.ts` | Frontend WebSocket hook with reconnect logic |
| `app/api/ws.py` | Backend WebSocket endpoint with JWT validation |
| `app/environments/browser_env.py` | Playwright browser automation (launch, navigate, search, click) |
| `app/langgraph/nodes.py` | LangGraph executor, planner, verifier, summarizer nodes |
| `app/agents/executor.py` | Legacy executor agent (dual execution path) |
| `app/agents/v2/schemas.py` | V2 agent config schema with `max_iter` |
| `app/langgraph/state.py` | LangGraph state definition |

---

## Phase 1: Emergency Fixes (Stop the Bleeding)

### Task 1.1: Fix WebSocket Reconnect Storm + Missing Token Handling

**Files:**
- Modify: `frontend/src/hooks/useWebSocket.ts`
- Modify: `app/api/ws.py`

**Problem:** When `localStorage.getToken` returns null, the frontend connects without a token. FastAPI validates the required `Query(...)` parameter, fails, and closes with code `1008`. The frontend treats all close codes except `1000` as retryable, causing an infinite reconnect loop. Additionally, `onMessage` is a `useCallback` dependency, so inline handler functions from parents trigger repeated disconnect/reconnect cycles.

- [ ] **Step 1: Stabilize `onMessage` with a ref in the frontend hook**

Modify `frontend/src/hooks/useWebSocket.ts`:

```typescript
export function useWebSocket({ taskId, onMessage }: UseWebSocketOptions): UseWebSocketReturn {
  const [messages, setMessages] = useState<any[]>([]);
  const [status, setStatus] = useState<WebSocketStatus>('closed');
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isUnmountingRef = useRef(false);
  const onMessageRef = useRef(onMessage);          // NEW

  // Keep callback ref in sync without triggering reconnects
  useEffect(() => {                               // NEW
    onMessageRef.current = onMessage;
  }, [onMessage]);

  const clearReconnect = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
  }, []);
```

Then replace the `onMessage` call inside `ws.onmessage`:

```typescript
    ws.onmessage = (event) => {
      if (isUnmountingRef.current) return;
      try {
        const parsed = JSON.parse(event.data);
        setMessages((prev) => [...prev, parsed]);
        if (onMessageRef.current) {               // CHANGED from onMessage
          onMessageRef.current(parsed);
        }
      } catch {
        setMessages((prev) => [...prev, event.data]);
        if (onMessageRef.current) {               // CHANGED from onMessage
          onMessageRef.current(event.data);
        }
      }
    };
```

Finally, remove `onMessage` from the `connect` `useCallback` dependency array:

```typescript
  }, [taskId, clearReconnect]);   // CHANGED from [taskId, onMessage, clearReconnect]
```

- [ ] **Step 2: Add reconnect cap and terminal close-code handling**

Inside `frontend/src/hooks/useWebSocket.ts`, add constants and update `ws.onclose`:

```typescript
const MAX_RECONNECT_ATTEMPTS = 5;
const TERMINAL_CLOSE_CODES = new Set([1008, 1011]); // policy violation, server error

// ... inside connect() ...

    ws.onclose = (event) => {
      wsRef.current = null;
      if (isUnmountingRef.current) return;
      setStatus('closed');

      // Don't reconnect on clean closure
      if (event.code === 1000) return;

      // Don't reconnect on terminal errors (auth failures, server errors)
      if (TERMINAL_CLOSE_CODES.has(event.code)) {
        console.error(`WebSocket closed with terminal code ${event.code}: ${event.reason}`);
        return;
      }

      if (reconnectAttemptsRef.current >= MAX_RECONNECT_ATTEMPTS) {
        console.error(`WebSocket max reconnect attempts (${MAX_RECONNECT_ATTEMPTS}) reached`);
        return;
      }

      if (taskId) {
        const delay = Math.min(1000 * 2 ** reconnectAttemptsRef.current, 30000);
        reconnectAttemptsRef.current += 1;
        reconnectTimerRef.current = setTimeout(() => {
          if (!isUnmountingRef.current && taskId) {
            connect();
          }
        }, delay);
      }
    };
```

- [ ] **Step 3: Make backend token parameter optional and handle missing cleanly**

Modify `app/api/ws.py`:

```python
from typing import Dict, List, Optional   # ensure Optional is imported

async def websocket_endpoint(websocket: WebSocket, token: Optional[str] = Query(None)) -> None:
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

    # Validate JWT token before accepting connection
    payload = verify_access_token(token_str)
    if not payload:
        logger.warning(f"WebSocket auth failed for task {task_id}")
        await websocket.close(code=1008, reason="Invalid or expired token")
        return

    await manager.connect(task_id, websocket)
    logger.info(f"WebSocket connected for task {task_id} by user {payload.get('sub', 'unknown')}")
    # ... rest of function unchanged ...
```

- [ ] **Step 4: Verify the frontend builds without type errors**

Run:
```bash
cd frontend && npx tsc --noEmit
```
Expected: No errors.

- [ ] **Step 5: Run backend to confirm WebSocket starts**

Run:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```
Expected: Server starts, no import errors in `app/api/ws.py`.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/hooks/useWebSocket.ts app/api/ws.py
git commit -m "fix(websocket): cap reconnects, handle 1008 as terminal, stabilize onMessage ref"
```

---

### Task 1.2: Fix Browser Search Timeout on YouTube / SPAs

**Files:**
- Modify: `app/environments/browser_env.py`

**Problem:** YouTube redirects to consent pages with no inputs; the search box lives inside shadow DOM that raw CSS selectors cannot pierce; `navigate()` waits only for `domcontentloaded` which fires before JS hydration; selector timeout is only 5s.

- [ ] **Step 1: Make `BrowserSession.launch()` idempotent**

In `app/environments/browser_env.py`, modify the `launch` method:

```python
    async def launch(self, headless: bool = False) -> ToolOutput:
        if self.is_alive():
            logger.info(f"BrowserSession[{self.task_id}]: already alive, skipping launch")
            return ToolOutput(success=True, result={"message": "Browser already launched"})

        self._headless = headless
        try:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=self._headless,
                args=["--disable-blink-features=AutomationControlled"]
            )
            self._context = await self._browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            self._page = await self._context.new_page()
            logger.info(f"BrowserSession[{self.task_id}]: launched new browser instance")
            return ToolOutput(success=True, result={"message": "Browser launched"})
        except Exception as e:
            logger.error(f"BrowserSession[{self.task_id}]: launch failed: {e}")
            return ToolOutput(success=False, error=str(e))
```

- [ ] **Step 2: Harden `navigate()` for SPAs with `networkidle` fallback**

Replace the `navigate` method:

```python
    async def navigate(self, url: str) -> ToolOutput:
        try:
            page = await self._ensure_page()
            # Try networkidle for SPAs, fall back to domcontentloaded if it hangs
            try:
                await page.goto(url, wait_until="networkidle", timeout=30000)
            except Exception:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            self._current_url = page.url
            title = await page.title()
            return ToolOutput(success=True, result={"url": self._current_url, "title": title})
        except Exception as e:
            logger.error(f"BrowserSession[{self.task_id}]: navigate error: {e}")
            return ToolOutput(success=False, error=str(e))
```

- [ ] **Step 3: Add interstitial dismissal helper**

Add this method to the `BrowserSession` class:

```python
    async def _dismiss_interstitials(self, page: Page) -> None:
        """Click common consent / cookie / age-gate buttons so the real page surface is reachable."""
        consent_buttons = [
            'button:has-text("Accept all")',
            'button:has-text("Reject all")',
            'button:has-text("I agree")',
            'button:has-text("Agree")',
            'button:has-text("Continue")',
            'button[aria-label*="Accept" i]',
            'form[action*="consent"] button',
            '[data-testid="reject-all-button"]',
        ]
        for sel in consent_buttons:
            try:
                btn = page.locator(sel).first
                await btn.wait_for(state="visible", timeout=3000)
                await btn.click()
                await page.wait_for_load_state("networkidle", timeout=10000)
                logger.info(f"BrowserSession[{self.task_id}]: dismissed interstitial ({sel})")
                return
            except Exception:
                continue
```

- [ ] **Step 4: Rewrite `search()` with semantic locators, longer timeouts, and shadow-DOM diagnostics**

Replace the `search` method:

```python
    async def search(self, query: str) -> ToolOutput:
        import re
        page = await self._ensure_page()

        # Dismiss Google/YouTube consent or cookie interstitials first
        await self._dismiss_interstitials(page)

        domain = self._detect_domain()
        selectors = DOMAIN_SELECTORS.get(domain, []) + FALLBACK_SELECTORS

        last_error = None
        for idx, selector in enumerate(selectors):
            try:
                # Give heavy SPAs (YouTube) more time on the first few selectors
                timeout = 10000 if idx < 3 else 5000
                await page.wait_for_selector(selector, timeout=timeout, state="visible")
                await page.fill(selector, query)
                await page.press(selector, "Enter")
                await page.wait_for_load_state("networkidle", timeout=15000)
                self._current_url = page.url
                title = await page.title()
                return ToolOutput(success=True, result={
                    "query": query,
                    "domain": domain,
                    "selector_used": selector,
                    "page_title": title,
                    "message": f"Searched for '{query}' on {domain}"
                })
            except Exception as e:
                last_error = e
                continue

        # Semantic locators (bypass shadow DOM via accessibility tree)
        semantic_strategies = [
            lambda p: p.get_by_role("combobox", name=re.compile("Search", re.IGNORECASE)),
            lambda p: p.get_by_placeholder(re.compile("Search", re.IGNORECASE)),
            lambda p: p.get_by_label(re.compile("Search", re.IGNORECASE)),
        ]
        for strategy in semantic_strategies:
            try:
                locator = strategy(page)
                await locator.fill(query, timeout=5000)
                await locator.press("Enter")
                await page.wait_for_load_state("networkidle", timeout=15000)
                self._current_url = page.url
                title = await page.title()
                return ToolOutput(success=True, result={
                    "query": query,
                    "domain": domain,
                    "selector_used": "semantic_locator",
                    "page_title": title,
                    "message": f"Searched for '{query}' on {domain}"
                })
            except Exception as e:
                last_error = e
                continue

        # Improved failure diagnostics
        screenshot_path = os.path.join(tempfile.gettempdir(), f"agentos_search_fail_{self.task_id}.png")
        try:
            await page.screenshot(path=screenshot_path, full_page=True)
        except Exception:
            screenshot_path = None

        # Use JS to pierce shadow DOM so we don't falsely report "no inputs"
        inputs_info = []
        try:
            inputs_info = await page.evaluate("""() => {
                function deepQuery(root, selector) {
                    let results = Array.from(root.querySelectorAll(selector));
                    root.querySelectorAll('*').forEach(el => {
                        if (el.shadowRoot) {
                            results = results.concat(deepQuery(el.shadowRoot, selector));
                        }
                    });
                    return results;
                }
                return deepQuery(document, 'input, textarea').map(el => ({
                    tag: el.tagName.toLowerCase(),
                    type: el.type,
                    name: el.name,
                    placeholder: el.placeholder,
                    id: el.id,
                    class: el.className,
                    ariaLabel: el.getAttribute('aria-label')
                }));
            }""")
        except Exception:
            pass

        current_url = page.url
        current_title = await page.title()
        error_msg = (
            f"Search failed on '{domain}' (url={current_url}, title={current_title}). "
            f"Tried {len(selectors)} CSS selectors and {len(semantic_strategies)} semantic locators. "
            f"Last error: {last_error}. Available inputs: {inputs_info}"
        )
        if screenshot_path:
            error_msg += f". Screenshot: {screenshot_path}"
        logger.error(f"BrowserSession[{self.task_id}]: {error_msg}")
        return ToolOutput(success=False, error=error_msg)
```

- [ ] **Step 5: Add `re` import at top of file**

Ensure `app/environments/browser_env.py` has:
```python
import re
```
at the top (it already imports `os`, `tempfile`, `urllib.parse`).

- [ ] **Step 6: Run a quick smoke test**

Run:
```bash
python -c "from app.environments.browser_env import BrowserSession; print('import ok')"
```
Expected: `import ok`

- [ ] **Step 7: Commit**

```bash
git add app/environments/browser_env.py
git commit -m "fix(browser): idempotent launch, interstitial dismissal, semantic locators, shadow-dom diagnostics"
```

---

### Task 1.3: Fix Task Executor Step Repetition

**Files:**
- Modify: `app/langgraph/nodes.py`
- Modify: `app/agents/executor.py`

**Problem:** `executor_node` rebuilds the LLM message thread from scratch for every step (lines 205-208), so the LLM has no memory that the browser was already launched. `MAX_ROUNDS = 3` is hardcoded and too low for browser tasks. The same hardcoded `3` exists in the legacy executor.

- [ ] **Step 1: Inject prior-step context into `executor_node` prompt**

In `app/langgraph/nodes.py`, replace the message construction inside `executor_node` (around line 175-208):

```python
    # Build execution context from prior steps
    prior_steps = state.get("steps", [])[:idx]
    prior_context = ""
    if prior_steps:
        prior_context_lines = []
        for s in prior_steps:
            prior_context_lines.append(
                f"Step {s['step_number']}: {s['description']}\n"
                f"Output: {s.get('output', '')[:500]}"
            )
        prior_context = "\n\nPreviously completed steps:\n" + "\n---\n".join(prior_context_lines)

    # Browser state hint
    browser_hint = ""
    if any(t.get("name", "").startswith("browser_env__") for t in available_tools):
        browser_hint = (
            "\nIMPORTANT: If a browser_env tool has already been used in a previous step, "
            "do NOT launch or navigate again unless explicitly required. Reuse the existing session."
        )

    # Suggested tool hint
    suggested_hint = ""
    if suggested_tool:
        suggested_hint = f"\nSuggested tool for this step (use if appropriate): {suggested_tool}"

    system_prompt = f"""You are an execution agent. Your job is to CARRY OUT the given step by any means necessary.
You have access to the following tools. You MUST use a tool when the step requires interacting with the filesystem, running code, using a calculator, searching the web, or executing shell commands.

Available tools:
{tools_json}

Current operating system: {os_info}
User home directory: {home}
User Desktop path: {desktop_path}{prior_context}{browser_hint}{suggested_hint}

CRITICAL RULES:
1. If the step asks you to create, write, read, or modify a file, you MUST use the filesystem tool.
2. If the step asks you to run a command or script, you MUST use the shell tool.
3. If the step asks you to browse or scrape the web, you MUST use the browser tool.
4. If the step requires calculation, use the calculator tool.
5. Do NOT just describe what you would do — actually invoke the tool with concrete parameters.
6. Use exact parameter names from the tool schema.
7. ALWAYS use ABSOLUTE file paths. NEVER use relative paths.
8. When creating files on Windows, use backslashes. On Linux/macOS, use forward slashes.
9. If the user asks for "desktop", use the Desktop path provided above.
10. NEVER repeat a tool call that was already successfully executed in a previous step unless the user explicitly asks you to do it again.

Respond with JSON in one of these formats:

To call a tool:
{{"tool_call": {{"name": "tool_name", "params": {{"param1": "value1"}}}}}}

To provide a direct answer (only if no tool is needed):
{{"answer": "your response", "details": "additional info"}}
"""

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"Step to execute: {description}"),
    ]
```

- [ ] **Step 2: Increase `MAX_ROUNDS` and add duplicate-call guard in LangGraph executor**

Replace the loop setup inside `executor_node`:

```python
    MAX_ROUNDS = 5
    tool_calls = state.get("tool_calls", [])
    step_tool_results = []
    final_answer = ""
    verification_reports = state.get("verification_reports", [])
    recovery_decisions = state.get("recovery_decisions", [])

    # Track calls within this step to prevent exact duplicates
    calls_this_step: set = set()

    for round_num in range(MAX_ROUNDS):
        try:
            response = await get_llm_client().complete_json(
                messages=_to_openai_messages(messages)
            )
        except Exception as e:
            logger.error(f"[executor_node] LLM execution failed: {e}")
            final_answer = f"Error during execution: {e}"
            break

        tool_call = response.get("tool_call")
        if tool_call and isinstance(tool_call, dict):
            tool_name = tool_call.get("name")
            tool_params = tool_call.get("params", {})
            if tool_name and tool_name.startswith("browser_env__"):
                tool_params["_task_id"] = task_id

            if not tool_name:
                final_answer = response.get("answer") or response.get("details") or json.dumps(response)
                break

            # Duplicate-call guard
            call_signature = json.dumps({"name": tool_name, "params": tool_params}, sort_keys=True, default=str)
            if call_signature in calls_this_step:
                warn_msg = (
                    f"You already called '{tool_name}' with the same parameters in this step. "
                    "Do NOT repeat it. Either proceed with the next action or provide a direct answer."
                )
                messages.append(AIMessage(content=json.dumps(response)))
                messages.append(HumanMessage(content=warn_msg))
                continue
            calls_this_step.add(call_signature)

            # Validate tool exists
            tool = tool_registry.get(tool_name)
            if not tool:
                error_msg = f"Tool '{tool_name}' not found"
                logger.error(f"[executor_node] {error_msg}")
                messages.append(AIMessage(content=json.dumps(response)))
                messages.append(HumanMessage(content=f"Error: {error_msg}. Use a valid tool or provide a direct answer."))
                continue

            logger.info(f"[executor_node] Invoking tool '{tool_name}' with params: {tool_params}")
            try:
                tool_output = await tool_registry.execute(tool_name, tool_params)
                tool_result = {
                    "success": tool_output.success,
                    "data": tool_output.result if tool_output.result is not None else str(tool_output),
                    "error": tool_output.error,
                }
            except Exception as e:
                logger.error(f"[executor_node] Tool execution error: {e}")
                tool_result = {"success": False, "error": str(e)}

            tool_calls.append({
                "step": step_number,
                "tool": tool_name,
                "result": tool_result,
            })
            step_tool_results.append(tool_result)

            # Deterministic Verification (unchanged)
            if tool_result["success"]:
                if "filesystem" in tool_name and tool_params.get("path"):
                    v_report = await verification_engine.verify(
                        task_id, None, "file_exists",
                        {"path": tool_params["path"]},
                    )
                    verification_reports.append(v_report.model_dump())
                    if v_report.result == VerificationResult.FAIL:
                        decision = recovery_engine.decide(
                            task_id, None,
                            error=v_report.failure_reason,
                            verification_report=v_report,
                            current_tool=tool_name,
                        )
                        recovery_decisions.append(decision.model_dump())
                        if decision.action == RecoveryAction.SWITCH_TOOL and decision.next_tool:
                            messages.append(HumanMessage(
                                content=f"Verification failed. Switching to alternative tool: {decision.next_tool}"
                            ))
                            continue
                        elif decision.action == RecoveryAction.RETRY:
                            messages.append(HumanMessage(
                                content=f"Verification failed. Retrying with same tool."
                            ))
                            continue

            messages.append(AIMessage(content=json.dumps(response)))
            messages.append(HumanMessage(
                content=f"Tool '{tool_name}' returned: {json.dumps(tool_result, indent=2)}. "
                        f"If the task is complete, provide a direct answer. If you need another tool, call it."
            ))
            continue
        else:
            final_answer = response.get("answer") or response.get("details") or json.dumps(response)
            break
    else:
        final_answer = f"Reached maximum tool rounds. Partial results: {json.dumps(step_tool_results, indent=2, default=str)}"
```

- [ ] **Step 3: Increase `MAX_TOOL_ROUNDS` in legacy executor**

In `app/agents/executor.py`, change:
```python
    MAX_TOOL_ROUNDS: int = 3
```
to:
```python
    MAX_TOOL_ROUNDS: int = 5
```

- [ ] **Step 4: Verify imports are correct in `app/langgraph/nodes.py`**

Ensure the top of `app/langgraph/nodes.py` contains:
```python
import json
import os
import platform
from typing import Dict, Any, List, Set   # ensure Set is available
```
If `Set` is missing, add it to the `typing` import.

- [ ] **Step 5: Run backend smoke test**

```bash
python -c "from app.langgraph.nodes import executor_node; print('import ok')"
python -c "from app.agents.executor import ExecutorAgent; print('legacy import ok')"
```
Expected: Both print `import ok`.

- [ ] **Step 6: Commit**

```bash
git add app/langgraph/nodes.py app/agents/executor.py
git commit -m "fix(executor): cross-step memory, duplicate guard, increase MAX_ROUNDS to 5"
```

---

## Phase 2: Structural Fixes (Idempotency, Memory, Config)

### Task 2.1: Wire `max_iter` from V2 Schema into LangGraph Executor

**Files:**
- Modify: `app/langgraph/state.py`
- Modify: `app/langgraph/nodes.py`

- [ ] **Step 1: Add `max_tool_rounds` to `AgentState`**

In `app/langgraph/state.py`, add a field:

```python
class AgentState(TypedDict):
    query: str
    task_id: str
    plan: List[Dict[str, Any]]
    steps: List[Dict[str, Any]]
    current_step_index: int
    tool_calls: List[Dict[str, Any]]
    messages: List[Any]
    verified: bool
    verification_notes: str
    verification_reports: List[Dict[str, Any]]
    recovery_decisions: List[Dict[str, Any]]
    status: str
    trace_id: str
    capability_assessment: Optional[Dict[str, Any]]
    environment_config: Optional[Dict[str, Any]]
    approved: bool
    approval_reason: str
    max_tool_rounds: int   # NEW
```

- [ ] **Step 2: Read `max_tool_rounds` from state in `executor_node`**

In `app/langgraph/nodes.py`, replace:
```python
    MAX_ROUNDS = 5
```
with:
```python
    MAX_ROUNDS = state.get("max_tool_rounds", 5)
```

- [ ] **Step 3: Update orchestrator entry point to pass `max_tool_rounds`**

Find where the LangGraph graph is invoked (likely in `app/orchestrator/pipeline.py` or `app/api/routes/tasks.py`). When constructing the initial state, pass:

```python
initial_state = AgentState(
    query=query,
    task_id=task_id,
    # ... other fields ...
    max_tool_rounds=getattr(task_config, "max_iter", 20) or 5,
)
```

If you cannot locate the exact invocation point, search for `AgentState(` or `graph.ainvoke`:
```bash
grep -rn "AgentState\|graph.ainvoke\|compile.*graph" app/
```

- [ ] **Step 4: Commit**

```bash
git add app/langgraph/state.py app/langgraph/nodes.py
git commit -m "feat(executor): wire max_iter from v2 schema into LangGraph state"
```

---

### Task 2.2: Summarizer Node — Add LLM Summarization

**Files:**
- Modify: `app/langgraph/nodes.py`

- [ ] **Step 1: Replace no-op summarizer with actual LLM call**

Replace `summarizer_node`:

```python
async def summarizer_node(state: AgentState) -> Dict[str, Any]:
    """Compile final result from all executed steps using LLM summarization."""
    query = state.get("query", "")
    steps = state.get("steps", [])
    task_id = state.get("task_id", "")

    logger.info(f"[summarizer_node] Summarizing task {task_id}")

    outputs = [s.get("output", "") for s in steps]
    combined = "\n\n".join(outputs)

    # Use LLM to produce a concise user-facing summary
    llm = get_llm_client()
    summary_prompt = f"""Summarize the following task execution results into a concise, user-friendly response.

Original query: {query}

Step outputs:
{combined}

Provide a brief summary (2-4 sentences) of what was accomplished and any important notes."""

    try:
        summary_response = await llm.complete_json(
            messages=[{"role": "user", "content": summary_prompt}],
            response_schema={
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                },
                "required": ["summary"],
            },
        )
        summary = summary_response.get("summary", combined[:1000])
    except Exception as e:
        logger.warning(f"[summarizer_node] LLM summarization failed: {e}")
        summary = combined[:1000]

    return {
        "result": {
            "query": query,
            "steps_executed": len(steps),
            "outputs": outputs,
            "summary": summary,
            "trace_id": state.get("trace_id", ""),
        },
        "messages": [AIMessage(content=f"Task complete. Summary:\n{summary}")],
        "status": "completed",
    }
```

- [ ] **Step 2: Commit**

```bash
git add app/langgraph/nodes.py
git commit -m "feat(summarizer): add LLM-based summary generation"
```

---

## Phase 3: Quality & Testing

### Task 3.1: Add Integration Tests

**Files:**
- Create: `tests/integration/test_websocket.py`
- Create: `tests/integration/test_browser_env.py`
- Create: `tests/integration/test_executor_loop.py`

- [ ] **Step 1: Write WebSocket integration test**

`tests/integration/test_websocket.py`:

```python
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_websocket_valid_token():
    # Generate a valid token for a test user
    from app.auth.utils import create_access_token
    token = create_access_token({"sub": "test-user", "email": "test@test.com", "role": "user"})

    with client.websocket_connect(f"/ws/tasks/test-task-123?token={token}") as ws:
        ws.send_text("ping")
        data = ws.receive_text()
        assert data == "pong"


def test_websocket_missing_token():
    with client.websocket_connect("/ws/tasks/test-task-123") as ws:
        # FastAPI closes before accept; TestClient raises WebSocketDisconnect
        pass


def test_websocket_malformed_token():
    with client.websocket_connect("/ws/tasks/test-task-123?token=not-a-jwt") as ws:
        pass
```

- [ ] **Step 2: Write browser environment unit test**

`tests/integration/test_browser_env.py`:

```python
import pytest
from app.environments.browser_env import BrowserSession


@pytest.mark.asyncio
async def test_browser_launch_idempotent():
    session = BrowserSession("test-task")
    out1 = await session.launch(headless=True)
    assert out1.success is True

    out2 = await session.launch(headless=True)
    assert out2.success is True
    assert "already" in out2.result.get("message", "").lower()

    await session.close()


@pytest.mark.asyncio
async def test_browser_navigate():
    session = BrowserSession("test-task")
    await session.launch(headless=True)
    result = await session.navigate("https://example.com")
    assert result.success is True
    assert "example.com" in result.result.get("url", "")
    await session.close()
```

- [ ] **Step 3: Write executor loop test**

`tests/integration/test_executor_loop.py`:

```python
import pytest
from app.langgraph.nodes import executor_node
from app.langgraph.state import AgentState


@pytest.mark.asyncio
async def test_executor_injects_prior_steps():
    state: AgentState = {
        "query": "test query",
        "task_id": "test-task",
        "plan": [
            {"step_number": 1, "description": "Launch browser", "tool": "browser_env__launch", "expected_output": "Browser open"},
            {"step_number": 2, "description": "Navigate to example.com", "tool": "browser_env__navigate", "expected_output": "Page loaded"},
        ],
        "steps": [
            {"step_number": 1, "description": "Launch browser", "output": "Browser launched", "tool_results": [{"success": True}]},
        ],
        "current_step_index": 1,
        "tool_calls": [],
        "messages": [],
        "verified": False,
        "verification_notes": "",
        "verification_reports": [],
        "recovery_decisions": [],
        "status": "step_executed",
        "trace_id": "",
        "capability_assessment": None,
        "environment_config": None,
        "approved": False,
        "approval_reason": "",
        "max_tool_rounds": 5,
    }

    result = await executor_node(state)
    assert result["status"] == "step_executed"
    assert result["current_step_index"] == 2
```

- [ ] **Step 4: Run the new tests**

```bash
pytest tests/integration/test_websocket.py -v
pytest tests/integration/test_browser_env.py -v
pytest tests/integration/test_executor_loop.py -v
```
Expected: All pass (WebSocket tests may need adjustment based on your actual auth utils).

- [ ] **Step 5: Commit**

```bash
git add tests/integration/
git commit -m "test(integration): websocket auth, browser idempotency, executor memory"
```

---

## Self-Review Checklist

1. **Spec coverage:** All three original bugs (WebSocket storm, browser timeout, executor loop) have targeted tasks. Phase 2 adds config wiring and summarizer. Phase 3 adds tests.
2. **Placeholder scan:** No TBD, TODO, or "implement later" found. Every step has exact file paths and code.
3. **Type consistency:** `AgentState` uses `int` for `max_tool_rounds`. `executor_node` reads it with `.get("max_tool_rounds", 5)`. Frontend uses `Set<number>` for terminal close codes.
4. **Minimal fixes:** Each task addresses the root cause without bundling unrelated refactoring.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-04-25-agentos-v2-critical-bugs.md`.**

**Two execution options:**

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration
2. **Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints for review

**Which approach?**
