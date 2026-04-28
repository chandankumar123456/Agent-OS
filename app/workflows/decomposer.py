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

    OPEN_ACTIONS: tuple[str, ...] = ("open", "launch", "start")
    CONTENT_GENERATION_KEYWORDS: tuple[str, ...] = (
        "opinion", "summary", "summarize", "draft", "compose", "compare", "comparison",
        "thoughts", "explain",
    )
    TEXT_ENTRY_ACTIONS: tuple[str, ...] = ("type", "write", "enter", "paste")
    BROWSER_APPS: tuple[str, ...] = ("chrome", "browser", "edge", "firefox")

    # Cross-app workflow extension keywords (browser → reasoning → desktop → file)
    TRANSFORM_KEYWORDS: tuple[str, ...] = (
        "summarize", "summary", "rewrite", "analyze", "translate", "paraphrase",
    )
    EXTRACT_KEYWORDS: tuple[str, ...] = (
        "top result", "first result", "article", "extract", "open result", "open the top",
        "comments",
    )
    PASTE_KEYWORDS: tuple[str, ...] = (
        "paste", "type into", "type in", "write into", "write in", "paste into",
    )
    SAVE_KEYWORDS: tuple[str, ...] = (
        "save file", "save it", "save as", "save to", "save the file", "save summary",
        "and save", "save the summary",
    )
    DESKTOP_PASTE_TARGETS: set = {"notepad", "wordpad"}
    KNOWN_SITES: set = {
        "youtube", "gmail", "twitter", "x.com", "github", "reddit", "amazon",
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

    def _extract_opened_app(self, query_lower: str) -> Optional[str]:
        """Return the app name if query contains open/launch/start <app>."""
        for verb in self.OPEN_ACTIONS:
            match = re.search(rf"\b{verb}\b\s+(?:the\s+)?([a-z0-9\.\-\s]+)", query_lower)
            if not match:
                continue
            segment = match.group(1).strip()
            # Take up to 3 words to avoid capturing the whole sentence.
            words = segment.split()
            candidates = [" ".join(words[:i]) for i in range(min(3, len(words)), 0, -1)]
            for cand in candidates:
                if cand in self.DESKTOP_APP_KEYWORDS or cand in self.BROWSER_APPS:
                    return cand
        return None

    def _decompose_open_and_type_desktop(self, query: str, query_lower: str) -> List[WorkflowPhase]:
        """Special-case: open desktop app and type/write content."""
        app = self._extract_opened_app(query_lower)
        if not app or app in self.BROWSER_APPS:
            return []

        has_open = any(v in query_lower for v in self.OPEN_ACTIONS)
        has_text_entry = any(v in query_lower for v in self.TEXT_ENTRY_ACTIONS)
        if not (has_open and has_text_entry):
            return []

        needs_generation = any(k in query_lower for k in self.CONTENT_GENERATION_KEYWORDS)
        app_label = "Notepad" if app == "notepad" else app.title()

        phases: List[WorkflowPhase] = [
            WorkflowPhase(
                phase_id="phase_1",
                name="desktop_automation",
                description=f"Open {app_label} using desktop_env__open_application.",
                intent="desktop_automation",
                verification_criteria=[{"type": "desktop_app_opened", "app": app_label}],
            ),
            WorkflowPhase(
                phase_id="phase_2",
                name="desktop_automation",
                description=f"Verify {app_label} is open using desktop_env__get_window_list.",
                intent="desktop_automation",
                verification_criteria=[{"type": "window_visible", "app": app_label}],
            ),
        ]

        if needs_generation:
            phases.append(
                WorkflowPhase(
                    phase_id=f"phase_{len(phases) + 1}",
                    name="content_generation",
                    description=f"Generate the text content requested by the user before typing it into {app_label}. Original task: {query}",
                    intent="content_generation",
                    verification_criteria=[{"type": "text_generated"}],
                )
            )

        phases.extend([
            WorkflowPhase(
                phase_id=f"phase_{len(phases) + 1}",
                name="desktop_automation",
                description=f"Focus the {app_label} window using desktop_env__focus_window or desktop_env__ensure_focus.",
                intent="desktop_automation",
                verification_criteria=[{"type": "window_focused", "app": app_label}],
            ),
            WorkflowPhase(
                phase_id=f"phase_{len(phases) + 1}",
                name="desktop_automation",
                description=f"Type the requested text into {app_label} using desktop_env__type_text.",
                intent="desktop_automation",
                verification_criteria=[{"type": "desktop_action_completed"}],
            ),
            WorkflowPhase(
                phase_id=f"phase_{len(phases) + 1}",
                name="desktop_automation",
                description=f"Verify the text was entered in {app_label} using desktop_env__screenshot or desktop__get_ui_tree.",
                intent="desktop_automation",
                verification_criteria=[{"type": "text_entry_verified"}],
            ),
        ])
        return phases

    def _extract_search_query(self, query_lower: str) -> str:
        """Extract the actual search target between `search` and the next connector verb.

        Falls back to empty string when no clean phrase is found; caller should
        handle that case by emitting a generic search-step description.
        """
        connector = (
            r"summariz|rewrite|analyz|translat|paraphras|paste|"
            r"open\s+\w|save\b|then\b|after\s+that\b|next\b|finally\b|and\s+save\b"
        )
        m = re.search(
            rf"\bsearch\b\s+(?:for\s+)?(.+?)(?=\s+(?:and\s+)?(?:{connector})|$)",
            query_lower,
        )
        if not m:
            return ""
        phrase = m.group(1).strip(" .,;:'\"")
        # Strip leading filler words.
        for filler in ("for ", "the ", "about "):
            if phrase.startswith(filler):
                phrase = phrase[len(filler):]
        return phrase

    def _detect_browser_trigger(self, query_lower: str) -> Optional[str]:
        """Return browser/site label when query opens a browser or known web site.

        Scans every `open|launch|start|go to <target>` occurrence so that prompts
        like "open notepad ... then open chrome ..." still surface the browser.
        """
        for m in re.finditer(
            r"\b(open|launch|start|go\s+to)\b\s+(?:the\s+)?([a-z0-9\.\-]+)",
            query_lower,
        ):
            target = m.group(2)
            if target in self.BROWSER_APPS or target in self.KNOWN_SITES:
                return target
        return None

    def _decompose_open_browser_and_search(self, query_lower: str) -> List[WorkflowPhase]:
        """Special-case: open browser (or known site) then search query."""
        target = self._detect_browser_trigger(query_lower)
        if not target:
            return []

        has_open = any(v in query_lower for v in self.OPEN_ACTIONS) or "go to" in query_lower
        has_search = any(k in query_lower for k in ("search", "look up", "find", "google"))
        if not (has_open and has_search):
            return []

        search_query = self._extract_search_query(query_lower)
        if search_query:
            search_desc = (
                f'Search for "{search_query}" in the browser using browser_env__search '
                f'(query="{search_query}"). Do NOT pass the entire user prompt as the query.'
            )
        else:
            search_desc = "Search for the requested query in the browser using browser_env__search."

        # Site-specific navigation: route through the known site first when applicable.
        if target in self.KNOWN_SITES:
            site_domain = "x.com" if target == "x.com" else f"{target}.com"
            launch_desc = (
                f"Open the browser using browser_env__launch and navigate to https://{site_domain} "
                f"using browser_env__navigate."
            )
        else:
            launch_desc = "Open the browser using browser_env__launch."

        phases = [
            WorkflowPhase(
                phase_id="phase_1",
                name="browser_navigation",
                description=launch_desc,
                intent="browser_navigation",
                verification_criteria=[{"type": "browser_opened"}],
            ),
            WorkflowPhase(
                phase_id="phase_2",
                name="browser_navigation",
                description="Verify the browser window is open and ready using browser_env__screenshot.",
                intent="browser_navigation",
                verification_criteria=[{"type": "browser_opened"}],
            ),
            WorkflowPhase(
                phase_id="phase_3",
                name="browser_navigation",
                description=search_desc,
                intent="browser_navigation",
                verification_criteria=[{"type": "browser_navigated"}],
            ),
            WorkflowPhase(
                phase_id="phase_4",
                name="browser_navigation",
                description="Verify search results loaded using browser_env__get_text or browser_env__screenshot.",
                intent="browser_navigation",
                verification_criteria=[{"type": "web_content"}],
            ),
        ]
        return phases

    def _extend_browser_workflow(
        self,
        query: str,
        query_lower: str,
        base_phases: List[WorkflowPhase],
    ) -> List[WorkflowPhase]:
        """Append cross-app follow-up phases (extract / summarize / desktop / save)."""
        has_extract = any(k in query_lower for k in self.EXTRACT_KEYWORDS)
        has_transform = any(k in query_lower for k in self.TRANSFORM_KEYWORDS)
        has_paste = any(k in query_lower for k in self.PASTE_KEYWORDS)
        has_save = any(k in query_lower for k in self.SAVE_KEYWORDS) or bool(
            re.search(r"\bsave\b", query_lower)
        )
        desktop_target: Optional[str] = None
        for app in self.DESKTOP_PASTE_TARGETS:
            if app in query_lower:
                desktop_target = app
                break

        # If none of the cross-app verbs are present, leave the base 4-phase plan untouched.
        if not (has_extract or has_transform or has_paste or has_save or desktop_target):
            return base_phases

        phases = list(base_phases)
        next_id = lambda: f"phase_{len(phases) + 1}"

        # Step: open top result and extract its content. Comments wins over the
        # generic top-result branch so YouTube-style prompts capture the comment thread.
        if "comments" in query_lower:
            phases.append(WorkflowPhase(
                phase_id=next_id(),
                name="browser_navigation",
                description=(
                    "Open the top result and scroll to the comments section, then extract the "
                    "comments text using browser_env__get_text."
                ),
                intent="browser_navigation",
                verification_criteria=[{"type": "web_content"}],
            ))
        elif has_extract or has_transform:
            phases.append(WorkflowPhase(
                phase_id=next_id(),
                name="browser_navigation",
                description=(
                    "Open the top search result and extract its main article text "
                    "using browser_env__click on the first result link, then browser_env__get_text "
                    "to capture the article body."
                ),
                intent="browser_navigation",
                verification_criteria=[{"type": "web_content"}],
            ))

        # Step: reasoning transformation (summarize/rewrite/analyze/translate).
        if has_transform:
            phases.append(WorkflowPhase(
                phase_id=next_id(),
                name="document_processing",
                description=(
                    "Summarize / transform the extracted content into a concise summary "
                    "using document__summarize or text_processor. Store the resulting summary "
                    "text for downstream paste/save steps."
                ),
                intent="document_processing",
                verification_criteria=[{"type": "summary_generated"}],
            ))

        # Step: desktop paste target (open + focus + type).
        notepad_branch = bool(desktop_target and (has_paste or has_transform))
        app_label = "Notepad" if desktop_target == "notepad" else (
            desktop_target.title() if desktop_target else "Notepad"
        )
        if notepad_branch:
            phases.append(WorkflowPhase(
                phase_id=next_id(),
                name="desktop_automation",
                description=(
                    f"Open {app_label} using desktop_env__open_application. This switches focus "
                    f"away from the browser to the {app_label} window."
                ),
                intent="desktop_automation",
                verification_criteria=[{"type": "desktop_app_opened", "app": app_label}],
            ))
            phases.append(WorkflowPhase(
                phase_id=next_id(),
                name="desktop_automation",
                description=(
                    f"Focus the {app_label} window using desktop_env__focus_window or "
                    f"desktop_env__ensure_focus before typing, to guarantee correct app focus "
                    f"after the browser→{app_label} transition."
                ),
                intent="desktop_automation",
                verification_criteria=[{"type": "window_focused", "app": app_label}],
            ))
            phases.append(WorkflowPhase(
                phase_id=next_id(),
                name="desktop_automation",
                description=(
                    f"Type / paste the produced summary text into {app_label} using "
                    f"desktop_env__type_text (or desktop_env__set_clipboard followed by Ctrl+V via "
                    f"desktop_env__press_key)."
                ),
                intent="desktop_automation",
                verification_criteria=[{"type": "desktop_action_completed"}],
            ))

        # Step: persist to filesystem (default summary.txt on Desktop).
        if has_save:
            phases.append(WorkflowPhase(
                phase_id=next_id(),
                name="file_write",
                description=(
                    "Save the produced text to the user's Desktop as 'summary.txt' using "
                    "filesystem__write_file. If the user did not specify a filename, default to "
                    "'summary.txt'. If the user did not specify a folder, default to the Desktop "
                    "(fallback to Downloads). This filesystem write is the authoritative save."
                ),
                intent="file_write",
                verification_criteria=[{"type": "file_exists"}],
            ))
            # Mirror the save in the open Notepad window so the user sees a saved document.
            if notepad_branch:
                phases.append(WorkflowPhase(
                    phase_id=next_id(),
                    name="desktop_automation",
                    description=(
                        f"Press Ctrl+S in {app_label} using desktop_env__press_key, then type "
                        f"'summary.txt' into the save dialog with desktop_env__type_text and "
                        f"confirm with Enter so the open {app_label} window also persists the file."
                    ),
                    intent="desktop_automation",
                    verification_criteria=[{"type": "desktop_action_completed"}],
                ))

        return phases

    def decompose(self, query: str) -> List[WorkflowPhase]:
        """Decompose a user query into ordered workflow phases.

        Uses deterministic keyword heuristics to separate desktop UI
        tasks from browser/web tasks. Mixed prompts are split sequentially
        (desktop first, browser later).
        """
        query_lower = query.lower()
        phases: List[WorkflowPhase] = []

        # Special deterministic decompositions for common "open X then act" workflows.
        special_desktop = self._decompose_open_and_type_desktop(query, query_lower)
        if special_desktop:
            # Mixed workflow support: desktop action followed by browser search.
            browser_follow_up = self._decompose_open_browser_and_search(query_lower)
            if browser_follow_up:
                offset = len(special_desktop)
                for idx, phase in enumerate(browser_follow_up, start=1):
                    phase.phase_id = f"phase_{offset + idx}"
                special_desktop.extend(browser_follow_up)

            for i in range(1, len(special_desktop)):
                special_desktop[i].depends_on = [special_desktop[i - 1].phase_id]
            logger.info(
                f"[WorkflowDecomposer] Special decomposition (desktop open/type) into {len(special_desktop)} phases"
            )
            return special_desktop

        special_browser = self._decompose_open_browser_and_search(query_lower)
        if special_browser:
            extended = self._extend_browser_workflow(query, query_lower, special_browser)
            for i in range(1, len(extended)):
                extended[i].depends_on = [extended[i - 1].phase_id]
            logger.info(
                f"[WorkflowDecomposer] Special decomposition (browser cross-app) into {len(extended)} phases"
            )
            return extended

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
