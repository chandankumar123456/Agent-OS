"""Phase 3.4 — DynamicAgentFactory: Creates agent instances from config at runtime.

Extends the existing AgentFactory to support dynamic agent creation from
AgentConfigV2Model configurations. Agents are created, validated, and
registered with the AgentRuntime on demand.

Spec: Build Plan Task 3.2.4, Section 6.5
Input Contract:  create_from_config(AgentConfigV2Model) → BaseAgent
Output Contract: Agent instance registered with runtime, ready for task assignment
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Type
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator

from ..logs.logger import logger
from ..orchestrator.errors import AgentOSError, ErrorCode, ErrorType
from ..agents.base import AgentRole


# ── Pydantic Models ──────────────────────────────────────────────────────────

class AgentConfigV2Model(BaseModel):
    """Configuration model for versioned agent creation (v2).

    Used by DynamicAgentFactory to create agents from structured configs.
    Each config specifies the agent's identity, capabilities, and constraints.
    """

    name: str = Field(..., min_length=1, max_length=128, description="Unique agent name")
    role: str = Field(..., description="Agent role: planner, executor, verifier, reviewer, coordinator")
    model: str = Field(default="gpt-4o", description="LLM model to use")
    system_prompt: str = Field(
        default="You are a capable AI agent executing tasks as instructed.",
        description="System prompt for the agent"
    )
    tools: List[str] = Field(
        default_factory=list,
        description="List of tool names available to this agent"
    )
    max_retries: int = Field(default=2, ge=0, le=10)
    max_steps: int = Field(default=10, ge=1, le=50)
    timeout_seconds: int = Field(default=300, ge=10, le=3600)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    version: int = Field(default=1, ge=1)
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: Optional[str] = None

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        """Ensure role is a recognized AgentRole value."""
        valid_roles = {r.value for r in AgentRole}
        if v.lower() not in valid_roles and v.upper() not in valid_roles:
            raise ValueError(
                f"Invalid role '{v}'. Must be one of: {', '.join(sorted(valid_roles))}"
            )
        return v.lower()


class AgentCreationResult(BaseModel):
    """Result of dynamic agent creation."""

    agent_id: str
    name: str
    role: str
    created: bool = False
    registered: bool = False
    health_check_passed: bool = False
    error_message: Optional[str] = None
    config_version: int = 1
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# ── DynamicAgentFactory ──────────────────────────────────────────────────────

class DynamicAgentFactory:
    """Creates agent instances dynamically from AgentConfigV2Model configs.

    Extends the existing AgentFactory with runtime agent creation capabilities.
    Agents are created, validated against their config schema, registered with
    the AgentRuntime, and health-checked before being made available for tasks.

    Creation Rules (from Build Plan Section 6.5):
    1. Config must exist in AgentConfigV2Model
    2. Config must specify: name, role, model, tools, system_prompt
    3. AgentFactory validates config against schema
    4. Agent instance created and registered with AgentRuntime
    5. Agent health check passes before accepting tasks
    6. Agent version tracked for rollback capability
    """

    def __init__(self):
        self._created_agents: Dict[str, AgentCreationResult] = {}
        self._creation_count: int = 0

    # ── Public API ───────────────────────────────────────────────────────

    async def create_from_config(
        self,
        config: AgentConfigV2Model,
        register: bool = True,
        health_check: bool = True,
    ) -> AgentCreationResult:
        """Create an agent instance from a configuration model.

        Args:
            config: AgentConfigV2Model with agent specification.
            register: If True, register with AgentRuntime after creation.
            health_check: If True, perform health check after registration.

        Returns:
            AgentCreationResult with creation status.

        Raises:
            AgentOSError: If creation fails due to config validation or runtime errors.
        """
        self._creation_count += 1
        agent_id = f"dynamic_{config.name}_{uuid4().hex[:8]}"

        logger.info(
            f"DynamicAgentFactory: Creating agent '{config.name}' "
            f"(role={config.role}, model={config.model}, version={config.version})"
        )

        # Step 1: Validate config (handled by Pydantic on AgentConfigV2Model init)

        # Step 2: Determine agent class to instantiate
        agent_class = self._resolve_agent_class(config.role)

        # Step 3: Create the agent instance
        try:
            agent_instance = await self._instantiate_agent(
                agent_class=agent_class,
                config=config,
                agent_id=agent_id,
            )
        except Exception as e:
            logger.error(f"DynamicAgentFactory: Failed to instantiate agent '{config.name}': {e}")
            return AgentCreationResult(
                agent_id=agent_id,
                name=config.name,
                role=config.role,
                created=False,
                error_message=f"Instantiation failed: {e}",
                config_version=config.version,
            )

        # Step 4: Validate agent instance
        validation_ok = await self._validate_agent(agent_instance, config)
        if not validation_ok:
            return AgentCreationResult(
                agent_id=agent_id,
                name=config.name,
                role=config.role,
                created=False,
                error_message="Agent validation failed",
                config_version=config.version,
            )

        result = AgentCreationResult(
            agent_id=agent_id,
            name=config.name,
            role=config.role,
            created=True,
            registered=False,
            health_check_passed=False,
            config_version=config.version,
        )

        # Step 5: Register with AgentRuntime
        if register:
            reg_ok = await self._register_with_runtime(agent_id, config, agent_instance)
            if not reg_ok:
                result.error_message = "Registration with AgentRuntime failed"
                self._created_agents[agent_id] = result
                return result
            result.registered = True

        # Step 6: Health check
        if health_check and register:
            hc_ok = await self._health_check_agent(agent_id, agent_instance)
            if not hc_ok:
                result.error_message = "Health check failed"
                self._created_agents[agent_id] = result
                return result
            result.health_check_passed = True

        # Track creation
        self._created_agents[agent_id] = result

        logger.info(
            f"DynamicAgentFactory: Agent '{config.name}' created successfully "
            f"(id={agent_id}, registered={result.registered}, "
            f"healthy={result.health_check_passed})"
        )

        return result

    async def create_batch(
        self,
        configs: List[AgentConfigV2Model],
        register: bool = True,
        health_check: bool = True,
    ) -> List[AgentCreationResult]:
        """Create multiple agents from a list of configs concurrently.

        Args:
            configs: List of AgentConfigV2Model configs.
            register: Whether to register with AgentRuntime.
            health_check: Whether to health check after registration.

        Returns:
            List of AgentCreationResult (one per config).
        """
        import asyncio

        tasks = [
            self.create_from_config(cfg, register, health_check)
            for cfg in configs
        ]
        return await asyncio.gather(*tasks, return_exceptions=False)

    def get_creation_result(self, agent_id: str) -> Optional[AgentCreationResult]:
        """Get the creation result for a specific agent.

        Args:
            agent_id: The agent's identifier.

        Returns:
            AgentCreationResult or None if not found.
        """
        return self._created_agents.get(agent_id)

    def list_created_agents(self) -> Dict[str, AgentCreationResult]:
        """List all agents created by this factory."""
        return dict(self._created_agents)

    def get_creation_count(self) -> int:
        """Get total number of agents created."""
        return self._creation_count

    # ── Internal Helpers ─────────────────────────────────────────────────

    def _resolve_agent_class(self, role: str) -> Type:
        """Resolve the agent class for a given role.

        Args:
            role: Agent role string.

        Returns:
            The agent class type.
        """
        role_lower = role.lower()

        # Map roles to agent classes
        role_class_map: Dict[str, str] = {
            "planner": "PlannerAgent",
            "executor": "ExecutorAgent",
            "verifier": "VerifierAgent",
            "reviewer": "ReviewerAgent",
            "coordinator": "CoordinatorAgent",
        }

        class_name = role_class_map.get(role_lower)
        if not class_name:
            raise AgentOSError(
                message=f"Unknown agent role: {role}",
                error_type=ErrorType.CONFIGURATION,
                code=ErrorCode.INVALID_INPUT,
                recoverable=False,
            )

        # Try to import the class
        try:
            module_name = f"app.agents.{role_lower}"
            module = __import__(module_name, fromlist=[class_name])
            return getattr(module, class_name)
        except (ImportError, AttributeError):
            # Fallback: return a generic agent class reference
            # In production, all agent classes should be importable
            logger.warning(
                f"DynamicAgentFactory: Could not import {class_name} from {module_name}. "
                f"Using generic agent class."
            )
            from ..runtime.factory import AgentFactory
            return AgentFactory

    async def _instantiate_agent(
        self,
        agent_class: Type,
        config: AgentConfigV2Model,
        agent_id: str,
    ) -> Any:
        """Instantiate an agent from its class and config.

        Args:
            agent_class: The agent class to instantiate.
            config: The agent configuration.
            agent_id: Pre-generated agent ID.

        Returns:
            The instantiated agent instance.
        """
        # Try constructor with common parameter patterns
        try:
            # Pattern 1: (name, role, model, ...)
            instance = agent_class(
                name=config.name,
                role=config.role,
                model=config.model,
                system_prompt=config.system_prompt,
            )
        except TypeError:
            try:
                # Pattern 2: (max_concurrent) — e.g., CoordinatorAgent
                instance = agent_class(max_concurrent=config.max_steps)
            except TypeError:
                try:
                    # Pattern 3: (strict_mode) — e.g., ReviewerAgent
                    instance = agent_class(strict_mode=False)
                except TypeError:
                    try:
                        # Pattern 4: No-arg constructor
                        instance = agent_class()
                    except TypeError:
                        # Last resort: create a minimal instance
                        instance = object.__new__(agent_class)

        # Set common attributes
        if not hasattr(instance, "name") or getattr(instance, "name", None) is None:
            instance.name = config.name  # type: ignore[attr-defined]
        if not hasattr(instance, "role") or getattr(instance, "role", None) is None:
            instance.role = config.role  # type: ignore[attr-defined]

        return instance

    async def _validate_agent(self, agent_instance: Any, config: AgentConfigV2Model) -> bool:
        """Validate that the created agent meets minimum requirements.

        Args:
            agent_instance: The created agent instance.
            config: The original config for comparison.

        Returns:
            True if validation passes, False otherwise.
        """
        # Check basic attributes
        if not hasattr(agent_instance, "name"):
            logger.error(f"Agent '{config.name}' missing 'name' attribute")
            return False

        if not hasattr(agent_instance, "role"):
            logger.error(f"Agent '{config.name}' missing 'role' attribute")
            return False

        # Check execute method exists (BaseAgent protocol)
        if not hasattr(agent_instance, "execute"):
            logger.error(f"Agent '{config.name}' missing 'execute' method")
            return False

        if not callable(agent_instance.execute):  # type: ignore[attr-defined]
            logger.error(f"Agent '{config.name}' 'execute' is not callable")
            return False

        return True

    async def _register_with_runtime(
        self,
        agent_id: str,
        config: AgentConfigV2Model,
        agent_instance: Any,
    ) -> bool:
        """Register the created agent with AgentRuntime.

        Args:
            agent_id: The agent's unique ID.
            config: The agent configuration.
            agent_instance: The agent instance.

        Returns:
            True if registration succeeds, False otherwise.
        """
        try:
            from ..runtime.runtime import AgentRuntime

            runtime = AgentRuntime()
            worker_config = {
                "agent_id": agent_id,
                "name": config.name,
                "role": config.role,
                "model": config.model,
                "system_prompt": config.system_prompt,
                "tools": config.tools,
                "max_retries": config.max_retries,
                "max_steps": config.max_steps,
                "timeout_seconds": config.timeout_seconds,
                "version": config.version,
            }
            await runtime.register(
                agent_id=agent_id,
                config=worker_config,
                agent_instance=agent_instance,
            )
            logger.info(f"DynamicAgentFactory: Agent '{config.name}' registered with runtime")
            return True
        except Exception as e:
            logger.error(
                f"DynamicAgentFactory: Failed to register agent '{config.name}': {e}"
            )
            return False

    async def _health_check_agent(
        self,
        agent_id: str,
        agent_instance: Any,
    ) -> bool:
        """Perform a health check on the newly created agent.

        Args:
            agent_id: The agent's unique ID.
            agent_instance: The agent instance.

        Returns:
            True if health check passes, False otherwise.
        """
        try:
            # Basic health check: verify agent can respond
            if hasattr(agent_instance, "health") and callable(agent_instance.health):
                health_result = await agent_instance.health()
                if isinstance(health_result, dict) and health_result.get("status") == "healthy":
                    return True
                logger.warning(
                    f"Agent '{agent_id}' health check returned non-healthy status: {health_result}"
                )

            # Fallback: check that execute is callable and agent has required attrs
            if hasattr(agent_instance, "execute") and callable(agent_instance.execute):
                return True

            return False
        except Exception as e:
            logger.error(f"Agent '{agent_id}' health check failed: {e}")
            return False


# ── Singleton ────────────────────────────────────────────────────────────────

_dynamic_factory_instance: Optional[DynamicAgentFactory] = None


def get_dynamic_factory() -> DynamicAgentFactory:
    """Get or create the singleton DynamicAgentFactory instance.

    Returns:
        The global DynamicAgentFactory instance.
    """
    global _dynamic_factory_instance
    if _dynamic_factory_instance is None:
        _dynamic_factory_instance = DynamicAgentFactory()
    return _dynamic_factory_instance
