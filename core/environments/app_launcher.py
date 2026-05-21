"""Deterministic application launcher for Windows desktop automation.

Provides reliable app launching that:
1. Maps common names to executables
2. Discovers installed apps via Windows Registry and filesystem
3. Launches via subprocess.Popen or os.startfile
4. Verifies process PID exists after launch
5. Verifies window appears within timeout
6. Falls back to UI automation (Win+R, Start menu typing) if direct launch fails
"""
import asyncio
import logging
import os
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Common app name → executable mappings ───────────────────────────
_APP_NAME_MAP: Dict[str, str] = {
    # Built-in Windows apps
    "notepad": "notepad.exe",
    "calc": "calc.exe",
    "calculator": "calc.exe",
    "mspaint": "mspaint.exe",
    "paint": "mspaint.exe",
    "wordpad": "wordpad.exe",
    "cmd": "cmd.exe",
    "command prompt": "cmd.exe",
    "powershell": "powershell.exe",
    "explorer": "explorer.exe",
    "task manager": "taskmgr.exe",
    "taskmgr": "taskmgr.exe",
    "snipping tool": "SnippingTool.exe",
    "settings": "control.exe",
    "control panel": "control.exe",
    # Browsers
    "chrome": "chrome.exe",
    "google chrome": "chrome.exe",
    "firefox": "firefox.exe",
    "mozilla firefox": "firefox.exe",
    "edge": "msedge.exe",
    "microsoft edge": "msedge.exe",
    "opera": "opera.exe",
    "brave": "brave.exe",
    # IDEs / Editors
    "vscode": "Code.exe",
    "visual studio code": "Code.exe",
    "notepad++": "notepad++.exe",
    "sublime": "sublime_text.exe",
    "sublime text": "sublime_text.exe",
    "pycharm": "pycharm64.exe",
    "intellij": "idea64.exe",
    "eclipse": "eclipse.exe",
    # Communication
    "whatsapp": "WhatsApp.exe",
    "telegram": "Telegram.exe",
    "slack": "slack.exe",
    "teams": "Teams.exe",
    "microsoft teams": "Teams.exe",
    "discord": "Discord.exe",
    "zoom": "Zoom.exe",
    "skype": "Skype.exe",
    # Media
    "vlc": "vlc.exe",
    "spotify": "Spotify.exe",
    "itunes": "iTunes.exe",
    # Office
    "word": "WINWORD.EXE",
    "excel": "EXCEL.EXE",
    "powerpoint": "POWERPNT.EXE",
    "outlook": "OUTLOOK.EXE",
    # Dev tools
    "git bash": "git-bash.exe",
    "docker desktop": "Docker Desktop.exe",
    "postman": "Postman.exe",
    "insomnia": "Insomnia.exe",
}


def _normalize_app_name(app_name: str) -> str:
    """Normalize app name for lookup."""
    normalized = app_name.strip().lower()
    if normalized.endswith(".exe"):
        normalized = normalized[:-4]
    return normalized


def _get_windows_program_files_paths() -> List[str]:
    """Return list of Program Files directories to search."""
    paths = []
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    lpf = os.environ.get("LocalAppData", r"C:\Users\%USERNAME%\AppData\Local")
    # Expand user
    lpf = os.path.expandvars(lpf)
    if os.path.isdir(pf):
        paths.append(pf)
    if os.path.isdir(pf86):
        paths.append(pf86)
    if os.path.isdir(lpf):
        paths.append(lpf)
    return paths


def _search_start_menu(app_name: str) -> Optional[str]:
    """Search Start Menu shortcuts for the app."""
    if sys.platform != "win32":
        return None
    import glob
    start_menu_paths = [
        os.path.expandvars(r"%ProgramData%\Microsoft\Windows\Start Menu\Programs"),
        os.path.expandvars(r"%AppData%\Microsoft\Windows\Start Menu\Programs"),
    ]
    normalized = _normalize_app_name(app_name)
    for base in start_menu_paths:
        if not os.path.isdir(base):
            continue
        # Search for .lnk files matching the app name
        pattern = os.path.join(base, "**", "*.lnk")
        for lnk in glob.glob(pattern, recursive=True):
            basename = os.path.splitext(os.path.basename(lnk))[0].lower()
            if normalized in basename or basename in normalized:
                # Resolve shortcut target (best effort without win32com)
                # For now, return the lnk path itself; Windows can execute it
                return lnk
    return None


