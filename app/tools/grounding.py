"""Tool Grounding Layer — deterministic capability-to-tool mapping."""
from typing import Dict, List, Set, Optional, Any
from enum import Enum


class ToolCategory(str, Enum):
    FILESYSTEM = "filesystem"
    BROWSER = "browser"
    DESKTOP = "desktop"
    SHELL = "shell"
    CLOUD = "cloud"
    CODE = "code"
    DOCUMENT = "document"
    COMMUNICATION = "communication"
    SEARCH = "search"
    CALCULATION = "calculation"
    UNKNOWN = "unknown"


# Capability → allowed tool name patterns (PRIMARY tools — ranked by preference)
CAPABILITY_TOOL_MAP: Dict[str, List[str]] = {
    "file_search": [
        "filesystem__search_files",
        "filesystem__list_directory",
        "shell__execute_command",
    ],
    "file_read": [
        "filesystem__read_file",
        "shell__execute_command",
    ],
    "file_write": [
        "filesystem__write_file",
        "shell__execute_command",
    ],
    "document_processing": [
        "document__parse",
        "document__parse_pdf",
        "document__parse_docx",
        "document__parse_txt",
        "document__parse_markdown",
        "filesystem__read_file",
        "text_processor",
    ],
    "browser_navigation": [
        "browser_env__launch",
        "browser_env__navigate",
        "browser_env__search",
        "browser_env__click",
        "browser_env__type",
        "browser_env__screenshot",
        "browser_env__get_text",
        "browser_env__close",
    ],
    "web_search": [
        "cloud_api__search_web",
        "cloud_api__http_request",
        "cloud_api__scrape_page",
        "web_search",
    ],
    "shell_execution": [
        "shell__execute_command",
        "shell__run_script",
        "shell__get_process_status",
    ],
    "desktop_automation": [
        "desktop_env__screenshot",
        "desktop_env__click",
        "desktop_env__type_text",
        "desktop_env__press_key",
        "desktop_env__get_window_list",
        "desktop_env__focus_window",
        "desktop_env__get_clipboard",
        "desktop_env__set_clipboard",
        "desktop_env__scroll",
        "desktop__desktop__screenshot",
        "desktop__desktop__click",
        "desktop__desktop__type_text",
        "desktop__desktop__press_key",
        "desktop__desktop__get_window_list",
        "desktop__desktop__focus_window",
    ],
    "content_generation": [
        "filesystem__write_file",
        "shell__execute_command",
        "shell__run_script",
    ],
    "browser_open": [
        "shell__execute_command",
        "browser_env__navigate",
        "browser_env__launch",
    ],
    "communication": [
        "cloud_api__send_email",
        "cloud_api__send_message",
        "slack__send_message",
    ],
    "code_execution": [
        "code_executor__run_python",
        "shell__execute_command",
        "shell__run_script",
    ],
    "calculation": [
        "calculator",
    ],
    "general": [
        "text_processor",
        "web_search",
        "calculator",
    ],
}

# Step intent keywords → capability
STEP_INTENT_MAP: Dict[str, str] = {
    # File operations
    "find file": "file_search",
    "search file": "file_search",
    "locate file": "file_search",
    "list directory": "file_search",
    "open folder": "file_search",
    "open file explorer": "file_search",
    "read file": "file_read",
    "extract text": "document_processing",
    "parse pdf": "document_processing",
    "parse docx": "document_processing",
    "summarize document": "document_processing",
    # Browser
    "open chrome": "browser_navigation",
    "open browser": "browser_navigation",
    "navigate to": "browser_navigation",
    "search in browser": "browser_navigation",
    "browse": "browser_navigation",
    # Desktop
    "click": "desktop_automation",
    "screenshot": "desktop_automation",
    "type text": "desktop_automation",
    "press key": "desktop_automation",
    "focus window": "desktop_automation",
    # Shell
    "run command": "shell_execution",
    "execute command": "shell_execution",
    # Browser open (local files)
    "open in chrome": "browser_open",
    "open in browser": "browser_open",
    "view in browser": "browser_open",
    # Web
    "search web": "web_search",
    "fetch data": "web_search",
    "scrape": "web_search",
    # Code
    "run python": "code_execution",
    "execute code": "code_execution",
    # Write
    "create file": "file_write",
    "write file": "file_write",
    "generate html": "content_generation",
    "generate css": "content_generation",
    "generate js": "content_generation",
    "create html": "content_generation",
    "create css": "content_generation",
    "create js": "content_generation",
}


