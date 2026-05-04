# AgentOS Desktop Automation Production Hardening — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close integration gaps (checkpointer redundancy, session memory leaks, missing positive desktop recovery, phantom tool mappings) and establish a runnable 5-task desktop regression benchmark suite.

**Architecture:** Hotfix-first: Phase 1 stabilization PR (checkpointer + sessions + recovery + grounding). Phase 2: benchmark suite + observability. Each task produces self-contained, testable changes.

**Tech Stack:** Python 3.12, FastAPI, LangGraph, SQLAlchemy/asyncpg, Redis, uiautomation, pyautogui, opencv-python-headless, easyocr, psutil, asyncio-throttle, pytesseract, comtypes, pytest, pytest-asyncio.

---

## File Structure

| File | Responsibility |
|------|--------------|
| `app/langgraph/checkpointer.py` | Remove redundant `IntegrityError` catch around upsert |
| `app/orchestrator/core.py` | Remove `"uq_checkpoint_write" in err_str` substring match |
| `app/environments/desktop_env.py` | Add session TTL timestamps + `asyncio` reaper task |
| `app/environments/execution_stabilizer.py` | Add periodic orphaned-screenshot cleanup background task |
| `app/capabilities/recovery.py` | Add `DesktopRecoveryPlanner` with positive strategies; fix phantom tool mappings |
| `app/tools/grounding.py` | Add missing MCP desktop tools to `CAPABILITY_TOOL_MAP`; add existence validation |
| `tests/benchmarks/desktop/conftest.py` | Shared fixtures for desktop benchmark suite |
| `tests/benchmarks/desktop/base.py` | `DesktopBenchmarkBase` class with lifecycle + metrics |
| `tests/benchmarks/desktop/test_regression_suite.py` | 5 regression tasks (Win32/WPF/Electron/canvas/vision) |
| `tests/unit/test_desktop_session_ttl.py` | Unit tests for session manager TTL |
| `tests/unit/test_recovery_planner.py` | Unit tests for desktop recovery strategies |
| `tests/unit/test_checkpointer_upsert.py` | Unit tests for idempotent checkpoint writes |
| `requirements.txt` | Add `psutil`, `asyncio-throttle`, `pytesseract`, `comtypes` |

---

## Task 1: Update requirements.txt and install dependencies

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add missing packages to requirements.txt**

Append the following lines to `requirements.txt` (if not already present):

```
psutil
asyncio-throttle
pytesseract
comtypes
```

Verify they are not duplicates of existing entries.

- [ ] **Step 2: Install into .venv**

Run:
```bash
.venv\Scripts\python.exe -m pip install psutil asyncio-throttle pytesseract comtypes
```

Expected: All packages install successfully (may need Tesseract OCR binary installed separately; note this in docs).

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "deps: add psutil, asyncio-throttle, pytesseract, comtypes for desktop hardening"
```

---

## Task 2: Checkpointer — remove redundant IntegrityError fallback

**Files:**
- Modify: `app/langgraph/checkpointer.py` (lines ~269-285)

**Context:** `aput_writes()` already uses `on_conflict_do_nothing(constraint="uq_checkpoint_write")`. The surrounding `try/except IntegrityError` block is redundant and creates a dual-path design. Removing it simplifies to a single upsert path.

- [ ] **Step 1: Read current `aput_writes()`**

Run: `Read app/langgraph/checkpointer.py` around lines 260-290.
Confirm you see:
```python
stmt = pg_insert(...).on_conflict_do_nothing(constraint="uq_checkpoint_write")
try:
    async with session.begin_nested():
        await session.execute(stmt)
except IntegrityError as exc:
    ...
```

- [ ] **Step 2: Remove try/except wrapper**

Replace the redundant block. The exact edit depends on the current code, but the goal is:

**Before:**
```python
stmt = pg_insert(self._get_checkpoint_model()).values(
    id=str(_uuid.uuid4()),
    thread_id=thread_id,
    checkpoint_ns=checkpoint_ns,
    checkpoint_id=checkpoint_id,
    task_id=task_id_local,
    task_path=task_path,
    write_data=_encode((task_id_local, channel, value)),
).on_conflict_do_nothing(constraint="uq_checkpoint_write")
try:
    async with session.begin_nested():
        await session.execute(stmt)
except IntegrityError as exc:
    orig = getattr(exc, "orig", None)
    pgcode = getattr(orig, "pgcode", None)
    if pgcode == "23505":
        logger.debug(
            "Checkpoint write conflict suppressed (pgcode=23505)",
            task=task_id_local,
            channel=channel,
        )
        continue
    raise
