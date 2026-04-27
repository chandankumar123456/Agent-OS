"""Capability Router — classifies tasks, detects required capabilities, and routes tasks."""
import re
from typing import List, Dict, Any, Optional

from .models import (
    Capability,
    CapabilityRequirement,
    CapabilityAssessment,
    ExecutionEnvironment,
)
from ..logs.logger import logger


class CapabilityRouter:
    """Analyzes user queries to determine required capabilities for execution.

    The router uses keyword heuristics combined with LLM-based classification
    to produce a CapabilityAssessment that drives downstream planning.
    """

    # Keyword patterns mapped to capabilities
    CAPABILITY_PATTERNS: Dict[Capability, List[str]] = {
        Capability.FILE: [
            "file", "files", "create file", "write file", "read file",
            "delete file", "edit file", "modify file", "save", "document",
            "csv", "json", "txt", "pdf", "desktop", "folder", "directory",
        ],
        Capability.CODE: [
            "code", "script", "python", "javascript", "typescript", "java",
            "run", "execute", "debug", "test", "compile", "build", "function",
            "class", "module", "program", "application", "app", "refactor",
        ],
        Capability.WEB: [
            "web", "website", "url", "http", "scrape", "search", "browse",
            "internet", "online", "page", "html", "download", "fetch",
            "api", "rest", "graphql", "endpoint",
        ],
        Capability.SHELL: [
            "shell", "command", "terminal", "bash", "powershell", "cmd",
            "run command", "execute command", "system", "install", "package",
            "git", "clone", "pull", "push", "commit", "docker", "compose",
        ],
        Capability.WORKFLOW: [
            "workflow", "pipeline", "automate", "schedule", "cron",
            "multi-step", "orchestrate", "chain", "dag", "sequence",
        ],
        Capability.DEPLOYMENT: [
            "deploy", "deployment", "server", "host", "publish", "release",
            "infrastructure", "cloud", "aws", "azure", "gcp", "kubernetes",
            "container", "docker", "vercel", "netlify",
        ],
        Capability.KNOWLEDGE: [
            "knowledge", "document", "rag", "search documents", "upload",
            "chunk", "embedding", "vector", "index", "retrieval",
        ],
        Capability.CHAT: [
            "chat", "conversation", "talk", "discuss", "brainstorm", "advice",
            "explain", "summarize", "translate", "help",
        ],
        Capability.RESEARCH: [
            "research", "investigate", "study", "analyze", "survey", "review",
            "literature", "findings", "explore", "discover", "academic",
            "paper", "journal", "source", "reference",
        ],
        Capability.COMMUNICATION: [
            "email", "message", "notify", "send", "contact", "call",
            "meeting", "calendar", "invite", "slack", "teams", "chat",
            "communication", "collaborate", "share", "report",
        ],
        Capability.DATA_PROCESSING: [
            "data", "process", "transform", "clean", "filter", "aggregate",
            "compute", "calculate", "statistics", "dataset", "dataframe",
            "csv", "excel", "spreadsheet", "table", "column", "row",
        ],
        Capability.DESKTOP: [
            "desktop", "gui", "window", "click", "type", "press key", "hotkey",
            "screenshot", "screen", "clipboard", "open app", "launch app",
            "menu", "dialog", "notification", "focus", "minimize", "maximize",
            "drag", "scroll", "right-click", "double-click", "form", "native",
            "open", "launch", "run app", "open notepad", "open file explorer",
        ],
    }

    # Safety flags — tasks that need extra scrutiny
    SAFETY_PATTERNS: Dict[str, List[str]] = {
        "destructive": ["delete", "remove", "drop", "destroy", "wipe", "rm -rf"],
        "system_mutation": ["install", "uninstall", "upgrade", "systemctl", "chmod", "chown"],
        "network_outbound": ["curl", "wget", "nc ", "netcat", "ssh", "telnet"],
        "credential_exposure": ["password", "secret", "token", "api_key", "private key"],
    }

    def __init__(self):
        self._compiled_patterns = {
            cap: [re.compile(rf"\b{re.escape(kw)}\b", re.IGNORECASE) for kw in kws]
            for cap, kws in self.CAPABILITY_PATTERNS.items()
        }
        self._compiled_safety = {
            flag: [re.compile(rf"\b{re.escape(kw)}\b", re.IGNORECASE) for kw in kws]
            for flag, kws in self.SAFETY_PATTERNS.items()
        }

    def classify(self, query: str, task_id: str = "") -> CapabilityAssessment:
        """Classify a user query into required capabilities."""
        query_lower = query.lower()
        scored_capabilities: Dict[Capability, float] = {}

        for cap, patterns in self._compiled_patterns.items():
            score = sum(1 for p in patterns if p.search(query_lower))
            if score > 0:
                scored_capabilities[cap] = score

        # Normalize scores
        max_score = max(scored_capabilities.values()) if scored_capabilities else 1.0
        normalized = {cap: min(score / max_score, 1.0) for cap, score in scored_capabilities.items()}

        # Default to CHAT if nothing else detected
        if not normalized:
            normalized = {Capability.CHAT: 1.0}

        # Determine primary capability
        primary = max(normalized, key=normalized.get)

        # Build requirements
        requirements: List[CapabilityRequirement] = []
        for cap, confidence in sorted(normalized.items(), key=lambda x: -x[1]):
            req = CapabilityRequirement(
                capability=cap,
                confidence=confidence,
                required_tools=self._suggest_tools(cap, query),
            )
            requirements.append(req)

        # Safety check
        safety_flags: List[str] = []
        for flag, patterns in self._compiled_safety.items():
            if any(p.search(query_lower) for p in patterns):
                safety_flags.append(flag)

        # Complexity heuristic
        complexity = len(requirements) + len(safety_flags)
        complexity = max(1, min(10, complexity))

        assessment = CapabilityAssessment(
            task_id=task_id,
            query=query,
            required_capabilities=requirements,
            primary_capability=primary,
            estimated_complexity=complexity,
            safety_flags=safety_flags,
        )

        logger.info(
            f"[CapabilityRouter] task={task_id} primary={primary.value} "
            f"caps={[r.capability.value for r in requirements]} safety={safety_flags}"
        )
        return assessment

    def route(self, assessment: CapabilityAssessment) -> str:
        """Determine the execution mode based on capability assessment."""
        caps = {r.capability for r in assessment.required_capabilities}

        if Capability.WORKFLOW in caps or len(caps) > 2:
            return "workflow"
        if Capability.DEPLOYMENT in caps:
            return "autonomous"
        if assessment.estimated_complexity > 5:
            return "autonomous"
        return "task"

    def _suggest_tools(self, cap: Capability, query: str) -> List[str]:
        """Suggest likely tools for a capability."""
        suggestions: Dict[Capability, List[str]] = {
            Capability.FILE: ["filesystem__write_file", "filesystem__read_file", "filesystem__list_directory"],
            Capability.CODE: ["shell__execute_command", "filesystem__write_file"],
            Capability.WEB: ["cloud_api__http_request", "cloud_api__scrape_page", "cloud_api__search_web"],
            Capability.SHELL: ["shell__execute_command", "shell__run_script"],
            Capability.WORKFLOW: [],
            Capability.DEPLOYMENT: ["shell__execute_command"],
            Capability.KNOWLEDGE: [],
            Capability.CHAT: [],
            Capability.RESEARCH: ["cloud_api__search_web", "cloud_api__http_request"],
            Capability.COMMUNICATION: ["cloud_api__send_email", "cloud_api__send_message"],
            Capability.DATA_PROCESSING: ["local__process_data", "local__compute_statistics"],
            Capability.DESKTOP: ["desktop_env__screenshot", "desktop_env__click", "desktop_env__type_text", "desktop_env__press_key", "desktop_env__get_window_list", "desktop_env__focus_window"],
        }
        return suggestions.get(cap, [])


