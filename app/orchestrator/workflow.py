from typing import Dict, Any, List


class WorkflowEngine:
    def __init__(self):
        pass
    
    async def plan(
        self,
        query: str,
        context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        return [
            {"step": "analyze task", "agent_type": "executor", "depends_on": []},
            {"step": "process request", "agent_type": "executor", "depends_on": [0]},
            {"step": "finalize result", "agent_type": "executor", "depends_on": [1]}
        ]
    
    def _break_into_steps(self, query: str) -> List[str]:
        return [
            f"analyze: {query}",
            f"process: {query}",
            f"finalize: {query}"
        ]