"""Multi-App Orchestrator — browser↔desktop orchestration layer for AgentOS Phase 5.

Coordinates transitions between browser and desktop environments, manages file
handoffs, and reduces clipboard dependency.
"""

import asyncio
import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..logs.logger import logger
from ..tools.base import ToolOutput
from .window_registry import WindowRef, WindowRegistry


@dataclass
class WorkflowCheckpoint:
    """Immutable snapshot of the current workflow state."""

    task_id: str
    step: str
    active_app: Optional[str] = None
    active_window: Optional[str] = None
    browser_url: Optional[str] = None
    browser_tab_title: Optional[str] = None
    desktop_file_path: Optional[str] = None
    open_files: List[str] = field(default_factory=list)
    open_windows: List[Dict] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        now = datetime.now(timezone.utc).isoformat()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "step": self.step,
            "active_app": self.active_app,
            "active_window": self.active_window,
            "browser_url": self.browser_url,
            "browser_tab_title": self.browser_tab_title,
            "desktop_file_path": self.desktop_file_path,
            "open_files": list(self.open_files),
            "open_windows": list(self.open_windows),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class MultiAppOrchestrator:
    """Coordinates browser and desktop environments for a single task.

    Manages app switching, file transfers, and workflow checkpoints so the
    agent can move seamlessly between browser automation and native desktop
    applications without relying on the clipboard.
    """

    CHECKPOINT_DIR = os.path.join(tempfile.gettempdir(), "agentos_checkpoints")

    def __init__(self, task_id: str):
        self.task_id = task_id
        self._window_registry: Optional[WindowRegistry] = None
        self._checkpoints: List[WorkflowCheckpoint] = []
        self._current_checkpoint: Optional[WorkflowCheckpoint] = None

    # ------------------------------------------------------------------
    # Lazy properties
    # ------------------------------------------------------------------

    @property
    def window_registry(self) -> WindowRegistry:
        if self._window_registry is None:
            self._window_registry = WindowRegistry()
        return self._window_registry

    @property
    def desktop_session(self):
        """Lazy-loaded DesktopSession from the session manager."""
        from .desktop_env import desktop_session_manager
        return desktop_session_manager.get_session(self.task_id)

    @property
    def browser_session(self):
        """Lazy-loaded BrowserSession from the session manager."""
        from .browser_env import browser_session_manager
        return browser_session_manager.get_session(self.task_id)

    # ------------------------------------------------------------------
    # Checkpoints
    # ------------------------------------------------------------------

    def save_checkpoint(self, step: str, **kwargs) -> WorkflowCheckpoint:
        """Snapshot current workflow state and append to the checkpoint list.

        Automatically captures:
        - Active window from the registry (if any)
        - Browser URL and title (if browser session is alive)
        - Known file paths from kwargs or current checkpoint
        """
        # Gather active window info
        active_window_ref: Optional[str] = None
        active_app_name: Optional[str] = None
        if self._current_checkpoint and self._current_checkpoint.active_window:
            existing_ref = self.window_registry.lookup(
                self._current_checkpoint.active_window
            )
            if existing_ref and existing_ref.is_alive:
                active_window_ref = existing_ref.ref_id
                active_app_name = existing_ref.process_name or "browser"

        # Try to capture browser state
        browser_url: Optional[str] = kwargs.get("browser_url")
        browser_tab_title: Optional[str] = kwargs.get("browser_tab_title")
        if self.browser_session is not None:
            try:
                if hasattr(self.browser_session, "_current_url"):
                    browser_url = browser_url or self.browser_session._current_url
            except Exception:
                pass

        # Collect open files
        open_files: List[str] = kwargs.get("open_files", [])
        if not open_files and self._current_checkpoint:
            open_files = list(self._current_checkpoint.open_files)
        if kwargs.get("desktop_file_path"):
            fp = kwargs["desktop_file_path"]
            if fp not in open_files:
                open_files.append(fp)

        # Collect open windows from registry
        open_windows = [ref.to_dict() for ref in self._registry_alive()]

        desktop_file_path: Optional[str] = kwargs.get(
            "desktop_file_path",
            self._current_checkpoint.desktop_file_path if self._current_checkpoint else None,
        )

        checkpoint = WorkflowCheckpoint(
            task_id=self.task_id,
            step=step,
            active_app=active_app_name or kwargs.get("active_app"),
            active_window=active_window_ref or kwargs.get("active_window"),
            browser_url=browser_url,
            browser_tab_title=browser_tab_title,
            desktop_file_path=desktop_file_path,
            open_files=open_files,
            open_windows=open_windows,
        )

        self._checkpoints.append(checkpoint)
        self._current_checkpoint = checkpoint
        logger.info(
            f"MultiAppOrchestrator[{self.task_id}]: checkpoint saved step='{step}' "
            f"app={checkpoint.active_app} url={checkpoint.browser_url}"
        )
        # Persist to disk for cross-restart recovery
        self.persist_checkpoint(checkpoint)
        return checkpoint

    def restore_from_checkpoint(self) -> Optional[WorkflowCheckpoint]:
        """Attempt to restore the most recent checkpoint.

        Returns the restored checkpoint on success, or None if no checkpoint
        exists or restoration failed.
        """
        # Try loading from disk first (survives restarts) — but only if
        # there's nothing in memory (true recovery scenario)
        if self._current_checkpoint is None and not self._checkpoints:
            disk_cp = self.load_persisted_checkpoint()
            if disk_cp is not None:
                self._current_checkpoint = disk_cp
                self._checkpoints.append(disk_cp)
                logger.info(
                    f"MultiAppOrchestrator[{self.task_id}]: loaded checkpoint from disk"
                )

        if self._current_checkpoint is None:
            if not self._checkpoints:
                logger.warning(
                    f"MultiAppOrchestrator[{self.task_id}]: no checkpoint to restore"
                )
                return None
            self._current_checkpoint = self._checkpoints[-1]

        cp = self._current_checkpoint
        logger.info(
            f"MultiAppOrchestrator[{self.task_id}]: restoring checkpoint "
            f"step='{cp.step}' app={cp.active_app}"
        )

        # Try to refocus the recorded window
        if cp.active_window:
            ref = self.window_registry.lookup(cp.active_window)
            if ref:
                self.window_registry.ensure_focus(ref)
            else:
                logger.warning(
                    f"MultiAppOrchestrator[{self.task_id}]: window ref_id={cp.active_window} "
                    f"not found in registry"
                )

        # Try to navigate browser back to the recorded URL
        if cp.browser_url and self.browser_session:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(
                        self.browser_session.navigate(cp.browser_url)
                    )
                    logger.info(
                        f"MultiAppOrchestrator[{self.task_id}]: scheduled browser "
                        f"navigation to {cp.browser_url}"
                    )
            except RuntimeError:
                # No running event loop — synchronous fallback not possible
                logger.warning(
                    f"MultiAppOrchestrator[{self.task_id}]: cannot navigate browser "
                    f"without running event loop"
                )

        # Update timestamp
        cp.updated_at = datetime.now(timezone.utc).isoformat()
        return cp

    # ------------------------------------------------------------------
    # App switching
    # ------------------------------------------------------------------

    def switch_to_app(self, app_name: str) -> ToolOutput:
        """Robustly switch focus to a desktop application.

        1. Look up app in window_registry by title pattern.
        2. Call ensure_focus() on the window.
        3. If not found, try to launch via subprocess (e.g. ``start notepad``).
        4. Wait for window to appear (poll window list for up to 5s).
        5. Register the new window in the registry.
        6. Return success/failure.
        """
        # Step 1 — look up existing window
        matches = self.window_registry.find_by_pattern(app_name)
        if matches:
            ref = matches[0]
            focused = self.window_registry.ensure_focus(ref)
            if focused:
                self.save_checkpoint(step=f"switched_to_app:{app_name}")
                return ToolOutput(
                    success=True,
                    result={
                        "message": f"Switched to app '{app_name}'",
                        "window_ref_id": ref.ref_id,
                        "window_title": ref.title,
                    },
                    metadata={"method": "existing_window"},
                )

        # Step 2 — try to launch the app
        launched = self._launch_app(app_name)
        if not launched:
            return ToolOutput(
                success=False,
                error=f"App '{app_name}' not found in registry and could not be launched",
            )

        # Step 3 — poll for the window to appear (up to 5s)
        ref = self._wait_for_window(app_name, timeout=5.0)
        if ref is None:
            return ToolOutput(
                success=False,
                error=f"App '{app_name}' launched but window did not appear within 5s",
            )

        # Step 4 — register and focus
        self.window_registry.ensure_focus(ref)
        self.save_checkpoint(step=f"switched_to_app:{app_name}")

        return ToolOutput(
            success=True,
            result={
                "message": f"Launched and switched to app '{app_name}'",
                "window_ref_id": ref.ref_id,
                "window_title": ref.title,
            },
            metadata={"method": "launched"},
        )

    def switch_to_browser(self) -> ToolOutput:
        """Switch focus to the browser window.

        If the browser session is alive, bring it to front. Uses the window
        registry for persistent tracking.
        """
        browser_session = self.browser_session
        if browser_session is None:
            return ToolOutput(
                success=False,
                error="No browser session found for this task",
            )

        # Check if browser is alive
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(browser_session.is_alive())
                logger.info(
                    f"MultiAppOrchestrator[{self.task_id}]: browser session scheduled "
                    f"for alive check"
                )
        except RuntimeError:
            pass

        # Try to find a browser window in the registry
        browser_matches = self.window_registry.find_by_pattern(
            "Chrome|Chromium|Firefox|Edge|Brave"
        )
        if browser_matches:
            ref = browser_matches[0]
            focused = self.window_registry.ensure_focus(ref)
            if focused:
                self.save_checkpoint(step="switched_to_browser")
                return ToolOutput(
                    success=True,
                    result={
                        "message": "Switched to browser",
                        "window_ref_id": ref.ref_id,
                        "window_title": ref.title,
                    },
                )

        # Try OS-level focus via desktop session
        if self.desktop_session:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(
                        self.desktop_session.focus_window("Chrome")
                    )
            except RuntimeError:
                pass

        # Register a browser window entry even if we couldn't focus it
        ref = self.window_registry.register(
            title="Browser",
            process_name="browser",
        )
        self.save_checkpoint(step="switched_to_browser")

        return ToolOutput(
            success=True,
            result={
                "message": "Browser focus requested (window may need manual activation)",
                "window_ref_id": ref.ref_id,
            },
        )

    # ------------------------------------------------------------------
    # File transfers
    # ------------------------------------------------------------------

    def transfer_file_to_desktop(
        self, file_path: str, app_name: Optional[str] = None
    ) -> ToolOutput:
        """Open a file in a desktop app WITHOUT clipboard.

        1. Validate file exists.
        2. If app_name specified, open with ``os.startfile`` (Windows file
           associations) or ``subprocess.Popen([app_name, file_path])``.
        3. Wait for the app window to appear (poll for up to 8s).
        4. Register the window.
        5. Save checkpoint.
        6. Return success with window ref_id.
        """
        # Step 1 — validate
        if not os.path.isfile(file_path):
            return ToolOutput(
                success=False,
                error=f"File not found: {file_path}",
            )

        abs_path = os.path.abspath(file_path)

        # Step 2 — open the file
        try:
            if sys.platform == "win32":
                if app_name:
                    # Specific application requested
                    subprocess.Popen([app_name, abs_path], shell=True)
                else:
                    # Use file association
                    os.startfile(abs_path)
            else:
                if app_name:
                    subprocess.Popen([app_name, abs_path])
                else:
                    # xdg-open on Linux, open on macOS
                    opener = "xdg-open" if sys.platform.startswith("linux") else "open"
                    subprocess.Popen([opener, abs_path])
        except Exception as e:
            return ToolOutput(
                success=False,
                error=f"Failed to open file '{abs_path}': {e}",
            )

        # Step 3 — wait for the window to appear (up to 8s)
        base_name = os.path.basename(abs_path)
        search_pattern = app_name or base_name
        ref = self._wait_for_window(search_pattern, timeout=8.0)

        if ref is None:
            # Register anyway with the file name as title
            ref = self.window_registry.register(
                title=base_name,
                process_name=app_name,
            )

        # Step 4 — save checkpoint
        self.save_checkpoint(
            step=f"transfer_file_to_desktop:{base_name}",
            desktop_file_path=abs_path,
            active_app=app_name or "default",
            active_window=ref.ref_id,
        )

        return ToolOutput(
            success=True,
            result={
                "message": f"Opened file '{base_name}' on desktop",
                "file_path": abs_path,
                "window_ref_id": ref.ref_id,
                "window_title": ref.title,
            },
        )

    async def transfer_file_to_browser(
        self, file_path: str, upload_selector: Optional[str] = None
    ) -> ToolOutput:
        """Upload a file to the browser via Playwright file chooser.

        1. Validate file exists.
        2. Perform the upload via _do_browser_upload and await the result.
        3. If upload fails, return error.
        4. Save checkpoint.
        5. Return success.
        """
        # Step 1 — validate
        if not os.path.isfile(file_path):
            return ToolOutput(
                success=False,
                error=f"File not found: {file_path}",
            )

        abs_path = os.path.abspath(file_path)
        browser_session = self.browser_session
        if browser_session is None:
            return ToolOutput(
                success=False,
                error="No browser session available for file upload",
            )

        # Step 2 — perform the upload and await the result
        try:
            result = await self._do_browser_upload(browser_session, abs_path, upload_selector)
            if not result:
                return ToolOutput(
                    success=False,
                    error="Browser file upload failed",
                )
        except RuntimeError:
            return ToolOutput(
                success=False,
                error="Cannot perform browser upload without a running event loop",
            )
        except Exception as e:
            logger.error(
                f"MultiAppOrchestrator[{self.task_id}]: browser upload failed: {e}"
            )
            return ToolOutput(
                success=False,
                error=f"Browser file upload failed: {e}",
            )

        # Step 3 — save checkpoint
        self.save_checkpoint(
            step=f"transfer_file_to_browser:{os.path.basename(abs_path)}",
            desktop_file_path=abs_path,
        )

        return ToolOutput(
            success=True,
            result={
                "message": f"File upload initiated for '{os.path.basename(abs_path)}'",
                "file_path": abs_path,
                "selector_used": upload_selector or "auto-detected",
            },
        )

    async def _do_browser_upload(self, browser_session, file_path: str,
                                  upload_selector: Optional[str] = None) -> bool:
        """Internal: actually set the file input via Playwright."""
        try:
            page = browser_session._page
            if page is None or page.is_closed():
                logger.error(
                    f"MultiAppOrchestrator[{self.task_id}]: browser page not available "
                    f"for file upload"
                )
                return False

            if upload_selector:
                await page.set_input_files(upload_selector, file_path)
                logger.info(
                    f"MultiAppOrchestrator[{self.task_id}]: uploaded file to "
                    f"selector '{upload_selector}'"
                )
                return True

            # Auto-detect file input elements — use first visible one
            file_inputs = await page.query_selector_all('input[type="file"]')
            if file_inputs:
                for fi in file_inputs:
                    try:
                        visible = await fi.is_visible()
                    except Exception:
                        visible = False
                    if visible:
                        await fi.set_input_files(file_path)
                        logger.info(
                            f"MultiAppOrchestrator[{self.task_id}]: uploaded file to "
                            f"auto-detected visible file input"
                        )
                        return True
                # Fall back to first (maybe hidden)
                try:
                    await file_inputs[0].set_input_files(file_path)
                    logger.info(
                        f"MultiAppOrchestrator[{self.task_id}]: uploaded file to "
                        f"first (possibly hidden) file input"
                    )
                    return True
                except Exception as e:
                    logger.debug(
                        f"MultiAppOrchestrator[{self.task_id}]: first file input failed: {e}"
                    )

            # Last resort: try to trigger file chooser by clicking common upload areas
            upload_trigger_selectors = [
                'button:has-text("Upload")',
                'button:has-text("Browse")',
                'button:has-text("Choose File")',
                'button:has-text("Select File")',
                'a:has-text("Upload")',
                'label:has-text("Upload")',
                '[aria-label*="upload" i]',
                '[aria-label*="choose" i]',
                '.upload-button',
                '#upload-button',
            ]
            for selector in upload_trigger_selectors:
                try:
                    trigger = await page.query_selector(selector)
                    if trigger:
                        visible = await trigger.is_visible()
                        if visible:
                            # Set up file chooser listener before clicking
                            async with page.expect_file_chooser() as fc_info:
                                await trigger.click()
                            file_chooser = await fc_info.value
                            await file_chooser.set_files(file_path)
                            logger.info(
                                f"MultiAppOrchestrator[{self.task_id}]: uploaded file "
                                f"via file chooser triggered by '{selector}'"
                            )
                            return True
                except Exception as e:
                    logger.debug(
                        f"MultiAppOrchestrator[{self.task_id}]: upload trigger "
                        f"'{selector}' failed: {e}"
                    )
                    continue

            logger.warning(
                f"MultiAppOrchestrator[{self.task_id}]: no file input or upload trigger "
                f"found on page for upload of '{file_path}'"
            )
            return False
        except Exception as e:
            logger.error(
                f"MultiAppOrchestrator[{self.task_id}]: browser upload failed: {e}"
            )
            return False

    async def transfer_file_to_browser_with_fallback(
        self, file_path: str, upload_selector: Optional[str] = None
    ) -> ToolOutput:
        """Upload a file to the browser with multi-strategy fallback.

        Tries multiple strategies in order:
        1. If selector provided, use it directly
        2. Scan for input[type=file]
        3. Click "Upload"/"Browse" buttons and handle the system file dialog
           (via Playwright file chooser)
        4. If all fail, return error with diagnostic info

        This is a more robust version of transfer_file_to_browser() that does not
        return early on partial success.
        """
        # Step 1 — validate
        if not os.path.isfile(file_path):
            return ToolOutput(
                success=False,
                error=f"File not found: {file_path}",
            )

        abs_path = os.path.abspath(file_path)
        browser_session = self.browser_session
        if browser_session is None:
            return ToolOutput(
                success=False,
                error="No browser session available for file upload",
            )

        # Step 2 — try all strategies
        diagnostic_info: Dict[str, Any] = {
            "file_path": abs_path,
            "selector_provided": upload_selector,
            "strategies_tried": [],
            "page_url": None,
            "page_title": None,
        }

        # Capture page diagnostics
        try:
            page = browser_session._page
            if page is not None and not page.is_closed():
                diagnostic_info["page_url"] = page.url
                diagnostic_info["page_title"] = await page.title()
        except Exception:
            pass

        # Run the upload
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                success = await self._do_browser_upload(browser_session, abs_path, upload_selector)
            else:
                return ToolOutput(
                    success=False,
                    error="No running event loop for browser upload",
                    metadata={"diagnostic": diagnostic_info},
                )
        except RuntimeError:
            return ToolOutput(
                success=False,
                error="No running event loop for browser upload",
                metadata={"diagnostic": diagnostic_info},
            )

        if success:
            # Save checkpoint
            self.save_checkpoint(
                step=f"transfer_file_to_browser:{os.path.basename(abs_path)}",
                desktop_file_path=abs_path,
            )
            return ToolOutput(
                success=True,
                result={
                    "message": f"File uploaded: '{os.path.basename(abs_path)}'",
                    "file_path": abs_path,
                    "selector_used": upload_selector or "auto-detected",
                },
            )
        else:
            diagnostic_info["strategies_tried"].append("all_failed")
            return ToolOutput(
                success=False,
                error=(
                    f"All upload strategies failed for '{os.path.basename(abs_path)}'. "
                    f"Page URL: {diagnostic_info.get('page_url', 'unknown')}. "
                    f"Page title: {diagnostic_info.get('page_title', 'unknown')}"
                ),
                metadata={"diagnostic": diagnostic_info},
            )

    # ------------------------------------------------------------------
    # State introspection
    # ------------------------------------------------------------------

    def get_state(self) -> Dict[str, Any]:
        """Return current workflow state as a dict."""
        cp = self._current_checkpoint
        active_app = cp.active_app if cp else None
        browser_url = cp.browser_url if cp else None

        # Try to get live browser URL
        if self.browser_session and hasattr(self.browser_session, "_current_url"):
            browser_url = browser_url or self.browser_session._current_url

        return {
            "task_id": self.task_id,
            "active_app": active_app,
            "browser_url": browser_url,
            "browser_tab_title": cp.browser_tab_title if cp else None,
            "desktop_file_path": cp.desktop_file_path if cp else None,
            "open_files": cp.open_files if cp else [],
            "window_count": len(self._registry_alive()),
            "windows": [ref.to_dict() for ref in self._registry_alive()],
            "checkpoint_count": len(self._checkpoints),
            "current_step": cp.step if cp else None,
        }

    # ------------------------------------------------------------------
    # Recovery
    # ------------------------------------------------------------------

    def recover(self) -> ToolOutput:
        """Try to recover after an interruption.

        1. Refresh window registry.
        2. If current checkpoint exists, try to restore from it.
        3. If browser was active, check if browser is still alive.
        4. If desktop app was active, check if window still exists.
        5. Return recovery status.
        """
        logger.info(f"MultiAppOrchestrator[{self.task_id}]: starting recovery")

        # Step 1 — refresh window registry
        self.window_registry.refresh()

        # Step 2 — restore checkpoint if available
        restored = self.restore_from_checkpoint()
        if restored is None:
            return ToolOutput(
                success=False,
                error="No checkpoint available for recovery",
                metadata={"recovery_status": "no_checkpoint"},
            )

        recovery_details: Dict[str, Any] = {
            "restored_step": restored.step,
            "restored_app": restored.active_app,
        }

        # Step 3 — check browser
        if restored.active_app == "browser" or restored.browser_url:
            browser_session = self.browser_session
            if browser_session:
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.ensure_future(browser_session.is_alive())
                        recovery_details["browser_check"] = "scheduled"
                except RuntimeError:
                    recovery_details["browser_check"] = "no_event_loop"
            else:
                recovery_details["browser_check"] = "no_browser_session"

        # Step 4 — check desktop window
        if restored.active_window:
            ref = self.window_registry.lookup(restored.active_window)
            if ref:
                recovery_details["window_alive"] = ref.is_alive
                if not ref.is_alive:
                    logger.warning(
                        f"MultiAppOrchestrator[{self.task_id}]: recovered window "
                        f"ref_id={ref.ref_id} is no longer alive"
                    )
            else:
                recovery_details["window_alive"] = False
                recovery_details["window_missing"] = True

        recovery_details["recovery_status"] = "partial" if any(
            v is False for v in recovery_details.values() if isinstance(v, bool)
        ) else "full"

        logger.info(
            f"MultiAppOrchestrator[{self.task_id}]: recovery complete "
            f"status={recovery_details['recovery_status']}"
        )

        return ToolOutput(
            success=recovery_details["recovery_status"] != "failed",
            result=recovery_details,
            metadata={"recovery_status": recovery_details["recovery_status"]},
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _checkpoint_path(self) -> str:
        """Return the path to the persisted checkpoint file for this task."""
        return os.path.join(self.CHECKPOINT_DIR, f"checkpoint_{self.task_id}.json")

    def persist_checkpoint(self, checkpoint: WorkflowCheckpoint) -> None:
        """Save checkpoint to disk for recovery across restarts."""
        try:
            os.makedirs(self.CHECKPOINT_DIR, exist_ok=True)
            path = self._checkpoint_path()
            with open(path, "w") as f:
                json.dump(checkpoint.to_dict(), f, indent=2, default=str)
            logger.info(f"[MultiAppOrchestrator] Checkpoint persisted to {path}")
        except Exception as e:
            logger.warning(f"[MultiAppOrchestrator] Failed to persist checkpoint: {e}")

    def load_persisted_checkpoint(self) -> Optional[WorkflowCheckpoint]:
        """Load checkpoint from disk if exists."""
        path = self._checkpoint_path()
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    data = json.load(f)
                return WorkflowCheckpoint(**data)
            except Exception as e:
                logger.warning(f"[MultiAppOrchestrator] Failed to load checkpoint: {e}")
        return None

    def _registry_alive(self) -> List[WindowRef]:
        """Return all alive window references."""
        return [ref for ref in self.window_registry._registry.values() if ref.is_alive]

    @staticmethod
    def _launch_app(app_name: str) -> bool:
        """Attempt to launch an application by name. Returns True on success.

        Uses deterministic path resolution first, then falls back to platform defaults.
        This is a lightweight launcher for internal orchestrator use.
        For full verification, use DesktopSession.open_application().
        """
        try:
            from .app_launcher import resolve_app_path
            resolved = resolve_app_path(app_name)
            if resolved:
                if sys.platform == "win32":
                    if resolved.lower().endswith(".lnk"):
                        os.startfile(resolved)
                    else:
                        subprocess.Popen(
                            resolved,
                            shell=False,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                        )
                else:
                    subprocess.Popen([resolved])
                return True
        except Exception:
            pass

        # Fallback to original platform-specific launch
        try:
            if sys.platform == "win32":
                subprocess.Popen(f"start {app_name}", shell=True)
                return True
            elif sys.platform.startswith("linux"):
                subprocess.Popen([app_name])
                return True
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-a", app_name])
                return True
        except Exception as e:
            logger.warning(
                f"MultiAppOrchestrator: failed to launch '{app_name}': {e}"
            )
        return False

    def _wait_for_window(self, pattern: str, timeout: float = 5.0) -> Optional[WindowRef]:
        """Poll the OS window list until a window matching *pattern* appears.

        Returns the registered WindowRef or None if timeout expires.
        """
        deadline = time.time() + timeout
        poll_interval = 0.3

        try:
            import pygetwindow as gw
        except Exception:
            gw = None  # type: ignore

        while time.time() < deadline:
            if gw is not None:
                try:
                    windows = gw.getAllWindows()
                    for w in windows:
                        if w.title and pattern.lower() in w.title.lower():
                            # Register if not already tracked
                            existing = self.window_registry.find_by_pattern(w.title)
                            if existing:
                                return existing[0]
                            ref = self.window_registry.register(
                                title=w.title,
                                process_name=pattern,
                                hwnd=getattr(w, "_hWnd", None),
                            )
                            return ref
                except Exception:
                    pass

            # Also check the registry for any matches that appeared
            matches = self.window_registry.find_by_pattern(pattern)
            if matches:
                return matches[0]

            time.sleep(poll_interval)

        return None
