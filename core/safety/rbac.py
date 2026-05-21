"""Role-based access control for agents and tools.

Defines roles and permissions for the agent system. Each role has
specific permissions for tools, memory access, and actions.
"""
from enum import Enum
from typing import Dict, List, Optional, Set

from pydantic import BaseModel, Field


class AgentRole(str, Enum):
    """Predefined agent roles."""
    PLANNER = "planner"
    EXECUTOR = "executor"
    VERIFIER = "verifier"
    REVIEWER = "reviewer"
    COORDINATOR = "coordinator"
    SYSTEM = "system"


class Permission(str, Enum):
    """Permission types."""
    TOOL_READ = "tool:read"
    TOOL_WRITE = "tool:write"
    TOOL_EXECUTE = "tool:execute"
    TOOL_SHELL = "tool:shell"
    MEMORY_READ = "memory:read"
    MEMORY_WRITE = "memory:write"
    TASK_CREATE = "task:create"
    TASK_APPROVE = "task:approve"
    WORKFLOW_MANAGE = "workflow:manage"


class RoleDefinition(BaseModel):
    """Definition of a role with its permissions."""
    role: AgentRole
    permissions: Set[Permission] = Field(default_factory=set)
    allowed_tool_prefixes: List[str] = Field(default_factory=list)
    denied_tool_prefixes: List[str] = Field(default_factory=list)
    description: str = ""


# Default role definitions
DEFAULT_ROLES: Dict[AgentRole, RoleDefinition] = {
    AgentRole.PLANNER: RoleDefinition(
        role=AgentRole.PLANNER,
        permissions={Permission.TOOL_READ, Permission.MEMORY_READ},
        allowed_tool_prefixes=["filesystem__read", "cloud_api__search", "browser__"],
        denied_tool_prefixes=["shell__", "desktop_env__write", "filesystem__write"],
        description="Read-only planning role",
    ),
    AgentRole.EXECUTOR: RoleDefinition(
        role=AgentRole.EXECUTOR,
        permissions={Permission.TOOL_READ, Permission.TOOL_WRITE, Permission.TOOL_EXECUTE},
        allowed_tool_prefixes=["filesystem__", "shell__", "browser__", "desktop_env__", "cloud_api__"],
        denied_tool_prefixes=[],
        description="Full execution role",
    ),
    AgentRole.VERIFIER: RoleDefinition(
        role=AgentRole.VERIFIER,
        permissions={Permission.TOOL_READ, Permission.MEMORY_READ},
        allowed_tool_prefixes=["filesystem__read", "browser__", "cloud_api__search"],
        denied_tool_prefixes=["shell__", "filesystem__write", "desktop_env__write"],
        description="Verification role with read-only access",
    ),
    AgentRole.REVIEWER: RoleDefinition(
        role=AgentRole.REVIEWER,
        permissions={Permission.TOOL_READ, Permission.MEMORY_READ},
        allowed_tool_prefixes=["filesystem__read", "browser__"],
        denied_tool_prefixes=["shell__", "filesystem__write", "desktop_env__write", "desktop_env__execute"],
        description="Review role with minimal access",
    ),
    AgentRole.COORDINATOR: RoleDefinition(
        role=AgentRole.COORDINATOR,
        permissions={
            Permission.TOOL_READ, Permission.TOOL_WRITE, Permission.TOOL_EXECUTE,
            Permission.MEMORY_READ, Permission.MEMORY_WRITE,
            Permission.TASK_CREATE, Permission.WORKFLOW_MANAGE,
        },
        allowed_tool_prefixes=["filesystem__", "shell__", "browser__", "desktop_env__", "cloud_api__"],
        denied_tool_prefixes=[],
        description="Coordinator with full workflow management",
    ),
    AgentRole.SYSTEM: RoleDefinition(
        role=AgentRole.SYSTEM,
        permissions=set(Permission),
        allowed_tool_prefixes=["*"],
        denied_tool_prefixes=[],
        description="System administrator role",
    ),
}


class RBAC:
    """Role-based access control manager.

    Usage:
        rbac = RBAC()
        if rbac.check_permission(AgentRole.PLANNER, Permission.TOOL_WRITE):
            # Denied
            pass
    """

    def __init__(self, roles: Optional[Dict[AgentRole, RoleDefinition]] = None):
        self.roles = roles or DEFAULT_ROLES.copy()

    def check_permission(self, role: AgentRole, permission: Permission) -> bool:
        """Check if a role has a specific permission.

        Args:
            role: Agent role.
            permission: Permission to check.

        Returns:
            True if allowed.
        """
        definition = self.roles.get(role)
        if not definition:
            return False
        return permission in definition.permissions

    def check_tool_permission(self, role: AgentRole, tool_name: str) -> bool:
        """Check if a role can use a specific tool.

        Args:
            role: Agent role.
            tool_name: Tool name.

        Returns:
            True if allowed.
        """
        definition = self.roles.get(role)
        if not definition:
            return False

        # System role allows everything
        if role == AgentRole.SYSTEM:
            return True

        # Check denied prefixes first
        for prefix in definition.denied_tool_prefixes:
            if tool_name.startswith(prefix):
                return False

        # Check allowed prefixes
        for prefix in definition.allowed_tool_prefixes:
            if prefix == "*" or tool_name.startswith(prefix):
                return True

        return False

    def get_role_permissions(self, role: AgentRole) -> Set[Permission]:
        """Get all permissions for a role.

        Args:
            role: Agent role.

        Returns:
            Set of permissions.
        """
        definition = self.roles.get(role)
        if not definition:
            return set()
        return definition.permissions.copy()

    def add_custom_role(self, definition: RoleDefinition) -> None:
        """Add or override a custom role.

        Args:
            definition: Role definition.
        """
        self.roles[definition.role] = definition


# Module-level singleton
rbac = RBAC()
