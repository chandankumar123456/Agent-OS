from .base import AgentInput, AgentOutput, AgentRole, AgentStatus
from uuid import uuid4
from typing import List, Dict, Any
from .llm_client import llm_client
from ..logs.logger import logger


EXECUTOR_PROMPT = """You are an Executor agent for Agent-OS. Your role is to execute specific steps from a plan.

Given a step description and context, perform the action and return results.

Step: {step}
Context: {context}

Return your response as JSON:
{{"result": "what you found or produced", "details": "additional information"}}"""


class ExecutorAgent:
    name: str = "executor"
    role: AgentRole = AgentRole.EXECUTOR
    
    async def execute(self, input_data: AgentInput) -> AgentOutput:
        step = input_data.input_data.get("step", "")
        context = input_data.context
        
        logger.info(f"Executor executing step: {step}")
        
        messages = [
            {"role": "system", "content": EXECUTOR_PROMPT.format(step=step, context=context)}
        ]
        
        try:
            result = await llm_client.complete_json(messages)
            
            return AgentOutput(
                task_id=input_data.task_id,
                step_id=input_data.step_id,
                status=AgentStatus.SUCCESS,
                output_data=result,
                confidence=0.85,
                reasoning_trace=[
                    f"Executed step: {step}",
                    f"Result: {result.get('result', 'completed')}"
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