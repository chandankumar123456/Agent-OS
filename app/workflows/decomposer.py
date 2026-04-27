"""Workflow Decomposition Engine — breaks complex tasks into structured phases."""
import re
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field

from ..logs.logger import logger


@dataclass
class WorkflowPhase:
    """A single phase in a decomposed workflow."""
    phase_id: str
    name: str
    description: str
    intent: str
    verification_criteria: List[Dict[str, Any]] = field(default_factory=list)
    depends_on: List[str] = field(default_factory=list)


class WorkflowDecomposer:
    """Decomposes complex user queries into executable phases."""

    # Deterministic routing: native desktop app keywords
    # NOTE: "file explorer" / "explorer" are intentionally EXCLUDED because
    # "open file explorer" is a filesystem task, not a desktop UI automation task.
    DESKTOP_APP_KEYWORDS: set = {
        "notepad", "calculator", "calc", "paint", "mspaint",
        "vscode", "code.exe",
        "settings", "control panel", "wordpad", "cmd", "terminal",
        "powershell", "command prompt",
    }

    # Deterministic routing: browser/web keywords
    BROWSER_WEB_KEYWORDS: set = {
        "chrome", "google", "browser", "website", "web", "search",
        "youtube", "bing", "duckduckgo", "yahoo", "amazon",
        "url", "http", "https", "online", "internet",
    }

    # Deterministic routing: desktop UI action keywords
    DESKTOP_UI_ACTIONS: set = {
        "click", "type", "write text", "enter text", "fill",
        "press button", "check box", "select menu",
    }

    PHASE_PATTERNS: List[Dict[str, Any]] = [
        {
            "name": "file_search",
            "description": "Search the filesystem to locate the requested file or folder",
            "intents": ["find", "search", "locate", "look for", "where is"],
            "regexes": [r"\b(find|search|locate|look\s+for)\b.*\b(file|document|report|folder)\b"],
            "tools_hint": ["filesystem__search_files", "filesystem__list_directory"],
            "verification": [{"type": "file_found", "path_extractor": True}],
        },
        {
            "name": "file_read",
            "description": "Read the contents of the located file",
            "intents": ["read", "open file", "extract content", "get text from"],
            "regexes": [r"\b(read|open|extract)\b.*\b(file|document|report|text)\b"],
            "tools_hint": ["filesystem__read_file"],
            "verification": [{"type": "file_exists"}, {"type": "content_extracted"}],
        },
        {
            "name": "document_processing",
            "description": "Process, parse, or summarize the document content",
            "intents": ["summarize", "parse pdf", "parse docx", "extract from document", "chunk"],
            "regexes": [r"\b(summarize|parse|extract\s+from|chunk)\b.*\b(document|pdf|docx|report|text)\b"],
            "tools_hint": ["document__parse", "document__parse_pdf", "document__parse_docx", "text_processor"],
            "verification": [{"type": "content_extracted"}, {"type": "summary_generated"}],
        },
        {
            "name": "content_generation",
            "description": "Create or generate new files (HTML, CSS, JS, etc.)",
            "intents": ["create html", "create css", "create js", "generate html", "generate css", "generate js", "write file", "create file"],
            "regexes": [
                r"\b(create|generate|write)\b.*\b(html|css|js|javascript|file)\b",
                r"\b(html|css|js)\b.*\b(file|files)\b",
            ],
            "tools_hint": ["filesystem__write_file"],
            "verification": [{"type": "file_exists"}, {"type": "file_contains", "pattern": "html|css|javascript"}],
        },
        {
            "name": "browser_open",
            "description": "Open a file or URL in Chrome or the default browser",
            "intents": ["open in chrome", "open in browser", "view in browser", "show in chrome"],
            "regexes": [
                r"\b(open|view|show)\b.*\b(in\s+chrome|in\s+browser)\b",
                r"\bopen\b.*\bchrome\b",
            ],
            "tools_hint": ["browser_env__navigate"],
            "verification": [{"type": "browser_opened", "url_extractor": True}],
        },
        {
            "name": "browser_navigation",
            "description": "Navigate the browser to a website or perform web UI actions",
            "intents": ["browse", "navigate", "search in browser", "open website", "login to"],
            "regexes": [r"\b(browse|navigate|search\s+in|open\s+website|login\s+to)\b"],
            "tools_hint": ["browser_env__launch", "browser_env__navigate", "browser_env__search"],
            "verification": [{"type": "browser_navigated"}],
        },
        {
            "name": "desktop_automation",
            "description": "Use desktop UI automation (clicks, typing, screenshots, window management)",
            "intents": ["click", "type", "screenshot", "focus window"],
            "regexes": [
                r"\b(click|type|screenshot|focus\s+window)\b",
            ],
            "tools_hint": ["desktop__get_ui_tree", "desktop__click_element", "desktop__type_element", "desktop_env__screenshot", "desktop_env__focus_window"],
            "verification": [{"type": "desktop_action_completed"}],
        },
        {
            "name": "shell_execution",
            "description": "Run system commands or scripts",
            "intents": ["run command", "execute command", "install", "git ", "docker ", "npm ", "pip "],
            "regexes": [r"\b(run|execute)\b.*\b(command|script)\b", r"\b(install|git\s|docker\s|npm\s|pip\s)\b"],
            "tools_hint": ["shell__execute_command", "shell__run_script"],
            "verification": [{"type": "command_succeeds"}],
        },
        {
            "name": "web_search",
            "description": "Search the web for information",
            "intents": ["search web", "find online", "google", "look up"],
            "regexes": [r"\b(search\s+web|find\s+online|google|look\s+up)\b"],
            "tools_hint": ["cloud_api__search_web", "cloud_api__http_request", "web_search"],
            "verification": [{"type": "web_content"}],
        },
    ]

    def _classify_query(self, query: str) -> tuple[bool, bool]:
        """Return (has_desktop, has_browser) based on keyword presence."""
        q = query.lower()
        has_desktop = any(kw in q for kw in self.DESKTOP_APP_KEYWORDS)
        has_browser = any(kw in q for kw in self.BROWSER_WEB_KEYWORDS)
        has_ui_action = any(kw in q for kw in self.DESKTOP_UI_ACTIONS)

        # If UI actions present but no browser keyword, assume desktop
        if has_ui_action and not has_browser:
            has_desktop = True

        return has_desktop, has_browser

    def decompose(self, query: str) -> List[WorkflowPhase]:
        """Decompose a user query into ordered workflow phases.

        Uses deterministic keyword heuristics to separate desktop UI
        tasks from browser/web tasks. Mixed prompts are split sequentially
        (desktop first, browser later).
        """
        query_lower = query.lower()
        phases: List[WorkflowPhase] = []

        # Phase 1: Deterministic keyword-based classification
        has_desktop, has_browser = self._classify_query(query)

        # Phase 2: Pattern matching for additional context
        matched_patterns: List[str] = []
        for pattern in self.PHASE_PATTERNS:
            matched = False
            for regex in pattern.get("regexes", []):
                if re.search(regex, query_lower):
                    matched = True
                    break
            if not matched:
                for intent_keyword in pattern["intents"]:
                    if intent_keyword in query_lower:
                        matched = True
                        break
            if matched:
                matched_patterns.append(pattern["name"])

        # Phase 3: Build phase list with deterministic overrides
        # If native desktop apps detected, ALWAYS add desktop_automation first
        if has_desktop:
            phases.append(WorkflowPhase(
                phase_id="phase_1",
                name="desktop_automation",
                description="Interact with native desktop applications using UI automation",
                intent="desktop_automation",
                verification_criteria=[{"type": "desktop_action_completed"}],
            ))

        # If browser/web detected, add browser_navigation AFTER desktop
        if has_browser:
            phase_id = f"phase_{len(phases) + 1}"
            phases.append(WorkflowPhase(
                phase_id=phase_id,
                name="browser_navigation",
                description="Navigate browser and perform web UI actions",
                intent="browser_navigation",
                verification_criteria=[{"type": "browser_navigated"}],
            ))

        # Phase 4: Append pattern-based phases that are NOT already covered
        # by deterministic overrides. This preserves fine-grained decomposition
        # for multi-step workflows (e.g., file_search -> file_read -> browser_open).
        deterministic_names = {p.name for p in phases}
        for pattern_name in matched_patterns:
            if pattern_name not in deterministic_names:
                phase_id = f"phase_{len(phases) + 1}"
                pattern = next(p for p in self.PHASE_PATTERNS if p["name"] == pattern_name)
                phases.append(WorkflowPhase(
                    phase_id=phase_id,
                    name=pattern_name,
                    description=pattern.get("description", f"Execute {pattern_name}"),
                    intent=pattern_name,
                    verification_criteria=pattern.get("verification", []),
                ))

        # Phase 5: Ultimate fallback
        if not phases:
            phases.append(WorkflowPhase(
                phase_id="phase_1",
                name="general_execution",
                description="Execute the user request",
                intent="general",
            ))

        # Phase 6: Set dependencies (sequential execution)
        for i, phase in enumerate(phases):
            if i > 0:
                phase.depends_on = [phases[i - 1].phase_id]

        logger.info(f"[WorkflowDecomposer] Decomposed query into {len(phases)} phases: {[p.name for p in phases]}")
        return phases

    def extract_paths(self, text: str) -> List[str]:
        """Extract likely file paths from text."""
        pattern = re.compile(r"([A-Za-z]:\\[^\s\"'<>]+|/~?(?:/[^\s\"'<>]+)+|(?:\$HOME|~)/[^\s\"'<>]+)")
        return pattern.findall(text)

    def extract_urls(self, text: str) -> List[str]:
        """Extract URLs from text."""
        pattern = re.compile(r"https?://[^\s\"'<>]+")
        return pattern.findall(text)


# Singleton
workflow_decomposer = WorkflowDecomposer()