def _search_registry_app_paths(app_name: str) -> Optional[str]:
    """Search Windows Registry App Paths for the executable."""
    if sys.platform != "win32":
        return None
    try:
        import winreg
    except ImportError:
        return None

    normalized = _normalize_app_name(app_name)
    executable = _APP_NAME_MAP.get(normalized, app_name)
    if not executable.lower().endswith(".exe"):
        executable += ".exe"

    # Check App Paths registry
    keys_to_check = [
        (winreg.HKEY_LOCAL_MACHINE, "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths\\" + executable),
        (winreg.HKEY_LOCAL_MACHINE, "SOFTWARE\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\App Paths\\" + executable),
        (winreg.HKEY_CURRENT_USER, "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths\\" + executable),
    ]
    for hkey, subkey in keys_to_check:
        try:
            with winreg.OpenKey(hkey, subkey) as key:
                path, _ = winreg.QueryValueEx(key, None)
                if path and os.path.isfile(path):
                    return path
        except Exception:
            continue
    return None


def _search_registry_uninstall(app_name: str) -> Optional[str]:
    """Search Windows Uninstall registry for InstallLocation."""
    if sys.platform != "win32":
        return None
    try:
        import winreg
    except ImportError:
        return None

    normalized = _normalize_app_name(app_name)
    uninstall_keys = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]

    for hkey, subkey in uninstall_keys:
        try:
            with winreg.OpenKey(hkey, subkey) as key:
                for i in range(winreg.QueryInfoKey(key)[0]):
                    try:
                        sub_name = winreg.EnumKey(key, i)
                        with winreg.OpenKey(key, sub_name) as app_key:
                            display_name, _ = winreg.QueryValueEx(app_key, "DisplayName")
                            if normalized in display_name.lower():
                                install_loc, _ = winreg.QueryValueEx(app_key, "InstallLocation")
                                if install_loc and os.path.isdir(install_loc):
                                    # Try to find the main executable
                                    return _find_main_executable(install_loc, normalized)
                    except Exception:
                        continue
        except Exception:
            continue
    return None


def _find_main_executable(directory: str, app_name: str) -> Optional[str]:
    """Find the main executable in a directory, heuristic based on name."""
    import fnmatch
    candidates = []
    for root, _, files in os.walk(directory):
        for f in files:
            if f.lower().endswith(".exe"):
                full = os.path.join(root, f)
                score = 0
                base = f.lower().replace(".exe", "")
                if app_name in base or base in app_name:
                    score += 10
                # Prefer executables in root over deep subdirs
                depth = root.replace(directory, "").count(os.sep)
                score -= depth
                # Penalize helper executables
                if any(x in base for x in ["update", "helper", "crash", "setup", "installer"]):
                    score -= 5
                candidates.append((score, full))
        # Don't walk too deep
        if root.replace(directory, "").count(os.sep) > 3:
            break
    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        best_score, best_path = candidates[0]
        if best_score > 0:
            return best_path
    return None


