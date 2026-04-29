"""Action V1 Capability Selector.

Lightweight classification into Browser / Desktop / Filesystem / Multi-step.
No regex explosion. No LLM required for classification.
"""
from __future__ import annotations

import re
from typing import Dict, List, Set

from .models import Capability
from ..logs.logger import logger


class CapabilitySelector:
    """Classifies natural-language instructions into execution capabilities."""

    # Simple keyword groups (not regex explosion)
    BROWSER_KEYWORDS: Set[str] = {
        "browser", "chrome", "firefox", "edge", "web", "website", "site",
        "search", "google", "navigate", "url", "http", "click link",
        "fill form", "scroll page", "download", "browse",
    }

    DESKTOP_KEYWORDS: Set[str] = {
        "desktop", "notepad", "calculator", "calc", "open app", "launch app",
        "window", "focus", "type", "click", "press key", "hotkey",
        "screenshot", "clipboard", "menu", "dialog", "gui",
        "switch to", "minimize", "maximize", "close app",
    }

    FILESYSTEM_KEYWORDS: Set[str] = {
        "file", "files", "folder", "directory", "create file", "write file",
        "read file", "save file", "delete file", "edit file", "move file",
        "csv", "json", "txt", "pdf", "docx", "html", "css", "js",
        "desktop"  # overlaps with desktop, resolved by scoring
    }

    def classify(self, query: str) -> Capability:
        """Return the primary capability for a query."""
        query_lower = query.lower()
        words = set(re.findall(r"[a-z]+", query_lower))

        browser_score = len(words & self.BROWSER_KEYWORDS)
        desktop_score = len(words & self.DESKTOP_KEYWORDS)
        filesystem_score = len(words & self.FILESYSTEM_KEYWORDS)

        # Phrase-level bonuses (stronger signals)
        if any(p in query_lower for p in ("open chrome", "open browser", "search web", "navigate to")):
            browser_score += 3
        if any(p in query_lower for p in ("open notepad", "open calculator", "open calc", "type text")):
            desktop_score += 3
        if any(p in query_lower for p in ("create file", "write file", "save file", "static page", "html file")):
            filesystem_score += 3

        scores: Dict[Capability, int] = {
            Capability.BROWSER: browser_score,
            Capability.DESKTOP: desktop_score,
            Capability.FILESYSTEM: filesystem_score,
        }

        primary = max(scores, key=scores.get)  # type: ignore[arg-type]
        max_score = scores[primary]

        if max_score == 0:
            # Default heuristic: if it mentions "create", "write", "save" → filesystem
            if any(v in query_lower for v in ("create", "write", "save", "file", "page")):
                primary = Capability.FILESYSTEM
            else:
                primary = Capability.UNKNOWN

        # Multi-step detection: if query has conjunctions or multiple verbs
        multi_step_markers = [" and ", " then ", " → ", "->", "summarize", "after", ", ", "find ", "create ", "save "]
        marker_count = sum(1 for m in multi_step_markers if m in query_lower)
        if marker_count >= 2 or ("search" in query_lower and "save" in query_lower) or ("find" in query_lower and "create" in query_lower):
            primary = Capability.MULTI_STEP

        logger.info(f"[ActionV1] CapabilitySelector: query='{query[:60]}' → {primary.value} (scores={scores})")
        return primary

    def get_tools_for_capability(self, capability: Capability, all_tools: List[Dict[str, Any]]) -> List[str]:
        """Return tool names relevant to a capability."""
        prefixes: Dict[Capability, List[str]] = {
            Capability.BROWSER: ["browser_env__"],
            Capability.DESKTOP: ["desktop_env__", "desktop__"],
            Capability.FILESYSTEM: ["filesystem__", "shell__"],
            Capability.MULTI_STEP: ["browser_env__", "desktop_env__", "desktop__", "filesystem__", "shell__", "cloud_api__"],
            Capability.UNKNOWN: [],
        }
        wanted = prefixes.get(capability, [])
        return [
            t["name"] for t in all_tools
            if any(t["name"].startswith(p) for p in wanted)
        ]
