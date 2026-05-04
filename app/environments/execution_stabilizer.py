"""Execution Stabilization + Verification Layer."""
import asyncio
import hashlib
import json
import os
import tempfile
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Callable, Awaitable
from datetime import datetime

from ..logs.logger import logger

try:
    from PIL import Image
except Exception:
    Image = None  # type: ignore

try:
    import cv2
    import numpy as np
except Exception:
    cv2 = None  # type: ignore
    np = None  # type: ignore


@dataclass
class ActionSnapshot:
    """Immutable record of an action attempt with truth logging."""
    timestamp: str
    action_name: str
    params: Dict[str, Any]
    before_screenshot_path: Optional[str]
    after_screenshot_path: Optional[str]
    before_tree_hash: Optional[str]
    after_tree_hash: Optional[str]
    before_element_map: Dict[int, Dict[str, Any]]
    selected_target: Optional[Dict[str, Any]]
    verification_result: Optional[Dict[str, Any]] = None
    retry_count: int = 0
    error: Optional[str] = None
    # Truth logging fields
    expected_outcome: Optional[str] = None
    actual_outcome: Optional[str] = None
    semantic_verified: bool = False
    semantic_notes: Optional[str] = None


@dataclass
class StabilizerConfig:
    """Tunable parameters for the stabilizer."""
    # Pre-action stabilization
    stabilization_max_wait: float = 3.0
    stabilization_poll_interval: float = 0.2
    stabilization_diff_threshold: float = 0.02  # 2% pixel change
    stabilization_min_stable_frames: int = 2

    # Post-action verification
    verification_timeout: float = 3.0
    verification_poll_interval: float = 0.3
    verification_tree_hash_timeout: float = 2.0

    # Coordinate drift
    drift_revalidation: bool = True
    drift_max_movement_px: int = 5

    # Popup/modal detection
    popup_check_enabled: bool = True
    popup_window_classes: List[str] = field(default_factory=lambda: [
        "#32770",  # Windows dialog
        "MozillaDialogClass",
        "Chrome_WidgetWin_2",  # Chrome popup
    ])

    # Retry policy
    max_retries: int = 2
    retry_backoff_base: float = 1.0
    retry_redetect_before_retry: bool = True

    # Temp screenshot cleanup
    temp_screenshot_max_age_seconds: int = 300

    # Per-action-type stabilization overrides (action_type -> config dict)
    action_configs: Dict[str, Dict[str, float]] = field(default_factory=lambda: {
        "click": {"stabilization_max_wait": 2.0, "verification_timeout": 2.0},
        "click_element": {"stabilization_max_wait": 2.0, "verification_timeout": 2.0},
        "type_text": {"stabilization_max_wait": 3.0, "verification_timeout": 3.0},
        "type_element": {"stabilization_max_wait": 3.0, "verification_timeout": 3.0},
        "press_key": {"stabilization_max_wait": 2.5, "verification_timeout": 2.5},
        "open_application": {"stabilization_max_wait": 5.0, "verification_timeout": 8.0},
        "launch_app_and_open_file": {"stabilization_max_wait": 5.0, "verification_timeout": 8.0},
        "focus_window": {"stabilization_max_wait": 3.0, "verification_timeout": 4.0},
        "scroll": {"stabilization_max_wait": 2.0, "verification_timeout": 2.0},
    })

    def get_for_action(self, action_name: str) -> "StabilizerConfig":
        """Return a config with action-specific overrides applied."""
        overrides = self.action_configs.get(action_name, {})
        if not overrides:
            return self
        # Create a shallow copy with overrides
        from copy import copy
        new_config = copy(self)
        for key, value in overrides.items():
            setattr(new_config, key, value)
        return new_config