class IntentRouter:
    """Maps capability assessments to execution environments dynamically."""

    ENVIRONMENT_MAP: Dict[Capability, ExecutionEnvironment] = {
        Capability.FILE: ExecutionEnvironment.FILE,
        Capability.CODE: ExecutionEnvironment.SHELL,
        Capability.WEB: ExecutionEnvironment.BROWSER_UI,
        Capability.SHELL: ExecutionEnvironment.SHELL,
        Capability.RESEARCH: ExecutionEnvironment.CLOUD_API,
        Capability.COMMUNICATION: ExecutionEnvironment.CLOUD_API,
        Capability.DATA_PROCESSING: ExecutionEnvironment.LOCAL,
        Capability.DEPLOYMENT: ExecutionEnvironment.SHELL,
        Capability.KNOWLEDGE: ExecutionEnvironment.CLOUD_API,
        Capability.CHAT: ExecutionEnvironment.LOCAL,
        Capability.WORKFLOW: ExecutionEnvironment.LOCAL,
        Capability.DESKTOP: ExecutionEnvironment.DESKTOP,
    }

    def select_environment(self, assessment: CapabilityAssessment) -> ExecutionEnvironment:
        """Select the most appropriate execution environment for a capability assessment."""
        primary = assessment.primary_capability
        return self.ENVIRONMENT_MAP.get(primary, ExecutionEnvironment.LOCAL)


# Global singletons
capability_router = CapabilityRouter()
intent_router = IntentRouter()
