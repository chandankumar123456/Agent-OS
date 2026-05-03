"""Tool Grounding Layer — deterministic capability-to-tool mapping."""
from typing import Dict, List, Set, Optional, Any
from enum import Enum
from ..logs.logger import logger
from .registry import tool_registry


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
        "desktop_env__open_application",
        "desktop_env__launch_app_and_open_file",
        "desktop_env__screenshot",
        "desktop_env__click",
        "desktop_env__type_text",
        "desktop_env__press_key",
        "desktop_env__get_window_list",
        "desktop_env__focus_window",
        "desktop_env__ensure_focus",
        "desktop_env__get_window_registry",
        "desktop_env__save_checkpoint",
        "desktop_env__get_workflow_state",
        "desktop_env__set_approval_mode",
        "desktop_env__get_clipboard",
        "desktop_env__set_clipboard",
        "desktop_env__scroll",
        "desktop__get_ui_tree",
        "desktop__click_element",
        "desktop__type_element",
        "desktop__focus_and_interact",
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
    # ── File operations ───────────────────────────────────────────────
    "find file": "file_search",
    "search file": "file_search",
    "locate file": "file_search",
    "list directory": "file_search",
    "open folder": "file_search",
    "open file explorer": "file_search",
    "where is": "file_search",
    "look for file": "file_search",
    "read file": "file_read",
    "open file": "file_read",
    "view file": "file_read",
    "get file contents": "file_read",
    "read document": "file_read",
    "create file": "file_write",
    "write file": "file_write",
    "save file": "file_write",
    "write to file": "file_write",
    "append to file": "file_write",
    "update file": "file_write",
    "edit file": "file_write",
    # ── Document processing ───────────────────────────────────────────
    "extract text": "document_processing",
    "parse pdf": "document_processing",
    "parse docx": "document_processing",
    "parse document": "document_processing",
    "read pdf": "document_processing",
    "read docx": "document_processing",
    "process document": "document_processing",
    "summarize document": "document_processing",
    # ── Browser ───────────────────────────────────────────────────────
    "open chrome": "browser_navigation",
    "open browser": "browser_navigation",
    "navigate to": "browser_navigation",
    "visit website": "browser_navigation",
    "go to url": "browser_navigation",
    "open url": "browser_navigation",
    "browse web": "browser_navigation",
    "browse to": "browser_navigation",
    "search in browser": "browser_navigation",
    "browse": "browser_navigation",
    "click link": "browser_navigation",
    "fill form": "browser_navigation",
    "login to": "browser_navigation",
    "scroll page": "browser_navigation",
    "browser screenshot": "browser_navigation",
    # ── Desktop ───────────────────────────────────────────────────────
    "click": "desktop_automation",
    "screenshot": "desktop_automation",
    "type text": "desktop_automation",
    "press key": "desktop_automation",
    "focus window": "desktop_automation",
    "take screenshot": "desktop_automation",
    "open notepad": "desktop_automation",
    "launch app": "desktop_automation",
    "launch application": "desktop_automation",
    "open app": "desktop_automation",
    "open application": "desktop_automation",
    "desktop automation": "desktop_automation",
    "ui tree": "desktop_automation",
    "click element": "desktop_automation",
    "type element": "desktop_automation",
    "get window list": "desktop_automation",
    "start menu": "desktop_automation",
    "run dialog": "desktop_automation",
    # ── Shell ─────────────────────────────────────────────────────────
    "run command": "shell_execution",
    "execute command": "shell_execution",
    "run shell": "shell_execution",
    "execute shell": "shell_execution",
    "bash command": "shell_execution",
    "powershell": "shell_execution",
    "terminal": "shell_execution",
    "command prompt": "shell_execution",
    # ── Browser open (local files) ────────────────────────────────────
    "open in chrome": "browser_open",
    "open in browser": "browser_open",
    "view in browser": "browser_open",
    "show in browser": "browser_open",
    # ── Web search ────────────────────────────────────────────────────
    "search web": "web_search",
    "search internet": "web_search",
    "google ": "web_search",
    "look up": "web_search",
    "fetch data": "web_search",
    "scrape": "web_search",
    "find online": "web_search",
    "search for": "web_search",
    # ── Code execution ────────────────────────────────────────────────
    "run python": "code_execution",
    "execute code": "code_execution",
    "run script": "code_execution",
    "run js": "code_execution",
    "run javascript": "code_execution",
    "compile code": "code_execution",
    "execute python": "code_execution",
    "python script": "code_execution",
    # ── Content generation ────────────────────────────────────────────
    "generate html": "content_generation",
    "generate css": "content_generation",
    "generate js": "content_generation",
    "create html": "content_generation",
    "create css": "content_generation",
    "create js": "content_generation",
    "build webpage": "content_generation",
    "write html": "content_generation",
    "write css": "content_generation",
    # ── Communication ─────────────────────────────────────────────────
    "send email": "communication",
    "send message": "communication",
    "email ": "communication",
    "slack ": "communication",
    "notify ": "communication",
    "mail to": "communication",
    # ── Calculation ───────────────────────────────────────────────────
    "calculate": "calculation",
    "compute": "calculation",
    "sum ": "calculation",
    "add up": "calculation",
    "average": "calculation",
    "percentage": "calculation",
}