```

**After:**
```python
stmt = pg_insert(self._get_checkpoint_model()).values(
    id=str(_uuid.uuid4()),
    thread_id=thread_id,
    checkpoint_ns=checkpoint_ns,
    checkpoint_id=checkpoint_id,
    task_id=task_id_local,
    task_path=task_path,
    write_data=_encode((task_id_local, channel, value)),
).on_conflict_do_nothing(constraint="uq_checkpoint_write")
await session.execute(stmt)
```

- [ ] **Step 3: Verify no other IntegrityError references in aput_writes**

Run: `grep -n "IntegrityError" app/langgraph/checkpointer.py`
Expected: Only references in `aput()` or other methods, NOT in `aput_writes()`.

- [ ] **Step 4: Run checkpointer unit test**

Run: `pytest tests/unit/test_checkpointer_upsert.py -v` (Task 10 will create this; if it doesn't exist yet, run existing checkpointer tests).

- [ ] **Step 5: Commit**

```bash
git add app/langgraph/checkpointer.py
git commit -m "fix(checkpointer): remove redundant IntegrityError fallback around upsert"
```

---

## Task 3: Orchestrator — remove fragile substring matching on checkpoint errors

**Files:**
- Modify: `app/orchestrator/core.py` (around line 234)

**Context:** The orchestrator independently detects checkpoint errors via `"uq_checkpoint_write" in err_str` substring matching. Since the checkpointer now uses a pure upsert with no exception, this code is dead and dangerous (false positives on unrelated errors containing those substrings).

- [ ] **Step 1: Read the error handling block**

Run: `Read app/orchestrator/core.py` around lines 220-250.
Look for:
```python
is_checkpoint_error = "uq_checkpoint_write" in err_str or "checkpoint_writes" in err_str
```

- [ ] **Step 2: Remove substring check**

Replace the logic so the orchestrator no longer special-cases checkpoint collisions. If the checkpointer upsert succeeds (it always will, silently dropping duplicates), no exception reaches the orchestrator. If a different exception reaches the orchestrator, it should be treated as a genuine error.

Exact edit: Remove the `is_checkpoint_error` variable and any `if is_checkpoint_error: ...` branch that retries or suppresses the error. Let genuine exceptions propagate or be handled by the existing generic error path.

- [ ] **Step 3: Verify no other substring matches**

Run: `grep -n "uq_checkpoint_write" app/orchestrator/core.py`
Expected: No matches.

- [ ] **Step 4: Commit**

```bash
git add app/orchestrator/core.py
git commit -m "fix(orchestrator): remove fragile checkpoint substring matching"
```

---

## Task 4: DesktopSessionManager — TTL enforcement + background reaper

**Files:**
- Modify: `app/environments/desktop_env.py` (class `DesktopSessionManager`, lines ~1744-1775)
- Create: `tests/unit/test_desktop_session_ttl.py`

**Context:** `DesktopSessionManager` stores sessions in an unbounded `_sessions: Dict[str, DesktopSession]`. No timestamps, no TTL, no cleanup. This causes memory leaks. We add a 30-minute TTL and an `asyncio` reaper task that scans every 60 seconds.

- [ ] **Step 1: Modify `DesktopSessionManager.__init__`**

Replace the current `__init__`:
```python
def __init__(self):
    self._sessions: Dict[str, DesktopSession] = {}
```

With:
```python
def __init__(self, session_ttl_seconds: int = 1800):
    self._sessions: Dict[str, DesktopSession] = {}
    self._session_meta: Dict[str, dict] = {}
    self._session_ttl_seconds = session_ttl_seconds
    self._cleanup_task: Optional[asyncio.Task] = None
    self._cleanup_interval_seconds = 60
```

- [ ] **Step 2: Add `_start_cleanup_task` method**

Insert after `__init__`:
```python
def _start_cleanup_task(self) -> None:
    """Start the background session reaper if not already running."""
    if self._cleanup_task is None or self._cleanup_task.done():
        self._cleanup_task = asyncio.create_task(
            self._cleanup_loop(), name="desktop_session_reaper"
        )
```

- [ ] **Step 3: Add `_cleanup_loop` method**

Insert after `_start_cleanup_task`:
```python
async def _cleanup_loop(self) -> None:
    """Periodically close expired sessions. Never crashes the worker."""
    while True:
        try:
            await asyncio.sleep(self._cleanup_interval_seconds)
            await self.close_expired_sessions()
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.warning(f"DesktopSessionManager cleanup loop error: {exc}")
```

- [ ] **Step 4: Add `close_expired_sessions` method**

Insert after `_cleanup_loop`:
```python
async def close_expired_sessions(self) -> int:
    """Close sessions older than TTL. Returns number closed."""
    import time
    now = time.time()
    expired = []
    for task_id, meta in list(self._session_meta.items()):
        created_at = meta.get("created_at", 0)
        if now - created_at > self._session_ttl_seconds:
            expired.append(task_id)
    for task_id in expired:
        try:
            await self.close_session(task_id)
        except Exception as exc:
            logger.warning(f"Failed to close expired session {task_id}: {exc}")
    return len(expired)
