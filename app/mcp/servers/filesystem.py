"""MCP Filesystem Server — provides file system tools to agents."""
import os
import fnmatch
from pathlib import Path
from typing import List

from mcp.server.fastmcp import FastMCP

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


def _resolve_path(path: str) -> Path:
    p = Path(path).resolve()
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
        matches: List[str] = []
        for root, _, files in os.walk(target):
            for filename in files:
                if fnmatch.fnmatch(filename, pattern):
                    matches.append(os.path.join(root, filename))
        if not matches:
            return f"No files matching '{pattern}' found in {path}"
        return "\n".join(matches[:100])  # Limit results
    except Exception as e:
        return f"Error searching files: {e}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