class ToolGroundingLayer:
    """Deterministically maps task intent to allowed tool sets."""

    def classify_intent(self, step_description: str) -> str:
        """Classify a step description into a capability intent."""
        desc_lower = step_description.lower()
        best_intent = "general"
        best_score = 0
        for keyword, intent in STEP_INTENT_MAP.items():
            if keyword in desc_lower:
                score = len(keyword)
                if score > best_score:
                    best_score = score
                    best_intent = intent
        return best_intent

    def get_allowed_tools(self, intent: str, all_tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter the full tool list to only tools allowed for this intent."""
        allowed_patterns = CAPABILITY_TOOL_MAP.get(intent, CAPABILITY_TOOL_MAP["general"])
        allowed = []
        for tool in all_tools:
            name = tool.get("name", "")
            for pattern in allowed_patterns:
                if name == pattern or name.startswith(pattern.rsplit("__", 1)[0] + "__"):
                    allowed.append(tool)
                    break
        if not allowed:
            forbidden_prefixes = self._get_forbidden_prefixes(intent)
            allowed = [t for t in all_tools if not any(t.get("name", "").startswith(fp) for fp in forbidden_prefixes)]
        return allowed

    def _get_forbidden_prefixes(self, intent: str) -> Set[str]:
        """Return tool prefixes that should NEVER be used for a given intent."""
        browser_forbidden = {"browser_env__"}
        desktop_forbidden = {"desktop_env__", "desktop__desktop__"}
        comm_forbidden = {"cloud_api__send", "slack__"}
        forbidden_map = {
            "file_search": browser_forbidden | comm_forbidden,
            "file_read": browser_forbidden | desktop_forbidden | comm_forbidden,
            "file_write": browser_forbidden | desktop_forbidden | comm_forbidden,
            "document_processing": browser_forbidden | desktop_forbidden | comm_forbidden,
            "content_generation": browser_forbidden | desktop_forbidden | comm_forbidden,
            "browser_navigation": desktop_forbidden | {"shell__execute_command"},
            "browser_open": desktop_forbidden | comm_forbidden,
            "desktop_automation": browser_forbidden | comm_forbidden,
            "shell_execution": browser_forbidden | desktop_forbidden | comm_forbidden,
            "web_search": desktop_forbidden | comm_forbidden,
            "code_execution": browser_forbidden | desktop_forbidden | comm_forbidden,
            "calculation": browser_forbidden | desktop_forbidden | comm_forbidden | {"shell__", "filesystem__", "cloud_api__"},
        }
        return forbidden_map.get(intent, set())

    def filter_tools_for_step(self, step_description: str, all_tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Main entry point: given a step description, return grounded tools."""
        intent = self.classify_intent(step_description)
        return self.get_allowed_tools(intent, all_tools)

    def get_intent_for_tool(self, tool_name: str) -> Optional[str]:
        """Reverse lookup: what intent is a tool valid for?"""
        for intent, patterns in CAPABILITY_TOOL_MAP.items():
            for pattern in patterns:
                if tool_name == pattern or tool_name.startswith(pattern.rsplit("__", 1)[0] + "__"):
                    return intent
        return None

    def is_tool_allowed(self, tool_name: str, step_description: str) -> bool:
        """Check if a specific tool is allowed for a step."""
        intent = self.classify_intent(step_description)
        allowed = self.get_allowed_tools(intent, [{"name": tool_name}])
        return len(allowed) > 0

    def rank_tools_for_intent(self, intent: str, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Rank tools for an intent: filesystem → document → browser → shell → cloud → desktop."""
        priority_order = [
            "filesystem__",
            "document__",
            "browser_env__",
            "shell__",
            "cloud_api__",
            "web_search",
            "calculator",
            "text_processor",
            "code_executor__",
            "desktop__desktop__",
            "desktop_env__",
        ]
        allowed = self.get_allowed_tools(intent, tools)

        def _score(tool: Dict[str, Any]) -> int:
            name = tool.get("name", "")
            for idx, prefix in enumerate(priority_order):
                if name.startswith(prefix) or name == prefix:
                    return idx
            return len(priority_order)

        return sorted(allowed, key=_score)

    def get_primary_tools(self, intent: str, tools: List[Dict[str, Any]], exclude_desktop_for_non_desktop: bool = True) -> List[Dict[str, Any]]:
        """Get primary (non-fallback) tools for an intent, excluding desktop unless intent is desktop."""
        ranked = self.rank_tools_for_intent(intent, tools)
        if exclude_desktop_for_non_desktop and intent != "desktop_automation":
            ranked = [t for t in ranked if not t.get("name", "").startswith(("desktop_env__", "desktop__desktop__"))]
        return ranked

    def get_fallback_tools(self, intent: str, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Get fallback tools (desktop, shell) for an intent."""
        all_tools = self.get_allowed_tools(intent, tools)
        primary_names = {t.get("name") for t in self.get_primary_tools(intent, tools, exclude_desktop_for_non_desktop=False)}
        fallback = [t for t in all_tools if t.get("name") not in primary_names]
        # For non-desktop intents, desktop tools are fallback
        if intent != "desktop_automation":
            desktop_fallback = [t for t in tools if t.get("name", "").startswith(("desktop_env__", "desktop__desktop__"))]
            fallback = fallback + [t for t in desktop_fallback if t.get("name") not in {f.get("name") for f in fallback}]
        return fallback


# Singleton
tool_grounding_layer = ToolGroundingLayer()