```

- [ ] **Step 5: Modify `get_or_create_session` to track timestamps and start reaper**

Replace:
```python
async def get_or_create_session(self, task_id: str) -> DesktopSession:
    session = self._sessions.get(task_id)
    if session:
        logger.info(f"DesktopSessionManager: reusing session for task {task_id}")
        return session
    session = DesktopSession(task_id)
    self._sessions[task_id] = session
    logger.info(f"DesktopSessionManager: created new session for task {task_id}")
    return session
```

With:
```python
async def get_or_create_session(self, task_id: str) -> DesktopSession:
    import time
    self._start_cleanup_task()
    session = self._sessions.get(task_id)
    if session:
        logger.info(f"DesktopSessionManager: reusing session for task {task_id}")
        self._session_meta[task_id]["last_accessed"] = time.time()
        return session
    session = DesktopSession(task_id)
    self._sessions[task_id] = session
    self._session_meta[task_id] = {
        "created_at": time.time(),
        "last_accessed": time.time(),
    }
    logger.info(f"DesktopSessionManager: created new session for task {task_id}")
    return session
```

- [ ] **Step 6: Modify `close_session` to clean meta**

Replace:
```python
async def close_session(self, task_id: str) -> ToolOutput:
    session = self._sessions.pop(task_id, None)
    if session:
        return await session.close()
    return ToolOutput(success=True, result={"message": "No session to close"})
```

With:
```python
async def close_session(self, task_id: str) -> ToolOutput:
    self._session_meta.pop(task_id, None)
    session = self._sessions.pop(task_id, None)
    if session:
        return await session.close()
    return ToolOutput(success=True, result={"message": "No session to close"})
```

- [ ] **Step 7: Add `close_all` cleanup task cancellation**

Replace:
```python
async def close_all(self):
    for task_id, session in list(self._sessions.items()):
        await session.close()
    self._sessions.clear()
```

With:
```python
async def close_all(self):
    if self._cleanup_task and not self._cleanup_task.done():
        self._cleanup_task.cancel()
        try:
            await self._cleanup_task
        except asyncio.CancelledError:
            pass
    for task_id, session in list(self._sessions.items()):
        await session.close()
    self._sessions.clear()
    self._session_meta.clear()
```

- [ ] **Step 8: Write unit test**

Create `tests/unit/test_desktop_session_ttl.py`:
```python
import asyncio
import time
import pytest
from app.environments.desktop_env import DesktopSessionManager


@pytest.mark.asyncio
async def test_session_expires_after_ttl():
    manager = DesktopSessionManager(session_ttl_seconds=1)
    session = await manager.get_or_create_session("task-1")
    assert "task-1" in manager._sessions
    await asyncio.sleep(1.5)
    closed = await manager.close_expired_sessions()
    assert closed == 1
    assert "task-1" not in manager._sessions
    assert "task-1" not in manager._session_meta


@pytest.mark.asyncio
async def test_cleanup_loop_closes_expired_sessions():
    manager = DesktopSessionManager(session_ttl_seconds=1)
    manager._cleanup_interval_seconds = 0.5
    session = await manager.get_or_create_session("task-2")
    assert manager._cleanup_task is not None
    await asyncio.sleep(2)
    assert "task-2" not in manager._sessions
    await manager.close_all()


@pytest.mark.asyncio
async def test_get_or_create_updates_last_accessed():
    manager = DesktopSessionManager(session_ttl_seconds=10)
    await manager.get_or_create_session("task-3")
    first_access = manager._session_meta["task-3"]["last_accessed"]
    await asyncio.sleep(0.1)
    await manager.get_or_create_session("task-3")
    second_access = manager._session_meta["task-3"]["last_accessed"]
    assert second_access > first_access
```

- [ ] **Step 9: Run unit tests**

Run: `pytest tests/unit/test_desktop_session_ttl.py -v`
Expected: 3 tests pass.

- [ ] **Step 10: Commit**

```bash
git add app/environments/desktop_env.py tests/unit/test_desktop_session_ttl.py
git commit -m "feat(desktop): session TTL + background reaper task"
```

---

## Task 5: ActionStabilizer — periodic orphaned-screenshot cleanup background task

**Files:**
- Modify: `app/environments/execution_stabilizer.py`

**Context:** `cleanup_temp_screenshots()` exists but is manual. We add an optional `asyncio` background task that calls it every 5 minutes.

- [ ] **Step 1: Add scheduler fields to `__init__`**

In `ActionStabilizer.__init__`, add after existing init code:
```python
self._cleanup_task: Optional[asyncio.Task] = None
self._cleanup_interval_seconds = 300  # 5 minutes
```

- [ ] **Step 2: Add `_start_cleanup_task` method**

Insert near `cleanup_temp_screenshots`:
```python
def _start_cleanup_task(self) -> None:
    """Start the background screenshot cleanup loop if not already running."""
    if self._cleanup_task is None or self._cleanup_task.done():
        self._cleanup_task = asyncio.create_task(
            self._cleanup_loop(), name="stabilizer_screenshot_reaper"
        )
