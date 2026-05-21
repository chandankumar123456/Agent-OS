"""Tests for ToolPermissions with RBAC integration and permission denial."""
import pytest

from core.tools.permissions import ToolPermissions, ToolPermissionModel
from core.safety.rbac import AgentRole


@pytest.fixture
def perms():
    return ToolPermissions()


class TestRBACIntegration:
    """Test RBAC-based permission checks."""

    @pytest.mark.asyncio
    async def test_planner_can_read_files(self, perms):
        result = await perms.check_permission(
            "filesystem__read_file",
            agent_id="agent-1",
            agent_role=AgentRole.PLANNER,
        )
        assert result.allowed is True
        assert "read" in result.reason.lower() or "allowed" in result.reason.lower()

    @pytest.mark.asyncio
    async def test_planner_cannot_execute_shell(self, perms):
        result = await perms.check_permission(
            "shell__execute_command",
            agent_id="agent-1",
            agent_role=AgentRole.PLANNER,
        )
        assert result.allowed is False
        assert "does not have permission" in result.reason

    @pytest.mark.asyncio
    async def test_executor_can_use_shell(self, perms):
        result = await perms.check_permission(
            "shell__execute_command",
            agent_id="agent-1",
            agent_role=AgentRole.EXECUTOR,
        )
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_verifier_can_use_verification_tools(self, perms):
        result = await perms.check_permission(
            "filesystem__read_file",
            agent_id="agent-1",
            agent_role=AgentRole.VERIFIER,
        )
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_reviewer_read_only(self, perms):
        result = await perms.check_permission(
            "filesystem__read_file",
            agent_id="agent-1",
            agent_role=AgentRole.REVIEWER,
        )
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_reviewer_cannot_write(self, perms):
        result = await perms.check_permission(
            "filesystem__write_file",
            agent_id="agent-1",
            agent_role=AgentRole.REVIEWER,
        )
        assert result.allowed is False

    @pytest.mark.asyncio
    async def test_coordinator_can_use_all_tools(self, perms):
        result = await perms.check_permission(
            "shell__execute_command",
            agent_id="agent-1",
            agent_role=AgentRole.COORDINATOR,
        )
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_system_can_use_all_tools(self, perms):
        result = await perms.check_permission(
            "shell__execute_command",
            agent_id="agent-1",
            agent_role=AgentRole.SYSTEM,
        )
        assert result.allowed is True


class TestNoRoleProvided:
    """Test default deny when no role is provided."""

    @pytest.mark.asyncio
    async def test_default_deny_without_role(self, perms):
        result = await perms.check_permission(
            "filesystem__read_file",
            agent_id="agent-1",
            agent_role=None,
        )
        assert result.allowed is False
        assert "No agent role provided" in result.reason

    @pytest.mark.asyncio
    async def test_default_deny_without_agent_id(self, perms):
        result = await perms.check_permission(
            "filesystem__read_file",
            agent_id=None,
            agent_role=None,
        )
        assert result.allowed is False


class TestToolOverrides:
    """Test tool-specific permission overrides."""

    @pytest.mark.asyncio
    async def test_explicit_agent_allow(self, perms):
        override = ToolPermissionModel(
            tool_name="shell__execute_command",
            allowed_agents=["special-agent"],
        )
        perms.set_tool_override(override)

        result = await perms.check_permission(
            "shell__execute_command",
            agent_id="special-agent",
            agent_role=AgentRole.PLANNER,  # Planner normally can't use shell
        )
        assert result.allowed is True
        assert "explicitly allowed" in result.reason

    @pytest.mark.asyncio
    async def test_explicit_agent_deny(self, perms):
        override = ToolPermissionModel(
            tool_name="filesystem__read_file",
            denied_agents=["bad-agent"],
        )
        perms.set_tool_override(override)

        result = await perms.check_permission(
            "filesystem__read_file",
            agent_id="bad-agent",
            agent_role=AgentRole.EXECUTOR,
        )
        assert result.allowed is False
        assert "explicitly denied" in result.reason

    @pytest.mark.asyncio
    async def test_explicit_role_allow(self, perms):
        override = ToolPermissionModel(
            tool_name="shell__execute_command",
            allowed_roles=["planner"],
        )
        perms.set_tool_override(override)

        result = await perms.check_permission(
            "shell__execute_command",
            agent_id="agent-1",
            agent_role=AgentRole.PLANNER,
        )
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_explicit_role_deny(self, perms):
        override = ToolPermissionModel(
            tool_name="filesystem__read_file",
            denied_roles=["executor"],
        )
        perms.set_tool_override(override)

        result = await perms.check_permission(
            "filesystem__read_file",
            agent_id="agent-1",
            agent_role=AgentRole.EXECUTOR,
        )
        assert result.allowed is False
        assert "denied access" in result.reason

    @pytest.mark.asyncio
    async def test_remove_override(self, perms):
        override = ToolPermissionModel(
            tool_name="shell__execute_command",
            allowed_agents=["special-agent"],
        )
        perms.set_tool_override(override)
        assert perms.remove_tool_override("shell__execute_command") is True
        assert perms.remove_tool_override("shell__execute_command") is False


