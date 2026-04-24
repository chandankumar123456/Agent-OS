import json
from .base import AgentInput, AgentOutput, AgentRole, AgentStatus
from uuid import uuid4
from typing import List, Dict, Any, Optional
from .llm_client import get_llm_client
from ..logs.logger import logger
from ..tools.parser import ToolCallParser
from ..tools.registry import tool_registry


EXECUTOR_PROMPT = """You are an Executor agent for Agent-OS. Your role is to execute specific steps from a plan.

Given a step description, available tools, and context, perform the action and return results.

Available Tools:
{tools}

Step: {step}
Context: {context}

If you need to use a tool, return JSON with a tool_call:
{{"result": "...", "tool_call": {{"name": "tool_name", "params": {{"param1": "value1"}}}}}}

If no tool is needed, return:
{{"result": "what you found or produced", "details": "additional information"}}"""


class ExecutorAgent:
    name: str = "executor"
    role: AgentRole = AgentRole.EXECUTOR
    MAX_TOOL_ROUNDS: int = 3
    allowed_tools: Optional[List[str]] = None

    def _get_allowed_tools(self, input_data: AgentInput) -> Optional[List[str]]:
        """Determine allowed tools from agent config or input. None means allow all."""
        if input_data.allowed_tools is not None:
            return input_data.allowed_tools
        return self.allowed_tools

    def _filter_tools(self, tools_schema: List[Dict[str, Any]], allowed: Optional[List[str]]) -> List[Dict[str, Any]]:
        if allowed is None:
            return tools_schema
        allowed_set = set(allowed)
        return [t for t in tools_schema if t.get("name") in allowed_set]

    async def execute(self, input_data: AgentInput) -> AgentOutput:
        step = input_data.input_data.get("step", "")
        context = input_data.context
        tools_schema = input_data.input_data.get("tools", [])
        allowed = self._get_allowed_tools(input_data)
        visible_tools = self._filter_tools(tools_schema, allowed)

        logger.info(f"Executor executing step: {step}")

        # Use custom prompt if configured, otherwise default
        custom_prompt = getattr(self, "_custom_prompt", None)
        if custom_prompt:
            system_prompt = custom_prompt.format(
                step=step,
                context=context,
                tools=json.dumps(visible_tools, indent=2) if visible_tools else "No tools available"
            )
        else:
            system_prompt = EXECUTOR_PROMPT.format(
                step=step,
                context=context,
                tools=json.dumps(visible_tools, indent=2) if visible_tools else "No tools available"
            )

        messages = [
            {"role": "system", "content": system_prompt}
        ]

        try:
            final_result = None
            for round_num in range(self.MAX_TOOL_ROUNDS):
                result = await get_llm_client().complete_json(messages)
                final_result = result

                # Check for tool call
                tool_call = ToolCallParser.parse(result)
                if not tool_call:
                    break

                tool_name = tool_call["name"]
                tool_params = tool_call["params"]

                # Enforce tool access control
                if allowed is not None and tool_name not in allowed:
                    logger.warning(f"Tool access denied: '{tool_name}' not in allowed tools {allowed}")
                    error_msg = f"Tool '{tool_name}' is not authorized for this agent."
                    messages.append({"role": "assistant", "content": json.dumps(result)})
                    messages.append({
                        "role": "system",
                        "content": f"Error: {error_msg} Please use only allowed tools."
                    })
                    continue

                logger.info(f"Executor invoking tool: {tool_name} with params: {tool_params}")

                # Execute tool
                tool_output = await tool_registry.execute(tool_name, tool_params)

                if tool_output.success:
                    tool_result = tool_output.result
                else:
                    tool_result = {"error": tool_output.error}

                # Feed tool result back as assistant message
                messages.append({"role": "assistant", "content": json.dumps(result)})
                messages.append({
                    "role": "system",
                    "content": f"Tool '{tool_name}' returned: {json.dumps(tool_result)}. Continue with your analysis."
                })

                logger.info(f"Tool round {round_num + 1} completed for step: {step}")

            return AgentOutput(
                task_id=input_data.task_id,
                step_id=input_data.step_id,
                status=AgentStatus.SUCCESS,
                output_data=final_result,
                confidence=0.85,
                reasoning_trace=[
                    f"Executed step: {step}",
                    f"Result: {final_result.get('result', 'completed') if final_result else 'completed'}"
                ]
            )
        except Exception as e:
            logger.error(f"Executor failed: {e}")
            return AgentOutput(
                task_id=input_data.task_id,
                step_id=input_data.step_id,
                status=AgentStatus.FAILURE,
                error_type="execution_error",
                error_message=str(e),
                recoverable=True
            )

