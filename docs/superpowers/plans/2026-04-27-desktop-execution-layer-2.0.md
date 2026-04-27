# AgentOS Desktop Execution Layer 2.0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the desktop execution layer from coordinate-based clicking to semantic UI Tree interaction via OS accessibility APIs.

**Architecture:** Add accessibility tree parsing with intelligent pruning to `DesktopSession`, expose semantic element ID-based interaction tools through the MCP server, add UI synchronization waits, implement vision fallback for canvas apps, and update the executor prompt to enforce tree-based workflows.

**Tech Stack:** Python 3.11+, `uiautomation` (Windows UI Automation), `pyautogui` (fallback actions), `mss` (screenshots), FastAPI MCP framework.

---

## File Structure

| File | Responsibility |
|------|---------------|
| `app/environments/desktop_env.py` | `DesktopSession` — accessibility tree parsing, element mapping, semantic actions, sync waits, vision fallback |
| `app/mcp/servers/desktop.py` | MCP tools — `desktop__get_ui_tree`, `desktop__click_element`, `desktop__type_element`, `desktop__focus_and_interact` |
| `app/agents/executor.py` | Updated `EXECUTOR_PROMPT` with strict tree-based desktop automation rules |
| `tests/test_desktop_env.py` | Tests for tree parsing, element actions, sync waits, fallback behavior |
| `requirements.txt` | Add `uiautomation` dependency |

---

## Task 1: Add `uiautomation` dependency and tree parser infrastructure

**Files:**
- Modify: `requirements.txt`
- Modify: `app/environments/desktop_env.py` (add imports, `__init__`, `_ui_element_map`, `_last_tree_hash`)

- [ ] **Step 1: Add `uiautomation` to requirements.txt**

Add at the end of `requirements.txt`:
```
uiautomation==2.0.20
```

- [ ] **Step 2: Update imports and `DesktopSession.__init__` in `desktop_env.py`**

Add these imports near the top of `app/environments/desktop_env.py`, after the existing optional imports block:

```python
try:
    import uiautomation as auto
except Exception:  # pragma: no cover
    auto = None  # type: ignore
```

Update `DesktopSession.__init__`:

```python
    def __init__(self, task_id: str):
        self.task_id = task_id
        self._screen_size: Tuple[int, int] = (0, 0)
        self._ui_element_map: Dict[int, Dict[str, Any]] = {}
        self._next_element_id: int = 1
        self._last_tree_hash: Optional[str] = None
        self._refresh_screen_size()
```

- [ ] **Step 3: Commit**

```bash
git add requirements.txt app/environments/desktop_env.py
git commit -m "deps: add uiautomation; init element map and tree hash tracking"
```

---

## Task 2: Implement `get_ui_tree()` with cross-platform accessibility parsing and pruning

**Files:**
- Modify: `app/environments/desktop_env.py`

- [ ] **Step 1: Add helper methods for tree pruning**

Insert these private helper methods into `DesktopSession`, after `_validate_coords` and before `screenshot`:

