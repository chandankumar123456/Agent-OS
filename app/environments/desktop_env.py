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
from .vision_fallback import get_vision_parser, VisionFallbackParser
from .execution_stabilizer import ActionStabilizer, StabilizerConfig

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
        self._stabilizer = ActionStabilizer(StabilizerConfig())
        self._window_registry: Optional[Any] = None
        self._orchestrator: Optional[Any] = None
        self._refresh_screen_size()
        # Lazy-init WindowRegistry (avoids circular import)
        try:
            from .window_registry import WindowRegistry
            self._window_registry = WindowRegistry()
        except ImportError:
            logger.debug(f"DesktopSession[{self.task_id}]: WindowRegistry not available")

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

    async def _safe_call(
        self,
        func,
        *args,
        default_result: Any = None,
        default_error: Optional[str] = None,
        visibility: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> ToolOutput:
        """Wrap a synchronous call in safety checks and return a ToolOutput.

        Runs the synchronous call in the default executor to avoid blocking
        the asyncio event loop.
        """
        func_name = getattr(func, '__name__', str(func))
        logger.info(f"[desktop_env][TRACE] OS CALL: {func_name} args={args} kwargs={kwargs}")
        if self._is_headless():
            logger.error(f"[desktop_env][TRACE] OS CALL BLOCKED: headless environment")
            return ToolOutput(
                success=False,
                error="Desktop automation unavailable: running headless (no display detected)",
            )
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: func(*args, **kwargs),
            )
            logger.info(f"[desktop_env][TRACE] OS CALL SUCCESS: {func_name} returned={result}")
            return ToolOutput(
                success=True,
                result=result if default_result is None else default_result,
                visibility=visibility,
            )
        except Exception as e:
            logger.error(
                f"[desktop_env][TRACE] OS CALL FAILED: {func_name} error={e}"
            )
            logger.error(
                f"DesktopSession[{self.task_id}]: {func_name} failed: {e}"
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
        """Wait for UI to stabilize using screenshot comparison."""
        stable, _ = await self._stabilizer.wait_for_ui_stability(
            screenshot_fn=self.screenshot,
            max_wait=timeout,
            poll_interval=poll_interval,
        )
        if not stable:
            logger.warning(f"DesktopSession[{self.task_id}]: UI did not stabilize within {timeout}s")

    async def _get_current_tree_hash(self) -> str:
        """Get tree hash without rebuilding the whole tree if possible."""
        if self._last_tree_hash is not None:
            return self._last_tree_hash
        # Fallback: rebuild
        tree = self._build_ui_tree_windows()
        return self._compute_tree_hash(tree)

    def _get_element_map_copy(self) -> Dict[int, Dict[str, Any]]:
        """Return a shallow copy of the current element map."""
        return dict(self._ui_element_map)

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
        """Linux desktop automation is not supported in V1."""
        logger.warning(
            f"DesktopSession[{self.task_id}]: Linux desktop automation is not supported. "
            "AgentOS V1 desktop environment supports Windows only."
        )
        return []

    def _build_ui_tree_darwin(self) -> List[Dict[str, Any]]:
        """macOS desktop automation is not supported in V1."""
        logger.warning(
            f"DesktopSession[{self.task_id}]: macOS desktop automation is not supported. "
            "AgentOS V1 desktop environment supports Windows only."
        )
        return []

    def _compute_tree_hash(self, tree: List[Dict[str, Any]]) -> str:
        """Compute a simple hash of the tree for sync detection."""
        canonical = json.dumps(tree, sort_keys=True, ensure_ascii=True)
        return hashlib.md5(canonical.encode("utf-8")).hexdigest()

    async def _vision_fallback(self) -> ToolOutput:
        """Real vision fallback: screenshot → vision parser → structured elements.

        Populates ``_ui_element_map`` so ``click_element``, ``type_element``,
        etc. work transparently whether elements came from UIA or vision.
        """
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
        if not screenshot_path:
            return ToolOutput(
                success=False,
                error="Vision fallback failed: no screenshot path returned",
            )

        parser = get_vision_parser()
        detected = parser.parse_screenshot(screenshot_path)

        if not detected:
            logger.warning(
                f"DesktopSession[{self.task_id}]: vision fallback detected 0 elements. "
                "Agent may be blind for this screen."
            )
            return ToolOutput(
                success=True,
                result={
                    "mode": "vision_fallback",
                    "screenshot_path": screenshot_path,
                    "tree": [],
                    "count": 0,
                    "actionable_count": 0,
                    "note": "Vision fallback active but no actionable elements were detected.",
                },
                visibility={"type": "vision_fallback", "screenshot_path": screenshot_path, "count": 0},
            )

        # Populate element map so existing tools work transparently
        tree: List[Dict[str, Any]] = []
        for elem in detected:
            self._ui_element_map[elem.id] = elem.to_element_map_entry()
            tree.append(elem.to_tree_node())

        actionable_count = sum(
            1 for node in tree
            if self._is_interactive_type(node.get("type", ""))
        )

        logger.info(
            f"DesktopSession[{self.task_id}]: vision fallback detected {len(detected)} elements "
            f"({actionable_count} actionable) from {screenshot_path}"
        )

        return ToolOutput(
            success=True,
            result={
                "mode": "vision_fallback",
                "screenshot_path": screenshot_path,
                "tree": tree,
                "count": len(tree),
                "actionable_count": actionable_count,
            },
            visibility={
                "type": "vision_fallback",
                "screenshot_path": screenshot_path,
                "count": len(tree),
            },
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
                return await self._vision_fallback()

            return ToolOutput(
                success=True,
                result=result_payload,
                visibility={"type": "desktop_ui_tree", "count": len(tree)},
            )
        except Exception as e:
            logger.error(
                f"DesktopSession[{self.task_id}]: get_ui_tree failed: {e}. "
                "Attempting vision fallback."
            )
            return await self._vision_fallback()

    async def click_element(self, element_id: int, verify: bool = True, stabilize: bool = True) -> ToolOutput:
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

        async def _action():
            return await self._safe_call(
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

        result, snapshot = await self._stabilizer.execute_with_retry(
            action_name="click_element",
            action_fn=_action,
            params={"element_id": element_id, "x": x, "y": y},
            screenshot_fn=self.screenshot,
            tree_hash_fn=self._get_current_tree_hash,
            window_list_fn=self.get_window_list,
            element_map_fn=self._get_element_map_copy,
            selected_target=meta,
            verify=verify,
            stabilize=stabilize,
        )
        self._stabilizer.add_snapshot(snapshot)
        self._last_tree_hash = None

        # Post-action: if no state change, warn but still return result
        if snapshot.verification_result and not snapshot.verification_result.get("changed"):
            if isinstance(result, ToolOutput):
                result.result = result.result or {}
                if isinstance(result.result, dict):
                    result.result["warning"] = "No UI state change detected after click"

        return result if result is not None else ToolOutput(success=False, error="Action failed")

    async def type_element(self, element_id: int, text: str, verify: bool = True, stabilize: bool = True) -> ToolOutput:
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
        x = y = None
        if center:
            x, y = center
            error = self._validate_coords(x, y)
            if error:
                return ToolOutput(success=False, error=error)

        async def _action():
            if center and x is not None and y is not None:
                click_result = await self._safe_call(
                    pyautogui.click,
                    x,
                    y,
                    default_result={"message": f"Focused element {element_id}"},
                )
                if not click_result.success:
                    return click_result
            return await self._safe_call(
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

        result, snapshot = await self._stabilizer.execute_with_retry(
            action_name="type_element",
            action_fn=_action,
            params={"element_id": element_id, "text": text},
            screenshot_fn=self.screenshot,
            tree_hash_fn=self._get_current_tree_hash,
            window_list_fn=self.get_window_list,
            element_map_fn=self._get_element_map_copy,
            selected_target=meta,
            verify=verify,
            stabilize=stabilize,
        )
        self._stabilizer.add_snapshot(snapshot)
        self._last_tree_hash = None
        return result if result is not None else ToolOutput(success=False, error="Action failed")

    async def focus_and_interact(self, element_id: int, key: str = "enter", verify: bool = True, stabilize: bool = True) -> ToolOutput:
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
        x = y = None
        if center:
            x, y = center
            error = self._validate_coords(x, y)
            if error:
                return ToolOutput(success=False, error=error)

        async def _action():
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
                if center and x is not None and y is not None:
                    click_result = await self._safe_call(
                        pyautogui.click,
                        x,
                        y,
                        default_result={"message": f"Focused element {element_id} via click"},
                    )
                    if not click_result.success:
                        return click_result
            _key = key.strip().lower()
            if "+" in _key:
                parts = [p.strip() for p in _key.split("+")]
                return await self._safe_call(
                    pyautogui.hotkey,
                    *parts,
                    default_result={"message": f"Pressed hotkey {_key} on element {element_id}"},
                    visibility={
                        "type": "desktop_focus_and_interact",
                        "element_id": element_id,
                        "key": _key,
                    },
                )
            else:
                return await self._safe_call(
                    pyautogui.press,
                    _key,
                    default_result={"message": f"Pressed key {_key} on element {element_id}"},
                    visibility={
                        "type": "desktop_focus_and_interact",
                        "element_id": element_id,
                        "key": _key,
                    },
                )

        result, snapshot = await self._stabilizer.execute_with_retry(
            action_name="focus_and_interact",
            action_fn=_action,
            params={"element_id": element_id, "key": key},
            screenshot_fn=self.screenshot,
            tree_hash_fn=self._get_current_tree_hash,
            window_list_fn=self.get_window_list,
            element_map_fn=self._get_element_map_copy,
            selected_target=meta,
            verify=verify,
            stabilize=stabilize,
        )
        self._stabilizer.add_snapshot(snapshot)
        self._last_tree_hash = None
        return result if result is not None else ToolOutput(success=False, error="Action failed")

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
            with mss.MSS() as sct:
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

    async def click(self, x: int, y: int, verify: bool = True, stabilize: bool = True) -> ToolOutput:
        logger.info(f"[desktop_env][TRACE] click CALLED: x={x} y={y} headless={self._is_headless()}")
        if self._is_headless():
            return ToolOutput(
                success=False,
                error="Desktop automation unavailable: running headless (no display detected)",
            )
        if pyautogui is None:
            logger.error(f"[desktop_env][TRACE] click ABORTED: pyautogui is None")
            return ToolOutput(
                success=False, error="Input automation library (pyautogui) not available"
            )
        error = self._validate_coords(x, y)
        if error:
            logger.error(f"[desktop_env][TRACE] click ABORTED: {error}")
            return ToolOutput(success=False, error=error)

        async def _action():
            return await self._safe_call(
                pyautogui.click,
                x,
                y,
                default_result={"message": f"Clicked at ({x}, {y})"},
                visibility={"type": "desktop_click", "x": x, "y": y},
            )

        result, snapshot = await self._stabilizer.execute_with_retry(
            action_name="click",
            action_fn=_action,
            params={"x": x, "y": y},
            screenshot_fn=self.screenshot,
            tree_hash_fn=self._get_current_tree_hash,
            window_list_fn=self.get_window_list,
            element_map_fn=self._get_element_map_copy,
            selected_target={"x": x, "y": y},
            verify=verify,
            stabilize=stabilize,
        )
        self._stabilizer.add_snapshot(snapshot)
        self._last_tree_hash = None
        logger.info(f"[desktop_env][TRACE] click RESULT: success={result.success if result else False}")
        return result if result is not None else ToolOutput(success=False, error="Action failed")

    def get_snapshot_history(self) -> List[Dict[str, Any]]:
        """Return action snapshots for debugging."""
        return [self._snapshot_to_dict(s) for s in self._stabilizer.get_snapshot_history()]

    @staticmethod
    def _snapshot_to_dict(snapshot: Any) -> Dict[str, Any]:
        """Convert ActionSnapshot to plain dict."""
        return {
            "timestamp": snapshot.timestamp,
            "action_name": snapshot.action_name,
            "params": snapshot.params,
            "before_screenshot_path": snapshot.before_screenshot_path,
            "after_screenshot_path": snapshot.after_screenshot_path,
            "before_tree_hash": snapshot.before_tree_hash,
            "after_tree_hash": snapshot.after_tree_hash,
            "verification_result": snapshot.verification_result,
            "retry_count": snapshot.retry_count,
            "error": snapshot.error,
        }

    async def type_text(self, text: str, interval: float = 0.01) -> ToolOutput:
        logger.info(f"[desktop_env][TRACE] type_text CALLED: text_len={len(text)} interval={interval} headless={self._is_headless()}")
        if pyautogui is None:
            logger.error(f"[desktop_env][TRACE] type_text ABORTED: pyautogui is None")
            return ToolOutput(
                success=False, error="Input automation library (pyautogui) not available"
            )
        result = await self._safe_call(
            pyautogui.typewrite,
            text,
            interval=interval,
            default_result={"message": f"Typed text (length {len(text)})"},
            visibility={"type": "desktop_type", "text_length": len(text)},
        )
        logger.info(f"[desktop_env][TRACE] type_text RESULT: success={result.success} result={result.result} error={result.error}")
        await self._sync_wait()
        self._last_tree_hash = None
        return result

    async def press_key(self, keys: str) -> ToolOutput:
        """Press a key or key combination.

        Examples: 'enter', 'ctrl+c', 'alt+f4'
        """
        logger.info(f"[desktop_env][TRACE] press_key CALLED: keys='{keys}' headless={self._is_headless()}")
        if pyautogui is None:
            logger.error(f"[desktop_env][TRACE] press_key ABORTED: pyautogui is None")
            return ToolOutput(
                success=False, error="Input automation library (pyautogui) not available"
            )
        keys = keys.strip().lower()
        if "+" in keys:
            parts = [p.strip() for p in keys.split("+")]
            logger.info(f"[desktop_env][TRACE] press_key EXECUTING HOTKEY: parts={parts}")
            result = await self._safe_call(
                pyautogui.hotkey,
                *parts,
                default_result={"message": f"Pressed hotkey {keys}"},
                visibility={"type": "desktop_key", "keys": keys},
            )
        else:
            logger.info(f"[desktop_env][TRACE] press_key EXECUTING: key='{keys}'")
            result = await self._safe_call(
                pyautogui.press,
                keys,
                default_result={"message": f"Pressed key {keys}"},
                visibility={"type": "desktop_key", "keys": keys},
            )
        logger.info(f"[desktop_env][TRACE] press_key RESULT: success={result.success} result={result.result} error={result.error}")
        await self._sync_wait()
        self._last_tree_hash = None
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
        """Focus a window by title. Delegates to ensure_focus for robust focusing."""
        return await self.ensure_focus(title=title)

    async def dismiss_any_popup(self) -> ToolOutput:
        """Detect and dismiss any popup/modal window.

        Uses ActionStabilizer.dismiss_popup() with the session's screenshot/click/key methods.
        """
        # Lazy import — avoid circular issues
        from .execution_stabilizer import ActionStabilizer

        async def _screenshot_fn(path: Optional[str] = None) -> Any:
            result = await self.screenshot(path)
            return result

        async def _click_fn(x: int, y: int) -> Any:
            return await self.click(x, y, verify=False, stabilize=False)

        async def _press_key_fn(keys: str) -> Any:
            return await self.press_key(keys)

        result = await self._stabilizer.dismiss_popup(
            screenshot_fn=_screenshot_fn,
            click_fn=_click_fn,
            press_key_fn=_press_key_fn,
        )

        # Re-verify popup is actually gone
        if result.get("dismissed"):
            remaining = await self._stabilizer.detect_popup_window(
                window_list_fn=lambda: self._get_window_list_for_stabilizer()
            )
            if remaining:
                logger.warning(
                    f"DesktopSession[{self.task_id}]: popup dismissal reported success "
                    f"but popup still detected: {remaining.get('title')}"
                )
                result["dismissed"] = False
                result["method"] = f"{result['method']}_failed_verify"

        return ToolOutput(
            success=result.get("dismissed", False),
            result={"dismissed": result.get("dismissed", False), "method": result.get("method", "none")},
            visibility={"type": "desktop_dismiss_popup", "dismissed": result.get("dismissed", False)},
        )

    async def _get_window_list_for_stabilizer(self) -> List[Dict[str, Any]]:
        """Get window list in the format expected by ActionStabilizer.detect_popup_window."""
        result = await self.get_window_list()
        if result.success and isinstance(result.result, dict):
            return result.result.get("windows", [])
        return []

    async def ensure_focus(
        self,
        window_ref_id: Optional[str] = None,
        title: Optional[str] = None,
    ) -> ToolOutput:
        """Robust window focus with Windows focus-stealing bypass, registry lookup, and verification.

        Either window_ref_id or title must be provided.
        """
        if window_ref_id is None and title is None:
            return ToolOutput(
                success=False,
                error="Either window_ref_id or title must be provided",
            )
        if self._is_headless():
            return ToolOutput(
                success=False,
                error="Desktop automation unavailable: running headless (no display detected)",
            )

        # --- Dismiss any blocking popup before focus attempt ---
        try:
            dismiss_result = await self.dismiss_any_popup()
            if dismiss_result.success and dismiss_result.result.get("dismissed"):
                logger.info(
                    f"DesktopSession[{self.task_id}]: dismissed blocking popup "
                    f"before focus attempt (method={dismiss_result.result.get('method')})"
                )
        except Exception as e:
            logger.debug(
                f"DesktopSession[{self.task_id}]: popup dismissal before focus failed: {e}"
            )

        # --- Resolve window reference ---
        hwnd: Optional[int] = None
        win_obj = None  # pygetwindow window object
        resolved_title: Optional[str] = None

        # 1. Try WindowRegistry lookup by ref_id
        if window_ref_id and self._window_registry is not None:
            entry = self._window_registry.get(window_ref_id)
            if entry:
                hwnd = getattr(entry, "hwnd", None) or getattr(entry, "handle", None)
                resolved_title = getattr(entry, "title", None)
                # Check if entry is stale
                if getattr(entry, "is_alive", True) is False:
                    # Try to recover
                    try:
                        recover_fn = getattr(self._window_registry, "recover", None)
                        if recover_fn:
                            await recover_fn(window_ref_id)
                            entry = self._window_registry.get(window_ref_id)
                            if entry:
                                hwnd = getattr(entry, "hwnd", None) or getattr(entry, "handle", None)
                                resolved_title = getattr(entry, "title", None)
                    except Exception as e:
                        logger.debug(f"DesktopSession[{self.task_id}]: window registry recover failed: {e}")

        # 2. Try WindowRegistry lookup by title
        if hwnd is None and title and self._window_registry is not None:
            try:
                find_fn = getattr(self._window_registry, "find_by_title", None)
                if find_fn:
                    entry = find_fn(title)
                    if entry:
                        hwnd = getattr(entry, "hwnd", None) or getattr(entry, "handle", None)
                        resolved_title = getattr(entry, "title", title)
            except Exception as e:
                logger.debug(f"DesktopSession[{self.task_id}]: registry find_by_title failed: {e}")

        # 3. Fall back to pygetwindow search
        if hwnd is None and gw is not None:
            search_title = title or resolved_title
            if search_title:
                matches = gw.getWindowsWithTitle(search_title)
                if matches:
                    win_obj = matches[0]
                    resolved_title = win_obj.title
                    # Try to get hwnd from pygetwindow
                    hwnd = getattr(win_obj, "_hWnd", None)

        if hwnd is None and win_obj is None:
            return ToolOutput(
                success=False,
                error=f"No window found for ref_id={window_ref_id!r}, title={title!r}",
            )

        # --- Focus attempt with retries ---
        max_retries = 3
        last_error: Optional[str] = None

        for attempt in range(max_retries):
            try:
                focused = False

                if sys.platform == "win32" and hwnd is not None:
                    focused = await self._focus_window_windows(hwnd)
                elif win_obj is not None and hasattr(win_obj, "activate"):
                    win_obj.activate()
                    await asyncio.sleep(0.2)
                    # Verify
                    if sys.platform == "win32":
                        focused = await self._verify_foreground_window(hwnd)
                    else:
                        focused = True

                if focused:
                    logger.info(
                        f"DesktopSession[{self.task_id}]: successfully focused window "
                        f"'{resolved_title}' on attempt {attempt + 1}"
                    )
                    # Register in WindowRegistry if not already there
                    if self._window_registry is not None and window_ref_id is None:
                        try:
                            register_fn = getattr(self._window_registry, "register", None)
                            if register_fn:
                                register_fn(resolved_title, hwnd=hwnd)
                        except Exception as e:
                            logger.debug(f"DesktopSession[{self.task_id}]: registry register failed: {e}")

                    # Save checkpoint if orchestrator available
                    try:
                        orch = await self.get_orchestrator()
                        save_fn = getattr(orch, "save_checkpoint", None)
                        if save_fn:
                            await save_fn({"action": "focus_window", "title": resolved_title})
                    except Exception as e:
                        logger.debug(f"DesktopSession[{self.task_id}]: checkpoint save failed: {e}")

                    self._last_tree_hash = None
                    return ToolOutput(
                        success=True,
                        result={
                            "message": f"Focused window: {resolved_title}",
                            "attempts": attempt + 1,
                            "hwnd": hwnd,
                        },
                        visibility={"type": "desktop_focus", "title": resolved_title},
                    )

                last_error = "Focus verification failed"
                logger.debug(
                    f"DesktopSession[{self.task_id}]: focus attempt {attempt + 1} failed, retrying..."
                )
                await asyncio.sleep(0.5)

            except Exception as e:
                last_error = str(e)
                logger.debug(
                    f"DesktopSession[{self.task_id}]: focus attempt {attempt + 1} error: {e}"
                )
                await asyncio.sleep(0.5)

        self._last_tree_hash = None
        return ToolOutput(
            success=False,
            error=f"Failed to focus window after {max_retries} attempts: {last_error}",
        )

    async def _focus_window_windows(self, hwnd: int) -> bool:
        """Focus a window on Windows using ctypes with focus-stealing bypass.

        Returns True if focus was successfully verified.
        """
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.WinDLL("user32", use_last_error=True)

            # Step 1: Press and release ALT key to give process foreground permission
            if pyautogui is not None:
                pyautogui.keyDown("alt")
                pyautogui.keyUp("alt")
                await asyncio.sleep(0.05)

            # Step 2: AllowSetForegroundWindow (ASFW_ANY = -1)
            ASFW_ANY = -1
            user32.AllowSetForegroundWindow(ASFW_ANY)
            await asyncio.sleep(0.05)

            # Step 3: Bring window to top and set foreground
            user32.BringWindowToTop(hwnd)
            await asyncio.sleep(0.05)
            result = user32.SetForegroundWindow(hwnd)

            if not result:
                # Attach thread input for stubborn windows
                # This is a well-known Windows trick for focus stealing
                if hasattr(user32, "AttachThreadInput"):
                    try:
                        fg_hwnd = user32.GetForegroundWindow()
                        if fg_hwnd and fg_hwnd != hwnd:
                            FG_THREAD_ID = user32.GetWindowThreadProcessId(fg_hwnd, None)
                            TARGET_THREAD_ID = user32.GetWindowThreadProcessId(hwnd, None)
                            if FG_THREAD_ID and TARGET_THREAD_ID and FG_THREAD_ID != TARGET_THREAD_ID:
                                user32.AttachThreadInput(FG_THREAD_ID, TARGET_THREAD_ID, True)
                                user32.SetForegroundWindow(hwnd)
                                user32.AttachThreadInput(FG_THREAD_ID, TARGET_THREAD_ID, False)
                                logger.debug(
                                    f"DesktopSession[{self.task_id}]: used AttachThreadInput "
                                    f"trick for focus (fg_thread={FG_THREAD_ID}, target_thread={TARGET_THREAD_ID})"
                                )
                                result = True
                    except Exception as e:
                        logger.debug(
                            f"DesktopSession[{self.task_id}]: AttachThreadInput failed: {e}"
                        )
                else:
                    logger.debug(
                        f"DesktopSession[{self.task_id}]: SetForegroundWindow returned 0, "
                        f"last_error={ctypes.get_last_error()}"
                    )

            # Step 4: Verify foreground window
            await asyncio.sleep(0.1)
            return await self._verify_foreground_window(hwnd)

        except Exception as e:
            logger.debug(
                f"DesktopSession[{self.task_id}]: ctypes focus failed: {e}, "
                "falling back to pygetwindow"
            )
            # Fallback to pygetwindow
            if gw is not None:
                matches = gw.getAllWindows()
                for w in matches:
                    if getattr(w, "_hWnd", None) == hwnd and hasattr(w, "activate"):
                        w.activate()
                        await asyncio.sleep(0.2)
                        return True
            return False

    async def _verify_foreground_window(self, hwnd: Optional[int]) -> bool:
        """Verify that the given hwnd is the current foreground window."""
        if hwnd is None:
            return False
        try:
            import ctypes

            user32 = ctypes.WinDLL("user32", use_last_error=True)
            fg_hwnd = user32.GetForegroundWindow()
            is_foreground = fg_hwnd == hwnd
            if not is_foreground:
                logger.debug(
                    f"DesktopSession[{self.task_id}]: foreground verification failed: "
                    f"expected {hwnd}, got {fg_hwnd}"
                )
            return is_foreground
        except Exception as e:
            logger.debug(f"DesktopSession[{self.task_id}]: verify foreground failed: {e}")
            return False

    async def launch_app_and_open_file(
        self,
        file_path: str,
        app_name: Optional[str] = None,
    ) -> ToolOutput:
        """Open a file in its associated application or a specific app, without clipboard.

        On Windows, uses os.startfile() for file association.
        If app_name specified, uses subprocess to launch the app with the file.
        Waits for the app window to appear and registers it.
        """
        if not os.path.exists(file_path):
            return ToolOutput(
                success=False,
                error=f"File not found: {file_path}",
            )

        abs_path = os.path.abspath(file_path)
        process = None

        try:
            if app_name:
                process = subprocess.Popen([app_name, abs_path])
            else:
                if sys.platform == "win32":
                    os.startfile(abs_path)
                elif sys.platform == "darwin":
                    process = subprocess.Popen(["open", abs_path])
                elif sys.platform.startswith("linux"):
                    process = subprocess.Popen(["xdg-open", abs_path])
                else:
                    return ToolOutput(
                        success=False,
                        error=f"File opening not supported on platform: {sys.platform}",
                    )

            # Poll for new window (up to 8 seconds)
            window_info = await self._wait_for_new_window(abs_path, process=process, timeout=8.0)

            if window_info:
                # Register in WindowRegistry
                if self._window_registry is not None:
                    try:
                        register_fn = getattr(self._window_registry, "register", None)
                        if register_fn:
                            ref_id = register_fn(
                                window_info.get("title", ""),
                                hwnd=window_info.get("hwnd"),
                                file_path=abs_path,
                            )
                            window_info["ref_id"] = ref_id
                    except Exception as e:
                        logger.debug(
                            f"DesktopSession[{self.task_id}]: registry register failed: {e}"
                        )

                return ToolOutput(
                    success=True,
                    result={
                        "message": f"Opened file in application: {window_info.get('title', 'unknown')}",
                        "file_path": abs_path,
                        "window": window_info,
                    },
                    visibility={
                        "type": "desktop_launch_app",
                        "file_path": abs_path,
                        "window_title": window_info.get("title"),
                    },
                )
            else:
                return ToolOutput(
                    success=True,
                    result={
                        "message": f"Launched file (no window detected): {abs_path}",
                        "file_path": abs_path,
                        "note": "Application launched but no window was detected within timeout.",
                    },
                    visibility={"type": "desktop_launch_app", "file_path": abs_path},
                )

        except Exception as e:
            logger.error(f"DesktopSession[{self.task_id}]: launch_app_and_open_file failed: {e}")
            return ToolOutput(success=False, error=str(e))

    async def _wait_for_new_window(
        self,
        file_path: str,
        process: Optional[subprocess.Popen] = None,
        timeout: float = 8.0,
        poll_interval: float = 0.5,
    ) -> Optional[Dict[str, Any]]:
        """Poll window list for a new window related to the launched file.

        Includes safety improvements:
        - Detect if the subprocess/command failed (process terminated before window appeared)
        - Detect partial window (title exists but window rect is 0x0 — window not ready)
        - Early-exit if the subprocess returns non-zero
        - Cap total wait time more strictly
        - After each poll, if the window is found but not visible/minimized, wait longer
        """
        if gw is None:
            return None

        # Capture existing window titles before launch
        existing_titles: set = set()
        try:
            for w in gw.getAllWindows():
                if w.title:
                    existing_titles.add(w.title)
        except Exception:
            pass

        file_basename = os.path.basename(file_path).lower()
        strict_deadline = asyncio.get_event_loop().time() + min(timeout, 12.0)

        while asyncio.get_event_loop().time() < strict_deadline:
            # Early-exit: check if subprocess terminated with non-zero
            if process is not None:
                retcode = process.poll()
                if retcode is not None:
                    if retcode != 0:
                        logger.warning(
                            f"DesktopSession[{self.task_id}]: process terminated "
                            f"with exit code {retcode} before window appeared"
                        )
                        return None
                    # retcode == 0 means it exited cleanly — maybe it's a CLI tool
                    # Continue polling briefly but don't wait full timeout
                    strict_deadline = min(
                        strict_deadline,
                        asyncio.get_event_loop().time() + 2.0,
                    )

            await asyncio.sleep(poll_interval)
            try:
                for w in gw.getAllWindows():
                    title = w.title
                    if not title or title in existing_titles:
                        continue
                    # Check if window title is related to our file
                    title_lower = title.lower()
                    if (
                        file_basename in title_lower
                        or os.path.splitext(file_basename)[0] in title_lower
                    ):
                        hwnd = getattr(w, "_hWnd", None)

                        # Detect partial/incomplete window — rect is 0x0 (not ready)
                        width = getattr(w, "width", 0) or 0
                        height = getattr(w, "height", 0) or 0
                        is_visible = True
                        is_minimized = False
                        try:
                            is_visible = getattr(w, "visible", True)
                            is_minimized = getattr(w, "isMinimized", False)
                        except Exception:
                            pass

                        if width == 0 and height == 0:
                            logger.debug(
                                f"DesktopSession[{self.task_id}]: window '{title}' found "
                                f"but rect is 0x0 — window not ready, waiting longer"
                            )
                            await asyncio.sleep(poll_interval * 2)
                            continue

                        if is_minimized or not is_visible:
                            logger.debug(
                                f"DesktopSession[{self.task_id}]: window '{title}' found "
                                f"but not visible/minimized — waiting longer"
                            )
                            await asyncio.sleep(poll_interval * 2)
                            continue

                        return {
                            "title": title,
                            "hwnd": hwnd,
                            "left": getattr(w, "left", 0),
                            "top": getattr(w, "top", 0),
                            "width": width,
                            "height": height,
                        }
            except Exception as e:
                logger.debug(
                    f"DesktopSession[{self.task_id}]: window poll error: {e}"
                )

        return None

    def get_window_registry(self) -> Optional[Any]:
        """Return the WindowRegistry instance, or None if not available."""
        return self._window_registry

    async def get_orchestrator(self) -> Optional[Any]:
        """Lazy-init and return the MultiAppOrchestrator."""
        if self._orchestrator is None:
            try:
                from .multi_app_orchestrator import MultiAppOrchestrator
                self._orchestrator = MultiAppOrchestrator(self.task_id)
            except ImportError:
                logger.debug(
                    f"DesktopSession[{self.task_id}]: MultiAppOrchestrator not available"
                )
                return None
        return self._orchestrator

    async def get_clipboard(self) -> ToolOutput:
        if pyperclip is None:
            return ToolOutput(
                success=False, error="Clipboard library (pyperclip) not available"
            )
        return await self._safe_call(pyperclip.paste)

    async def set_clipboard(self, text: str) -> ToolOutput:
        if pyperclip is None:
            return ToolOutput(
                success=False, error="Clipboard library (pyperclip) not available"
            )
        return await self._safe_call(
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

        return await self._safe_call(_get_pos)

    async def scroll(self, amount: int) -> ToolOutput:
        if pyautogui is None:
            return ToolOutput(
                success=False, error="Input automation library (pyautogui) not available"
            )
        result = await self._safe_call(
            pyautogui.scroll,
            amount,
            default_result={"message": f"Scrolled {amount}"},
            visibility={"type": "desktop_scroll", "amount": amount},
        )
        await self._sync_wait()
        self._last_tree_hash = None
        return result

    async def close(self) -> ToolOutput:
        self._stabilizer.clear_history()
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