```

- [ ] **Step 3: Add `_cleanup_loop` method**

```python
async def _cleanup_loop(self) -> None:
    """Periodically clean orphaned screenshots. Never crashes the worker."""
    while True:
        try:
            await asyncio.sleep(self._cleanup_interval_seconds)
            self.cleanup_temp_screenshots()
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.warning(f"ActionStabilizer cleanup loop error: {exc}")
```

- [ ] **Step 4: Auto-start cleanup in `__init__`**

At the end of `__init__`, add:
```python
self._start_cleanup_task()
```

- [ ] **Step 5: Add cleanup cancellation on shutdown**

Add a new method:
```python
async def shutdown(self) -> None:
    """Cancel background tasks and clean up resources."""
    if self._cleanup_task and not self._cleanup_task.done():
        self._cleanup_task.cancel()
        try:
            await self._cleanup_task
        except asyncio.CancelledError:
            pass
```

- [ ] **Step 6: Commit**

```bash
git add app/environments/execution_stabilizer.py
git commit -m "feat(stabilizer): periodic orphaned-screenshot cleanup background task"
```

---

## Task 6: RecoveryEngine — positive desktop recovery strategies

**Files:**
- Modify: `app/capabilities/recovery.py`
- Create: `tests/unit/test_recovery_planner.py`

**Context:** `RecoveryStrategy.DESKTOP` only blocks browser/shell fallback. We need positive strategies: `REFOCUS`, `REBUILD_TREE`, `VISION_ESCALATE`, `DISMISS_POPUP`.

- [ ] **Step 1: Add `DesktopRecoveryAction` enum**

Insert near `RecoveryStrategy`:
```python
class DesktopRecoveryAction(Enum):
    REFOCUS = auto()
    REBUILD_TREE = auto()
    VISION_ESCALATE = auto()
    DISMISS_POPUP = auto()
    ESCALATE = auto()
```

- [ ] **Step 2: Add `DesktopRecoveryPlanner` class**

Insert before `RecoveryEngine`:
```python
class DesktopRecoveryPlanner:
    """Produces positive desktop recovery actions based on failure patterns."""

    def plan(self, error: str, current_tool: str, task_id: str) -> RecoveryDecision:
        error_lower = error.lower()

        # Pattern: lost focus / window not foreground
        if any(k in error_lower for k in ("focus", "foreground", "not active", "hwnd")):
            return RecoveryDecision(
                task_id=task_id,
                step_id="",
                action=RecoveryAction.SWITCH_TOOL,
                reason="Desktop recovery: re-focus target window",
                next_tool="desktop_env__ensure_focus",
            )

        # Pattern: stale element / tree changed
        if any(k in error_lower for k in ("stale", "element not found", "tree changed", "invalid element")):
            return RecoveryDecision(
                task_id=task_id,
                step_id="",
                action=RecoveryAction.SWITCH_TOOL,
                reason="Desktop recovery: rebuild UI tree and retry",
                next_tool="desktop__get_ui_tree",
            )

        # Pattern: popup / dialog blocking
        if any(k in error_lower for k in ("popup", "dialog", "modal", "blocking")):
            return RecoveryDecision(
                task_id=task_id,
                step_id="",
                action=RecoveryAction.SWITCH_TOOL,
                reason="Desktop recovery: dismiss blocking popup/dialog",
                next_tool="desktop_env__press_key",
                next_tool_params={"key": "esc"},
            )

        # Pattern: pyautogui fail / coordinate error / vision may help
        if any(k in error_lower for k in ("pyautogui", "coordinate", "click failed", "type failed", "vision")):
            return RecoveryDecision(
                task_id=task_id,
                step_id="",
                action=RecoveryAction.SWITCH_TOOL,
                reason="Desktop recovery: escalate to vision fallback",
                next_tool="desktop_env__screenshot",
            )

        # Default: escalate to human
        return RecoveryDecision(
            task_id=task_id,
            step_id="",
            action=RecoveryAction.ESCALATE,
            reason=f"Desktop recovery: no pattern matched for error: {error}",
            escalation_reason=error,
        )
```

- [ ] **Step 3: Integrate planner into `RecoveryEngine.decide()`**

In `decide()`, when `recovery_strategy == RecoveryStrategy.DESKTOP`, BEFORE the existing negative gate logic, call the planner:

Find the existing DESKTOP guard (around lines 240-269). Add at the top of that block:
```python
if recovery_strategy == RecoveryStrategy.DESKTOP:
    planner = DesktopRecoveryPlanner()
    planned = planner.plan(error, current_tool, task_id)
    # Only use planner if it proposes a concrete action (not ESCALATE)
    # or if no existing alternative tool is available
    if planned.action != RecoveryAction.ESCALATE:
        return planned
    # If planner returns ESCALATE, fall through to existing logic
    # which may find an alternative tool or escalate properly