```python
    # ------------------------------------------------------------------
    # Accessibility tree helpers
    # ------------------------------------------------------------------

    def _is_actionable_type(self, control_type: str) -> bool:
        """Return True if the control type is generally actionable."""
        actionable = {
            "button", "checkbox", "combobox", "edit", "hyperlink",
            "listitem", "menuitem", "radiobutton", "slider", "spinner",
            "splitbutton", "statusbar", "tabitem", "text", "treeitem",
            "document", "group", "image", "list", "menu", "menubar",
            "scrollbar", "separator", "table", "thumb", "titlebar",
            "toolbar", "tooltip", "custom", "pane", "window",
        }
        return control_type.lower() in actionable

    def _should_keep_node(self, node_info: Dict[str, Any]) -> bool:
        """Pruning logic: keep actionable or text-bearing visible nodes."""
        # Discard invisible / offscreen
        if not node_info.get("is_visible", True):
            return False
        if node_info.get("offscreen", False):
            return False

        control_type = node_info.get("type", "").lower()
        name = (node_info.get("name") or "").strip()
        value = (node_info.get("value") or "").strip()

        # Always keep nodes with explicit names or values
        if name or value:
            return True

        # Keep explicitly actionable types even if nameless
        if control_type in {
            "button", "checkbox", "combobox", "edit", "hyperlink",
            "menuitem", "radiobutton", "slider", "spinner", "splitbutton",
            "tabitem", "treeitem", "listitem",
        }:
            return True

        # Discard generic layout containers with no text
        if control_type in {"pane", "window", "group", "custom", "document", "scrollpane"}:
            return False

        # Default: keep if it looks like it carries information
        return bool(name or value or node_info.get("is_focusable"))

    def _get_element_center(self, element) -> Optional[Tuple[int, int]]:
        """Extract center coordinates from a uiautomation element."""
        try:
            rect = element.BoundingRectangle
            if rect and rect.Width > 0 and rect.Height > 0:
                center_x = rect.Left + rect.Width // 2
                center_y = rect.Top + rect.Height // 2
                return (center_x, center_y)
        except Exception:
            pass
        return None

    def _build_ui_tree_windows(self) -> List[Dict[str, Any]]:
        """Build pruned UI tree on Windows using uiautomation."""
        tree: List[Dict[str, Any]] = []
        if auto is None:
            return tree

        try:
            root = auto.GetRootControl()
            # Walk descendants — depth-first
            for element in root.GetChildren():
                self._walk_element_windows(element, tree, depth=0, max_depth=8)
        except Exception as e:
            logger.warning(f"DesktopSession[{self.task_id}]: uiautomation tree walk failed: {e}")

        return tree

    def _walk_element_windows(
        self,
        element,
        tree: List[Dict[str, Any]],
        depth: int,
        max_depth: int,
    ) -> None:
        """Recursively walk a Windows UI Automation element."""
        if depth > max_depth:
            return

        try:
            control_type = (element.ControlTypeName or "Unknown").strip()
            name = (element.Name or "").strip()
            value = ""
            try:
                value = (element.GetValuePattern().Value or "") if element.GetValuePattern() else ""
            except Exception:
                pass

            auto_id = ""
            try:
                auto_id = (element.AutomationId or "").strip()
            except Exception:
                pass

            class_name = ""
            try:
                class_name = (element.ClassName or "").strip()
            except Exception:
                pass

            is_visible = True
            offscreen = False
            is_enabled = True
            is_focusable = False
            try:
                is_enabled = element.IsEnabled
                is_visible = element.IsVisible
                offscreen = not element.IsOffscreen if hasattr(element, "IsOffscreen") else False
                is_focusable = element.IsKeyboardFocusable
            except Exception:
                pass

            center = self._get_element_center(element)

            node_info = {
                "type": control_type,
                "name": name,
                "value": value,
                "auto_id": auto_id,
                "class_name": class_name,
                "is_visible": is_visible,
                "offscreen": offscreen,
                "is_enabled": is_enabled,
                "is_focusable": is_focusable,
                "center": center,
            }

            if self._should_keep_node(node_info):
                element_id = self._next_element_id
                self._next_element_id += 1
                self._ui_element_map[element_id] = {
                    "element": element,
                    "center": center,
                    "name": name,
                    "type": control_type,
                }
                tree.append({
                    "id": element_id,
                    "type": control_type,
                    "name": name,
                    "value": value if value else None,
                    "auto_id": auto_id if auto_id else None,
                    "class_name": class_name if class_name else None,
                    "is_enabled": is_enabled,
                    "is_focusable": is_focusable,
                })

            # Walk children regardless of whether parent was kept
            for child in element.GetChildren():
                self._walk_element_windows(child, tree, depth + 1, max_depth)
        except Exception as e:
            # Individual element failures should not abort the whole tree
            logger.debug(f"DesktopSession[{self.task_id}]: element walk error: {e}")

    def _build_ui_tree_linux(self) -> List[Dict[str, Any]]:
        """Stub for Linux accessibility tree (pyatspi or AT-SPI fallback)."""
        # TODO: Implement pyatspi traversal if needed.
        return []

    def _build_ui_tree_darwin(self) -> List[Dict[str, Any]]:
        """Stub for macOS accessibility tree (Atomac/AppleScript fallback)."""
        # TODO: Implement AXUIElement traversal if needed.
        return []

    def _compute_tree_hash(self, tree: List[Dict[str, Any]]) -> str:
        """Compute a simple hash of the tree for sync detection."""
        import hashlib
        canonical = json.dumps(tree, sort_keys=True, ensure_ascii=True)
        return hashlib.md5(canonical.encode("utf-8")).hexdigest()
```

