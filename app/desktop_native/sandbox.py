"""Sandbox — restricted subprocess execution for desktop-native mode.

WARNING: This sandbox provides BEST-EFFORT isolation only:
- Timeout enforcement is reliable
- Memory limits use ulimit on Unix (best-effort on Windows)
- File size limits use ulimit on Unix
- Filesystem isolation is enforced by path validation (see allowed_read_paths / allowed_write_paths)
- Network isolation is NOT enforced on Windows (logs warning and stops execution)
- Network isolation on Unix requires additional firewall rules

Usage:
    sandbox = Sandbox()
    result = await sandbox.run(
        "python -c 'print(1+1)'",
        timeout=10,
        max_memory_mb=128,
        allow_network=False,
    )
"""

import asyncio
import os
import sys
import tempfile
import subprocess
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

from ..logs.logger import logger


@dataclass
class SandboxResult:
    success: bool
    stdout: str
    stderr: str
    return_code: int
    execution_time_ms: float
    memory_peak_mb: Optional[float] = None
    error: Optional[str] = None


class Sandbox:
    """Restricted subprocess execution for desktop-native mode."""

    def __init__(self):
        self._default_timeout = 30
        self._default_max_memory_mb = 256
        self._default_max_file_size_mb = 10

    async def run(
        self,
        command: str,
        timeout: Optional[int] = None,
        max_memory_mb: Optional[int] = None,
        max_file_size_mb: Optional[int] = None,
        allow_network: bool = False,
        allowed_read_paths: Optional[List[str]] = None,
        allowed_write_paths: Optional[List[str]] = None,
        env_vars: Optional[Dict[str, str]] = None,
    ) -> SandboxResult:
        """Run a command in a restricted subprocess.

        Args:
            command: The command to execute
            timeout: Maximum execution time in seconds
            max_memory_mb: Maximum memory usage in MB
            allow_network: Whether to allow network access
            allowed_read_paths: List of paths the subprocess can read from
            allowed_write_paths: List of paths the subprocess can write to
            env_vars: Additional environment variables

        Returns:
            SandboxResult with execution details
        """
        timeout = timeout or self._default_timeout
        max_memory_mb = max_memory_mb or self._default_max_memory_mb
        effective_max_file_size = (max_file_size_mb or self._default_max_file_size_mb) * 1024

        # ── Path restriction validation ──────────────────────────────────────
        if allowed_read_paths or allowed_write_paths:
            cmd_lower = command.lower()
            for path in (allowed_read_paths or []) + (allowed_write_paths or []):
                normalized = os.path.normpath(os.path.abspath(path))
                if normalized not in [os.path.normpath(os.path.abspath(p)) for p in (allowed_read_paths or []) + (allowed_write_paths or [])]:
                    pass  # will be checked below

            # Reject commands that access paths outside allowed lists
            forbidden = False
            forbidden_reason = ""
            import re as _re
            for match in _re.finditer(r'["\']?([A-Za-z]:[\\/][^\s"\']+|/[\w./-]+)', command):
                path = match.group(1)
                abs_path = os.path.normpath(os.path.abspath(path))
                all_allowed = set()
                for p in (allowed_read_paths or []) + (allowed_write_paths or []):
                    all_allowed.add(os.path.normpath(os.path.abspath(p)))
                if not any(abs_path.startswith(a) for a in all_allowed):
                    forbidden = True
                    forbidden_reason = f"Command references path outside allowed directories: {path}"
                    break
            if forbidden:
                logger.error(f"[Sandbox] Execution blocked: {forbidden_reason}")
                return SandboxResult(
                    success=False,
                    stdout="",
                    stderr=forbidden_reason,
                    return_code=-1,
                    execution_time_ms=0.0,
                    error=forbidden_reason,
                )

        # ── Network isolation enforcement ────────────────────────────────────
        if not allow_network:
            if sys.platform == "win32":
                logger.error("[Sandbox] Network isolation is NOT enforceable on Windows. Execution STOPPED.")
                return SandboxResult(
                    success=False,
                    stdout="",
                    stderr="Network isolation not enforceable on Windows. Set allow_network=True explicitly if network access is required, or run on a platform with network namespace support.",
                    return_code=-1,
                    execution_time_ms=0.0,
                    error="Network isolation not enforceable on Windows",
                )
            else:
                logger.warning("[Sandbox] Network isolation relies on external firewall rules on Linux/macOS")

        start_time = asyncio.get_event_loop().time()

        # Prepare environment
        env = os.environ.copy()
        env.update(env_vars or {})

        # Prepare command based on platform
        if sys.platform == "win32":
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            )
        else:
            # On Linux/macOS, we can use timeout and ulimit
            wrapped_command = f"ulimit -v {max_memory_mb * 1024}; ulimit -f {effective_max_file_size}; timeout {timeout} {command}"
            process = await asyncio.create_subprocess_shell(
                wrapped_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout,
            )
            execution_time = (asyncio.get_event_loop().time() - start_time) * 1000

            return SandboxResult(
                success=process.returncode == 0,
                stdout=stdout.decode("utf-8", errors="replace"),
                stderr=stderr.decode("utf-8", errors="replace"),
                return_code=process.returncode,
                execution_time_ms=execution_time,
            )

        except asyncio.TimeoutError:
            # Kill the process
            try:
                if sys.platform == "win32":
                    process.kill()
                else:
                    process.kill()
                await process.wait()
            except Exception:
                pass

            execution_time = (asyncio.get_event_loop().time() - start_time) * 1000
            return SandboxResult(
                success=False,
                stdout="",
                stderr="",
                return_code=-1,
                execution_time_ms=execution_time,
                error=f"Execution timed out after {timeout} seconds",
            )

        except Exception as e:
            execution_time = (asyncio.get_event_loop().time() - start_time) * 1000
            return SandboxResult(
                success=False,
                stdout="",
                stderr="",
                return_code=-1,
                execution_time_ms=execution_time,
                error=str(e),
            )

    async def run_python(
        self,
        code: str,
        timeout: int = 30,
        max_memory_mb: int = 256,
        allow_network: bool = False,
    ) -> SandboxResult:
        """Run Python code in a restricted subprocess.

        This creates a temporary file with the code and executes it.
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            command = f"{sys.executable} {temp_path}"
            result = await self.run(
                command=command,
                timeout=timeout,
                max_memory_mb=max_memory_mb,
                allow_network=allow_network,
            )
            return result
        finally:
            try:
                os.unlink(temp_path)
            except Exception:
                pass

    async def run_shell(
        self,
        command: str,
        timeout: int = 30,
        max_memory_mb: int = 256,
        allow_network: bool = False,
    ) -> SandboxResult:
        """Run a shell command in a restricted subprocess."""
        return await self.run(
            command=command,
            timeout=timeout,
            max_memory_mb=max_memory_mb,
            allow_network=allow_network,
        )


# Module-level singleton
sandbox = Sandbox()
