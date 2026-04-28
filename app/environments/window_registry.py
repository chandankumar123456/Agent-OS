"""WindowRef registry — persistent window references for multi-app workflows.

Phase 5: Tracks window handles, PIDs, and titles across sessions so that
focus_window() and other automation tools can recover from stale references
instead of re-scanning by title substring every time.

All OS-specific imports (ctypes, psutil, pygetwindow, pyautogui) are lazy
and optional — the module degrades gracefully when they are unavailable.
"""

from __future__ import annotations

import importlib
import platform
import sys
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Lazy-import helpers
# ---------------------------------------------------------------------------

def _lazy_ctypes() -> Optional[Any]:
    """Return the ctypes module or None."""
    try:
        return importlib.import_module("ctypes")
    except Exception:
        return None


def _lazy_psutil() -> Optional[Any]:
    """Return the psutil module or None."""
    try:
        return importlib.import_module("psutil")
    except Exception:
        return None


def _lazy_pygetwindow() -> Optional[Any]:
    """Return pygetwindow (aliased as gw) or None."""
    try:
        return importlib.import_module("pygetwindow")
    except Exception:
        return None


def _lazy_pyautogui() -> Optional[Any]:
    """Return pyautogui or None."""
    try:
        return importlib.import_module("pyautogui")
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclass
class WindowRef:
    """Persistent reference to a desktop window."""

    ref_id: str
    """Unique identifier for this reference."""

    hwnd: Optional[int] = None
    """Windows handle (HWND). None on non-Windows or if unknown."""

    pid: Optional[int] = None
    """Owning process ID."""

    process_name: Optional[str] = None
    """Executable name of the owning process."""

    title: str = ""
    """Last known window title."""

    title_patterns: List[str] = field(default_factory=list)
    """Patterns used for fuzzy / recovery matching."""

    registered_at: str = ""
    """ISO-8601 timestamp of registration."""

    last_seen_at: str = ""
    """ISO-8601 timestamp of last successful refresh."""

    is_alive: bool = True
    """Whether the window is still reachable."""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WindowRef":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class WindowRegistry:
    """Dict-based registry keyed by ``ref_id``.

    Provides registration, lookup, refresh, recovery, and serialization
    for persistent window references across multi-app workflows.
    """

    def __init__(self) -> None:
        from ..logs.logger import logger as _logger

        self._logger = _logger
        self._registry: Dict[str, WindowRef] = {}

    # -- public API -----------------------------------------------------------

    def register(
        self,
        title: str,
        hwnd: Optional[int] = None,
        pid: Optional[int] = None,
        process_name: Optional[str] = None,
        title_patterns: Optional[List[str]] = None,
    ) -> WindowRef:
        """Register a window and auto-detect hwnd/pid on Windows.

        Parameters
        ----------
        title : str
            Human-readable title (also used as a default pattern).
        hwnd : int, optional
            Pre-known window handle.
        pid : int, optional
            Pre-known process ID.
        process_name : str, optional
            Pre-known process/executable name.
        title_patterns : list[str], optional
            Additional patterns for fuzzy matching / recovery.

        Returns
        -------
        WindowRef
        """
        ref_id = uuid.uuid4().hex[:12]
        now = datetime.now(timezone.utc).isoformat()

        # Auto-detect on Windows when hwnd/pid not supplied
        if sys.platform == "win32" and (hwnd is None or pid is None):
            hwnd, pid, process_name = self._detect_window_info(
                title, hwnd, pid, process_name
            )

        # Default patterns include the title itself
        patterns = list(title_patterns) if title_patterns else []
        if title and title not in patterns:
            patterns.insert(0, title)

        ref = WindowRef(
            ref_id=ref_id,
            hwnd=hwnd,
            pid=pid,
            process_name=process_name,
            title=title,
            title_patterns=patterns,
            registered_at=now,
            last_seen_at=now,
            is_alive=True,
        )
        self._registry[ref_id] = ref
        self._logger.info(
            f"WindowRegistry: registered ref_id={ref_id} title={title!r} "
            f"hwnd={hwnd} pid={pid}"
        )
        return ref

    def lookup(self, ref_id: str) -> Optional[WindowRef]:
        """Find a window reference by its ``ref_id``."""
        ref = self._registry.get(ref_id)
        if ref:
            self._logger.debug(f"WindowRegistry: lookup ref_id={ref_id} found=True")
        else:
            self._logger.debug(f"WindowRegistry: lookup ref_id={ref_id} found=False")
        return ref

    def find_by_title(self, title_substring: str) -> Optional[WindowRef]:
        """Find a registered window whose current title contains *title_substring*."""
        lower = title_substring.lower()
        for ref in self._registry.values():
            if lower in ref.title.lower():
                self._logger.debug(
                    f"WindowRegistry: find_by_title substring={title_substring!r} "
                    f"matched ref_id={ref.ref_id}"
                )
                return ref
        self._logger.debug(
            f"WindowRegistry: find_by_title substring={title_substring!r} no match"
        )
        return None

    def find_by_pid(self, pid: int) -> Optional[WindowRef]:
        """Find a registered window by process ID."""
        for ref in self._registry.values():
            if ref.pid == pid:
                self._logger.debug(
                    f"WindowRegistry: find_by_pid pid={pid} matched ref_id={ref.ref_id}"
                )
                return ref
        self._logger.debug(f"WindowRegistry: find_by_pid pid={pid} no match")
        return None

    def refresh(self) -> List[WindowRef]:
        """Update all registered windows: check validity, update titles, mark stale.

        Returns a list of refs whose ``is_alive`` status changed.
        """
        changed: List[WindowRef] = []
        for ref in list(self._registry.values()):
            was_alive = ref.is_alive
            self._refresh_single(ref)
            if ref.is_alive != was_alive:
                changed.append(ref)
                self._logger.info(
                    f"WindowRegistry: refresh ref_id={ref.ref_id} "
                    f"is_alive={ref.is_alive} title={ref.title!r}"
                )
        self._logger.info(
            f"WindowRegistry: refresh complete — {len(changed)} refs changed"
        )
        return changed

    def recover(self, ref_id: str) -> Optional[WindowRef]:
        """Try to re-find a stale window by title pattern, PID, or process name.

        On Windows this re-scans all OS windows and re-attaches the hwnd/pid
        if a match is found.  On non-Windows it falls back to pygetwindow.

        Returns the updated ``WindowRef`` or ``None`` if recovery failed.
        """
        ref = self._registry.get(ref_id)
        if ref is None:
            self._logger.warning(
                f"WindowRegistry: recover ref_id={ref_id} not found"
            )
            return None

        self._logger.info(
            f"WindowRegistry: recovering ref_id={ref_id} "
            f"patterns={ref.title_patterns} pid={ref.pid}"
        )

        # Strategy 1: match by PID (most reliable)
        if ref.pid is not None:
            recovered = self._find_by_pid_os(ref.pid)
            if recovered:
                self._apply_recovery(ref, recovered)
                return ref

        # Strategy 2: match by title patterns
        for pattern in ref.title_patterns:
            recovered = self._find_by_title_os(pattern)
            if recovered:
                self._apply_recovery(ref, recovered)
                return ref

        # Strategy 3: match by process name
        if ref.process_name:
            recovered = self._find_by_process_name_os(ref.process_name)
            if recovered:
                self._apply_recovery(ref, recovered)
                return ref

        self._logger.warning(
            f"WindowRegistry: recover ref_id={ref_id} failed — no match found"
        )
        return None

    def mark_stale(self, ref_id: str) -> None:
        """Mark a window reference as no longer alive."""
        ref = self._registry.get(ref_id)
        if ref:
            ref.is_alive = False
            self._logger.info(f"WindowRegistry: marked stale ref_id={ref_id}")
        else:
            self._logger.warning(
                f"WindowRegistry: mark_stale ref_id={ref_id} not found"
            )

    def get_active_window(self) -> Optional[WindowRef]:
        """Return the currently focused/foreground window reference.

        If the foreground window is already registered, returns that ref.
        Otherwise registers a new one and returns it.
        """
        active_hwnd: Optional[int] = None
        active_title: str = ""
        active_pid: Optional[int] = None
        active_proc_name: Optional[str] = None

        if sys.platform == "win32":
            ct = _lazy_ctypes()
            if ct is not None:
                try:
                    user32 = ct.windll.user32
                    kernel32 = ct.windll.kernel32
                    active_hwnd = user32.GetForegroundWindow()
                    if active_hwnd:
                        # Get title length first
                        length = user32.GetWindowTextLengthW(active_hwnd)
                        buf = ct.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(active_hwnd, buf, length + 1)
                        active_title = buf.value or ""

                        # Get PID
                        pid_val = ct.c_ulong()
                        user32.GetWindowThreadProcessId(active_hwnd, ct.byref(pid_val))
                        active_pid = pid_val.value or None
                        if active_pid:
                            ps = _lazy_psutil()
                            if ps is not None:
                                try:
                                    proc = ps.Process(active_pid)
                                    active_proc_name = proc.name()
                                except Exception:
                                    pass
                except Exception as exc:
                    self._logger.warning(
                        f"WindowRegistry: get_active_window ctypes error: {exc}"
                    )

            # Fallback to pygetwindow if ctypes didn't yield a title
            if not active_title:
                gw = _lazy_pygetwindow()
                if gw is not None:
                    try:
                        aw = gw.getActiveWindow()
                        if aw:
                            active_title = aw.title or ""
                            active_hwnd = active_hwnd or getattr(aw, "_hWnd", None)
                    except Exception:
                        pass
        else:
            # Non-Windows: pygetwindow fallback
            gw = _lazy_pygetwindow()
            if gw is not None:
                try:
                    aw = gw.getActiveWindow()
                    if aw:
                        active_title = aw.title or ""
                except Exception:
                    pass

        if not active_title and active_hwnd is None:
            self._logger.warning("WindowRegistry: get_active_window — no active window detected")
            return None

        # Check if already registered
        for ref in self._registry.values():
            if active_hwnd and ref.hwnd == active_hwnd:
                ref.title = active_title
                ref.last_seen_at = datetime.now(timezone.utc).isoformat()
                ref.is_alive = True
                self._logger.debug(
                    f"WindowRegistry: get_active_window reusing ref_id={ref.ref_id}"
                )
                return ref
            if active_pid and ref.pid == active_pid:
                ref.title = active_title
                ref.last_seen_at = datetime.now(timezone.utc).isoformat()
                ref.is_alive = True
                self._logger.debug(
                    f"WindowRegistry: get_active_window reusing ref_id={ref.ref_id}"
                )
                return ref

        # Register as new
        return self.register(
            title=active_title,
            hwnd=active_hwnd,
            pid=active_pid,
            process_name=active_proc_name,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the entire registry to a plain dict."""
        return {
            ref_id: ref.to_dict() for ref_id, ref in self._registry.items()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WindowRegistry":
        """Deserialize a registry from a plain dict."""
        registry = cls()
        for ref_id, ref_data in data.items():
            ref = WindowRef.from_dict(ref_data)
            # Ensure ref_id matches the key
            ref.ref_id = ref_id
            registry._registry[ref_id] = ref
        return registry

    # -- internal helpers -----------------------------------------------------

    def _detect_window_info(
        self,
        title: str,
        hwnd: Optional[int],
        pid: Optional[int],
        process_name: Optional[str],
    ) -> tuple[Optional[int], Optional[int], Optional[str]]:
        """Auto-detect hwnd/pid/process_name on Windows via ctypes + pygetwindow."""
        if sys.platform != "win32":
            return hwnd, pid, process_name

        ct = _lazy_ctypes()
        if ct is not None:
            try:
                user32 = ct.windll.user32
                # Enumerate all windows looking for a title match
                matches: List[tuple] = []

                def enum_proc(h: int, _l: int) -> int:
                    length = user32.GetWindowTextLengthW(h)
                    if length > 0:
                        buf = ct.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(h, buf, length + 1)
                        w_title = buf.value or ""
                        if title.lower() in w_title.lower():
                            pid_val = ct.c_ulong()
                            user32.GetWindowThreadProcessId(h, ct.byref(pid_val))
                            matches.append((h, pid_val.value or None))
                    return 1

                WNDENUMPROC = ct.WINFUNCTYPE(ct.c_int, ct.c_ulong, ct.c_ulong)
                user32.EnumWindows(WNDENUMPROC(enum_proc), 0)

                if matches:
                    h, p = matches[0]
                    hwnd = hwnd or h
                    pid = pid or p
                    if pid:
                        ps = _lazy_psutil()
                        if ps is not None:
                            try:
                                proc = ps.Process(pid)
                                process_name = process_name or proc.name()
                            except Exception:
                                pass
            except Exception as exc:
                self._logger.warning(
                    f"WindowRegistry: _detect_window_info ctypes error: {exc}"
                )

        # Fallback: pygetwindow
        if hwnd is None:
            gw = _lazy_pygetwindow()
            if gw is not None:
                try:
                    wins = gw.getWindowsWithTitle(title)
                    if wins:
                        w = wins[0]
                        hwnd = getattr(w, "_hWnd", None)
                except Exception:
                    pass

        return hwnd, pid, process_name

    def _refresh_single(self, ref: WindowRef) -> None:
        """Refresh a single WindowRef in place."""
        now = datetime.now(timezone.utc).isoformat()

        if sys.platform == "win32" and ref.hwnd is not None:
            ct = _lazy_ctypes()
            if ct is not None:
                try:
                    user32 = ct.windll.user32
                    is_valid = bool(user32.IsWindow(ref.hwnd))
                    if is_valid:
                        length = user32.GetWindowTextLengthW(ref.hwnd)
                        buf = ct.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(ref.hwnd, buf, length + 1)
                        new_title = buf.value or ""
                        if new_title:
                            ref.title = new_title
                        ref.is_alive = True
                        ref.last_seen_at = now
                    else:
                        ref.is_alive = False
                        self._logger.debug(
                            f"WindowRegistry: hwnd={ref.hwnd} is no longer valid"
                        )
                    return
                except Exception as exc:
                    self._logger.warning(
                        f"WindowRegistry: _refresh_single ctypes error: {exc}"
                    )

        # Non-Windows or ctypes unavailable — fuzzy title check via pygetwindow
        gw = _lazy_pygetwindow()
        if gw is not None and ref.title:
            try:
                wins = gw.getWindowsWithTitle(ref.title)
                if wins:
                    ref.is_alive = True
                    ref.title = wins[0].title or ref.title
                    ref.last_seen_at = now
                    return
            except Exception:
                pass

        # If we still have a PID, check via psutil
        if ref.pid is not None:
            ps = _lazy_psutil()
            if ps is not None:
                try:
                    proc = ps.Process(ref.pid)
                    if proc.is_running() and proc.status() != ps.STATUS_ZOMBIE:
                        ref.is_alive = True
                        ref.last_seen_at = now
                        ref.process_name = ref.process_name or proc.name()
                        return
                except (ps.NoSuchProcess, ps.AccessDenied, ps.ZombieProcess):
                    pass
                except Exception:
                    pass

        ref.is_alive = False

    # -- OS-level search helpers (used by recover) ----------------------------

    def _find_by_pid_os(self, pid: int) -> Optional[Dict[str, Any]]:
        """Scan OS windows for one belonging to *pid*. Returns dict or None."""
        if sys.platform == "win32":
            ct = _lazy_ctypes()
            if ct is not None:
                try:
                    user32 = ct.windll.user32
                    result: Optional[Dict[str, Any]] = None

                    def enum_proc(h: int, _l: int) -> int:
                        nonlocal result
                        if result is not None:
                            return 0
                        pid_val = ct.c_ulong()
                        user32.GetWindowThreadProcessId(h, ct.byref(pid_val))
                        if pid_val.value == pid:
                            length = user32.GetWindowTextLengthW(h)
                            if length > 0:
                                buf = ct.create_unicode_buffer(length + 1)
                                user32.GetWindowTextW(h, buf, length + 1)
                                title = buf.value or ""
                                if title:
                                    result = {"hwnd": h, "pid": pid, "title": title}
                                    return 0
                        return 1

                    WNDENUMPROC = ct.WINFUNCTYPE(ct.c_int, ct.c_ulong, ct.c_ulong)
                    user32.EnumWindows(WNDENUMPROC(enum_proc), 0)
                    return result
                except Exception as exc:
                    self._logger.warning(
                        f"WindowRegistry: _find_by_pid_os ctypes error: {exc}"
                    )

        # Fallback: pygetwindow + psutil
        gw = _lazy_pygetwindow()
        ps = _lazy_psutil()
        if gw is not None and ps is not None:
            try:
                for w in gw.getAllWindows():
                    if not w.title:
                        continue
                    h = getattr(w, "_hWnd", None)
                    if h is not None:
                        pid_val = None
                        if sys.platform == "win32":
                            ct = _lazy_ctypes()
                            if ct is not None:
                                try:
                                    pv = ct.c_ulong()
                                    ct.windll.user32.GetWindowThreadProcessId(
                                        h, ct.byref(pv)
                                    )
                                    pid_val = pv.value
                                except Exception:
                                    pass
                        if pid_val == pid:
                            return {"hwnd": h, "pid": pid, "title": w.title}
            except Exception:
                pass
        return None

    def _find_by_title_os(self, title_substring: str) -> Optional[Dict[str, Any]]:
        """Scan OS windows for a title match. Returns dict or None."""
        gw = _lazy_pygetwindow()
        if gw is not None:
            try:
                wins = gw.getWindowsWithTitle(title_substring)
                if wins:
                    w = wins[0]
                    h = getattr(w, "_hWnd", None)
                    pid = None
                    if sys.platform == "win32" and h is not None:
                        ct = _lazy_ctypes()
                        if ct is not None:
                            try:
                                pv = ct.c_ulong()
                                ct.windll.user32.GetWindowThreadProcessId(
                                    h, ct.byref(pv)
                                )
                                pid = pv.value or None
                            except Exception:
                                pass
                    return {"hwnd": h, "pid": pid, "title": w.title}
            except Exception:
                pass
        return None

    def _find_by_process_name_os(self, process_name: str) -> Optional[Dict[str, Any]]:
        """Scan OS windows for one whose process name matches. Returns dict or None."""
        ps = _lazy_psutil()
        if ps is not None:
            try:
                target_pids: List[int] = []
                for proc in ps.process_iter(["pid", "name"]):
                    try:
                        if proc.info.get("name", "").lower() == process_name.lower():
                            target_pids.append(proc.info["pid"])
                    except (ps.NoSuchProcess, ps.AccessDenied):
                        continue

                if target_pids:
                    # Try to find a visible window for any of these PIDs
                    for pid in target_pids:
                        result = self._find_by_pid_os(pid)
                        if result:
                            return result
            except Exception as exc:
                self._logger.warning(
                    f"WindowRegistry: _find_by_process_name_os psutil error: {exc}"
                )
        return None

    def ensure_focus(self, ref: WindowRef) -> bool:
        """Bring the window referenced by *ref* to the foreground.

        Uses ctypes ``SetForegroundWindow`` on Windows, pygetwindow elsewhere.
        Marks the ref as stale if the window no longer exists.

        Returns ``True`` on success, ``False`` otherwise.
        """
        if not ref.is_alive and ref.hwnd is None:
            self._logger.warning(
                f"WindowRegistry: ensure_focus ref_id={ref.ref_id} — "
                f"ref is stale and has no hwnd"
            )
            return False

        if sys.platform == "win32":
            ct = _lazy_ctypes()
            if ct is not None and ref.hwnd is not None:
                try:
                    user32 = ct.windll.user32
                    if not user32.IsWindow(ref.hwnd):
                        ref.is_alive = False
                        self._logger.warning(
                            f"WindowRegistry: ensure_focus ref_id={ref.ref_id} — "
                            f"hwnd={ref.hwnd} is no longer valid"
                        )
                        return False
                    # Bring to front
                    user32.ShowWindow(ref.hwnd, 9)  # SW_RESTORE
                    user32.SetForegroundWindow(ref.hwnd)
                    ref.is_alive = True
                    ref.last_seen_at = datetime.now(timezone.utc).isoformat()
                    self._logger.info(
                        f"WindowRegistry: focused hwnd={ref.hwnd} ref_id={ref.ref_id}"
                    )
                    return True
                except Exception as exc:
                    self._logger.warning(
                        f"WindowRegistry: ensure_focus ctypes error: {exc}"
                    )

            # Fallback: pygetwindow by title
            gw = _lazy_pygetwindow()
            if gw is not None and ref.title:
                try:
                    wins = gw.getWindowsWithTitle(ref.title)
                    if wins:
                        w = wins[0]
                        if hasattr(w, "isMinimized") and w.isMinimized:
                            w.restore()
                        if hasattr(w, "activate"):
                            w.activate()
                        ref.is_alive = True
                        ref.last_seen_at = datetime.now(timezone.utc).isoformat()
                        return True
                except Exception:
                    pass

            ref.is_alive = False
            return False

        # Non-Windows: pygetwindow fallback
        gw = _lazy_pygetwindow()
        if gw is not None and ref.title:
            try:
                wins = gw.getWindowsWithTitle(ref.title)
                if wins:
                    ref.is_alive = True
                    ref.last_seen_at = datetime.now(timezone.utc).isoformat()
                    return True
            except Exception:
                pass

        ref.is_alive = False
        return False

    def find_by_pattern(self, pattern: str) -> List[WindowRef]:
        """Return all alive refs whose title or title_patterns match *pattern*.

        Tries regex first; falls back to case-insensitive substring match.
        """
        import re
        try:
            compiled = re.compile(pattern, re.IGNORECASE)
        except re.error:
            compiled = None

        results: List[WindowRef] = []
        for ref in self._registry.values():
            if not ref.is_alive:
                continue
            # Check title
            if compiled:
                if compiled.search(ref.title):
                    results.append(ref)
                    continue
            else:
                if pattern.lower() in ref.title.lower():
                    results.append(ref)
                    continue
            # Check title_patterns
            for p in ref.title_patterns:
                if compiled:
                    if compiled.search(p):
                        results.append(ref)
                        break
                else:
                    if pattern.lower() in p.lower():
                        results.append(ref)
                        break
        return results

    def _apply_recovery(self, ref: WindowRef, recovered: Dict[str, Any]) -> None:
        """Apply recovered window info to an existing WindowRef."""
        ref.hwnd = recovered.get("hwnd", ref.hwnd)
        ref.pid = recovered.get("pid", ref.pid)
        ref.title = recovered.get("title", ref.title)
        ref.is_alive = True
        ref.last_seen_at = datetime.now(timezone.utc).isoformat()
        self._logger.info(
            f"WindowRegistry: recovered ref_id={ref.ref_id} "
            f"hwnd={ref.hwnd} pid={ref.pid} title={ref.title!r}"
        )