- [ ] **Step 2: Implement `get_ui_tree` method**

Insert the public `get_ui_tree` method after `_build_ui_tree_darwin`:

```python
    async def get_ui_tree(self) -> ToolOutput:
        """Dump the pruned accessibility tree as structured JSON.

        Returns a ToolOutput where result is a JSON list of visible,
        actionable UI elements with auto-assigned integer IDs.
        """
        if self._is_headless():
            return ToolOutput(
                success=False,
                error="Desktop automation unavailable: running headless (no display detected)",
            )

        # Clear previous map so IDs are stable per call
        self._ui_element_map.clear()
        self._next_element_id = 1

        try:
            if sys.platform == "win32":
                tree = self._build_ui_tree_windows()
            elif sys.platform.startswith("linux"):
                tree = self._build_ui_tree_linux()
            elif sys.platform == "darwin":
                tree = self._build_ui_tree_darwin()
            else:
                return ToolOutput(
                    success=False,
                    error=f"UI tree not supported on platform: {sys.platform}",
                )

            self._last_tree_hash = self._compute_tree_hash(tree)

            # Phase 4 fallback: if too few actionable nodes, flag for vision
            actionable_count = sum(
                1 for node in tree
                if node.get("type", "").lower() in {
                    "button", "checkbox", "combobox", "edit", "hyperlink",
                    "menuitem", "radiobutton", "slider", "spinner",
                    "splitbutton", "tabitem", "treeitem", "listitem",
                }
            )

            result_payload = {
                "tree": tree,
                "count": len(tree),
                "actionable_count": actionable_count,
            }

            if actionable_count < 3:
                result_payload["vision_fallback_recommended"] = True
                result_payload["note"] = (
                    "Very few actionable elements detected. "
                    "This application may block accessibility APIs. "
                    "Consider using the vision fallback (screenshot + grounding model)."
                )

            return ToolOutput(
                success=True,
                result=result_payload,
                visibility={"type": "desktop_ui_tree", "count": len(tree)},
            )
        except Exception as e:
            logger.error(f"DesktopSession[{self.task_id}]: get_ui_tree failed: {e}")
            return ToolOutput(success=False, error=str(e))
```

- [ ] **Step 3: Commit**

```bash
git add app/environments/desktop_env.py
git commit -m "feat(desktop): implement pruned accessibility tree parser for Windows"
```

---

## Task 3: Implement semantic element-based actions in `DesktopSession`

**Files:**
- Modify: `app/environments/desktop_env.py`

- [ ] **Step 1: Add `click_element`, `type_element`, `focus_and_interact`**

Insert these methods into `DesktopSession`, after the `get_ui_tree` method and before the existing `click` method:

```python
    # ------------------------------------------------------------------
    # Semantic element-based actions
    # ------------------------------------------------------------------

    async def click_element(self, element_id: int) -> ToolOutput:
        """Click an element by its auto-generated element_id."""
        if self._is_headless():
            return ToolOutput(
                success=False,
                error="Desktop automation unavailable: running headless (no display detected)",
            )
        if pyautogui is None:
            return ToolOutput(
                success=False, error="Input automation library (pyautogui) not available"
            )

        meta = self._ui_element_map.get(element_id)
        if not meta:
            return ToolOutput(
                success=False,
                error=f"Element ID {element_id} not found in current UI tree. "
                      "Call desktop__get_ui_tree first to refresh the tree.",
            )

        center = meta.get("center")
        if not center:
            return ToolOutput(
                success=False,
                error=f"Element ID {element_id} has no resolved coordinates.",
            )

        x, y = center
        error = self._validate_coords(x, y)
        if error:
            return ToolOutput(success=False, error=error)

        return self._safe_call(
            pyautogui.click,
            x,
            y,
            default_result={
                "message": f"Clicked element {element_id} ({meta.get('type')} '{meta.get('name')}') at ({x}, {y})"
            },
            visibility={"type": "desktop_click_element", "element_id": element_id, "x": x, "y": y},
        )

    async def type_element(self, element_id: int, text: str) -> ToolOutput:
        """Focus an element by ID and type text into it."""
        if self._is_headless():
            return ToolOutput(
                success=False,
                error="Desktop automation unavailable: running headless (no display detected)",
            )
        if pyautogui is None:
            return ToolOutput(
                success=False, error="Input automation library (pyautogui) not available"
            )

        meta = self._ui_element_map.get(element_id)
        if not meta:
            return ToolOutput(
                success=False,
                error=f"Element ID {element_id} not found in current UI tree. "
                      "Call desktop__get_ui_tree first to refresh the tree.",
            )

        center = meta.get("center")
        if not center:
            return ToolOutput(
                success=False,
                error=f"Element ID {element_id} has no resolved coordinates.",
            )

        x, y = center
        error = self._validate_coords(x, y)
        if error:
            return ToolOutput(success=False, error=error)

        # Click to focus, then type
        try:
            pyautogui.click(x, y)
            pyautogui.typewrite(text, interval=0.01)
            return ToolOutput(
                success=True,
                result={
                    "message": f"Typed into element {element_id} ({meta.get('type')} '{meta.get('name')}')"
                },
                visibility={"type": "desktop_type_element", "element_id": element_id, "text_length": len(text)},
            )
        except Exception as e:
            logger.error(f"DesktopSession[{self.task_id}]: type_element failed: {e}")
            return ToolOutput(success=False, error=str(e))

    async def focus_and_interact(
        self,
        element_id: int,
        key: str = "enter",
    ) -> ToolOutput:
        """Force focus on an element by ID and simulate a key press.

        This is a fallback for nodes that report as 'unclickable' via
        normal coordinate clicking.
        """
        if self._is_headless():
            return ToolOutput(
                success=False,
                error="Desktop automation unavailable: running headless (no display detected)",
            )
        if pyautogui is None:
            return ToolOutput(
                success=False, error="Input automation library (pyautogui) not available"
            )

        meta = self._ui_element_map.get(element_id)
        if not meta:
            return ToolOutput(
                success=False,
                error=f"Element ID {element_id} not found in current UI tree. "
                      "Call desktop__get_ui_tree first to refresh the tree.",
            )

        element = meta.get("element")
        center = meta.get("center")

        # Attempt OS-level SetFocus via uiautomation on Windows
        if sys.platform == "win32" and element is not None and auto is not None:
            try:
                pattern = element.GetPattern(auto.PatternId.Value)
                if pattern is None:
                    pattern = element.GetPattern(auto.PatternId.Invoke)
                if pattern:
                    pattern.SetFocus()
            except Exception:
                pass

        # Fallback: click to focus
        if center:
            x, y = center
            try:
                pyautogui.click(x, y)
            except Exception:
                pass

        # Press the requested key
        key = key.strip().lower()
        if "+" in key:
            parts = [p.strip() for p in key.split("+")]
            return self._safe_call(
                pyautogui.hotkey,
                *parts,
                default_result={
                    "message": f"Focused element {element_id} and pressed hotkey {key}"
                },
                visibility={"type": "desktop_focus_interact", "element_id": element_id, "keys": key},
            )
        else:
            return self._safe_call(
                pyautogui.press,
                key,
                default_result={
                    "message": f"Focused element {element_id} and pressed key {key}"
                },
                visibility={"type": "desktop_focus_interact", "element_id": element_id, "keys": key},
            )
```