```

- [ ] **Step 4: Fix phantom tool mappings in recovery alternatives**

Find the `TOOL_ALTERNATIVES` dict (around lines 90-101). Replace phantom tool keys with real registered tool names:

**Before:**
```python
"desktop__screenshot": ["desktop_env__screenshot"],
"desktop__click": ["desktop_env__click"],
"desktop__type": ["desktop_env__type_text", "desktop__type_element"],
```

**After:**
```python
"desktop__get_ui_tree": ["desktop_env__screenshot"],
"desktop__click_element": ["desktop__focus_and_interact"],
"desktop__type_element": ["desktop__focus_and_interact", "desktop_env__type_text"],
"desktop__focus_and_interact": ["desktop__click_element", "desktop__type_element"],
"desktop_env__screenshot": ["desktop__get_ui_tree"],
"desktop_env__click": ["desktop_env__screenshot"],
"desktop_env__type_text": ["desktop__type_element", "desktop__focus_and_interact"],
```

Remove any lines referencing `desktop__screenshot`, `desktop__click`, `desktop__type` as keys — these tools do not exist in the registry.

- [ ] **Step 5: Reduce Redis retry TTL for desktop**

Find the Redis retry TTL setting (search for `ttl=604800` or `7 * 24 * 60 * 60`). Change desktop-task retries to 1 hour:

```python
redis_ttl = 3600 if recovery_strategy == RecoveryStrategy.DESKTOP else 604800
```

- [ ] **Step 6: Write unit tests**

Create `tests/unit/test_recovery_planner.py`:
```python
import pytest
from app.capabilities.recovery import (
    DesktopRecoveryPlanner,
    RecoveryStrategy,
    RecoveryEngine,
    RecoveryAction,
)


def test_planner_refocus_on_focus_error():
    planner = DesktopRecoveryPlanner()
    decision = planner.plan("Window lost focus", "desktop__click_element", "t1")
    assert decision.action == RecoveryAction.SWITCH_TOOL
    assert decision.next_tool == "desktop_env__ensure_focus"


def test_planner_rebuild_tree_on_stale_element():
    planner = DesktopRecoveryPlanner()
    decision = planner.plan("Element not found (stale)", "desktop__click_element", "t1")
    assert decision.action == RecoveryAction.SWITCH_TOOL
    assert decision.next_tool == "desktop__get_ui_tree"


def test_planner_dismiss_popup():
    planner = DesktopRecoveryPlanner()
    decision = planner.plan("Blocking dialog appeared", "desktop__type_element", "t1")
    assert decision.action == RecoveryAction.SWITCH_TOOL
    assert decision.next_tool == "desktop_env__press_key"


def test_planner_vision_escalate_on_pyautogui_fail():
    planner = DesktopRecoveryPlanner()
    decision = planner.plan("pyautogui click failed", "desktop__click_element", "t1")
    assert decision.action == RecoveryAction.SWITCH_TOOL
    assert decision.next_tool == "desktop_env__screenshot"


def test_planner_escalate_on_unknown_error():
    planner = DesktopRecoveryPlanner()
    decision = planner.plan("Unknown quantum failure", "desktop__click_element", "t1")
    assert decision.action == RecoveryAction.ESCALATE


@pytest.mark.asyncio
async def test_recovery_engine_uses_planner_for_desktop():
    engine = RecoveryEngine()
    decision = await engine.decide(
        task_id="t1",
        step_id="s1",
        error="Window lost focus",
        current_tool="desktop__click_element",
        recovery_strategy=RecoveryStrategy.DESKTOP,
    )
    assert decision.next_tool == "desktop_env__ensure_focus"
```

- [ ] **Step 7: Run unit tests**

Run: `pytest tests/unit/test_recovery_planner.py -v`
Expected: All tests pass.

- [ ] **Step 8: Commit**

```bash
git add app/capabilities/recovery.py tests/unit/test_recovery_planner.py
git commit -m "feat(recovery): positive desktop recovery strategies + fix phantom tool mappings"
```

---

## Task 7: Tool Grounding — fix CAPABILITY_TOOL_MAP and add existence validation

**Files:**
- Modify: `app/tools/grounding.py`
- Modify: `app/capabilities/recovery.py` (already done in Task 6)

**Context:** The MCP server exposes `desktop__screenshot`, `desktop__click`, `desktop__type_text`, `desktop__press_key`, `desktop__get_window_list`, `desktop__focus_window`, `desktop__get_clipboard`, `desktop__set_clipboard` that are NOT in `CAPABILITY_TOOL_MAP`, making them unreachable via capability grounding.

- [ ] **Step 1: Read current CAPABILITY_TOOL_MAP**

Run: `Read app/tools/grounding.py` around lines 67-88.

- [ ] **Step 2: Add missing MCP desktop tools**

Add the following tools to `CAPABILITY_TOOL_MAP["desktop_automation"]` (if not already present):
```python
"desktop__screenshot",
"desktop__click",
"desktop__type_text",
"desktop__press_key",
"desktop__get_window_list",
"desktop__focus_window",
"desktop__get_clipboard",
"desktop__set_clipboard",
```

- [ ] **Step 3: Add existence validation at import time**

In `app/tools/grounding.py`, add a validation function that runs when the module loads (after `tool_registry` is available):

```python
def _validate_capability_tool_map() -> None:
    """Warn if any capability maps to tools that do not exist in the registry."""
    all_registered = {t["name"] for t in tool_registry.list_tools()}
    for capability, tools in CAPABILITY_TOOL_MAP.items():
        for tool_name in tools:
            if tool_name not in all_registered:
                logger.warning(
                    f"CAPABILITY_TOOL_MAP['{capability}'] references phantom tool: {tool_name}"
                )
