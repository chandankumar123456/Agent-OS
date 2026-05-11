"""Shared path utilities for cross-platform path handling."""
import os
import platform
import re
from typing import Dict, Any, List, Optional


def get_desktop_path() -> str:
    """Return the user's Desktop absolute path for the current OS."""
    home = os.path.expanduser("~")
    if platform.system() == "Windows":
        user_desktop = os.path.join(home, "Desktop")
        if os.path.isdir(user_desktop):
            return user_desktop
        public_desktop = os.path.join(os.path.dirname(home), "Public", "Desktop")
        if os.path.isdir(public_desktop):
            return public_desktop
        return user_desktop
    elif platform.system() == "Darwin":
        return os.path.join(home, "Desktop")
    else:
        return os.path.join(home, "Desktop")


def looks_like_foreign_path(path: str) -> bool:
    """Check if a path looks like it belongs to a different OS."""
    if not path or not isinstance(path, str):
        return False
    system = platform.system()
    if system == "Windows" and (path.startswith("/") or path.startswith("~")):
        return True
    if system in ("Linux", "Darwin") and len(path) > 1 and path[1] == ":":
        return True
    return False


def remap_path(path: str, home_path: str, desktop_path: str) -> str:
    """Remap a hallucinated foreign path to the current OS."""
    if not looks_like_foreign_path(path):
        return path
    system = platform.system()
    if path.startswith("~/"):
        path = os.path.join(home_path, path[2:])
        return os.path.normpath(path)
    if system == "Windows":
        if re.match(r"/home/[^/]+/Desktop(/|$)", path):
            suffix = re.sub(r"/home/[^/]+/Desktop", "", path, count=1)
            return os.path.normpath(os.path.join(desktop_path, suffix.lstrip("/").replace("/", os.sep)))
        if re.match(r"/home/[^/]+(/|$)", path):
            suffix = re.sub(r"/home/[^/]+", "", path, count=1)
            return os.path.normpath(os.path.join(home_path, suffix.lstrip("/").replace("/", os.sep)))
        if path.startswith("/"):
            return os.path.normpath(os.path.join(home_path, path[1:].replace("/", os.sep)))
    if system in ("Linux", "Darwin"):
        if re.match(r"[A-Za-z]:\\Users\\[^\\]+\\Desktop(\\|$)", path):
            suffix = re.sub(r"[A-Za-z]:\\Users\\[^\\]+\\Desktop", "", path, count=1)
            return os.path.join(desktop_path, suffix.lstrip("\\").replace("\\", os.sep))
        if len(path) > 1 and path[1] == ":":
            suffix = re.sub(r"[A-Za-z]:(\\|/)", "", path, count=1)
            return os.path.join(home_path, suffix.replace("\\", os.sep))
    return path


def normalize_paths_in_text(text: str, home_path: str, desktop_path: str) -> str:
    """Replace common hallucinated paths in a text block with actual OS paths."""
    if not text or not isinstance(text, str):
        return text
    pattern = re.compile(r"(?:^|\s)([~]?(?:/[A-Za-z0-9_\-\$.]+)+/?|[A-Za-z]:\\(?:[^\\\s]+\\?)+)(?=$|\s)")
    def replace_match(m):
        p = m.group(1)
        remapped = remap_path(p, home_path, desktop_path)
        return m.group(0).replace(p, remapped)
    return pattern.sub(replace_match, text)


def remap_tool_params(params: Dict[str, Any], home_path: str, desktop_path: str) -> Dict[str, Any]:
    """Recursively remap foreign paths in tool parameters."""
    if not isinstance(params, dict):
        return params
    remapped = {}
    for key, value in params.items():
        if isinstance(value, str):
            remapped[key] = remap_path(value, home_path, desktop_path)
        elif isinstance(value, dict):
            remapped[key] = remap_tool_params(value, home_path, desktop_path)
        elif isinstance(value, list):
            remapped[key] = [
                remap_path(v, home_path, desktop_path) if isinstance(v, str) else
                remap_tool_params(v, home_path, desktop_path) if isinstance(v, dict) else v
                for v in value
            ]
        else:
            remapped[key] = value
    return remapped


def extract_path_from_description(description: str) -> Optional[str]:
    """Extract a likely file path from a step description."""
    matches = re.findall(r"([A-Za-z]:\\[^\s\"'<>]+|~?(?:/[^\s\"'<>]+)+)", description)
    return matches[0] if matches else None


def resolve_default_params(tool_name: str, description: str, desktop_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Build default parameters for obviously-intended tools without LLM."""
    path = extract_path_from_description(description)
    if desktop_path is None:
        desktop_path = get_desktop_path()
    if tool_name == "filesystem__read_file" and path:
        return {"path": path}
    if tool_name == "filesystem__list_directory" and path:
        return {"path": path}
    if tool_name == "filesystem__search_files":
        path_match = re.findall(r"([A-Za-z]:\\[^\s\"'<>]*|~?(?:/[^\s\"'<>]+)*)", description)
        search_path = path_match[0] if path_match else desktop_path
        words = description.lower().split()
        stopwords = {"find", "search", "locate", "look", "for", "my", "the", "a", "in", "under", "at", "file", "files", "and", "or"}
        pattern = "*"
        for w in words:
            if w not in stopwords and len(w) > 2:
                pattern = f"*{w}*"
                break
        return {"path": search_path, "pattern": pattern}
    if tool_name == "document__parse" and path:
        return {"path": path}
    if tool_name.startswith("browser_env__"):
        if "navigate" in description.lower() or "go to" in description.lower():
            url_match = re.findall(r"https?://[^\s\"'<>]+", description)
            if url_match:
                return {"url": url_match[0]}
        return None
    return None