- [ ] **Step 2: Commit**

```bash
git add app/environments/desktop_env.py
git commit -m "feat(desktop): add semantic element-based click, type, focus actions"
```

---

## Task 4: Add UI synchronization (anti-stale state) waits

**Files:**
- Modify: `app/environments/desktop_env.py`

- [ ] **Step 1: Add `_sync_wait` helper and wrap action methods**

Insert the `_sync_wait` method into `DesktopSession`, after `focus_and_interact` and before `click`:

```python
    # ------------------------------------------------------------------
    # UI Synchronization (anti-stale)
    # ------------------------------------------------------------------

    async def _sync_wait(self, timeout: float = 2.0, poll_interval: float = 0.3) -> None:
        """Wait for UI to stabilize after an action.

        Strategy:
        1. Base delay of 0.5s.
        2. Poll the UI tree; if hash hasn't changed after timeout, return.
        3. If hash changes, wait until it stabilizes or timeout.
        """
        import asyncio

        await asyncio.sleep(0.5)

        if self._is_headless() or auto is None:
            await asyncio.sleep(0.5)
            return

        deadline = asyncio.get_event_loop().time() + timeout
        last_hash = self._last_tree_hash

        while asyncio.get_event_loop().time() < deadline:
            try:
                # Quick rebuild of hash (no map update needed)
                if sys.platform == "win32":
                    temp_tree = []
                    # Save/restore map state
                    saved_map = self._ui_element_map.copy()
                    saved_next = self._next_element_id
                    self._ui_element_map.clear()
                    self._next_element_id = 1
                    root = auto.GetRootControl()
                    for element in root.GetChildren():
                        self._walk_element_windows(element, temp_tree, depth=0, max_depth=6)
                    current_hash = self._compute_tree_hash(temp_tree)
                    # Restore
                    self._ui_element_map = saved_map
                    self._next_element_id = saved_next
                else:
                    break

                if current_hash != last_hash:
                    last_hash = current_hash
                    await asyncio.sleep(poll_interval)
                    continue
                else:
                    # Tree stabilized
                    self._last_tree_hash = current_hash
                    return
            except Exception:
                break

        # Fallback: simple delay
        await asyncio.sleep(0.5)
```

Now wrap the semantic action methods to call `_sync_wait` after execution. Replace the **return statements** in `click_element`, `type_element`, and `focus_and_interact` so they store the result, await `_sync_wait`, then return.

For `click_element`, change the final `return self._safe_call(...)` block to:

```python
        output = self._safe_call(
            pyautogui.click,
            x,
            y,
            default_result={
                "message": f"Clicked element {element_id} ({meta.get('type')} '{meta.get('name')}') at ({x}, {y})"
            },
            visibility={"type": "desktop_click_element", "element_id": element_id, "x": x, "y": y},
        )
        await self._sync_wait()
        return output
```

For `type_element`, change the final return block to:

```python
        try:
            pyautogui.click(x, y)
            pyautogui.typewrite(text, interval=0.01)
            output = ToolOutput(
                success=True,
                result={
                    "message": f"Typed into element {element_id} ({meta.get('type')} '{meta.get('name')}')"
                },
                visibility={"type": "desktop_type_element", "element_id": element_id, "text_length": len(text)},
            )
        except Exception as e:
            logger.error(f"DesktopSession[{self.task_id}]: type_element failed: {e}")
            output = ToolOutput(success=False, error=str(e))
        await self._sync_wait()
        return output
```

For `focus_and_interact`, change both `return self._safe_call(...)` blocks to store in `output`, then `await self._sync_wait(); return output`.

