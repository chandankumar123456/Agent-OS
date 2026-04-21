from .base import AgentInput, AgentOutput, AgentRole, AgentStatus
from uuid import uuid4


class DummyAgent:
    name: str = "dummy_agent"
    role: AgentRole = AgentRole.EXECUTOR
    
    async def execute(self, input_data: AgentInput) -> AgentOutput:
        query = input_data.input_data.get("query", "")
        
        return AgentOutput(
            task_id=input_data.task_id,
            step_id=input_data.step_id,
            status=AgentStatus.SUCCESS,
            output_data={
                "result": f"processed: {query}",
                "steps_completed": 1
            },
            confidence=1.0,
            reasoning_trace=[
                f"Received query: {query}",
                "Processing query through dummy agent",
                "Returning processed result"
            ]
        )