def _search_common_install_dirs(app_name: str) -> Optional[str]:
    """Search common installation directories for the executable."""
    normalized = _normalize_app_name(app_name)
    executable = _APP_NAME_MAP.get(normalized)
    if not executable:
        executable = app_name if app_name.lower().endswith(".exe") else app_name + ".exe"

    search_dirs = _get_windows_program_files_paths()
    # Add some app-specific known paths
    known_paths = {
        "vscode": [r"Microsoft VS Code\bin\code.cmd", r"Microsoft VS Code\Code.exe"],
        "visual studio code": [r"Microsoft VS Code\bin\code.cmd", r"Microsoft VS Code\Code.exe"],
        "chrome": [r"Google\Chrome\Application\chrome.exe"],
        "google chrome": [r"Google\Chrome\Application\chrome.exe"],
        "edge": [r"Microsoft\Edge\Application\msedge.exe"],
        "microsoft edge": [r"Microsoft\Edge\Application\msedge.exe"],
        "firefox": [r"Mozilla Firefox\firefox.exe"],
        "whatsapp": [r"WhatsApp\WhatsApp.exe"],
        "teams": [r"Microsoft\Teams\current\Teams.exe", r"Microsoft\Teams\Teams.exe"],
        "slack": [r"Slack\slack.exe"],
        "discord": [r"Discord\Discord.exe", r"Discord\app-*\Discord.exe"],
        "spotify": [r"Spotify\Spotify.exe"],
        "vlc": [r"VideoLAN\VLC\vlc.exe"],
        "postman": [r"Postman\Postman.exe"],
    }

    # Check known paths first
    for rel_path in known_paths.get(normalized, []):
        for base_dir in search_dirs:
            full = os.path.join(base_dir, rel_path)
            if "*" in full:
                import glob
                matches = glob.glob(full)
                if matches:
                    return matches[0]
            elif os.path.isfile(full):
                return full

    # Generic search
    for base_dir in search_dirs:
        if not os.path.isdir(base_dir):
            continue
        result = _find_main_executable(base_dir, normalized)
        if result:
            return result

    return None


def resolve_app_path(app_name: str) -> Optional[str]:
    """Resolve an application name to its full executable path.

    Resolution order:
    1. Direct path (if app_name contains backslash or already ends with .exe and exists)
    2. Common name map
    3. Windows Registry App Paths
    4. Windows Registry Uninstall (InstallLocation)
    5. Start Menu shortcuts
    6. Common installation directories (Program Files, LocalAppData)
    7. PATH search via shutil.which
    """
    if not app_name:
        return None

    # 1. If it's already a valid path, use it directly
    if os.path.isfile(app_name):
        return os.path.abspath(app_name)

    normalized = _normalize_app_name(app_name)

    # 2. Common name map
    executable = _APP_NAME_MAP.get(normalized)
    if executable:
        # Try direct launch first (works for built-ins like notepad.exe)
        import shutil
        found = shutil.which(executable)
        if found:
            return found
        # Check if it's an absolute path from the map
        if os.path.isfile(executable):
            return os.path.abspath(executable)

    # 3. Registry App Paths
    reg_path = _search_registry_app_paths(app_name)
    if reg_path:
        return reg_path

    # 4. Registry Uninstall
    uninstall_path = _search_registry_uninstall(app_name)
    if uninstall_path:
        return uninstall_path

    # 5. Start Menu
    start_menu_path = _search_start_menu(app_name)
    if start_menu_path:
        return start_menu_path

    # 6. Common install dirs
    install_path = _search_common_install_dirs(app_name)
    if install_path:
        return install_path

    # 7. PATH search
    import shutil
    search_name = executable or (app_name if app_name.lower().endswith(".exe") else app_name + ".exe")
    found = shutil.which(search_name)
    if found:
        return found

    return None