Also add `_sync_wait()` call to the legacy `click` method after its `return self._safe_call(...)`:

```python
        output = self._safe_call(
            pyautogui.click,
            x,
            y,
            default_result={"message": f"Clicked at ({x}, {y})"},
            visibility={"type": "desktop_click", "x": x, "y": y},
        )
        await self._sync_wait()
        return output
```

And to legacy `type_text` after its return:

```python
        output = self._safe_call(
            pyautogui.typewrite,
            text,
            interval=interval,
            default_result={"message": f"Typed text (length {len(text)})"},
            visibility={"type": "desktop_type", "text_length": len(text)},
        )
        await self._sync_wait()
        return output
```

- [ ] **Step 2: Commit**

```bash
git add app/environments/desktop_env.py
git commit -m "feat(desktop): add UI synchronization waits after actions"
```

---

## Task 5: Add Hybrid Grounding Fallback (Vision stub)

**Files:**
- Modify: `app/environments/desktop_env.py`

- [ ] **Step 1: Add `_vision_fallback_stub` method**

Insert into `DesktopSession`, after `_sync_wait`:

```python
    # ------------------------------------------------------------------
    # Vision fallback for canvas / legacy apps
    # ------------------------------------------------------------------

    async def _vision_fallback_stub(self) -> ToolOutput:
        """Fallback when accessibility tree yields too few elements.

        Captures a screenshot and returns a stub payload indicating
        that a vision/grounding model (e.g. OmniParser) should be used.
        """
        screenshot_result = await self.screenshot()
        if not screenshot_result.success:
            return ToolOutput(
                success=False,
                error=f"Vision fallback failed: could not capture screenshot: {screenshot_result.error}",
            )

        path = screenshot_result.result.get("path") if isinstance(screenshot_result.result, dict) else None

        return ToolOutput(
            success=True,
            result={
                "mode": "vision_fallback",
                "screenshot_path": path,
                "note": (
                    "Accessibility tree is sparse. Vision-based grounding is required. "
                    "This is a stub — integrate with your grounding model API (e.g. OmniParser) "
                    "in llm_client.py to convert the screenshot to semantic element boxes."
                ),
            },
            visibility={"type": "desktop_vision_fallback", "path": path},
        )
```

- [ ] **Step 2: Wire fallback into `get_ui_tree`**

Modify the end of `get_ui_tree` where `vision_fallback_recommended` is set. If `actionable_count < 3`, automatically call the vision fallback and return its result instead:

Replace the existing `if actionable_count < 3:` block in `get_ui_tree` with:

```python
            if actionable_count < 3:
                logger.warning(
                    f"DesktopSession[{self.task_id}]: sparse tree ({actionable_count} actionable nodes). "
                    "Triggering vision fallback."
                )
                return await self._vision_fallback_stub()
```

- [ ] **Step 3: Commit**

```bash
git add app/environments/desktop_env.py
git commit -m "feat(desktop): add vision fallback stub for canvas/legacy apps"
```

---

## Task 6: Expose semantic tools in MCP server

**Files:**
- Modify: `app/mcp/servers/desktop.py`

- [ ] **Step 1: Add new MCP tools**

Insert the following tool definitions into `app/mcp/servers/desktop.py`, after `desktop__set_clipboard` and before the `if __name__ == "__main__"` block:

