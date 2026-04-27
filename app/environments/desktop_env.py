"""Desktop Environment — native desktop UI automation."""
import asyncio
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from typing import Any, Dict, List, Optional, Tuple

from ..logs.logger import logger
from ..tools.base import ToolOutput

# Optional dependencies (graceful degradation if missing)
try:
    import pyautogui
except Exception:  # pragma: no cover
    pyautogui = None  # type: ignore

try:
    import pyperclip
except Exception:  # pragma: no cover
    pyperclip = None  # type: ignore

try:
    import pygetwindow as gw
except Exception:  # pragma: no cover
    gw = None  # type: ignore

try:
    from mss import mss
    from mss.exception import ScreenShotError
except Exception:  # pragma: no cover
    mss = None  # type: ignore
    ScreenShotError = Exception  # type: ignore

try:
    import uiautomation as auto
except Exception:  # pragma: no cover
    auto = None  # type: ignore


class DesktopSession:
    """A single desktop automation session scoped to one task."""

    def __init__(self, task_id: str):
        self.task_id = task_id
        self._screen_size: Tuple[int, int] = (0, 0)
        self._ui_element_map: Dict[int, Dict[str, Any]] = {}
        self._next_element_id: int = 1
        self._last_tree_hash: Optional[str] = None
        self._refresh_screen_size()

    def _refresh_screen_size(self) -> None:
        if self._is_headless():
            self._screen_size = (0, 0)
            return
        try:
            if pyautogui:
                size = pyautogui.size()
                self._screen_size = (size.width, size.height)
            else:
                self._screen_size = (0, 0)
        except Exception as e:
            logger.warning(f"DesktopSession[{self.task_id}]: failed to get screen size: {e}")
            self._screen_size = (0, 0)

    def _is_headless(self) -> bool:
        """Heuristic to detect headless / no-display environments."""
        if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
            return True
        try:
            if pyautogui:
                pyautogui.size()
            return False
        except Exception:
            return True

    def _safe_call(
        self,
        func,
        *args,
        default_result: Any = None,
        default_error: Optional[str] = None,
        visibility: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> ToolOutput:
        """Wrap a synchronous call in safety checks and return a ToolOutput."""
        if self._is_headless():
            return ToolOutput(
                success=False,
                error="Desktop automation unavailable: running headless (no display detected)",
            )
        try:
            result = func(*args, **kwargs)
            return ToolOutput(
                success=True,
                result=result if default_result is None else default_result,
                visibility=visibility,
            )
        except Exception as e:
            logger.error(
                f"DesktopSession[{self.task_id}]: {getattr(func, '__name__', func)} failed: {e}"
            )
            return ToolOutput(success=False, error=default_error or str(e))

    def _validate_coords(self, x: int, y: int) -> Optional[str]:
        width, height = self._screen_size
        if width == 0 or height == 0:
            return "Screen size unknown; cannot validate coordinates"
        if not (0 <= x <= width and 0 <= y <= height):
            return f"Coordinates ({x}, {y}) out of screen bounds ({width}, {height})"
        return None

    async def _sync_wait(self, timeout: float = 2.0, poll_interval: float = 0.3) -> None:
        """Wait for the UI to stabilize after an action.

        Currently uses a fixed sleep of 1.0s. Future enhancement: poll the
        accessibility tree hash and wait until it stabilizes.
        """
        await asyncio.sleep(1.0)

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

    def _is_interactive_type(self, control_type: str) -> bool:
        """Return True only for truly interactive control types."""
        interactive = {
            "button", "checkbox", "combobox", "edit", "hyperlink",
            "listitem", "menuitem", "radiobutton", "slider", "spinner",
            "splitbutton", "tabitem", "treeitem",
        }
        return control_type.lower() in interactive

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
        if self._is_actionable_type(control_type):
            return True

        # Discard generic layout containers with no text
        if control_type in {"pane", "window", "group", "custom", "document", "scrollpane"}:
            return False

        # Default: keep if it is focusable
        return bool(node_info.get("is_focusable"))

    def _get_element_center(self, element) -> Optional[Tuple[int, int]]:
        """Extract center coordinates from a uiautomation element."""
        try:
            rect = element.BoundingRectangle
            if rect:
                width = rect.right - rect.left
                height = rect.bottom - rect.top
                if width > 0 and height > 0:
                    center_x = rect.left + width // 2
                    center_y = rect.top + height // 2
                    return (center_x, center_y)
        except Exception:
            pass
        return None

    def _build_ui_tree_windows(self, max_depth: int = 8, max_nodes: int = 100) -> List[Dict[str, Any]]:
        """Build pruned UI tree on Windows using uiautomation."""
        tree: List[Dict[str, Any]] = []
        if auto is None:
            return tree

        try:
            root = auto.GetRootControl()
            # Walk descendants — depth-first
            for element in root.GetChildren():
                self._walk_element_windows(element, tree, depth=0, max_depth=max_depth, max_nodes=max_nodes)
                if len(tree) >= max_nodes:
                    break
        except Exception as e:
            logger.warning(f"DesktopSession[{self.task_id}]: uiautomation tree walk failed: {e}")

        return tree

    def _walk_element_windows(
        self,
        element,
        tree: List[Dict[str, Any]],
        depth: int,
        max_depth: int,
        max_nodes: int = 100,
    ) -> None:
        """Recursively walk a Windows UI Automation element."""
        if depth > max_depth:
            return
        if len(tree) >= max_nodes:
            return

        try:
            control_type = (element.ControlTypeName or "Unknown").strip()
            # uiautomation returns suffixed names like "ButtonControl"; strip suffix
            if control_type.lower().endswith("control"):
                control_type = control_type[:-7]
            name = (element.Name or "").strip()
            value = ""
            try:
                vp = element.GetValuePattern()
                value = (vp.Value or "") if vp else ""
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
                offscreen = element.IsOffscreen if hasattr(element, "IsOffscreen") else False
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

            if len(tree) >= max_nodes:
                return

            # Walk children regardless of whether parent was kept
            for child in element.GetChildren():
                self._walk_element_windows(child, tree, depth + 1, max_depth, max_nodes)
                if len(tree) >= max_nodes:
                    return
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
        canonical = json.dumps(tree, sort_keys=True, ensure_ascii=True)
        return hashlib.md5(canonical.encode("utf-8")).hexdigest()

    async def _vision_fallback_stub(self) -> ToolOutput:
        screenshot_result = await self.screenshot()
        if not screenshot_result.success:
            return ToolOutput(
                success=False,
                error=f"Vision fallback failed: {screenshot_result.error}",
            )
        screenshot_path = (
            screenshot_result.result.get("path")
            if isinstance(screenshot_result.result, dict)
            else None
        )
        return ToolOutput(
            success=True,
            result={
                "mode": "vision_fallback",
                "screenshot_path": screenshot_path,
                "note": "This is a stub for integrating with a grounding model like OmniParser.",
            },
            visibility={"type": "vision_fallback", "screenshot_path": screenshot_path},
        )

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

            # If too few interactive nodes, trigger vision fallback
            actionable_count = sum(
                1 for node in tree
                if self._is_interactive_type(node.get("type", ""))
            )

            result_payload = {
                "tree": tree,
                "count": len(tree),
                "actionable_count": actionable_count,
            }

            if actionable_count < 3:
                logger.warning(
                    f"DesktopSession[{self.task_id}]: sparse tree ({actionable_count} actionable nodes). "
                    "Triggering vision fallback."
                )
                return await self._vision_fallback_stub()

            return ToolOutput(
                success=True,
                result=result_payload,
                visibility={"type": "desktop_ui_tree", "count": len(tree)},
            )
        except Exception as e:
            logger.error(f"DesktopSession[{self.task_id}]: get_ui_tree failed: {e}")
            return ToolOutput(success=False, error=str(e))

    async def click_element(self, element_id: int) -> ToolOutput:
        if pyautogui is None:
            return ToolOutput(
                success=False, error="Input automation library (pyautogui) not available"
            )
        meta = self._ui_element_map.get(element_id)
        if not meta:
            return ToolOutput(
                success=False,
                error="Element not found. Call get_ui_tree first to refresh the UI tree.",
            )
        center = meta.get("center")
        if not center:
            return ToolOutput(
                success=False,
                error="Element has no center coordinates.",
            )
        x, y = center
        error = self._validate_coords(x, y)
        if error:
            return ToolOutput(success=False, error=error)
        result = self._safe_call(
            pyautogui.click,
            x,
            y,
            default_result={
                "message": f"Clicked element {element_id} ({meta.get('name') or meta.get('type')})"
            },
            visibility={
                "type": "desktop_click_element",
                "element_id": element_id,
                "x": x,
                "y": y,
            },
        )
        await self._sync_wait()
        return result

    async def type_element(self, element_id: int, text: str) -> ToolOutput:
        if pyautogui is None:
            return ToolOutput(
                success=False, error="Input automation library (pyautogui) not available"
            )
        meta = self._ui_element_map.get(element_id)
        if not meta:
            return ToolOutput(
                success=False,
                error="Element not found. Call get_ui_tree first to refresh the UI tree.",
            )
        center = meta.get("center")
        if center:
            x, y = center
            error = self._validate_coords(x, y)
            if error:
                return ToolOutput(success=False, error=error)
            click_result = self._safe_call(
                pyautogui.click,
                x,
                y,
                default_result={"message": f"Focused element {element_id}"},
            )
            if not click_result.success:
                await self._sync_wait()
                return click_result
        result = self._safe_call(
            pyautogui.typewrite,
            text,
            interval=0.01,
            default_result={"message": f"Typed text into element {element_id} (length {len(text)})"},
            visibility={
                "type": "desktop_type_element",
                "element_id": element_id,
                "text_length": len(text),
            },
        )
        await self._sync_wait()
        return result

    async def focus_and_interact(self, element_id: int, key: str = "enter") -> ToolOutput:
        if pyautogui is None:
            return ToolOutput(
                success=False, error="Input automation library (pyautogui) not available"
            )
        meta = self._ui_element_map.get(element_id)
        if not meta:
            return ToolOutput(
                success=False,
                error="Element not found. Call get_ui_tree first to refresh the UI tree.",
            )
        element = meta.get("element")
        focused = False
        if sys.platform == "win32" and auto is not None and element is not None:
            try:
                vp = element.GetValuePattern()
                if vp:
                    element.SetFocus()
                    focused = True
                else:
                    ip = element.GetInvokePattern()
                    if ip:
                        element.SetFocus()
                        focused = True
            except Exception:
                pass
        if not focused:
            center = meta.get("center")
            if center:
                x, y = center
                error = self._validate_coords(x, y)
                if error:
                    return ToolOutput(success=False, error=error)
                click_result = self._safe_call(
                    pyautogui.click,
                    x,
                    y,
                    default_result={"message": f"Focused element {element_id} via click"},
                )
                if not click_result.success:
                    await self._sync_wait()
                    return click_result
        key = key.strip().lower()
        if "+" in key:
            parts = [p.strip() for p in key.split("+")]
            result = self._safe_call(
                pyautogui.hotkey,
                *parts,
                default_result={"message": f"Pressed hotkey {key} on element {element_id}"},
                visibility={
                    "type": "desktop_focus_and_interact",
                    "element_id": element_id,
                    "key": key,
                },
            )
        else:
            result = self._safe_call(
                pyautogui.press,
                key,
                default_result={"message": f"Pressed key {key} on element {element_id}"},
                visibility={
                    "type": "desktop_focus_and_interact",
                    "element_id": element_id,
                    "key": key,
                },
            )
        await self._sync_wait()
        return result

    async def screenshot(self, path: Optional[str] = None) -> ToolOutput:
        if self._is_headless():
            return ToolOutput(
                success=False,
                error="Desktop automation unavailable: running headless (no display detected)",
            )
        if mss is None:
            return ToolOutput(success=False, error="Screenshot library (mss) not available")
        try:
            if not path:
                path = os.path.join(
                    tempfile.gettempdir(),
                    f"agentos_desktop_screenshot_{self.task_id}.png",
                )
            with mss() as sct:
                sct.shot(output=path)
            logger.info(f"DesktopSession[{self.task_id}]: screenshot saved to {path}")
            return ToolOutput(
                success=True,
                result={"path": path, "message": f"Screenshot saved to {path}"},
                visibility={"type": "desktop_screenshot", "path": path},
            )
        except ScreenShotError as e:
            logger.error(f"DesktopSession[{self.task_id}]: screenshot failed: {e}")
            return ToolOutput(success=False, error=f"Screenshot failed: {e}")
        except Exception as e:
            logger.error(f"DesktopSession[{self.task_id}]: screenshot failed: {e}")
            return ToolOutput(success=False, error=str(e))

    async def click(self, x: int, y: int) -> ToolOutput:
        if self._is_headless():
            return ToolOutput(
                success=False,
                error="Desktop automation unavailable: running headless (no display detected)",
            )
        if pyautogui is None:
            return ToolOutput(
                success=False, error="Input automation library (pyautogui) not available"
            )
        error = self._validate_coords(x, y)
        if error:
            return ToolOutput(success=False, error=error)
        result = self._safe_call(
            pyautogui.click,
            x,
            y,
            default_result={"message": f"Clicked at ({x}, {y})"},
            visibility={"type": "desktop_click", "x": x, "y": y},
        )
        await self._sync_wait()
        return result

    async def type_text(self, text: str, interval: float = 0.01) -> ToolOutput:
        if pyautogui is None:
            return ToolOutput(
                success=False, error="Input automation library (pyautogui) not available"
            )
        result = self._safe_call(
            pyautogui.typewrite,
            text,
            interval=interval,
            default_result={"message": f"Typed text (length {len(text)})"},
            visibility={"type": "desktop_type", "text_length": len(text)},
        )
        await self._sync_wait()
        return result

    async def press_key(self, keys: str) -> ToolOutput:
        """Press a key or key combination.

        Examples: 'enter', 'ctrl+c', 'alt+f4'
        """
        if pyautogui is None:
            return ToolOutput(
                success=False, error="Input automation library (pyautogui) not available"
            )
        keys = keys.strip().lower()
        if "+" in keys:
            parts = [p.strip() for p in keys.split("+")]
            result = self._safe_call(
                pyautogui.hotkey,
                *parts,
                default_result={"message": f"Pressed hotkey {keys}"},
                visibility={"type": "desktop_key", "keys": keys},
            )
        else:
            result = self._safe_call(
                pyautogui.press,
                keys,
                default_result={"message": f"Pressed key {keys}"},
                visibility={"type": "desktop_key", "keys": keys},
            )
        await self._sync_wait()
        return result

    async def get_window_list(self) -> ToolOutput:
        if self._is_headless():
            return ToolOutput(
                success=False,
                error="Desktop automation unavailable: running headless (no display detected)",
            )
        try:
            windows: List[Dict[str, Any]] = []
            if sys.platform == "win32" and gw is not None:
                for w in gw.getAllWindows():
                    if w.title:
                        windows.append(
                            {
                                "title": w.title,
                                "left": w.left,
                                "top": w.top,
                                "width": w.width,
                                "height": w.height,
                            }
                        )
            elif sys.platform.startswith("linux"):
                result = subprocess.run(
                    ["wmctrl", "-l"],
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0:
                    for line in result.stdout.splitlines():
                        parts = line.split(None, 3)
                        if len(parts) >= 4:
                            windows.append({"title": parts[3]})
                else:
                    result = subprocess.run(
                        ["xdotool", "search", "--onlyvisible", "--name", ".*", "getwindowname"],
                        capture_output=True,
                        text=True,
                    )
                    if result.returncode == 0:
                        for title in result.stdout.splitlines():
                            if title:
                                windows.append({"title": title})
            elif sys.platform == "darwin":
                result = subprocess.run(
                    [
                        "osascript",
                        "-e",
                        'tell application "System Events" to get name of every window of '
                        '(get processes whose visible is true)',
                    ],
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0:
                    for title in result.stdout.split(","):
                        t = title.strip()
                        if t:
                            windows.append({"title": t})
            else:
                return ToolOutput(
                    success=False,
                    error=f"Window listing not supported on platform: {sys.platform}",
                )
            return ToolOutput(
                success=True,
                result={"windows": windows, "count": len(windows)},
                visibility={"type": "desktop_windows", "count": len(windows)},
            )
        except Exception as e:
            logger.error(f"DesktopSession[{self.task_id}]: get_window_list failed: {e}")
            return ToolOutput(success=False, error=str(e))

    async def focus_window(self, title: str) -> ToolOutput:
        if self._is_headless():
            return ToolOutput(
                success=False,
                error="Desktop automation unavailable: running headless (no display detected)",
            )
        try:
            if sys.platform == "win32" and gw is not None:
                matches = gw.getWindowsWithTitle(title)
                if not matches:
                    return ToolOutput(
                        success=False,
                        error=f"No window found with title: {title}",
                    )
                win = matches[0]
                if hasattr(win, "activate"):
                    win.activate()
                output = ToolOutput(
                    success=True,
                    result={"message": f"Focused window: {win.title}"},
                    visibility={"type": "desktop_focus", "title": win.title},
                )
                await self._sync_wait()
                return output
            elif sys.platform.startswith("linux"):
                result = subprocess.run(
                    ["wmctrl", "-a", title],
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0:
                    output = ToolOutput(
                        success=True,
                        result={"message": f"Focused window: {title}"},
                        visibility={"type": "desktop_focus", "title": title},
                    )
                    await self._sync_wait()
                    return output
                result = subprocess.run(
                    ["xdotool", "search", "--name", title, "windowactivate"],
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0:
                    output = ToolOutput(
                        success=True,
                        result={"message": f"Focused window: {title}"},
                        visibility={"type": "desktop_focus", "title": title},
                    )
                    await self._sync_wait()
                    return output
                return ToolOutput(
                    success=False,
                    error=f"Failed to focus window: {title}",
                )
            elif sys.platform == "darwin":
                script = (
                    f'tell application "System Events" to tell process "{title}" '
                    f"to set frontmost to true"
                )
                result = subprocess.run(
                    ["osascript", "-e", script],
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0:
                    output = ToolOutput(
                        success=True,
                        result={"message": f"Focused window: {title}"},
                        visibility={"type": "desktop_focus", "title": title},
                    )
                    await self._sync_wait()
                    return output
                return ToolOutput(
                    success=False,
                    error=f"Failed to focus window: {title}",
                )
            else:
                return ToolOutput(
                    success=False,
                    error=f"Window focus not supported on platform: {sys.platform}",
                )
        except Exception as e:
            logger.error(f"DesktopSession[{self.task_id}]: focus_window failed: {e}")
            return ToolOutput(success=False, error=str(e))

    async def get_clipboard(self) -> ToolOutput:
        if pyperclip is None:
            return ToolOutput(
                success=False, error="Clipboard library (pyperclip) not available"
            )
        return self._safe_call(pyperclip.paste)

    async def set_clipboard(self, text: str) -> ToolOutput:
        if pyperclip is None:
            return ToolOutput(
                success=False, error="Clipboard library (pyperclip) not available"
            )
        return self._safe_call(
            pyperclip.copy,
            text,
            default_result={"message": "Clipboard updated"},
        )

    async def get_mouse_position(self) -> ToolOutput:
        if pyautogui is None:
            return ToolOutput(
                success=False, error="Input automation library (pyautogui) not available"
            )

        def _get_pos():
            pos = pyautogui.position()
            return {"x": pos.x, "y": pos.y}

        return self._safe_call(_get_pos)

    async def scroll(self, amount: int) -> ToolOutput:
        if pyautogui is None:
            return ToolOutput(
                success=False, error="Input automation library (pyautogui) not available"
            )
        result = self._safe_call(
            pyautogui.scroll,
            amount,
            default_result={"message": f"Scrolled {amount}"},
            visibility={"type": "desktop_scroll", "amount": amount},
        )
        await self._sync_wait()
        return result

    async def close(self) -> ToolOutput:
        logger.info(f"DesktopSession[{self.task_id}]: session closed")
        return ToolOutput(success=True, result={"message": "Desktop session closed"})


class DesktopSessionManager:
    """Manages desktop sessions per task_id."""

    def __init__(self):
        self._sessions: Dict[str, DesktopSession] = {}

    async def get_or_create_session(self, task_id: str) -> DesktopSession:
        session = self._sessions.get(task_id)
        if session:
            logger.info(f"DesktopSessionManager: reusing session for task {task_id}")
            return session
        session = DesktopSession(task_id)
        self._sessions[task_id] = session
        logger.info(f"DesktopSessionManager: created new session for task {task_id}")
        return session

    def get_session(self, task_id: str) -> Optional[DesktopSession]:
        return self._sessions.get(task_id)

    async def close_session(self, task_id: str) -> ToolOutput:
        session = self._sessions.pop(task_id, None)
        if session:
            return await session.close()
        return ToolOutput(success=True, result={"message": "No session to close"})

    async def close_all(self):
        for task_id, session in list(self._sessions.items()):
            await session.close()
        self._sessions.clear()


desktop_session_manager = DesktopSessionManager()
