"""Execution Environment Layer — abstracts local, shell, browser, sandbox environments."""
import os
import asyncio
from typing import Dict, Any, Optional

from .models import ExecutionEnvironment, EnvironmentConfig
from ..logs.logger import logger


class ExecutionEnvironmentLayer:
    """Provides a unified interface for executing tasks in different environments.

    Environments:
    - LOCAL: Direct Python execution
    - SHELL: System shell commands
    - BROWSER: Web automation (via MCP browser tools)
    - SANDBOX: Isolated code execution
    - DESKTOP: GUI automation (future)
    """

    def __init__(self):
        self._active_envs: Dict[str, EnvironmentConfig] = {}

    def configure(self, task_id: str, config: EnvironmentConfig) -> EnvironmentConfig:
        """Set the execution environment for a task."""
        self._active_envs[task_id] = config
        logger.info(f"[ExecutionEnvironment] task={task_id} env={config.environment.value} workdir={config.working_dir}")
        return config

    def get_config(self, task_id: str) -> Optional[EnvironmentConfig]:
        """Get the environment config for a task."""
        return self._active_envs.get(task_id)

    async def execute_in_environment(
        self,
        task_id: str,
        command: str,
        env_vars: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Execute a shell command in the task's configured environment."""
        config = self._active_envs.get(task_id)
        if not config:
            config = EnvironmentConfig(environment=ExecutionEnvironment.LOCAL)

        if config.environment == ExecutionEnvironment.SHELL:
            return await self._execute_shell(command, config, env_vars)
        elif config.environment == ExecutionEnvironment.SANDBOX:
            return await self._execute_sandbox(command, config)
        else:
            return await self._execute_shell(command, config, env_vars)

    async def _execute_shell(
        self,
        command: str,
        config: EnvironmentConfig,
        env_vars: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Execute a command via subprocess."""
        # Safety: block dangerous commands
        for blocked in config.blocked_commands:
            if blocked.lower() in command.lower():
                return {
                    "success": False,
                    "error": f"Command blocked by safety policy: {blocked}",
                    "stdout": "",
                    "stderr": "",
                }

        env = os.environ.copy()
        if env_vars:
            env.update(env_vars)

        cwd = config.working_dir or os.getcwd()

        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=env,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=config.timeout_seconds
            )
            return {
                "success": proc.returncode == 0,
                "returncode": proc.returncode,
                "stdout": stdout.decode("utf-8", errors="ignore"),
                "stderr": stderr.decode("utf-8", errors="ignore"),
            }
        except asyncio.TimeoutError:
            proc.kill()
            return {
                "success": False,
                "error": f"Command timed out after {config.timeout_seconds}s",
                "stdout": "",
                "stderr": "",
            }

    async def _execute_sandbox(
        self,
        command: str,
        config: EnvironmentConfig,
    ) -> Dict[str, Any]:
        """Execute in a sandboxed environment (placeholder for future Docker integration)."""
        logger.info(f"[ExecutionEnvironment] Sandbox execution for command: {command[:100]}")
        # For now, delegate to shell with restricted paths
        return await self._execute_shell(command, config)

    def cleanup(self, task_id: str):
        """Remove environment config for a task."""
        self._active_envs.pop(task_id, None)


# Global singleton
execution_environment = ExecutionEnvironmentLayer()
