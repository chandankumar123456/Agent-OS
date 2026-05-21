"""Unit tests for RBAC system: AgentRole, Permission, RoleDefinition, RBAC."""

from core.safety.rbac import (
    AgentRole,
    DEFAULT_ROLES,
    Permission,
    RBAC,
    RoleDefinition,
    rbac,
)


# ═════════════════════════════════════════════════════════════════════════════
# AgentRole Enum Tests
# ═════════════════════════════════════════════════════════════════════════════

class TestAgentRole:
    """Verify the role enum has all expected members."""

    def test_agent_role_has_six_distinct_values(self):
        """AgentRole must have exactly 6 members."""
        values = {r.value for r in AgentRole}
        assert len(values) == 6
        assert values == {
            "planner", "executor", "verifier",
            "reviewer", "coordinator", "system",
        }


# ═════════════════════════════════════════════════════════════════════════════
# RoleDefinition Tests
# ═════════════════════════════════════════════════════════════════════════════

class TestRoleDefinition:
    """Model creation with Permission enum values."""

    def test_create_role_definition_with_permission_enums(self):
        rd = RoleDefinition(
            role=AgentRole.PLANNER,
            permissions={Permission.TOOL_READ, Permission.MEMORY_READ},
        )
        assert rd.role == AgentRole.PLANNER
        assert Permission.TOOL_READ in rd.permissions
        assert Permission.MEMORY_READ in rd.permissions


# ═════════════════════════════════════════════════════════════════════════════
# DEFAULT_ROLES Tests
# ═════════════════════════════════════════════════════════════════════════════

class TestDefaultRoles:
    """DEFAULT_ROLES must contain all 6 roles as RoleDefinition instances."""

    def test_default_roles_has_all_six_roles(self):
        assert set(DEFAULT_ROLES.keys()) == set(AgentRole)

    def test_default_roles_entries_are_role_definitions(self):
        for role, definition in DEFAULT_ROLES.items():
            assert isinstance(definition, RoleDefinition), f"{role} is not a RoleDefinition"
            assert definition.role == role


# ═════════════════════════════════════════════════════════════════════════════
# RBAC.check_permission Tests
# ═════════════════════════════════════════════════════════════════════════════

class TestCheckPermission:
    """Permission checking logic using Permission enum."""

    def setup_method(self):
        self.rbac = RBAC()

    def test_planner_has_tool_read(self):
        assert self.rbac.check_permission(AgentRole.PLANNER, Permission.TOOL_READ) is True

    def test_planner_does_not_have_tool_write(self):
        assert self.rbac.check_permission(AgentRole.PLANNER, Permission.TOOL_WRITE) is False

    def test_unknown_role_returns_false(self):
        assert self.rbac.check_permission("NONEXISTENT_ROLE", Permission.TOOL_READ) is False


# ═════════════════════════════════════════════════════════════════════════════
# RBAC.check_tool_permission Tests
# ═════════════════════════════════════════════════════════════════════════════

class TestCheckToolPermission:
    """Tool-level permission checking via allowed/denied prefixes."""

    def setup_method(self):
        self.rbac = RBAC()

    def test_system_role_has_wildcard_access(self):
        """SYSTEM role has allowed_tool_prefixes=['*'] so any tool is allowed."""
        assert self.rbac.check_tool_permission(AgentRole.SYSTEM, "any_tool_name") is True
        assert self.rbac.check_tool_permission(AgentRole.SYSTEM, "shell__execute_command") is True

    def test_executor_can_access_filesystem_read(self):
        """EXECUTOR allowed_tool_prefixes includes 'filesystem__'."""
        assert self.rbac.check_tool_permission(AgentRole.EXECUTOR, "filesystem__read_file") is True

    def test_planner_denied_shell_execute(self):
        """PLANNER denied_tool_prefixes includes 'shell__'."""
        assert self.rbac.check_tool_permission(AgentRole.PLANNER, "shell__execute_command") is False

    def test_unknown_role_returns_false(self):
        assert self.rbac.check_tool_permission("nonexistent", "some_tool") is False


# ═════════════════════════════════════════════════════════════════════════════
# RBAC.get_role_permissions Tests
# ═════════════════════════════════════════════════════════════════════════════

class TestGetRolePermissions:
    """Permission listing returns a Set[Permission]."""

    def setup_method(self):
        self.rbac = RBAC()

    def test_returns_set_for_known_role(self):
        perms = self.rbac.get_role_permissions(AgentRole.PLANNER)
        assert isinstance(perms, set)
        assert perms == {Permission.TOOL_READ, Permission.MEMORY_READ}

    def test_returns_empty_set_for_unknown_role(self):
        perms = self.rbac.get_role_permissions("unknown_role")
        assert perms == set()


# ═════════════════════════════════════════════════════════════════════════════
# RBAC.add_custom_role Tests
# ═════════════════════════════════════════════════════════════════════════════

class TestAddCustomRole:
    """Custom role registration."""

    def setup_method(self):
        self.rbac = RBAC()

    def test_add_custom_role_and_verify(self):
        custom = RoleDefinition(
            role=AgentRole.REVIEWER,
            permissions={Permission.TOOL_READ, Permission.TASK_APPROVE},
        )
        self.rbac.add_custom_role(custom)
        perms = self.rbac.get_role_permissions(AgentRole.REVIEWER)
        assert Permission.TASK_APPROVE in perms

    def test_custom_role_appears_in_check_permission(self):
        custom = RoleDefinition(
            role=AgentRole.VERIFIER,
            permissions={Permission.TOOL_READ, Permission.MEMORY_WRITE},
        )
        self.rbac.add_custom_role(custom)
        assert self.rbac.check_permission(AgentRole.VERIFIER, Permission.MEMORY_WRITE) is True

    def test_overwrite_existing_role(self):
        """add_custom_role replaces the existing definition for that role."""
        new_def = RoleDefinition(
            role=AgentRole.PLANNER,
            permissions={Permission.WORKFLOW_MANAGE},
        )
        self.rbac.add_custom_role(new_def)
        perms = self.rbac.get_role_permissions(AgentRole.PLANNER)
        assert perms == {Permission.WORKFLOW_MANAGE}
        assert Permission.TOOL_READ not in perms


# ═════════════════════════════════════════════════════════════════════════════
# Module-Level Singleton
# ═════════════════════════════════════════════════════════════════════════════

class TestModuleSingleton:
    """Verify module-level rbac singleton."""

    def test_module_singleton_is_rbac_instance(self):
        assert isinstance(rbac, RBAC)

    def test_module_singleton_has_default_roles(self):
        assert rbac.check_permission(AgentRole.PLANNER, Permission.TOOL_READ) is True
        assert len(rbac.roles) == 6
