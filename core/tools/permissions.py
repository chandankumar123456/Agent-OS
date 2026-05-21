"""Tool permission model for agent-to-tool access control.

Enforces which agents can use which tools at execution time,
integrating with the RBAC system and ToolRegistry.
"""
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from ..logs.logger import logger
from ..safety.rbac import AgentRole, RBAC, rbac as default_rbac
from .base import ToolOutput


class PermissionResult(BaseModel):
    """Result of a permission check."""
    allowed: bool
    reason: str
    required_role: Optional[str] = None
    tool_name: str
    agent_id: Optional[str] = None


class ToolPermissionModel(BaseModel):
    """Permission mapping for a specific tool."""
    tool_name: str
    allowed_roles: List[str] = Field(default_factory=list)
    denied_roles: List[str] = Field(default_factory=list)
    allowed_agents: List[str] = Field(default_factory=list)
    denied_agents: List[str] = Field(default_factory=list)
    requires_approval: bool = False


class ToolPermissions:
    """Manages and enforces tool permissions for agents.

    Usage:
        perms = ToolPermissions()
        result = await perms.check_permission(agent_id="agent-1", tool_name="shell__execute_command")
        if not result.allowed:
            # Deny execution
            pass
    """

    def __init__(
        self,
        rbac: Optional[RBAC] = None,
    ):
        self.rbac = rbac or default_rbac
        # Tool-specific overrides
        self._tool_overrides: Dict[str, ToolPermissionModel] = {}

    def set_tool_override(self, override: ToolPermissionModel) -> None:
        """Set a permission override for a specific tool.

        Args:
            override: Tool permission override.
        """
        self._tool_overrides[override.tool_name] = override

    def remove_tool_override(self, tool_name: str) -> bool:
        """Remove a tool permission override.

        Args:
            tool_name: Tool name.

        Returns:
            True if removed.
        """
        if tool_name in self._tool_overrides:
            del self._tool_overrides[tool_name]
            return True
        return False

    async def check_permission(
        self,
        tool_name: str,
        agent_id: Optional[str] = None,
        agent_role: Optional[AgentRole] = None,
    ) -> PermissionResult:
        """Check if an agent has permission to use a tool.

        Args:
            tool_name: Name of the tool.
            agent_id: Agent identifier.
            agent_role: Agent role.

        Returns:
            PermissionResult.
        """
        # Check tool-specific overrides first
        override = self._tool_overrides.get(tool_name)
        if override:
            if agent_id and agent_id in override.denied_agents:
                return PermissionResult(
                    allowed=False,
                    reason=f"Agent {agent_id} is explicitly denied access to {tool_name}",
                    tool_name=tool_name,
                    agent_id=agent_id,
                )
            if agent_id and agent_id in override.allowed_agents:
                return PermissionResult(
                    allowed=True,
                    reason=f"Agent {agent_id} is explicitly allowed access to {tool_name}",
                    tool_name=tool_name,
                    agent_id=agent_id,
                )
            if agent_role and agent_role.value in override.denied_roles:
                return PermissionResult(
                    allowed=False,
                    reason=f"Role {agent_role.value} is denied access to {tool_name}",
                    required_role=agent_role.value,
                    tool_name=tool_name,
                    agent_id=agent_id,
                )
            if agent_role and agent_role.value in override.allowed_roles:
                return PermissionResult(
                    allowed=True,
                    reason=f"Role {agent_role.value} is allowed access to {tool_name}",
                    required_role=agent_role.value,
                    tool_name=tool_name,
                    agent_id=agent_id,
                )

        # Fall back to RBAC
        if agent_role:
            allowed = self.rbac.check_tool_permission(agent_role, tool_name)
            if allowed:
                return PermissionResult(
                    allowed=True,
                    reason=f"Role {agent_role.value} has permission for {tool_name}",
                    required_role=agent_role.value,
                    tool_name=tool_name,
                    agent_id=agent_id,
                )
            else:
                return PermissionResult(
                    allowed=False,
                    reason=f"Role {agent_role.value} does not have permission for {tool_name}",
                    required_role=agent_role.value,
                    tool_name=tool_name,
                    agent_id=agent_id,
                )

        # No role provided - default deny for safety
        return PermissionResult(
            allowed=False,
            reason=f"No agent role provided for tool {tool_name}, default deny",
            tool_name=tool_name,
            agent_id=agent_id,
        )

    async def enforce_permission(
        self,
        tool_name: str,
        agent_id: Optional[str] = None,
        agent_role: Optional[AgentRole] = None,
    ) -> PermissionResult:
        """Enforce permission check and raise if denied.

        Args:
            tool_name: Name of the tool.
            agent_id: Agent identifier.
            agent_role: Agent role.

        Returns:
            PermissionResult if allowed.

        Raises:
            PermissionError: If permission is denied.
        """
        result = await self.check_permission(tool_name, agent_id, agent_role)
        if not result.allowed:
            logger.warning(
                "Tool permission denied",
                extra={
                    "tool_name": tool_name,
                    "agent_id": agent_id,
                    "agent_role": agent_role.value if agent_role else None,
                    "reason": result.reason,
                },
            )
            raise PermissionError(result.reason)
        return result

    async def filter_allowed_tools(
        self,
        tools: List[str],
        agent_id: Optional[str] = None,
        agent_role: Optional[AgentRole] = None,
    ) -> List[str]:
        """Filter a list of tools to only those the agent is allowed to use.

        Args:
            tools: List of tool names.
            agent_id: Agent identifier.
            agent_role: Agent role.

        Returns:
            Filtered list of allowed tool names.
        """
        allowed = []
        for tool_name in tools:
            result = await self.check_permission(tool_name, agent_id, agent_role)
            if result.allowed:
                allowed.append(tool_name)
        return allowed

    def get_role_permissions(self, role: AgentRole) -> List[str]:
        """Get the list of tool prefixes a role is allowed to use.

        Args:
            role: Agent role.

        Returns:
            List of allowed tool prefixes.
        """
        definition = self.rbac.roles.get(role)
        if not definition:
            return []
        return list(definition.allowed_tool_prefixes)

    async def wrap_tool_execution(
        self,
        tool_name: str,
        execute_fn,
        agent_id: Optional[str] = None,
        agent_role: Optional[AgentRole] = None,
    ) -> ToolOutput:
        """Wrap a tool execution with permission check.

        Args:
            tool_name: Tool name.
            execute_fn: Async callable that performs the tool execution.
            agent_id: Agent identifier.
            agent_role: Agent role.

        Returns:
            ToolOutput.
        """
        try:
            await self.enforce_permission(tool_name, agent_id, agent_role)
        except PermissionError as e:
            return ToolOutput(
                success=False,
                error=str(e),
                metadata={"permission_denied": True, "tool": tool_name},
            )

        try:
            result = await execute_fn()
            return result
        except Exception as e:
            logger.error(f"Tool execution failed for {tool_name}: {e}")
            return ToolOutput(
                success=False,
                error=str(e),
                metadata={"tool": tool_name, "agent_id": agent_id},
            )


# Module-level singleton
tool_permissions = ToolPermissions()
