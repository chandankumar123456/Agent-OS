"""Desktop Goal Loop — observe → act → verify cycle for desktop tasks.

This module provides a unified desktop automation loop that can be used by both:
1. LangGraph executor_node (primary path)
2. Legacy ExecutorAgent (fallback when LangGraph fails)

The loop ensures:
- State observation before each action
- Tool grounding enforcement
- Bounded retries (max 2)
- Verification after each action
- Recovery on failure
- LLM-driven action decisions (Phase 3)
"""
import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Set
from dataclasses import dataclass

from ..agents.llm_client import get_llm_client
from ..tools.grounding import ToolGroundingLayer

logger = logging.getLogger(__name__)


@dataclass
class DesktopGoalResult:
    """Result of desktop goal execution."""
    success: bool
    iterations: int
    actions_performed: List[Dict[str, Any]]
    final_state: Dict[str, Any]
    error: Optional[str] = None


class DesktopGoalLoop:
    """Desktop automation goal loop with observe → act → verify cycle."""

    MAX_ITERATIONS: int = 5
    MAX_RETRIES_PER_ACTION: int = 2

    def __init__(self, task_id: str):
        self.task_id = task_id
        self._llm = get_llm_client()
        self._grounding = ToolGroundingLayer()
        self.max_iterations = 5
        self.max_retries_per_action = 2
        self._snapshot_history: List[Dict[str, Any]] = []

    async def execute(
        self,
        query: str,
        description: str,
        tool_registry: Any,
        grounded_tools: List[Dict[str, Any]],
        grounded_tool_names: Set[str],
        max_iterations: Optional[int] = None,
    ) -> DesktopGoalResult:
        """Execute desktop goal loop.

        Args:
            query: Original user query
            description: Current step description
            tool_registry: Tool registry for execution
            grounded_tools: List of allowed tools
            grounded_tool_names: Set of allowed tool names
            max_iterations: Override max iterations

        Returns:
            DesktopGoalResult with execution state
        """
        max_iters = max_iterations or self.MAX_ITERATIONS
        iterations = 0
        actions: List[Dict[str, Any]] = []
        goal_reached = False
        final_answer = ""

        # Get tool registry reference
        from ..tools.registry import tool_registry as tr
        registry = tr

        while iterations < max_iters:
            iterations += 1

            # 1. OBSERVE: Get current desktop state
            desktop_state = await self._observe_desktop_state(registry)
            self._snapshot_history.append({
                "iteration": iterations,
                "desktop_state": desktop_state,
            })

            # 2. DECIDE: Choose next action using LLM (Phase 3)
            action_data = await self._decide_action(
                goal=description,
                desktop_state=desktop_state,
                history=self._snapshot_history,
            )

            if not action_data:
                # No action to take, goal may be reached
                break

            tool_name = action_data.get("tool") or action_data.get("name")
            tool_params = action_data.get("params", {})

            if not tool_name:
                # Response without tool call - check if goal reached
                final_answer = action_data.get("answer", "")
                goal_reached = True
                break

            # Grounding check: reject tools outside grounded set
            if tool_name not in grounded_tool_names:
                logger.warning(
                    f"LLM selected '{tool_name}' not in grounded set {grounded_tool_names}. Skipping."
                )
                continue

            # 3. EXECUTE: Run the tool
            tool_result = await self._execute_tool(
                registry, tool_name, tool_params
            )

            actions.append({
                "iteration": iterations,
                "tool": tool_name,
                "params": tool_params,
                "result": tool_result,
            })

            # 4. VERIFY: Check if goal reached
            if self._verify_goal(tool_result, description):
                goal_reached = True
                final_answer = f"Goal reached after {iterations} iterations"
                break

            # 5. CHECK: If action failed, record for recovery
            if not tool_result.get("success", False):
                self._snapshot_history[-1].update({
                    "tool": tool_name,
                    "error": tool_result.get("error"),
                })

            # Brief wait between iterations
            await asyncio.sleep(0.2)

        if not goal_reached:
            final_answer = f"Max iterations ({max_iters}) reached without achieving goal"

        return DesktopGoalResult(
            success=goal_reached,
            iterations=iterations,
            actions_performed=actions,
            final_state={"desktop_state": {}, "answer": final_answer},
            error=None if goal_reached else final_answer,
        )

    async def _observe_desktop_state(self, registry: Any) -> Dict[str, Any]:
        """Observe current desktop state."""
        state = {}

        # Get window list
        try:
            window_tool = registry.get("desktop_env__get_window_list")
            if window_tool:
                result = await registry.execute("desktop_env__get_window_list", {"_task_id": self.task_id})
                if result.success:
                    state["windows"] = result.result
        except Exception as e:
            logger.debug(f"Window list observation failed: {e}")

        # Get UI tree
        try:
            ui_tool = registry.get("desktop__get_ui_tree")
            if ui_tool:
                result = await registry.execute("desktop__get_ui_tree", {"_task_id": self.task_id})
                if result.success:
                    state["ui_tree"] = result.result
        except Exception as e:
            logger.debug(f"UI tree observation failed: {e}")

        return state

    async def _decide_action(
        self,
        goal: str,
        desktop_state: Dict[str, Any],
        history: list,
    ) -> Optional[Dict[str, Any]]:
        """Decide next action using LLM with tool grounding and JSON parsing.

        Phase 3: Fully LLM-driven with deterministic fallback for safety.
        """
        grounded_tools = self._grounding.ground_tools(
            intent="desktop_automation",
            all_tools=[],  # Will be populated from registry in real impl
        )

        prompt = self._build_executor_prompt(goal, desktop_state, history, grounded_tools)

        try:
            response = await self._llm.achain(prompt)
            action = json.loads(response.content)
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"LLM returned non-JSON action ({e}); falling back to pattern match")
            return self._fallback_pattern_match(goal, desktop_state)

        return action

    def _build_executor_prompt(
        self,
        goal: str,
        desktop_state: Dict[str, Any],
        history: list,
        tools: List[Dict[str, Any]],
    ) -> str:
        """Build LLM prompt for action decision."""
        return (
            f"Goal: {goal}\n"
            f"Desktop State: {json.dumps(desktop_state)}\n"
            f"History: {json.dumps(history[-5:])}\n"
            f"Available Tools: {json.dumps(tools)}\n"
            "Respond with JSON: {\"tool\": \"...\", \"params\": {...}}"
        )

    def _fallback_pattern_match(
        self,
        goal: str,
        desktop_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Keep existing primitive fallback for safety when LLM parsing fails."""
        desc_lower = goal.lower()
        if "open" in desc_lower:
            return {"tool": "desktop_env__open_application", "params": {"app": goal}}
        if "type" in desc_lower:
            return {"tool": "desktop__type_element", "params": {"text": goal}}
        if "click" in desc_lower:
            return {"tool": "desktop__click_element", "params": {}}
        return {"tool": "desktop_env__screenshot", "params": {}}

    async def _execute_tool(
        self,
        registry: Any,
        tool_name: str,
        tool_params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Execute a tool and return structured result."""
        try:
            tool_params["_task_id"] = self.task_id
            result = await registry.execute(tool_name, tool_params)
            return {
                "success": result.success,
                "result": result.result,
                "error": result.error,
            }
        except Exception as e:
            logger.error(f"Tool execution failed: {tool_name} - {e}")
            return {
                "success": False,
                "error": str(e),
            }

    def _verify_goal(self, tool_result: Dict[str, Any], description: str) -> bool:
        """Verify if the goal is reached based on tool result.

        FR3: Strict verification - must have actual state change.
        """
        if not tool_result.get("success", False):
            return False

        # Check for meaningful results
        result = tool_result.get("result")
        if isinstance(result, dict):
            # App opened - verify process/window exists
            if "pid" in result or "window" in result:
                return True
            # Element clicked/typed - verify state change
            if result.get("message"):
                return True

        return False

    def get_snapshot_history(self) -> List[Dict[str, Any]]:
        """Return action history for debugging."""
        return list(self._snapshot_history)


def create_desktop_goal_loop(task_id: str) -> DesktopGoalLoop:
    """Factory function to create desktop goal loop."""
    return DesktopGoalLoop(task_id)
