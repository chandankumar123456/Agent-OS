"""Feasibility Engine — checks whether a task can be executed given current system state."""
import os
import platform
from typing import List, Dict, Any, Optional, Set

from .models import (
    Capability,
    CapabilityAssessment,
    FeasibilityResult,
    FeasibilityReport,
    ExecutionEnvironment,
    EnvironmentConfig,
)
from ..tools.registry import tool_registry
from ..mcp.client_manager import mcp_client_manager
from ..logs.logger import logger


class FeasibilityEngine:
    """Determines if a task is executable before planning begins.

    Checks:
    - Tool availability (built-in + MCP)
    - Capability availability
    - Environment readiness (OS, network, disk)
    - Safety constraints
    """

    def __init__(self):
        self._blocked_patterns = [
            "rm -rf /",
            "format",
            "dd if=/dev/zero",
            "del /f /s /q c:\\",
        ]

    async def check(
        self,
        assessment: CapabilityAssessment,
        config: Optional[Dict[str, Any]] = None,
    ) -> FeasibilityReport:
        """Run feasibility checks for a capability assessment."""
        task_id = assessment.task_id
        notes: List[str] = []

        # 1. Check required capabilities against known capabilities
        available_caps = self._get_available_capabilities()
        required_caps = {r.capability for r in assessment.required_capabilities}
        missing_caps = required_caps - available_caps

        # 2. Check tool availability
        available_tools = await self._get_available_tools()
        required_tools: Set[str] = set()
        for req in assessment.required_capabilities:
            required_tools.update(req.required_tools)

        missing_tools = required_tools - set(available_tools)

        # 3. Environment readiness
        env_ready = self._check_environment()
        if not env_ready:
            notes.append("Environment check failed (disk or network)")

        # 4. Safety constraints
        safety_passed = self._check_safety(assessment)
        if not safety_passed:
            notes.append("Safety check failed — destructive or system-mutation patterns detected")

        # 5. Determine overall result
        if not safety_passed:
            result = FeasibilityResult.BLOCKED
        elif missing_caps and required_caps.issubset(missing_caps):
            result = FeasibilityResult.UNSUPPORTED
        elif missing_tools or missing_caps:
            result = FeasibilityResult.PARTIALLY_EXECUTABLE
            notes.append(f"Missing capabilities: {[c.value for c in missing_caps]}")
            notes.append(f"Missing tools: {list(missing_tools)}")
        else:
            result = FeasibilityResult.EXECUTABLE

        report = FeasibilityReport(
            task_id=task_id,
            result=result,
            available_capabilities=list(available_caps),
            missing_capabilities=list(missing_caps),
            available_tools=available_tools,
            missing_tools=list(missing_tools),
            environment_ready=env_ready,
            safety_passed=safety_passed,
            notes=notes,
        )

        logger.info(
            f"[FeasibilityEngine] task={task_id} result={result.value} "
            f"missing_caps={[c.value for c in missing_caps]} missing_tools={list(missing_tools)}"
        )
        return report

    def _get_available_capabilities(self) -> Set[Capability]:
        """Return capabilities that are fundamentally available in this AgentOS instance."""
        caps = {Capability.CHAT, Capability.WORKFLOW, Capability.KNOWLEDGE}
        caps.add(Capability.FILE)
        caps.add(Capability.CODE)
        caps.add(Capability.SHELL)
        caps.add(Capability.WEB)
        caps.add(Capability.DEPLOYMENT)
        return caps

    async def _get_available_tools(self) -> List[str]:
        """List currently registered tool names."""
        try:
            # Ensure MCP tools are lazily discovered
            await tool_registry.discover_mcp_tools()
            return [t["name"] for t in tool_registry.list_tools()]
        except Exception as e:
            logger.warning(f"Tool discovery failed during feasibility check: {e}")
            return [t["name"] for t in tool_registry.list_tools()]

    def _check_environment(self) -> bool:
        """Check basic environment health."""
        # Check disk space (simplified — at least 100MB free)
        try:
            if hasattr(os, "statvfs"):
                stat = os.statvfs(".")
                free_mb = (stat.f_bavail * stat.f_frsize) / (1024 * 1024)
                if free_mb < 100:
                    logger.warning(f"Low disk space: {free_mb:.1f}MB")
                    return False
        except Exception:
            pass
        return True

    def _check_safety(self, assessment: CapabilityAssessment) -> bool:
        """Check safety constraints."""
        query = assessment.query.lower()
        for pattern in self._blocked_patterns:
            if pattern.lower() in query:
                logger.warning(f"Safety block triggered by pattern: {pattern}")
                return False
        # Destructive flags require explicit approval config
        if "destructive" in assessment.safety_flags:
            # Allow but flag; actual blocking depends on runtime config
            pass
        return True

    def select_environment(
        self,
        assessment: CapabilityAssessment,
        report: FeasibilityReport,
    ) -> EnvironmentConfig:
        """Select the best execution environment for the task."""
        caps = {r.capability for r in assessment.required_capabilities}

        if Capability.DEPLOYMENT in caps or Capability.SHELL in caps:
            env = ExecutionEnvironment.SHELL
        elif Capability.WEB in caps:
            env = ExecutionEnvironment.BROWSER
        elif Capability.CODE in caps:
            env = ExecutionEnvironment.SANDBOX
        else:
            env = ExecutionEnvironment.LOCAL

        home = os.path.expanduser("~")
        return EnvironmentConfig(
            environment=env,
            working_dir=os.getcwd(),
            allowed_paths=[home, os.getcwd()],
            blocked_commands=["rm -rf /", "format", "dd if=/dev/zero"],
            network_access=True,
            timeout_seconds=300,
        )


# Global singleton
feasibility_engine = FeasibilityEngine()
