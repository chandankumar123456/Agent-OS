"""Desktop Environment — native desktop UI automation."""
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


class DesktopSession:
    """A single desktop automation session scoped to one task."""

    def __init__(self, task_id: str):
        self.task_id = task_id
        self._screen_size: Tuple[int, int] = (0, 0)
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
        return self._safe_call(
            pyautogui.click,
            x,
            y,
            default_result={"message": f"Clicked at ({x}, {y})"},
        )

    async def type_text(self, text: str, interval: float = 0.01) -> ToolOutput:
        if pyautogui is None:
            return ToolOutput(
                success=False, error="Input automation library (pyautogui) not available"
            )
        return self._safe_call(
            pyautogui.typewrite,
            text,
            interval=interval,
            default_result={"message": f"Typed text (length {len(text)})"},
        )

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
            return self._safe_call(
                pyautogui.hotkey,
                *parts,
                default_result={"message": f"Pressed hotkey {keys}"},
            )
        else:
            return self._safe_call(
                pyautogui.press,
                keys,
                default_result={"message": f"Pressed key {keys}"},
            )

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
                return ToolOutput(
                    success=True,
                    result={"message": f"Focused window: {win.title}"},
                )
            elif sys.platform.startswith("linux"):
                result = subprocess.run(
                    ["wmctrl", "-a", title],
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0:
                    return ToolOutput(
                        success=True,
                        result={"message": f"Focused window: {title}"},
                    )
                result = subprocess.run(
                    ["xdotool", "search", "--name", title, "windowactivate"],
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0:
                    return ToolOutput(
                        success=True,
                        result={"message": f"Focused window: {title}"},
                    )
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
                    return ToolOutput(
                        success=True,
                        result={"message": f"Focused window: {title}"},
                    )
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
        return self._safe_call(
            pyautogui.scroll,
            amount,
            default_result={"message": f"Scrolled {amount}"},
        )

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