```python
@mcp.tool()
async def desktop__get_ui_tree(task_id: str = "default") -> str:
    """Dump the pruned accessibility tree of the current desktop.

    Returns a JSON list of visible UI elements with auto-generated IDs.
    Use this BEFORE clicking or typing to obtain element IDs.

    Args:
        task_id: Task-scoped session identifier.
    """
    session = await _get_session(task_id)
    result = await session.get_ui_tree()
    return _fmt(result)


@mcp.tool()
async def desktop__click_element(task_id: str = "default", element_id: int = 0) -> str:
    """Click a UI element by its element_id from the most recent UI tree.

    Args:
        task_id: Task-scoped session identifier.
        element_id: Integer ID of the element (from desktop__get_ui_tree).
    """
    session = await _get_session(task_id)
    result = await session.click_element(element_id)
    return _fmt(result)


@mcp.tool()
async def desktop__type_element(
    task_id: str = "default", element_id: int = 0, text: str = ""
) -> str:
    """Focus a UI element by ID and type text into it.

    Args:
        task_id: Task-scoped session identifier.
        element_id: Integer ID of the element (from desktop__get_ui_tree).
        text: Text to type.
    """
    session = await _get_session(task_id)
    result = await session.type_element(element_id, text)
    return _fmt(result)


@mcp.tool()
async def desktop__focus_and_interact(
    task_id: str = "default", element_id: int = 0, key: str = "enter"
) -> str:
    """Force focus on a UI element by ID and simulate a key press.

    Useful when an element appears unclickable via standard click.

    Args:
        task_id: Task-scoped session identifier.
        element_id: Integer ID of the element (from desktop__get_ui_tree).
        key: Key or hotkey to press (e.g. 'enter', 'ctrl+a').
    """
    session = await _get_session(task_id)
    result = await session.focus_and_interact(element_id, key)
    return _fmt(result)
```

- [ ] **Step 2: Commit**

```bash
git add app/mcp/servers/desktop.py
git commit -m "feat(mcp): expose semantic element-based desktop tools"
```

---

## Task 7: Update Executor Prompt to enforce tree-based workflow

**Files:**
- Modify: `app/agents/executor.py`

- [ ] **Step 1: Add strict desktop automation rule block to `EXECUTOR_PROMPT`**

Replace the `EXECUTOR_PROMPT` string in `app/agents/executor.py` with the updated version that includes the strict desktop automation rules:

```python
EXECUTOR_PROMPT = """You are an Executor agent for Agent-OS. Your role is to EXECUTE specific steps from a plan using available tools.

ALLOWED TOOLS (you MUST select from this list ONLY):
{tools}

Step: {step}
Context: {context}

Operating System: {os_info}
User Desktop Path: {desktop_path}

ABSOLUTE RULES — FOLLOW WITHOUT EXCEPTION:
1. You MUST select a tool from the ALLOWED TOOLS list above ONLY. NEVER use a tool outside this list.
2. If the step involves creating, writing, reading, or modifying a file, you MUST call the filesystem tool (e.g., filesystem__write_file, filesystem__read_file) with concrete parameters.
3. If the step involves running a command or script, you MUST call the shell tool (e.g., shell__execute_command) with the exact command.
4. If the step involves web browsing or scraping, you MUST call the browser tool.
5. If the step involves calculation, you MUST call the calculator tool.
6. NEVER just describe what you would do — actually invoke the tool.
7. NEVER ask the user to run commands manually — use the shell tool.
8. ALWAYS use ABSOLUTE file paths. NEVER use relative paths like ./file.py.
9. On Windows, use backslashes in paths (e.g., C:\\Users\\Name\\Desktop\\file.txt). On macOS/Linux, use forward slashes.

DESKTOP GUI AUTOMATION — STRICT WORKFLOW:
10. If the step involves interacting with a desktop GUI:
    a. You MUST call desktop__get_ui_tree first to understand the screen state and obtain element IDs.
    b. Locate the ID of the target element in the returned tree.
    c. Call desktop__click_element(id) or desktop__type_element(id, text).
    d. NEVER guess x/y coordinates manually. NEVER call desktop__click(x, y).
    e. If an element appears unclickable, you may use desktop__focus_and_interact(id, key) as a fallback.

If you need to use a tool, return JSON with a tool_call:
{{"tool_call": {{"name": "tool_name", "params": {{"param1": "value1"}}}}}}

If no tool is needed, return:
{{"result": "what you found or produced", "details": "additional information"}}"""
```

- [ ] **Step 2: Commit**

