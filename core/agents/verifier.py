from .base import AgentInput, AgentOutput, AgentRole, AgentStatus
from .llm_client import get_llm_client
from ..logs.logger import logger


VERIFIER_PROMPT = """You are a Verifier agent for Agent-OS. Your role is to validate outputs from other agents.

Review the output and determine if it meets quality standards:
- Is the result coherent and logical?
- Does it address the original task?
- Are there any obvious errors or hallucinations?

Output to verify: {output}
Original query: {query}

Return your response as JSON:
{{"valid": true/false, "confidence": 0.0-1.0, "issues": ["issue1", "issue2"], "feedback": "suggestions"}}"""


class VerifierAgent:
    name: str = "verifier"
    role: AgentRole = AgentRole.VERIFIER

    async def execute(self, input_data: AgentInput) -> AgentOutput:
        output = input_data.input_data.get("output", {})
        query = input_data.context.get("query", "")

        logger.info(f"Verifying output for query: {query}")

        messages = [
            {"role": "system", "content": VERIFIER_PROMPT.format(
                output=str(output),
                query=query
            )}
        ]

        try:
            result = await get_llm_client().complete_json(messages)
            if not isinstance(result, dict):
                raise ValueError("Verifier output must be an object")

            is_valid = bool(result.get("valid", False))
            confidence = float(result.get("confidence", 0.5))

            return AgentOutput(
                task_id=input_data.task_id,
                step_id=input_data.step_id,
                status=AgentStatus.SUCCESS if is_valid else AgentStatus.FAILURE,
                output_data=result,
                confidence=confidence,
                reasoning_trace=[
                    "Verified output",
                    f"Valid: {is_valid}",
                    f"Confidence: {confidence}"
                ]
            )
        except Exception as e:
            logger.error(f"Verifier failed: {e}")
            return AgentOutput(
                task_id=input_data.task_id,
                step_id=input_data.step_id,
                status=AgentStatus.FAILURE,
                output_data={"valid": False, "confidence": 0.0, "issues": [str(e)], "feedback": "verification failed"},
                confidence=0.5,
                error_type="verification_error",
                error_message=str(e),
                recoverable=True,
                reasoning_trace=["Verification failed"]
            )