def is_process_running(process_name: str) -> bool:
    """Check if a process is running by name (Windows: tasklist, Linux/mac: pgrep)."""
    if sys.platform == "win32":
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq {process_name}"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return process_name.lower() in result.stdout.lower()
        except Exception:
            return False
    else:
        try:
            result = subprocess.run(
                ["pgrep", "-f", process_name],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except Exception:
            return False


def _find_window_by_title(title_substring: str, timeout: float = 8.0) -> Optional[Dict[str, Any]]:
    """Poll for a window with title containing the substring."""
    try:
        import pygetwindow as gw
    except Exception:
        return None

    deadline = time.time() + timeout
    poll_interval = 0.3
    existing_titles = set()
    try:
        for w in gw.getAllWindows():
            if w.title:
                existing_titles.add(w.title.lower())
    except Exception:
        pass

    while time.time() < deadline:
        try:
            for w in gw.getAllWindows():
                title = w.title
                if not title:
                    continue
                if title_substring.lower() in title.lower() or title.lower() in existing_titles:
                    continue
                # New window matching our target
                width = getattr(w, "width", 0) or 0
                height = getattr(w, "height", 0) or 0
                if width == 0 and height == 0:
                    time.sleep(poll_interval)
                    continue
                return {
                    "title": title,
                    "hwnd": getattr(w, "_hWnd", None),
                    "left": getattr(w, "left", 0),
                    "top": getattr(w, "top", 0),
                    "width": width,
                    "height": height,
                }
        except Exception:
            pass
        time.sleep(poll_interval)
    return None


class LaunchResult:
    """Result of an application launch attempt."""
    def __init__(
        self,
        success: bool,
        process_path: Optional[str] = None,
        pid: Optional[int] = None,
        window_info: Optional[Dict[str, Any]] = None,
        method: str = "unknown",
        error: Optional[str] = None,
    ):
        self.success = success
        self.process_path = process_path
        self.pid = pid
        self.window_info = window_info or {}
        self.method = method
        self.error = error

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "process_path": self.process_path,
            "pid": self.pid,
            "window": self.window_info,
            "method": self.method,
            "error": self.error,
        }