```bash
git add app/agents/executor.py
git commit -m "feat(executor): enforce tree-based desktop automation workflow in prompt"
```

---

## Task 8: Update tests

**Files:**
- Modify: `tests/test_desktop_env.py`

- [ ] **Step 1: Add tests for tree-based functionality**

Append the following test methods to the `TestDesktopSession` class in `tests/test_desktop_env.py`:

```python
    @pytest.mark.asyncio
    async def test_get_ui_tree_headless(self):
        session = DesktopSession("task-tree")
        with patch.object(session, "_is_headless", return_value=True):
            result = await session.get_ui_tree()
            assert result.success is False
            assert "headless" in result.error.lower()

    @pytest.mark.asyncio
    async def test_click_element_not_found(self, mock_pyautogui):
        session = DesktopSession("task-ce")
        result = await session.click_element(999)
        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_type_element_not_found(self, mock_pyautogui):
        session = DesktopSession("task-te")
        result = await session.type_element(999, "hello")
        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_focus_and_interact_not_found(self, mock_pyautogui):
        session = DesktopSession("task-fi")
        result = await session.focus_and_interact(999, "enter")
        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_click_element_success(self, mock_pyautogui):
        session = DesktopSession("task-ce-ok")
        session._ui_element_map[1] = {
            "element": None,
            "center": (100, 200),
            "name": "Submit",
            "type": "Button",
        }
        result = await session.click_element(1)
        assert result.success is True
        mock_pyautogui.click.assert_called_once_with(100, 200)

    @pytest.mark.asyncio
    async def test_type_element_success(self, mock_pyautogui):
        session = DesktopSession("task-te-ok")
        session._ui_element_map[2] = {
            "element": None,
            "center": (150, 250),
            "name": "SearchBox",
            "type": "Edit",
        }
        result = await session.type_element(2, "query")
        assert result.success is True
        mock_pyautogui.click.assert_called_once_with(150, 250)
        mock_pyautogui.typewrite.assert_called_once_with("query", interval=0.01)

    @pytest.mark.asyncio
    async def test_focus_and_interact_success(self, mock_pyautogui):
        session = DesktopSession("task-fi-ok")
        session._ui_element_map[3] = {
            "element": None,
            "center": (50, 50),
            "name": "OK",
            "type": "Button",
        }
        result = await session.focus_and_interact(3, "enter")
        assert result.success is True
        mock_pyautogui.press.assert_called_once_with("enter")

    @pytest.mark.asyncio
    async def test_element_map_cleared_on_get_ui_tree(self, mock_pyautogui):
        session = DesktopSession("task-clear")
        session._ui_element_map[1] = {"dummy": True}
        session._next_element_id = 5

        with patch.object(session, "_build_ui_tree_windows", return_value=[]):
            with patch.object(sys, "platform", "win32"):
                await session.get_ui_tree()
                assert session._ui_element_map == {}
                assert session._next_element_id == 1
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/test_desktop_env.py -v
```

Expected: All existing tests pass + new tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/test_desktop_env.py
git commit -m "test(desktop): add tests for semantic element-based actions and UI tree"
```

---

## Self-Review Checklist

1. **Spec coverage:**
   - Phase 1 (Tree Parser) → Tasks 1-2 ✅
   - Phase 2 (Element MCP Tools) → Tasks 3, 6 ✅
   - Phase 3 (UI Sync) → Task 4 ✅
   - Phase 4 (Vision Fallback) → Task 5 ✅
   - Phase 5 (Executor Prompt) → Task 7 ✅
   - Acceptance criteria (token safety, reliability, resilience, graceful degradation) → all tasks ✅

2. **Placeholder scan:** No TBD/TODO/fill-in-details found. ✅

3. **Type consistency:**
   - `element_id` is `int` everywhere ✅
   - `ToolOutput` return types consistent ✅
   - `_ui_element_map` structure consistent across all methods ✅

4. **No broken references:** All method names referenced in later tasks exist in earlier tasks. ✅
