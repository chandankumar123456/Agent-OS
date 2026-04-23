from typing import Dict, Any
from ..agents.planner import PlannerAgent
from ..agents.executor import ExecutorAgent
from ..agents.verifier import VerifierAgent
from ..agents.base import BaseAgent
from ..logs.logger import logger


class AgentFactory:
    """Creates BaseAgent implementations from DB config."""

    def create_agent(self, agent_type: str, config: Dict[str, Any]):
        """Create an agent instance based on type and config."""
        agent_type = agent_type.lower()

        if agent_type == "planner":
            return PlannerAgent()
        elif agent_type == "executor":
            return ExecutorAgent()
        elif agent_type == "verifier":
            return VerifierAgent()
        elif agent_type == "custom":
            # For custom agents, create an ExecutorAgent with custom system prompt
            agent = ExecutorAgent()
            if config.get("system_prompt"):
                # Store custom prompt for use in execution
                agent._custom_prompt = config["system_prompt"]
            return agent
        else:
            logger.warning(f"Unknown agent type {agent_type}, defaulting to executor")
            return ExecutorAgent()
