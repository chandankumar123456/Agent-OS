import json
from .base import AgentInput, AgentOutput, AgentRole, AgentStatus
from uuid import uuid4
from typing import List, Dict, Any
from .llm_client import llm_client
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
{{"result": "...", "tool_call": {{"name": "tool_name", "params": {{"param1": "value1"}}}}}

If no tool is needed, return:
{{"result": "what you found or produced", "details": "additional information"}}"""


class ExecutorAgent:
    name: str = "executor"
    role: AgentRole = AgentRole.EXECUTOR
    MAX_TOOL_ROUNDS: int = 3

    async def execute(self, input_data: AgentInput) -> AgentOutput:
        step = input_data.input_data.get("step", "")
        context = input_data.context
        tools_schema = input_data.input_data.get("tools", [])

        logger.info(f"Executor executing step: {step}")

        messages = [
            {"role": "system", "content": EXECUTOR_PROMPT.format(
                step=step,
                context=context,
                tools=json.dumps(tools_schema, indent=2) if tools_schema else "No tools available"
            )}
        ]

        try:
            final_result = None
            for round_num in range(self.MAX_TOOL_ROUNDS):
                result = await llm_client.complete_json(messages)
                final_result = result

                # Check for tool call
                tool_call = ToolCallParser.parse(result)
                if not tool_call:
                    break

                tool_name = tool_call["name"]
                tool_params = tool_call["params"]
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

