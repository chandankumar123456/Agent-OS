"""Action V1 Fallback Layers.

Vision Fallback: Only when deterministic execution fails.
Human Fallback: Pause and request user intervention for sensitive actions.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from .models import Capability, ExecutionContext, ActionResult, ActionStatus
from ..tools.registry import tool_registry
from ..logs.logger import logger


class VisionFallback:
    """Uses screenshots / OCR when deterministic execution fails.
    
    Action V1 principle: vision is FALLBACK ONLY.
    """

    def __init__(self, llm_client=None):
        self._llm_client = llm_client

    @property
    def _llm(self):
        if self._llm_client is None:
            from ..agents.llm_client import get_llm_client
            self._llm_client = get_llm_client()
        return self._llm_client

    async def attempt(self, ctx: ExecutionContext, result: ActionResult) -> ActionResult:
        """Try vision-based recovery using real screenshot tools."""
        logger.info(f"[ActionV1] VisionFallback triggered for task={ctx.task_id}")

        # Capture screenshot based on capability
        screenshot_tool = None
        screenshot_params: Dict[str, Any] = {}
        if ctx.capability == Capability.BROWSER:
            screenshot_tool = "browser_env__screenshot"
            screenshot_params = {"task_id": ctx.task_id}
        elif ctx.capability == Capability.DESKTOP:
            screenshot_tool = "desktop_env__screenshot"
            screenshot_params = {"_task_id": ctx.task_id}

        if screenshot_tool:
            try:
                screenshot_result = await tool_registry.execute(screenshot_tool, screenshot_params)
                if screenshot_result.success:
                    logger.info(f"[ActionV1] Screenshot captured via {screenshot_tool}")
                    result.output = result.output or {}
                    if isinstance(result.output, dict):
                        result.output["screenshot"] = screenshot_result.result
                else:
                    logger.warning(f"[ActionV1] Screenshot via {screenshot_tool} failed: {screenshot_result.error}")
            except Exception as e:
                logger.warning(f"[ActionV1] Screenshot execution failed: {e}")

        # Desktop: get UI tree for accessible text fallback
        if ctx.capability == Capability.DESKTOP:
            try:
                ui_tree = await tool_registry.execute("desktop__get_ui_tree", {"_task_id": ctx.task_id})
                if ui_tree.success:
                    logger.info(f"[ActionV1] UI tree captured for task={ctx.task_id}")
                    result.output = result.output or {}
                    if isinstance(result.output, dict):
                        result.output["ui_tree"] = ui_tree.result
            except Exception as e:
                logger.debug(f"[ActionV1] UI tree fallback failed: {e}")

        # Browser: get page text
        if ctx.capability == Capability.BROWSER:
            try:
                page_text = await tool_registry.execute("browser_env__get_text", {"task_id": ctx.task_id, "selector": "body"})
                if page_text.success:
                    logger.info(f"[ActionV1] Page text captured for task={ctx.task_id}")
                    result.output = result.output or {}
                    if isinstance(result.output, dict):
                        result.output["page_text"] = page_text.result
            except Exception as e:
                logger.debug(f"[ActionV1] Page text fallback failed: {e}")

        result.fallback_used = "vision"
        result.status = ActionStatus.NEEDS_VISION
        result.error = result.error or "Deterministic execution failed; vision fallback executed"
        return result


class HumanFallback:
    """Requests human intervention for dangerous or ambiguous actions.
    
    Triggers for: logins, OTP, payments, captcha, destructive actions.
    """

    DANGEROUS_KEYWORDS = {
        "delete", "remove", "drop", "destroy", "wipe", "rm -rf",
        "install", "uninstall", "systemctl", "chmod", "chown",
        "password", "secret", "token", "api_key", "private key",
        "payment", "credit card", "purchase", "buy",
        "login", "sign in", "authenticate", "captcha",
    }

    def should_intervene(self, query: str) -> bool:
        query_lower = query.lower()
        return any(kw in query_lower for kw in self.DANGEROUS_KEYWORDS)

    async def request(self, ctx: ExecutionContext, reason: str) -> ActionResult:
        """Return a result that signals human intervention is needed."""
        logger.warning(f"[ActionV1] HumanFallback requested for task={ctx.task_id}: {reason}")
        return ActionResult(
            status=ActionStatus.NEEDS_HUMAN,
            task_id=ctx.task_id,
            error=f"Human intervention required: {reason}",
            fallback_used="human",
        )
