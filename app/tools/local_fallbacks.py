"""Local fallback implementations for MCP tools.

These functions provide direct implementations of filesystem and shell tools
that bypass the MCP stdio server process. They are used as fallbacks when the
MCP server is not running (e.g., in desktop-native mode without external
MCP processes).

Safety logic is reused from the MCP server implementations.
"""
import os
import subprocess
import shlex
import fnmatch
from pathlib import Path
from typing import Optional


# ---- Security: path resolution (from app/mcp/servers/filesystem.py) ----

_home = os.path.expanduser("~")
SAFE_ROOTS = [
    os.getcwd(),
    _home,
    os.path.join(_home, "Desktop"),
    os.path.join(_home, "Documents"),
    os.path.join(_home, "Downloads"),
    "/tmp",
]


def _normalize_path_for_os(path: str) -> str:
    """Detect and remap cross-platform hallucinated paths to real OS paths."""
    if not path or not isinstance(path, str):
        return path
    system = os.name  # 'nt' for Windows, 'posix' for Linux/macOS
    home = os.path.expanduser("~")

    # Expand ~ first
    if path.startswith("~/") or path.startswith("~\\"):
        path = os.path.join(home, path[2:])

    # Unix-style absolute path on Windows
    if system == "nt" and path.startswith("/"):
        if path.startswith("/home/"):
            suffix = path[len("/home/"):]
            if "/" in suffix:
                suffix = suffix[suffix.find("/"):]
            else:
                suffix = ""
            for known in ("Desktop", "Documents", "Downloads"):
                if suffix.startswith(f"/{known}"):
                    suffix = suffix[len(f"/{known}"):]
                    return os.path.join(home, known, suffix.lstrip("/").replace("/", os.sep))
            return os.path.join(home, suffix.lstrip("/").replace("/", os.sep))
        return os.path.join(home, path[1:].replace("/", os.sep))

    # Windows-style absolute path on Unix
    if system == "posix" and len(path) > 1 and path[1] == ":":
        suffix = path[2:].lstrip("\\").replace("\\", "/")
        parts = suffix.split("/")
        if len(parts) >= 2 and parts[0].lower() == "users":
            subpath = "/".join(parts[2:]) if len(parts) > 2 else ""
            for known in ("Desktop", "Documents", "Downloads"):
                if subpath.startswith(known):
                    subpath = subpath[len(known):]
                    return os.path.join(home, known, subpath.lstrip("/"))
            return os.path.join(home, subpath)
        return os.path.join(home, suffix)

    return path


def _resolve_path(path: str) -> Path:
    """Resolve and validate a path is within SAFE_ROOTS."""
    normalized = _normalize_path_for_os(path)
    p = Path(normalized).resolve()
    for root in SAFE_ROOTS:
        if str(p).startswith(str(Path(root).resolve())):
            return p
    raise ValueError(f"Path '{path}' is outside allowed directories")


# ---- Security: command safety (from app/mcp/servers/shell.py) ----

BLOCKED_COMMANDS = {"rm", "del", "format", "fdisk", "mkfs", "dd"}


def _is_safe(command: str) -> bool:
    """Check if a shell command is safe to execute."""
    try:
        parts = shlex.split(command)
    except ValueError:
        return False
    if not parts:
        return False
    base = os.path.basename(parts[0]).lower()
    base = os.path.splitext(base)[0]
    return base not in BLOCKED_COMMANDS


# ---- Filesystem tool fallbacks ----

async def local_read_file(path: str) -> str:
    """Read the contents of a file."""
    try:
        target = _resolve_path(path)
        if not target.exists():
            return f"Error: File not found: {path}"
        if target.is_dir():
            return f"Error: Path is a directory: {path}"
        with open(target, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception as e:
        return f"Error reading file: {e}"


async def local_write_file(path: str, content: str) -> str:
    """Write content to a file. Creates directories if needed."""
    try:
        target = _resolve_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            f.write(content)
        return f"File written: {path}"
    except Exception as e:
        return f"Error writing file: {e}"


async def local_list_directory(path: str) -> str:
    """List files and directories at the given path."""
    try:
        target = _resolve_path(path)
        if not target.exists():
            return f"Error: Path not found: {path}"
        if not target.is_dir():
            return f"Error: Path is not a directory: {path}"
        entries = []
        for entry in target.iterdir():
            entry_type = "dir" if entry.is_dir() else "file"
            entries.append(f"[{entry_type}] {entry.name}")
        return "\n".join(entries) if entries else "(empty directory)"
    except Exception as e:
        return f"Error listing directory: {e}"


async def local_search_files(path: str, pattern: str) -> str:
    """Search for files matching a pattern recursively."""
    try:
        target = _resolve_path(path)
        if not target.exists():
            return f"Error: Path not found: {path}"
        matches = []
        for root, dirs, files in os.walk(str(target)):
            for fname in files:
                if fnmatch.fnmatch(fname, pattern):
                    matches.append(os.path.join(root, fname))
                    if len(matches) >= 100:
                        break
            if len(matches) >= 100:
                break
        if not matches:
            return f"No files matching '{pattern}' found in {path}"
        return "\n".join(matches)
    except Exception as e:
        return f"Error searching files: {e}"


# ---- Shell tool fallbacks ----

async def local_execute_command(command: str, timeout: int = 30, cwd: Optional[str] = None) -> str:
    """Execute a shell command and return stdout/stderr."""
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


async def local_run_script(script: str, interpreter: str = "python", timeout: int = 30) -> str:
    """Run a script using the specified interpreter."""
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
                ["python3", "-c", script],
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


# ---- Fallback registry ----
# Maps MCP tool names to their local fallback async functions.
# The fallback function receives keyword arguments matching the tool parameters.

LOCAL_FALLBACKS = {
    "filesystem__read_file": local_read_file,
    "filesystem__write_file": local_write_file,
    "filesystem__list_directory": local_list_directory,
    "filesystem__search_files": local_search_files,
    "shell__execute_command": local_execute_command,
    "shell__run_script": local_run_script,
}