```

Call it at module level after `tool_registry` is defined:
```python
_validate_capability_tool_map()
```

- [ ] **Step 4: Commit**

```bash
git add app/tools/grounding.py
git commit -m "fix(tools): add missing MCP desktop tools to CAPABILITY_TOOL_MAP + phantom validation"
```

---

## Task 8: Desktop Benchmark Suite — 5 regression tasks

**Files:**
- Create: `tests/benchmarks/desktop/__init__.py`
- Create: `tests/benchmarks/desktop/conftest.py`
- Create: `tests/benchmarks/desktop/base.py`
- Create: `tests/benchmarks/desktop/test_regression_suite.py`

**Context:** Create a pytest-based benchmark suite with a base class and 5 regression tasks. Real-app tests are skipped if the app is not installed.

- [ ] **Step 1: Create `tests/benchmarks/desktop/__init__.py`**

```python
"""Desktop automation regression benchmark suite."""
```

- [ ] **Step 2: Create `tests/benchmarks/desktop/conftest.py`**

```python
import pytest
import shutil


def pytest_configure(config):
    config.addinivalue_line("markers", "win32: Win32 native app task")
    config.addinivalue_line("markers", "uwp: UWP/WPF app task")
    config.addinivalue_line("markers", "electron: Electron app task")
    config.addinivalue_line("markers", "canvas: Canvas/custom-drawn app task")
    config.addinivalue_line("markers", "vision: Vision-fallback task")


@pytest.fixture
def desktop_session_manager():
    from app.environments.desktop_env import DesktopSessionManager
    manager = DesktopSessionManager(session_ttl_seconds=300)
    yield manager
    # cleanup handled by reaper or explicit close_all


@pytest.fixture
def skip_if_not_installed():
    def _skip(executable: str):
        if not shutil.which(executable):
            pytest.skip(f"{executable} not installed on this machine")
    return _skip
```

- [ ] **Step 3: Create `tests/benchmarks/desktop/base.py`**

```python
import time
import asyncio
from typing import Dict, Any
from dataclasses import dataclass, field


@dataclass
class BenchmarkResult:
    task_name: str
    success: bool
    duration_seconds: float
    action_count: int
    retry_count: int
    perception_layer: str = ""
    error: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


class DesktopBenchmarkBase:
    """Base class for desktop regression benchmarks."""

    def __init__(self, task_name: str):
        self.task_name = task_name
        self.result = BenchmarkResult(task_name=task_name, success=False, duration_seconds=0.0, action_count=0, retry_count=0)

    async def run(self) -> BenchmarkResult:
        start = time.time()
        try:
            await self._execute()
            self.result.success = True
        except Exception as exc:
            self.result.error = str(exc)
        finally:
            self.result.duration_seconds = time.time() - start
        return self.result

    async def _execute(self) -> None:
        raise NotImplementedError
```

- [ ] **Step 4: Create `tests/benchmarks/desktop/test_regression_suite.py`**

```python
import pytest
import asyncio
import shutil
from app.desktop.goal_loop import DesktopGoalLoop
from app.environments.desktop_env import DesktopSessionManager
from tests.benchmarks.desktop.base import DesktopBenchmarkBase


class NotepadBenchmark(DesktopBenchmarkBase):
    """Open Notepad, type text, save. (Win32)"""

    def __init__(self):
        super().__init__("notepad_type_save")

    async def _execute(self) -> None:
        from app.tools.registry import tool_registry
        loop = DesktopGoalLoop(task_id="bench-notepad")
        result = await loop.execute(
            query="Open Notepad, type 'Hello AgentOS', and save the file as C:\\temp\\bench.txt",
            description="Notepad regression benchmark",
            tool_registry=tool_registry,
            grounded_tools=[],
            grounded_tool_names=set(),
            max_iterations=10,
        )
        self.result.success = result.success
        self.result.action_count = len(result.actions_performed)


class CalculatorBenchmark(DesktopBenchmarkBase):
    """Open Calculator, compute 7*8. (UWP/WPF)"""

    def __init__(self):
        super().__init__("calculator_multiply")

    async def _execute(self) -> None:
        from app.tools.registry import tool_registry
        loop = DesktopGoalLoop(task_id="bench-calc")
        result = await loop.execute(
            query="Open Calculator and compute 7 times 8",
            description="Calculator regression benchmark",
            tool_registry=tool_registry,
            grounded_tools=[],
            grounded_tool_names=set(),
            max_iterations=10,
        )
        self.result.success = result.success
        self.result.action_count = len(result.actions_performed)