class ToolGroundingLayer:
    """Deterministically maps task intent to allowed tool sets."""

    DESKTOP_OPEN_VERBS = ("open", "launch", "start")
    DESKTOP_LAUNCH_TOOL_NAMES = (
        "desktop_env__open_application",
        "desktop_env__launch_app_and_open_file",
    )

    def classify_intent(self, step_description: str) -> str:
        """Classify a step description into a capability intent."""
        desc_lower = step_description.lower()

        # Fast-path indicators: if description mentions intent-specific verbs, never default to general
        intent_indicators = {
            "desktop_automation": [
                "notepad", "desktop automation", "ui tree", "click element", "type element",
                "focus window", "get window list", "start menu", "run dialog", "launch app",
                "open app", "open application", "launch application", "press key", "take screenshot",
                "desktop ", "screenshot", "type text",
            ],
            "browser_navigation": [
                "open chrome", "open browser", "navigate to", "visit website", "go to url",
                "open url", "browse web", "browse to", "click link", "fill form", "login to",
                "scroll page", "browser screenshot", "browser", "chrome", "website", "url",
                "web page", "webpage", "html page",
            ],
            "shell_execution": [
                "run command", "execute command", "run shell", "execute shell", "bash command",
                "powershell", "terminal", "cmd ", "command prompt", "shell script",
            ],
            "file_search": [
                "find file", "search file", "locate file", "list directory", "open folder",
                "open file explorer", "where is", "look for file", "where are",
            ],
            "file_read": [
                "read file", "open file", "view file", "get file contents", "read document",
                "contents of", "read the", ".txt", ".pdf", ".docx", ".md", ".json", ".py",
            ],
            "file_write": [
                "write file", "create file", "save file", "write to file", "append to file",
                "update file", "edit file", "write to", "save as", ".txt", ".md", ".json",
            ],
            "web_search": [
                "search web", "search internet", "google ", "look up", "fetch data",
                "scrape", "find online", "search for", "web search", "online search",
            ],
            "code_execution": [
                "run python", "execute code", "run script", "run js", "run javascript",
                "compile code", "execute python", "python script", "node ", "python ",
            ],
            "document_processing": [
                "parse pdf", "parse docx", "parse document", "read pdf", "read docx",
                "process document", "summarize document", "pdf", "docx", "extract text",
                "summarize", "document",
            ],
            "content_generation": [
                "generate html", "generate css", "generate js", "create html", "create css",
                "create js", "build webpage", "write html", "write css", "build website",
                "create website",
            ],
            "browser_open": [
                "open in chrome", "open in browser", "view in browser", "show in browser",
                "in chrome", "in browser", "launch browser",
            ],
            "communication": [
                "send email", "send message", "email ", "slack ", "notify ", "mail to",
                "email to", "message to",
            ],
            "calculation": [
                "calculate", "compute", "math", "sum ", "add up", "subtract", "multiply",
                "divide ", "average", "percentage", "total of", "count of",
            ],
        }
        for intent, indicators in intent_indicators.items():
            if any(ind in desc_lower for ind in indicators):
                return intent

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
        # FR4.3: Validate tools against registry at entry point (ground_tools replacement).
        # Warn about unregistered tools so phantom entries surface in production logs,
        # but do NOT exclude — MCP tools are registered late (post-discovery).
        registered_tool_names = set(tool_registry.tools.keys())
        for tool in all_tools:
            name = tool.get("name", "")
            if name and name not in registered_tool_names:
                logger.warning(f"Tool '{name}' not registered; may be phantom or pending MCP discovery")

        allowed_patterns = CAPABILITY_TOOL_MAP.get(intent, CAPABILITY_TOOL_MAP["general"])

        # Build exact-match allowed set (Issue 2 fix: no prefix leakage)
        allowed_names: Set[str] = set()
        all_tool_names = [t.get("name") for t in all_tools]
        for pattern in allowed_patterns:
            if "__" in pattern:
                # MCP-style tool name: exact match only (security fix)
                allowed_names.add(pattern)
            else:
                # Bare pattern: exact match + namespace expansion
                allowed_names.add(pattern)
                allowed_names.update(t for t in all_tool_names if t.startswith(pattern + "__"))

        allowed = [t for t in all_tools if t.get("name") in allowed_names]

        # Issue 3: Apply forbidden-prefix blacklist for ALL intents
        forbidden_prefixes = self._get_forbidden_prefixes(intent)
        if forbidden_prefixes:
            allowed = [t for t in allowed if not any(t.get("name", "").startswith(fp) for fp in forbidden_prefixes)]

        if not allowed:
            # For ANY specialized intent, NEVER silently fall back to generic tools.
            # Only "general" intent is allowed to use the broad fallback.
            if intent != "general":
                return []
            allowed = all_tools

        return allowed

    def _get_forbidden_prefixes(self, intent: str) -> Set[str]:
        """Return tool prefixes that should NEVER be used for a given intent."""
        browser_forbidden = {"browser_env__"}
        desktop_forbidden = {"desktop_env__"}
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
        allowed = self.get_allowed_tools(intent, all_tools)

        # Hard constraint: desktop open/launch/start requests must keep app-launch tools.
        desc_lower = step_description.lower()
        if intent == "desktop_automation" and any(v in desc_lower for v in self.DESKTOP_OPEN_VERBS):
            allowed_by_name = {t.get("name"): t for t in allowed}
            for tool in all_tools:
                name = tool.get("name", "")
                if name in self.DESKTOP_LAUNCH_TOOL_NAMES and name not in allowed_by_name:
                    allowed.append(tool)
        return allowed

    def get_intent_for_tool(self, tool_name: str) -> Optional[str]:
        """Reverse lookup: what intent is a tool valid for?"""
        for intent, patterns in CAPABILITY_TOOL_MAP.items():
            for pattern in patterns:
                if "__" in pattern:
                    if tool_name == pattern:
                        return intent
                else:
                    if tool_name == pattern or tool_name.startswith(pattern + "__"):
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
            "desktop_env__",
            "desktop__",
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
        # Launch/open tools must never be dropped for desktop automation plans.
        if intent == "desktop_automation":
            launch_tools = [t for t in ranked if t.get("name") in self.DESKTOP_LAUNCH_TOOL_NAMES]
            remainder = [t for t in ranked if t.get("name") not in self.DESKTOP_LAUNCH_TOOL_NAMES]
            ranked = launch_tools + remainder
        if exclude_desktop_for_non_desktop and intent != "desktop_automation":
            ranked = [t for t in ranked if not t.get("name", "").startswith(("desktop_env__", "desktop__"))]
        return ranked

    def get_fallback_tools(self, intent: str, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Get fallback tools (desktop, shell) for an intent."""
        all_tools = self.get_allowed_tools(intent, tools)
        primary_names = {t.get("name") for t in self.get_primary_tools(intent, tools, exclude_desktop_for_non_desktop=False)}
        fallback = [t for t in all_tools if t.get("name") not in primary_names]
        # For non-desktop intents, desktop tools are fallback
        if intent != "desktop_automation":
            desktop_fallback = [t for t in tools if t.get("name", "").startswith(("desktop_env__", "desktop__"))]
            fallback = fallback + [t for t in desktop_fallback if t.get("name") not in {f.get("name") for f in fallback}]
        return fallback

    def ground_tools(self, intent: str, all_tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Ground tool list against the global ToolRegistry.

        FR4.3: Warns if any tool in the capability map is not registered
        in the global ToolRegistry and excludes it from the grounded set.
        """
        registered_tool_names = set(tool_registry.tools.keys())
        grounded: List[Dict[str, Any]] = []
        for tool in all_tools:
            name = tool.get("name", "")
            if name and name not in registered_tool_names:
                logger.warning(
                    f"Tool '{name}' referenced in capability map but not registered in ToolRegistry. "
                    "It will be excluded from grounded tools."
                )
                continue
            grounded.append(tool)
        return grounded


# Singleton
tool_grounding_layer = ToolGroundingLayer()