async def launch_application(
    app_name: str,
    timeout: float = 10.0,
    verify_window: bool = True,
) -> LaunchResult:
    """Launch an application with deterministic verification.

    Flow:
        1. Resolve app path
        2. Try subprocess.Popen() or os.startfile()
        3. Verify process exists
        4. Verify window appears
        5. If failed → fallback to UI automation (Win+R)
        6. Verify again
        7. Fail cleanly if both fail
    """
    logger.info(f"[AppLauncher] Launching '{app_name}'...")

    # ── Step 1: Resolve path ──────────────────────────────────────────
    resolved_path = resolve_app_path(app_name)
    if not resolved_path:
        logger.warning(f"[AppLauncher] Could not resolve path for '{app_name}'")
        return LaunchResult(success=False, error=f"Could not resolve path for '{app_name}'")

    logger.info(f"[AppLauncher] Resolved '{app_name}' -> '{resolved_path}'")

    # ── Step 2: Launch ────────────────────────────────────────────────
    process = None
    launched = False
    method = "direct"

    try:
        if resolved_path.lower().endswith(".lnk"):
            # Windows shortcut
            if sys.platform == "win32":
                os.startfile(resolved_path)
                launched = True
        elif resolved_path.lower().endswith(".exe") or resolved_path.lower().endswith(".cmd") or resolved_path.lower().endswith(".bat"):
            process = subprocess.Popen(
                [resolved_path],
                shell=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            launched = True
        else:
            # Fallback to os.startfile for anything else
            if sys.platform == "win32":
                os.startfile(resolved_path)
                launched = True
            else:
                process = subprocess.Popen([resolved_path])
                launched = True
    except Exception as e:
        logger.warning(f"[AppLauncher] Direct launch failed for '{app_name}': {e}")
        launched = False

    if not launched:
        return await _fallback_ui_launch(app_name, resolved_path, timeout, verify_window)

    # ── Step 3: Verify process ────────────────────────────────────────
    process_name = os.path.basename(resolved_path)
    await asyncio.sleep(0.5)  # Brief yield for process startup
    process_running = is_process_running(process_name)

    if not process_running:
        # Maybe it's a wrapper/launcher that spawns a different process
        # Wait a bit longer and check again
        await asyncio.sleep(1.5)
        process_running = is_process_running(process_name)

    logger.info(f"[AppLauncher] Process verification for '{process_name}': running={process_running}")

    # ── Step 4: Verify window ─────────────────────────────────────────
    window_info = None
    if verify_window:
        # Use the app name (without .exe) as window title hint
        window_hint = _normalize_app_name(app_name)
        window_info = _find_window_by_title(window_hint, timeout=timeout)
        if window_info:
            logger.info(f"[AppLauncher] Window found: {window_info.get('title')}")
        else:
            # Try with executable base name
            window_hint = process_name.replace(".exe", "")
            window_info = _find_window_by_title(window_hint, timeout=timeout * 0.5)

    if process_running or (window_info is not None):
        return LaunchResult(
            success=True,
            process_path=resolved_path,
            pid=process.pid if process else None,
            window_info=window_info or {},
            method=method,
        )

    # ── Step 5: Fallback to UI automation ─────────────────────────────
    logger.warning(f"[AppLauncher] Direct launch succeeded but no process/window verified for '{app_name}'. Trying UI fallback.")
    return await _fallback_ui_launch(app_name, resolved_path, timeout, verify_window)


async def _fallback_ui_launch(
    app_name: str,
    resolved_path: str,
    timeout: float,
    verify_window: bool,
) -> LaunchResult:
    """Fallback: use Win+R or Start menu typing to launch app."""
    if sys.platform != "win32":
        return LaunchResult(success=False, error="UI fallback only supported on Windows")

    try:
        import pyautogui
    except Exception:
        return LaunchResult(success=False, error="pyautogui not available for UI fallback")

    logger.info(f"[AppLauncher] UI fallback: attempting Win+R launch for '{app_name}'")

    # Method A: Win + R → type path → Enter
    try:
        pyautogui.keyDown("win")
        pyautogui.keyDown("r")
        pyautogui.keyUp("r")
        pyautogui.keyUp("win")
        await asyncio.sleep(0.5)

        # Type the path or app name
        if os.path.isfile(resolved_path):
            pyautogui.typewrite(resolved_path, interval=0.01)
        else:
            pyautogui.typewrite(app_name, interval=0.01)
        await asyncio.sleep(0.2)
        pyautogui.keyDown("return")
        pyautogui.keyUp("return")
        await asyncio.sleep(1.0)

        process_name = os.path.basename(resolved_path)
        process_running = is_process_running(process_name)
        window_info = None
        if verify_window:
            window_hint = _normalize_app_name(app_name)
            window_info = _find_window_by_title(window_hint, timeout=timeout)

        if process_running or (window_info is not None):
            logger.info(f"[AppLauncher] UI fallback (Win+R) succeeded for '{app_name}'")
            return LaunchResult(
                success=True,
                process_path=resolved_path,
                window_info=window_info or {},
                method="ui_fallback_winr",
            )
    except Exception as e:
        logger.warning(f"[AppLauncher] Win+R fallback failed: {e}")

    # Method B: Start menu typing
    logger.info(f"[AppLauncher] UI fallback: attempting Start menu typing for '{app_name}'")
    try:
        pyautogui.keyDown("win")
        pyautogui.keyUp("win")
        await asyncio.sleep(0.5)
        pyautogui.typewrite(app_name, interval=0.01)
        await asyncio.sleep(1.0)
        pyautogui.keyDown("return")
        pyautogui.keyUp("return")
        await asyncio.sleep(1.5)

        process_name = os.path.basename(resolved_path)
        process_running = is_process_running(process_name)
        window_info = None
        if verify_window:
            window_hint = _normalize_app_name(app_name)
            window_info = _find_window_by_title(window_hint, timeout=timeout)

        if process_running or (window_info is not None):
            logger.info(f"[AppLauncher] UI fallback (Start menu) succeeded for '{app_name}'")
            return LaunchResult(
                success=True,
                process_path=resolved_path,
                window_info=window_info or {},
                method="ui_fallback_startmenu",
            )
    except Exception as e:
        logger.warning(f"[AppLauncher] Start menu fallback failed: {e}")

    return LaunchResult(
        success=False,
        error=f"All launch methods failed for '{app_name}'",
    )