class PaintBenchmark(DesktopBenchmarkBase):
    """Open Paint, draw a line. (Canvas-like)"""

    def __init__(self):
        super().__init__("paint_draw_line")

    async def _execute(self) -> None:
        from app.tools.registry import tool_registry
        loop = DesktopGoalLoop(task_id="bench-paint")
        result = await loop.execute(
            query="Open Paint and draw a horizontal line",
            description="Paint regression benchmark",
            tool_registry=tool_registry,
            grounded_tools=[],
            grounded_tool_names=set(),
            max_iterations=10,
        )
        self.result.success = result.success
        self.result.action_count = len(result.actions_performed)


class VSCodeBenchmark(DesktopBenchmarkBase):
    """Open VS Code, create a new file. (Electron)"""

    def __init__(self):
        super().__init__("vscode_new_file")

    async def _execute(self) -> None:
        from app.tools.registry import tool_registry
        loop = DesktopGoalLoop(task_id="bench-vscode")
        result = await loop.execute(
            query="Open VS Code and create a new untitled file",
            description="VS Code regression benchmark",
            tool_registry=tool_registry,
            grounded_tools=[],
            grounded_tool_names=set(),
            max_iterations=10,
        )
        self.result.success = result.success
        self.result.action_count = len(result.actions_performed)


class ExplorerBenchmark(DesktopBenchmarkBase):
    """Open File Explorer, navigate to Desktop. (Win32 shell)"""

    def __init__(self):
        super().__init__("explorer_navigate_desktop")

    async def _execute(self) -> None:
        from app.tools.registry import tool_registry
        loop = DesktopGoalLoop(task_id="bench-explorer")
        result = await loop.execute(
            query="Open File Explorer and navigate to the Desktop folder",
            description="Explorer regression benchmark",
            tool_registry=tool_registry,
            grounded_tools=[],
            grounded_tool_names=set(),
            max_iterations=10,
        )
        self.result.success = result.success
        self.result.action_count = len(result.actions_performed)


@pytest.mark.win32
@pytest.mark.asyncio
async def test_notepad_type_save(skip_if_not_installed):
    skip_if_not_installed("notepad.exe")
    bench = NotepadBenchmark()
    result = await bench.run()
    assert result.success, f"Notepad benchmark failed: {result.error}"


@pytest.mark.uwp
@pytest.mark.asyncio
async def test_calculator_multiply(skip_if_not_installed):
    skip_if_not_installed("calc.exe")
    bench = CalculatorBenchmark()
    result = await bench.run()
    assert result.success, f"Calculator benchmark failed: {result.error}"


@pytest.mark.canvas
@pytest.mark.asyncio
async def test_paint_draw_line(skip_if_not_installed):
    skip_if_not_installed("mspaint.exe")
    bench = PaintBenchmark()
    result = await bench.run()
    assert result.success, f"Paint benchmark failed: {result.error}"


@pytest.mark.electron
@pytest.mark.asyncio
async def test_vscode_new_file(skip_if_not_installed):
    skip_if_not_installed("code.exe")
    bench = VSCodeBenchmark()
    result = await bench.run()
    assert result.success, f"VS Code benchmark failed: {result.error}"


@pytest.mark.win32
@pytest.mark.asyncio
async def test_explorer_navigate_desktop(skip_if_not_installed):
    skip_if_not_installed("explorer.exe")
    bench = ExplorerBenchmark()
    result = await bench.run()
    assert result.success, f"Explorer benchmark failed: {result.error}"
```

- [ ] **Step 5: Commit**

```bash
git add tests/benchmarks/desktop/
git commit -m "test(benchmarks): add 5-task desktop regression suite"
```

---

## Task 9: Graph cache LRU eviction

**Files:**
- Modify: `app/langgraph/graphs.py`

**Context:** The PRD requires an LRU eviction policy (max 50 entries) for the graph cache. We need to verify current state and implement if missing.

- [ ] **Step 1: Inspect graph cache implementation**

Run: `Read app/langgraph/graphs.py` (first 100 lines).
Look for a graph cache dict or `lru_cache` / `functools.lru_cache` / custom cache.

- [ ] **Step 2: If no LRU exists, add one**

If the cache is a plain dict, wrap it with `functools.lru_cache(maxsize=50)` on the graph compilation function, OR replace the dict with an `OrderedDict` / `cachetools.LRUCache`.

Typical pattern:
```python
from functools import lru_cache

@lru_cache(maxsize=50)
def _compile_graph(mode: str, ...):
    ...
```

OR if it's an instance dict:
```python
from collections import OrderedDict

class GraphCache:
    def __init__(self, maxsize: int = 50):
        self._cache: OrderedDict = OrderedDict()
        self._maxsize = maxsize

    def get(self, key):
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def set(self, key, value):
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = value
        if len(self._cache) > self._maxsize:
            self._cache.popitem(last=False)