class TestEnforcePermission:
    """Test enforce_permission which raises on denial."""

    @pytest.mark.asyncio
    async def test_enforce_allows(self, perms):
        result = await perms.enforce_permission(
            "filesystem__read_file",
            agent_id="agent-1",
            agent_role=AgentRole.PLANNER,
        )
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_enforce_raises_on_deny(self, perms):
        with pytest.raises(PermissionError) as exc_info:
            await perms.enforce_permission(
                "shell__execute_command",
                agent_id="agent-1",
                agent_role=AgentRole.PLANNER,
            )
        assert "does not have permission" in str(exc_info.value)


class TestFilterAllowedTools:
    """Test filtering tool lists by permissions."""

    @pytest.mark.asyncio
    async def test_filter_for_planner(self, perms):
        tools = [
            "filesystem__read_file",
            "filesystem__write_file",
            "shell__execute_command",
            "cloud_api__search_web",
        ]
        allowed = await perms.filter_allowed_tools(
            tools, agent_id="agent-1", agent_role=AgentRole.PLANNER
        )
        assert "filesystem__read_file" in allowed
        assert "cloud_api__search_web" in allowed
        assert "shell__execute_command" not in allowed
        assert "filesystem__write_file" not in allowed

    @pytest.mark.asyncio
    async def test_filter_for_executor(self, perms):
        tools = [
            "filesystem__read_file",
            "shell__execute_command",
            "browser__search_web",
        ]
        allowed = await perms.filter_allowed_tools(
            tools, agent_id="agent-1", agent_role=AgentRole.EXECUTOR
        )
        assert "shell__execute_command" in allowed
        assert "filesystem__read_file" in allowed


class TestWrapToolExecution:
    """Test the tool execution wrapper."""

    @pytest.mark.asyncio
    async def test_wrap_executes_when_allowed(self, perms):
        async def execute_fn():
            from core.tools.base import ToolOutput
            return ToolOutput(success=True, result="done")

        result = await perms.wrap_tool_execution(
            "filesystem__read_file",
            execute_fn,
            agent_id="agent-1",
            agent_role=AgentRole.PLANNER,
        )
        assert result.success is True
        assert result.result == "done"

    @pytest.mark.asyncio
    async def test_wrap_denies_when_not_allowed(self, perms):
        async def execute_fn():
            from core.tools.base import ToolOutput
            return ToolOutput(success=True, result="done")

        result = await perms.wrap_tool_execution(
            "shell__execute_command",
            execute_fn,
            agent_id="agent-1",
            agent_role=AgentRole.PLANNER,
        )
        assert result.success is False
        assert result.metadata.get("permission_denied") is True

    @pytest.mark.asyncio
    async def test_wrap_catches_execution_error(self, perms):
        async def bad_execute_fn():
            raise RuntimeError("tool crashed")

        result = await perms.wrap_tool_execution(
            "filesystem__read_file",
            bad_execute_fn,
            agent_id="agent-1",
            agent_role=AgentRole.PLANNER,
        )
        assert result.success is False
        assert "tool crashed" in result.error


class TestGetRolePermissions:
    """Test retrieving role permission lists."""

    def test_planner_permissions(self, perms):
        prefixes = perms.get_role_permissions(AgentRole.PLANNER)
        assert "filesystem__read" in prefixes
        assert "cloud_api__search" in prefixes
        assert "shell__" not in prefixes

    def test_executor_permissions(self, perms):
        prefixes = perms.get_role_permissions(AgentRole.EXECUTOR)
        assert "shell__" in prefixes
        assert "filesystem__" in prefixes

    def test_system_role_permissions(self, perms):
        # SYSTEM should have wildcard access
        prefixes = perms.get_role_permissions(AgentRole.SYSTEM)
        assert "*" in prefixes
        assert len(prefixes) == 1
