"""Action V1 Deterministic Verification Layer.

After each action, verify whether the expected state change happened.
If deterministic verification succeeds, DO NOT invoke LLM verification.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List

from .models import Capability, ExecutionContext, ActionResult, ActionStatus
from ..tools.registry import tool_registry
from ..logs.logger import logger


class DeterministicVerifier:
    """Verifies execution results using deterministic checks."""

    async def verify(self, ctx: ExecutionContext, result: ActionResult) -> ActionResult:
        """Run deterministic verification and mutate result in place."""
        if ctx.capability == Capability.FILESYSTEM:
            verified = await self._verify_filesystem(result)
        elif ctx.capability == Capability.BROWSER:
            verified = await self._verify_browser(result)
        elif ctx.capability == Capability.DESKTOP:
            verified = await self._verify_desktop(result)
        else:
            verified = True  # General / multi-step: trust step results

        result.verification_passed = verified
        if not verified and result.status == ActionStatus.SUCCESS:
            result.status = ActionStatus.PARTIAL

        logger.info(f"[ActionV1] DeterministicVerifier: verified={verified} for task={ctx.task_id}")
        return result

    async def _verify_filesystem(self, result: ActionResult) -> bool:
        """Verify file operations by checking file existence."""
        output = result.output
        if isinstance(output, dict) and output.get("file_path"):
            path = output["file_path"]
            exists = os.path.exists(path)
            if exists:
                size = os.path.getsize(path)
                logger.info(f"[ActionV1] File verification: {path} exists ({size} bytes)")
                return True
            logger.warning(f"[ActionV1] File verification: {path} does NOT exist")
            return False
        # For list/read operations, success flag is sufficient
        return True

    async def _verify_browser(self, result: ActionResult) -> bool:
        """Verify browser state by trusting successful tool responses.
        
        Only falls back to URL check if no successful navigation step is recorded.
        """
        steps = result.steps_executed
        had_successful_nav = any(
            s.get("tool") in ("browser_env__navigate", "browser_env__search")
            and s.get("result", {}).get("success")
            for s in steps
        )
        if had_successful_nav:
            return True
        # Fallback: try to get current URL if tool exists
        try:
            url_check = await tool_registry.execute("browser_env__get_url", {"task_id": result.task_id})
            if url_check.success and url_check.result:
                logger.info(f"[ActionV1] Browser verification: URL={url_check.result}")
                return True
        except Exception as e:
            logger.debug(f"[ActionV1] Browser verification failed: {e}")
        return False

    async def _verify_desktop(self, result: ActionResult) -> bool:
        """Verify desktop state by trusting successful tool responses.
        
        If open_application or type_text succeeded, the goal is reached.
        Only falls back to window list if no successful desktop step is recorded.
        """
        steps = result.steps_executed
        had_successful_desktop = any(
            s.get("tool", "").startswith("desktop_env__")
            and s.get("result", {}).get("success")
            for s in steps
        )
        if had_successful_desktop:
            return True
        # Fallback: check window list
        try:
            win_check = await tool_registry.execute("desktop_env__get_window_list", {"_task_id": result.task_id})
            if win_check.success and win_check.result:
                windows = win_check.result if isinstance(win_check.result, list) else []
                if windows:
                    logger.info(f"[ActionV1] Desktop verification: {len(windows)} windows open")
                    return True
        except Exception as e:
            logger.debug(f"[ActionV1] Desktop verification failed: {e}")
        return False