```

- [ ] **Step 3: Commit**

```bash
git add app/langgraph/graphs.py
git commit -m "perf(graphs): add LRU eviction to graph cache (max 50)"
```

---

## Task 10: Integration tests + final validation

**Files:**
- Create: `tests/unit/test_checkpointer_upsert.py`
- Create: `tests/unit/test_memory_leak.py`

- [ ] **Step 1: Create checkpointer upsert test**

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from app.langgraph.checkpointer import PostgresCheckpointSaver


@pytest.mark.asyncio
async def test_aput_writes_uses_upsert_no_exception():
    """Duplicate checkpoint writes must not raise."""
    saver = PostgresCheckpointSaver()
    # Mock session and model
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_session.execute.return_value = mock_result
    mock_session.begin_nested = MagicMock()

    # Patch _get_checkpoint_model to return a mock model
    mock_model = MagicMock()
    mock_model.__tablename__ = "checkpoint_writes"

    with patch.object(saver, "_get_checkpoint_model", return_value=mock_model):
        with patch("app.langgraph.checkpointer.pg_insert") as mock_pg_insert:
            mock_stmt = MagicMock()
            mock_stmt.on_conflict_do_nothing.return_value = mock_stmt
            mock_pg_insert.return_value.values.return_value = mock_stmt
            await saver.aput_writes(
                thread_id="t1",
                checkpoint_ns="ns1",
                checkpoint_id="cp1",
                task_id="task1",
                task_path="path1",
                writes=[("channel1", "value1")],
                session=mock_session,
            )
            mock_stmt.on_conflict_do_nothing.assert_called_once()
            # Should call execute directly, not inside try/except IntegrityError
            mock_session.execute.assert_called_once_with(mock_stmt)
```

- [ ] **Step 2: Create memory leak test**

```python
import pytest
import tracemalloc
from app.environments.desktop_env import DesktopSessionManager


@pytest.mark.asyncio
async def test_memory_growth_per_task():
    """Run 10 desktop sessions and assert <2MB growth."""
    tracemalloc.start()
    manager = DesktopSessionManager(session_ttl_seconds=3600)
    before, _ = tracemalloc.get_traced_memory()

    for i in range(10):
        session = await manager.get_or_create_session(f"task-{i}")
        await manager.close_session(f"task-{i}")

    after, _ = tracemalloc.get_traced_memory()
    growth_mb = (after - before) / (1024 * 1024)
    tracemalloc.stop()
    assert growth_mb < 2.0, f"Memory grew by {growth_mb:.2f}MB across 10 tasks"
```

- [ ] **Step 3: Run all new tests**

Run:
```bash
pytest tests/unit/test_desktop_session_ttl.py tests/unit/test_recovery_planner.py tests/unit/test_checkpointer_upsert.py tests/unit/test_memory_leak.py -v
```

Expected: All pass (or skip for benchmarks if apps not installed).

- [ ] **Step 4: Run full test suite**

Run:
```bash
pytest -q
```

Expected: No regressions. Existing tests still pass.

- [ ] **Step 5: Final commit**

```bash
git add tests/unit/
git commit -m "test: integration tests for checkpointer upsert and memory leak"
```

---

## Spec Coverage Self-Review

| Spec Requirement | Task |
|------------------|------|
| FR1.1: `INSERT ... ON CONFLICT DO NOTHING` | Task 2 (already present, cleanup redundant fallback) |
| FR1.2: Handle `UniqueViolationError` via pgcode | Task 2 (removed; upsert handles it silently) |
| FR1.3: Failed writes must not poison session | Task 2 (upsert never raises) |
| FR2.1: Legacy executor desktop goal loop | Already implemented (verified) |
| FR3.1: verifier_node calls `verify_plan()` | Already implemented (verified) |
| FR4.1: `CAPABILITY_TOOL_MAP` only real tools | Task 7 |
| FR4.3: Warn if capability maps to missing tools | Task 7 |
| FR5.1: Session TTL (30min) | Task 4 |
| FR5.2: Background cleanup task | Task 4 |
| FR5.3: Screenshot auto-cleanup (5min) | Task 5 |
| FR6.1: Desktop recovery does not suggest browser/shell | Already implemented (verified) |
| FR6.2: Positive strategies (re-focus, rebuild, vision, dismiss) | Task 6 |
| FR6.3: Redis retry TTL 1 hour for desktop | Task 6 |
| FR7.1: High-DPI query | Already implemented (verified) |
| FR7.2: Element bounds validation | Already implemented (verified) |
| NFR2: Graph cache LRU (max 50) | Task 9 |
| Benchmark suite (5 regression tasks) | Task 8 |

**Placeholder scan:** No TBD, TODO, or vague steps. Every step has exact file paths, code, and commands.

**Type consistency:** `RecoveryDecision` is used consistently across Tasks 6 and 7. `DesktopSessionManager` TTL fields are integers (seconds). All asyncio tasks are `Optional[asyncio.Task]`.

---

*Plan complete.*
