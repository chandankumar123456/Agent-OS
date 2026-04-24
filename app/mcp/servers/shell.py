"""MCP Shell Server — provides command execution tools to agents."""
import subprocess
import shlex
import os
from typing import Optional

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("shell")

# Security: block dangerous commands
BLOCKED_COMMANDS = {"rm", "del", "format", "fdisk", "mkfs", "dd"}


def _is_safe(command: str) -> bool:
    parts = shlex.split(command)
    if not parts:
        return False
    base = os.path.basename(parts[0]).lower()
    # Remove extension for Windows
    base = os.path.splitext(base)[0]
    return base not in BLOCKED_COMMANDS


@mcp.tool()
async def execute_command(command: str, timeout: int = 30, cwd: Optional[str] = None) -> str:
    """Execute a shell command and return stdout/stderr.

    Args:
        command: The command to execute
        timeout: Maximum seconds to wait (default 30)
        cwd: Working directory for the command
    """
    if not _is_safe(command):
        return f"Error: Command blocked for safety: {command}"

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
        output = result.stdout
        if result.stderr:
            output += f"\n[stderr]\n{result.stderr}"
        if result.returncode != 0:
            output += f"\n[exit code: {result.returncode}]"
        return output
    except subprocess.TimeoutExpired:
        return f"Error: Command timed out after {timeout} seconds"
    except Exception as e:
        return f"Error executing command: {e}"


@mcp.tool()
async def run_script(script: str, interpreter: str = "python", timeout: int = 30) -> str:
    """Run a script using the specified interpreter.

    Args:
        script: The script content
        interpreter: Interpreter to use (python, bash, sh, etc.)
        timeout: Maximum seconds to wait
    """
    try:
        if interpreter in ("bash", "sh", "cmd", "powershell"):
            result = subprocess.run(
                [interpreter, "-c", script],
                capture_output=True,
                text=True,
                timeout=timeout,
                shell=False,
            )
        elif interpreter == "python":
            result = subprocess.run(
                ["python", "-c", script],
                capture_output=True,
                text=True,
                timeout=timeout,
                shell=False,
            )
        else:
            result = subprocess.run(
                [interpreter, script],
                capture_output=True,
                text=True,
                timeout=timeout,
                shell=False,
            )
        output = result.stdout
        if result.stderr:
            output += f"\n[stderr]\n{result.stderr}"
        if result.returncode != 0:
            output += f"\n[exit code: {result.returncode}]"
        return output
    except subprocess.TimeoutExpired:
        return f"Error: Script timed out after {timeout} seconds"
    except Exception as e:
        return f"Error running script: {e}"


@mcp.tool()
async def get_process_status(pid: int) -> str:
    """Check if a process is running by PID."""
    try:
        import psutil
        proc = psutil.Process(pid)
        return f"PID {pid} is running. Status: {proc.status()}. CPU: {proc.cpu_percent()}%. Memory: {proc.memory_info().rss} bytes"
    except psutil.NoSuchProcess:
        return f"Process {pid} not found"
    except ImportError:
        # Fallback without psutil
        if os.name == "nt":
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"],
                capture_output=True,
                text=True,
            )
            return result.stdout if result.returncode == 0 else f"Process {pid} not found"
        else:
            result = subprocess.run(
                ["ps", "-p", str(pid)],
                capture_output=True,
                text=True,
            )
            return result.stdout if result.returncode == 0 else f"Process {pid} not found"
    except Exception as e:
        return f"Error checking process: {e}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
