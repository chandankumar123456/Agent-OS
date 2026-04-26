"""MCP Filesystem Server — provides file system tools to agents."""
import os
import fnmatch
from pathlib import Path
from typing import List

from mcp.server.fastmcp import FastMCP

from app.tools.file_discovery import FastFileDiscovery

mcp = FastMCP("filesystem")

# Security: restrict to working directory and common safe paths
_home = os.path.expanduser("~")
SAFE_ROOTS = [
    os.getcwd(),
    _home,
    os.path.join(_home, "Desktop"),
    os.path.join(_home, "Documents"),
    os.path.join(_home, "Downloads"),
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
        # /home/$USER/Desktop/... -> C:\Users\...\Desktop\...
        if path.startswith("/home/"):
            suffix = path[len("/home/"):]
            # Skip the username segment
            if "/" in suffix:
                suffix = suffix[suffix.find("/"):]
            else:
                suffix = ""
            # Map Desktop, Documents, Downloads
            for known in ("Desktop", "Documents", "Downloads"):
                if suffix.startswith(f"/{known}"):
                    suffix = suffix[len(f"/{known}"):]
                    return os.path.join(home, known, suffix.lstrip("/").replace("/", os.sep))
            return os.path.join(home, suffix.lstrip("/").replace("/", os.sep))
        # Generic Unix absolute path on Windows
        return os.path.join(home, path[1:].replace("/", os.sep))

    # Windows-style absolute path on Unix
    if system == "posix" and len(path) > 1 and path[1] == ":":
        # C:\Users\Name\Desktop\... -> /home/name/Desktop/...
        suffix = path[2:].lstrip("\\").replace("\\", "/")
        # Map known Windows user folders
        parts = suffix.split("/")
        if len(parts) >= 2 and parts[0].lower() == "users":
            # Skip the username segment
            subpath = "/".join(parts[2:]) if len(parts) > 2 else ""
            for known in ("Desktop", "Documents", "Downloads"):
                if subpath.startswith(known):
                    subpath = subpath[len(known):]
                    return os.path.join(home, known, subpath.lstrip("/"))
            return os.path.join(home, subpath)
        return os.path.join(home, suffix)

    return path


def _resolve_path(path: str) -> Path:
    normalized = _normalize_path_for_os(path)
    p = Path(normalized).resolve()
    for root in SAFE_ROOTS:
        if str(p).startswith(str(Path(root).resolve())):
            return p
    raise ValueError(f"Path '{path}' is outside allowed directories")


@mcp.tool()
async def read_file(path: str) -> str:
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


@mcp.tool()
async def write_file(path: str, content: str) -> str:
    """Write content to a file. Creates directories if needed."""
    try:
        target = _resolve_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            f.write(content)
        return f"File written: {path}"
    except Exception as e:
        return f"Error writing file: {e}"


@mcp.tool()
async def list_directory(path: str = ".") -> str:
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


@mcp.tool()
async def search_files(path: str, pattern: str) -> str:
    """Search for files matching a pattern recursively."""
    try:
        target = _resolve_path(path)
        if not target.exists():
            return f"Error: Path not found: {path}"
        engine = FastFileDiscovery()
        matches = await engine.search(str(target), pattern, max_results=100)
        if not matches:
            return f"No files matching '{pattern}' found in {path}"
        return "\n".join(matches)
    except Exception as e:
        return f"Error searching files: {e}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
