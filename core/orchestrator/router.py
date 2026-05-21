from typing import Dict, List, Optional
from ..runtime.runtime import AgentRuntime
from ..logs.logger import logger


class AgentRouter:
    """Routes tasks to appropriate agents based on role/type with fallback support."""

    def __init__(self, runtime: AgentRuntime):
        self.runtime = runtime
        self._fallbacks: Dict[str, List[str]] = {
            "planner": ["core_planner"],
            "executor": ["core_executor"],
            "verifier": ["core_verifier"],
        }

    def register_fallback(self, role: str, fallback_chain: List[str]) -> None:
        """Register a fallback chain for a given role."""
        self._fallbacks[role] = fallback_chain

    def resolve(self, role: str) -> Optional[object]:
        """Resolve a role to an agent instance, trying fallback chain if needed."""
        chain = self._fallbacks.get(role, [f"core_{role}"])
        for agent_id in chain:
            worker = self.runtime.get(agent_id)
            if worker and getattr(worker, "agent_instance", None):
                logger.info(f"Router resolved role '{role}' to agent '{agent_id}'")
                return worker.agent_instance
        logger.warning(f"Router could not resolve role '{role}' using chain {chain}")
        return None

    def resolve_worker(self, role: str) -> Optional[object]:
        """Resolve a role to an AgentWorker (not just the instance)."""
        chain = self._fallbacks.get(role, [f"core_{role}"])
        for agent_id in chain:
            worker = self.runtime.get(agent_id)
            if worker:
                return worker
        return None

    def add_agent_to_role(self, role: str, agent_id: str, priority: int = -1) -> None:
        """Add an agent to a role's fallback chain."""
        chain = self._fallbacks.setdefault(role, [f"core_{role}"])
        if agent_id not in chain:
            if priority >= 0:
                chain.insert(priority, agent_id)
            else:
                chain.append(agent_id)

    def list_roles(self) -> Dict[str, List[str]]:
        """Return current role-to-agent mappings."""
        return dict(self._fallbacks)