@dataclass
class ActionStabilizer:
    config: StabilizerConfig = field(default_factory=StabilizerConfig)
    _snapshot_history: List[ActionSnapshot] = field(default_factory=list)
    _cleanup_task: Optional[asyncio.Task] = field(default=None, repr=False)
    _cleanup_interval_seconds: int = field(default=300, repr=False)

    def __post_init__(self) -> None:
        """Start the background screenshot cleanup task."""
        self._start_cleanup_task()

    def _start_cleanup_task(self) -> None:
        """Start the background screenshot reaper if not already running."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return  # No event loop — skip (e.g. during dataclass init outside async context)
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = loop.create_task(
                self._cleanup_loop(), name="stabilizer_screenshot_reaper"
            )

    async def _cleanup_loop(self) -> None:
        """Background loop that cleans orphaned screenshots every 5 minutes."""
        try:
            while True:
                await asyncio.sleep(self._cleanup_interval_seconds)
                try:
                    removed = self.cleanup_temp_screenshots()
                    if removed:
                        logger.info(
                            f"[ActionStabilizer] Background reaper removed {removed} orphaned screenshot(s)"
                        )
                except Exception as exc:
                    logger.error(
                        f"[ActionStabilizer] Screenshot cleanup iteration failed: {exc}"
                    )
        except asyncio.CancelledError:
            pass  # Normal shutdown — do not re-raise

    async def shutdown(self) -> None:
        """Cancel the background cleanup task."""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None

    # ── Screenshot comparison helpers ──

    def _compare_screenshots(self, path_a: str, path_b: str) -> float:
        """Return fraction of pixels that changed between two screenshots."""
        if cv2 is None or np is None:
            # Fallback: file size comparison (very crude)
            try:
                size_a = os.path.getsize(path_a)
                size_b = os.path.getsize(path_b)
                if size_a == 0:
                    return 1.0
                return abs(size_a - size_b) / size_a
            except Exception:
                return 1.0
        try:
            img_a = cv2.imread(path_a)
            img_b = cv2.imread(path_b)
            if img_a is None or img_b is None:
                return 1.0
            if img_a.shape != img_b.shape:
                return 1.0
            diff = cv2.absdiff(img_a, img_b)
            non_zero = np.count_nonzero(diff)
            total = diff.size
            return non_zero / total if total > 0 else 1.0
        except Exception as e:
            logger.warning(f"[ActionStabilizer] Screenshot comparison failed: {e}")
            return 1.0

    # ── Pre-action stabilization ──

    async def wait_for_ui_stability(
        self,
        screenshot_fn: Callable[[Optional[str]], Awaitable[Any]],
        max_wait: Optional[float] = None,
        poll_interval: Optional[float] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Poll screenshots until UI is stable or timeout.

        Returns (stable, last_screenshot_path).
        """
        max_wait = max_wait or self.config.stabilization_max_wait
        poll_interval = poll_interval or self.config.stabilization_poll_interval
        threshold = self.config.stabilization_diff_threshold
        min_stable = self.config.stabilization_min_stable_frames

        stable_count = 0
        prev_path: Optional[str] = None
        start = asyncio.get_event_loop().time()
        collected_paths: List[str] = []

        try:
            while (asyncio.get_event_loop().time() - start) < max_wait:
                # Save temp screenshot
                path = os.path.join(tempfile.gettempdir(), f"stab_{datetime.utcnow().timestamp()}.png")
                result = await screenshot_fn(path)
                if not getattr(result, "success", True):
                    # Clean up failed screenshot
                    if os.path.exists(path):
                        try:
                            os.remove(path)
                        except Exception:
                            pass
                    await asyncio.sleep(poll_interval)
                    continue

                collected_paths.append(path)

                if prev_path is None:
                    prev_path = path
                    stable_count = 1
                    await asyncio.sleep(poll_interval)
                    continue

                diff = self._compare_screenshots(prev_path, path)
                if diff <= threshold:
                    stable_count += 1
                    if stable_count >= min_stable:
                        logger.info(f"[ActionStabilizer] UI stable after {diff:.4f} diff ({stable_count} frames)")
                        # Keep only the final stable path; all others get cleaned in finally
                        return True, path
                else:
                    stable_count = 0
                    prev_path = path

                await asyncio.sleep(poll_interval)

            logger.warning(f"[ActionStabilizer] UI did not stabilize within {max_wait}s")
            return False, prev_path
        finally:
            # Clean up all intermediate screenshots except the one being returned
            returned_path = None
            if stable_count >= min_stable and collected_paths:
                # We returned True with a path — keep the last (current) path
                returned_path = collected_paths[-1] if collected_paths else None
            elif prev_path:
                # We returned False — keep prev_path for caller diagnostics
                returned_path = prev_path
            for p in collected_paths:
                if p != returned_path and os.path.exists(p):
                    try:
                        os.remove(p)
                    except Exception:
                        pass

    # ── Post-action verification ──

    async def verify_state_change(
        self,
        before_screenshot_path: Optional[str],
        before_tree_hash: Optional[str],
        screenshot_fn: Callable[[Optional[str]], Awaitable[Any]],
        tree_hash_fn: Callable[[], Awaitable[str]],
        timeout: Optional[float] = None,
        poll_interval: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Verify that UI state changed after an action.

        Returns dict with:
        - changed: bool
        - screenshot_changed: bool
        - tree_changed: bool
        - after_screenshot_path: Optional[str]
        - after_tree_hash: Optional[str]
        - notes: str
        """
        timeout = timeout or self.config.verification_timeout
        poll_interval = poll_interval or self.config.verification_poll_interval
        start = asyncio.get_event_loop().time()

        after_screenshot_path: Optional[str] = None
        after_tree_hash: Optional[str] = None
        screenshot_changed = False
        tree_changed = False

        while (asyncio.get_event_loop().time() - start) < timeout:
            # Screenshot check
            path = os.path.join(tempfile.gettempdir(), f"verify_{datetime.utcnow().timestamp()}.png")
            result = await screenshot_fn(path)
            if getattr(result, "success", True):
                # Clean up previous intermediate screenshot
                if after_screenshot_path and os.path.exists(after_screenshot_path):
                    try:
                        os.remove(after_screenshot_path)
                    except Exception:
                        pass
                after_screenshot_path = path
                if before_screenshot_path and os.path.exists(before_screenshot_path):
                    diff = self._compare_screenshots(before_screenshot_path, path)
                    screenshot_changed = diff > self.config.stabilization_diff_threshold

            # Tree hash check
            try:
                after_tree_hash = await tree_hash_fn()
                if before_tree_hash and after_tree_hash != before_tree_hash:
                    tree_changed = True
            except Exception as e:
                logger.debug(f"[ActionStabilizer] Tree hash check failed: {e}")

            if screenshot_changed or tree_changed:
                return {
                    "changed": True,
                    "screenshot_changed": screenshot_changed,
                    "tree_changed": tree_changed,
                    "after_screenshot_path": after_screenshot_path,
                    "after_tree_hash": after_tree_hash,
                    "notes": f"State changed: screenshot={screenshot_changed}, tree={tree_changed}",
                }

            await asyncio.sleep(poll_interval)

        return {
            "changed": False,
            "screenshot_changed": False,
            "tree_changed": False,
            "after_screenshot_path": after_screenshot_path,
            "after_tree_hash": after_tree_hash,
            "notes": "No state change detected within timeout",
        }

    # ── Window stabilization ──

    async def wait_for_window_stability(
        self,
        window_list_fn: Callable[[], Awaitable[List[Dict[str, Any]]]],
        max_wait: Optional[float] = None,
        poll_interval: Optional[float] = None,
    ) -> Tuple[bool, List[Dict[str, Any]]]:
        """Poll window list until it stabilizes (no new/closed windows).

        Returns (stable, last_window_list).
        """
        max_wait = max_wait or self.config.stabilization_max_wait
        poll_interval = poll_interval or self.config.stabilization_poll_interval
        min_stable = self.config.stabilization_min_stable_frames

        stable_count = 0
        prev_windows: List[str] = []
        start = asyncio.get_event_loop().time()

        while (asyncio.get_event_loop().time() - start) < max_wait:
            try:
                windows = await window_list_fn()
                if not isinstance(windows, list):
                    windows = windows.result.get("windows", []) if hasattr(windows, "result") else []
                current_titles = sorted([w.get("title", "") for w in windows if w.get("title")])
                if current_titles == prev_windows:
                    stable_count += 1
                    if stable_count >= min_stable:
                        return True, windows
                else:
                    stable_count = 0
                    prev_windows = current_titles
            except Exception as e:
                logger.debug(f"[ActionStabilizer] Window stability check failed: {e}")
            await asyncio.sleep(poll_interval)

        logger.warning(f"[ActionStabilizer] Window list did not stabilize within {max_wait}s")
        try:
            last_windows = await window_list_fn()
            if not isinstance(last_windows, list):
                last_windows = last_windows.result.get("windows", []) if hasattr(last_windows, "result") else []
        except Exception:
            last_windows = []
        return False, last_windows

    # ── Tree hash stabilization ──

    async def wait_for_tree_stability(
        self,
        tree_hash_fn: Callable[[], Awaitable[str]],
        max_wait: Optional[float] = None,
        poll_interval: Optional[float] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Poll accessibility tree hash until it stabilizes.

        Returns (stable, last_tree_hash).
        """
        max_wait = max_wait or self.config.stabilization_max_wait
        poll_interval = poll_interval or self.config.stabilization_poll_interval
        min_stable = self.config.stabilization_min_stable_frames

        stable_count = 0
        prev_hash: Optional[str] = None
        start = asyncio.get_event_loop().time()

        while (asyncio.get_event_loop().time() - start) < max_wait:
            try:
                current_hash = await tree_hash_fn()
                if current_hash == prev_hash and current_hash is not None:
                    stable_count += 1
                    if stable_count >= min_stable:
                        return True, current_hash
                else:
                    stable_count = 0
                    prev_hash = current_hash
            except Exception as e:
                logger.debug(f"[ActionStabilizer] Tree stability check failed: {e}")
            await asyncio.sleep(poll_interval)

        logger.warning(f"[ActionStabilizer] Tree hash did not stabilize within {max_wait}s")
        return False, prev_hash

    # ── Semantic verification ──

    async def verify_expected_state(
        self,
        expected_state_fn: Callable[[], Awaitable[Tuple[bool, str]]],
        timeout: Optional[float] = None,
        poll_interval: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Verify that the UI is in the expected semantic state.

        expected_state_fn should return (passed, notes).
        """
        timeout = timeout or self.config.verification_timeout
        poll_interval = poll_interval or self.config.verification_poll_interval
        start = asyncio.get_event_loop().time()

        while (asyncio.get_event_loop().time() - start) < timeout:
            try:
                passed, notes = await expected_state_fn()
                if passed:
                    return {"passed": True, "notes": notes}
            except Exception as e:
                logger.debug(f"[ActionStabilizer] Expected state check failed: {e}")
            await asyncio.sleep(poll_interval)

        return {"passed": False, "notes": "Expected state not achieved within timeout"}

    # ── Popup/modal detection ──

    async def detect_popup_window(self, window_list_fn: Callable[[], Awaitable[List[Dict[str, Any]]]]) -> Optional[Dict[str, Any]]:
        """Check for unexpected foreground popup/modal windows.

        Returns the popup window info if detected, else None.
        """
        if not self.config.popup_check_enabled:
            return None
        try:
            windows = await window_list_fn()
            if not isinstance(windows, list):
                windows = windows.result.get("windows", []) if hasattr(windows, "result") else []
        except Exception as e:
            logger.debug(f"[ActionStabilizer] Window list failed: {e}")
            return None

        for win in windows:
            title = (win.get("title") or "").lower()
            class_name = (win.get("class_name") or "").lower()
            # Heuristic: common popup keywords
            popup_keywords = ["save as", "open", "confirm", "warning", "error", "permission",
                              "update", "install", "blocked", "captcha", "login", "sign in",
                              "are you sure", "delete", "replace"]
            if any(kw in title for kw in popup_keywords):
                return win
            if class_name in {c.lower() for c in self.config.popup_window_classes}:
                return win
        return None

    # ── Popup dismissal ──

    async def dismiss_popup(
        self,
        screenshot_fn: Callable[[Optional[str]], Awaitable[Any]],
        click_fn: Callable[[int, int], Awaitable[Any]],
        press_key_fn: Callable[[str], Awaitable[Any]],
        window_list_fn: Optional[Callable[[], Awaitable[List[Dict[str, Any]]]]] = None,
    ) -> Dict[str, Any]:
        """Try to dismiss a detected popup window.

        Strategies (in order):
        1. Press Escape key
        2. Click at screen center (dialog dismiss outside)
        3. Press Alt+F4
        4. Press Tab + Enter (navigate to cancel/OK button)

        After each strategy, if window_list_fn is provided, the stabilizer
        verifies that the popup is actually gone before returning success.

        Returns: {"dismissed": bool, "method": str, "reason": Optional[str]}
        """
        strategies = [
            ("escape", lambda: press_key_fn("escape")),
            ("click_center", lambda: click_fn(960, 540)),  # common center resolutions
            ("alt_f4", lambda: press_key_fn("alt+f4")),
            ("tab_enter", lambda keys=press_key_fn: self._tab_enter_dismiss(keys)),
        ]

        for method_name, strategy_fn in strategies:
            try:
                # Execute the dismissal action
                await strategy_fn()
                # Wait 300ms for UI to settle
                await asyncio.sleep(0.3)
                # Take a screenshot (don't need the path, just need fresh capture)
                ss_path = os.path.join(
                    tempfile.gettempdir(),
                    f"dismiss_check_{method_name}_{datetime.utcnow().timestamp()}.png",
                )
                await screenshot_fn(ss_path)
                # NFR3: Verify popup is actually gone before claiming success
                if window_list_fn is not None:
                    remaining = await self.detect_popup_window(window_list_fn)
                    if remaining:
                        logger.info(
                            f"[ActionStabilizer] Popup still present after {method_name}, "
                            f"trying next strategy"
                        )
                        continue
                logger.info(f"[ActionStabilizer] Popup dismissed successfully: method={method_name}")
                return {"dismissed": True, "method": method_name}
            except Exception as e:
                logger.debug(f"[ActionStabilizer] Dismissal method '{method_name}' failed: {e}")
                continue

        logger.warning("[ActionStabilizer] All popup dismissal strategies failed")
        return {"dismissed": False, "method": "none", "reason": "popup_still_present"}

    async def _tab_enter_dismiss(self, press_key_fn: Callable[[str], Awaitable[Any]]) -> None:
        """Helper: Press Tab then Enter to navigate to a dialog's default button."""
        await press_key_fn("tab")
        await asyncio.sleep(0.1)
        await press_key_fn("enter")

    # ── Retry orchestration ──

    async def execute_with_retry(
        self,
        action_name: str,
        action_fn: Callable[[], Awaitable[Any]],
        params: Dict[str, Any],
        screenshot_fn: Callable[[Optional[str]], Awaitable[Any]],
        tree_hash_fn: Callable[[], Awaitable[str]],
        window_list_fn: Callable[[], Awaitable[List[Dict[str, Any]]]],
        element_map_fn: Callable[[], Dict[int, Dict[str, Any]]],
        selected_target: Optional[Dict[str, Any]] = None,
        verify: bool = True,
        stabilize: bool = True,
        expected_state_fn: Optional[Callable[[], Awaitable[Tuple[bool, str]]]] = None,
    ) -> Tuple[Any, ActionSnapshot]:
        """Execute an action with full stabilization, verification, retry chain.

        Args:
            expected_state_fn: Optional async callable that returns (passed, notes)
                               for semantic verification of the expected outcome.

        Returns (action_result, snapshot).
        """
        # Use action-specific config overrides
        action_config = self.config.get_for_action(action_name)
        max_retries = action_config.max_retries
        last_error: Optional[str] = None
        last_result: Any = None

        for attempt in range(max_retries + 1):
            snapshot = ActionSnapshot(
                timestamp=datetime.utcnow().isoformat(),
                action_name=action_name,
                params=params,
                before_screenshot_path=None,
                after_screenshot_path=None,
                before_tree_hash=None,
                after_tree_hash=None,
                before_element_map={},
                selected_target=selected_target,
                retry_count=attempt,
                error=None,
                expected_outcome=expected_state_fn.__name__ if expected_state_fn else None,
                actual_outcome=None,
                semantic_verified=False,
                semantic_notes=None,
            )

            # ── Pre-action: capture state ──
            try:
                snapshot.before_element_map = element_map_fn()
            except Exception as e:
                logger.debug(f"[ActionStabilizer] Could not capture element map: {e}")

            try:
                snapshot.before_tree_hash = await tree_hash_fn()
            except Exception as e:
                logger.debug(f"[ActionStabilizer] Could not capture tree hash: {e}")

            # Screenshot before
            before_path = os.path.join(tempfile.gettempdir(), f"before_{action_name}_{datetime.utcnow().timestamp()}.png")
            sc_result = await screenshot_fn(before_path)
            if getattr(sc_result, "success", True):
                snapshot.before_screenshot_path = before_path

            # ── Pre-action: stabilization ──
            if stabilize:
                # Screenshot stabilization
                stable, stable_path = await self.wait_for_ui_stability(
                    screenshot_fn,
                    max_wait=action_config.stabilization_max_wait,
                    poll_interval=action_config.stabilization_poll_interval,
                )
                if stable_path:
                    snapshot.before_screenshot_path = stable_path
                if not stable:
                    logger.warning(f"[ActionStabilizer] Proceeding with unstable UI for {action_name}")

                # Window list stabilization (for app launch / focus actions)
                if action_name in {"open_application", "launch_app_and_open_file", "focus_window", "ensure_focus"}:
                    win_stable, _ = await self.wait_for_window_stability(
                        window_list_fn,
                        max_wait=action_config.stabilization_max_wait,
                        poll_interval=action_config.stabilization_poll_interval,
                    )
                    if not win_stable:
                        logger.warning(f"[ActionStabilizer] Window list unstable before {action_name}")

                # Tree stabilization (for element interactions)
                if action_name in {"click_element", "type_element", "focus_and_interact", "click", "type_text", "press_key"}:
                    tree_stable, _ = await self.wait_for_tree_stability(
                        tree_hash_fn,
                        max_wait=action_config.stabilization_max_wait,
                        poll_interval=action_config.stabilization_poll_interval,
                    )
                    if not tree_stable:
                        logger.warning(f"[ActionStabilizer] Tree hash unstable before {action_name}")

            # ── Pre-action: popup check ──
            popup = await self.detect_popup_window(window_list_fn)
            if popup:
                logger.warning(f"[ActionStabilizer] Detected popup before action: {popup.get('title')}")
                snapshot.error = f"Popup detected: {popup.get('title')}"
                self._log_action_truth(snapshot, last_result, "POPUP_BLOCKED")
                if snapshot.before_screenshot_path and os.path.exists(snapshot.before_screenshot_path):
                    try:
                        os.remove(snapshot.before_screenshot_path)
                    except Exception:
                        pass
                return last_result, snapshot

            # ── Execute action ──
            try:
                last_result = await action_fn()
            except Exception as e:
                last_error = str(e)
                snapshot.error = last_error
                logger.error(f"[ActionStabilizer] Action {action_name} attempt {attempt} failed: {e}")
                self._log_action_truth(snapshot, last_result, "EXECUTION_ERROR")
                if snapshot.before_screenshot_path and os.path.exists(snapshot.before_screenshot_path):
                    try:
                        os.remove(snapshot.before_screenshot_path)
                    except Exception:
                        pass
                if attempt < max_retries:
                    self.add_snapshot(snapshot)
                    self.detect_infinite_loop()
                    backoff = action_config.retry_backoff_base * (2 ** attempt)
                    logger.info(f"[ActionStabilizer] Retrying {action_name} in {backoff}s...")
                    await asyncio.sleep(backoff)
                    continue
                else:
                    return last_result, snapshot

            # ── Post-action: capture state ──
            after_path = os.path.join(tempfile.gettempdir(), f"after_{action_name}_{datetime.utcnow().timestamp()}.png")
            sc_result = await screenshot_fn(after_path)
            if getattr(sc_result, "success", True):
                snapshot.after_screenshot_path = after_path

            try:
                snapshot.after_tree_hash = await tree_hash_fn()
            except Exception as e:
                logger.debug(f"[ActionStabilizer] Could not capture after tree hash: {e}")

            # ── Post-action: structural verification ──
            structural_changed = True  # Assume changed if we skip verification
            if verify and snapshot.before_screenshot_path:
                verification = await self.verify_state_change(
                    before_screenshot_path=snapshot.before_screenshot_path,
                    before_tree_hash=snapshot.before_tree_hash,
                    screenshot_fn=screenshot_fn,
                    tree_hash_fn=tree_hash_fn,
                    timeout=action_config.verification_timeout,
                    poll_interval=action_config.verification_poll_interval,
                )
                snapshot.verification_result = verification
                structural_changed = verification.get("changed", True)
                if not structural_changed:
                    logger.warning(f"[ActionStabilizer] No state change detected after {action_name}")
                    snapshot.actual_outcome = "No structural state change detected"
                    self._log_action_truth(snapshot, last_result, "NO_STATE_CHANGE")
                    if snapshot.before_screenshot_path and os.path.exists(snapshot.before_screenshot_path):
                        try:
                            os.remove(snapshot.before_screenshot_path)
                        except Exception:
                            pass
                    if attempt < max_retries:
                        self.add_snapshot(snapshot)
                        self.detect_infinite_loop()
                        backoff = action_config.retry_backoff_base * (2 ** attempt)
                        logger.info(f"[ActionStabilizer] Retrying {action_name} (no state change) in {backoff}s...")
                        await asyncio.sleep(backoff)
                        continue
                    else:
                        # Exhausted retries with no state change
                        return last_result, snapshot

            # ── Post-action: semantic verification ──
            semantic_passed = True
            semantic_notes = "No semantic check requested"
            if expected_state_fn is not None:
                semantic = await self.verify_expected_state(
                    expected_state_fn,
                    timeout=action_config.verification_timeout,
                    poll_interval=action_config.verification_poll_interval,
                )
                semantic_passed = semantic.get("passed", False)
                semantic_notes = semantic.get("notes", "")
                snapshot.semantic_verified = semantic_passed
                snapshot.semantic_notes = semantic_notes
                if not semantic_passed:
                    logger.warning(f"[ActionStabilizer] Semantic verification failed after {action_name}: {semantic_notes}")
                    snapshot.actual_outcome = f"Semantic check failed: {semantic_notes}"
                    self._log_action_truth(snapshot, last_result, "SEMANTIC_FAIL")
                    if snapshot.before_screenshot_path and os.path.exists(snapshot.before_screenshot_path):
                        try:
                            os.remove(snapshot.before_screenshot_path)
                        except Exception:
                            pass
                    if attempt < max_retries:
                        self.add_snapshot(snapshot)
                        self.detect_infinite_loop()
                        backoff = action_config.retry_backoff_base * (2 ** attempt)
                        logger.info(f"[ActionStabilizer] Retrying {action_name} (semantic fail) in {backoff}s...")
                        await asyncio.sleep(backoff)
                        continue
                    else:
                        return last_result, snapshot
                else:
                    snapshot.actual_outcome = f"Semantic check passed: {semantic_notes}"

            # ── Success path ──
            if snapshot.before_screenshot_path and os.path.exists(snapshot.before_screenshot_path):
                try:
                    os.remove(snapshot.before_screenshot_path)
                except Exception:
                    pass
            snapshot.error = None
            self._log_action_truth(snapshot, last_result, "SUCCESS")
            return last_result, snapshot

        # Exhausted retries
        if snapshot.before_screenshot_path and os.path.exists(snapshot.before_screenshot_path):
            try:
                os.remove(snapshot.before_screenshot_path)
            except Exception:
                pass
        self._log_action_truth(snapshot, last_result, "EXHAUSTED_RETRIES")
        return last_result, snapshot

    def _log_action_truth(self, snapshot: ActionSnapshot, result: Any, status: str) -> None:
        """Log structured action truth for observability and debugging.

        Format:
            ACTION: <name>
            EXPECTED: <expected outcome description>
            ACTUAL: <actual outcome>
            VERIFICATION: struct=<bool> semantic=<bool>
            RETRY: <count>
            RESULT: <status>
        """
        action = snapshot.action_name
        expected = snapshot.expected_outcome or "(not specified)"
        actual = snapshot.actual_outcome or "(pending)"
        struct_ok = snapshot.verification_result.get("changed", True) if snapshot.verification_result else True
        semantic_ok = snapshot.semantic_verified
        retry = snapshot.retry_count
        error = snapshot.error or "none"

        logger.info(
            f"[ACTION_TRUTH] "
            f"ACTION={action} | "
            f"EXPECTED={expected} | "
            f"ACTUAL={actual} | "
            f"VERIFICATION=struct:{struct_ok}_semantic:{semantic_ok} | "
            f"RETRY={retry} | "
            f"STATUS={status} | "
            f"ERROR={error}"
        )

    # ── Snapshot history management ──

    def add_snapshot(self, snapshot: ActionSnapshot) -> None:
        self._snapshot_history.append(snapshot)
        # Keep last 50 snapshots to prevent memory bloat
        if len(self._snapshot_history) > 50:
            old = self._snapshot_history.pop(0)
            self._cleanup_snapshot(old)

    def get_snapshot_history(self) -> List[ActionSnapshot]:
        return list(self._snapshot_history)

    def get_last_snapshot(self) -> Optional[ActionSnapshot]:
        return self._snapshot_history[-1] if self._snapshot_history else None

    def _cleanup_snapshot(self, snapshot: ActionSnapshot) -> None:
        for path in [snapshot.before_screenshot_path, snapshot.after_screenshot_path]:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass

    def detect_infinite_loop(self, threshold: int = 3) -> None:
        """RR4: Abort if the same action on the same target fails threshold times with no state change."""
        if len(self._snapshot_history) < threshold:
            return
        recent = self._snapshot_history[-threshold:]
        first = recent[0]
        if all(
            s.action_name == first.action_name
            and s.params == first.params
            and not (s.verification_result or {}).get("changed", True)
            for s in recent
        ):
            raise RuntimeError(
                f"infinite loop detected: action='{first.action_name}' params={first.params} "
                f"failed {threshold} times with no state change. Aborting."
            )

    def clear_history(self) -> None:
        for old in self._snapshot_history:
            self._cleanup_snapshot(old)
        self._snapshot_history.clear()

    def cleanup_temp_screenshots(self, max_age: Optional[int] = None) -> int:
        """Remove orphaned temp screenshots older than configured age.

        Removes files matching agentos_*, stab_*, verify_*, before_*, after_*
        patterns in the system temp directory.

        Args:
            max_age: Override the config's temp_screenshot_max_age_seconds.
                     Defaults to self.config.temp_screenshot_max_age_seconds.

        Returns the number of files removed.
        """
        import time as _time
        temp_dir = tempfile.gettempdir()
        patterns = ("agentos_", "stab_", "verify_", "before_", "after_",
                     "dismiss_check_")
        max_age = max_age if max_age is not None else self.config.temp_screenshot_max_age_seconds
        now = _time.time()
        removed = 0
        try:
            for fname in os.listdir(temp_dir):
                if not any(fname.startswith(p) for p in patterns):
                    continue
                fpath = os.path.join(temp_dir, fname)
                try:
                    if os.path.isfile(fpath) and (now - os.path.getmtime(fpath)) > max_age:
                        os.remove(fpath)
                        removed += 1
                except Exception:
                    pass
        except Exception:
            pass
        if removed:
            logger.info(f"[ActionStabilizer] Cleaned up {removed} orphaned temp screenshots")
        return removed
