"""Adaptive execution router for fast-path task handling.

This module introduces a lightweight pre-planner routing layer:
- Tier 0: Direct deterministic execution for atomic intents.
- Tier 1: Lightweight sequential execution for small workflows.
- Tier 2: Existing full LangGraph runtime.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Dict, List, Optional, Sequence, Tuple
from uuid import UUID

from ..logs.logger import logger
from ..tools.base import ToolOutput
from ..tools.registry import tool_registry

# Lazy import to avoid circular deps on module load
def _get_llm_client():
    from ..agents.llm_client import get_llm_client
    return get_llm_client()


class ExecutionTier(IntEnum):
    DIRECT = 0
    SEQUENTIAL = 1
    FULL_RUNTIME = 2


@dataclass(frozen=True)
class TaskIntent:
    kind: str
    argument: Optional[str] = None
    raw_clause: str = ""


@dataclass(frozen=True)
class TaskRoutingDecision:
    tier: ExecutionTier
    reason: str
    intents: Tuple[TaskIntent, ...] = ()
    has_multi_step: bool = False
    uses_external_dependencies: bool = False
    reasoning_depth: str = "simple"


@dataclass
class ExecutionReport:
    success: bool
    execution_path: str
    tier: ExecutionTier
    actions: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None
    verification: Dict[str, Any] = field(default_factory=dict)

    def to_output(self, query: str, task_id: UUID) -> Dict[str, Any]:
        return {
            "query": query,
            "task_id": str(task_id),
            "execution_path": self.execution_path,
            "tier": int(self.tier),
            "actions": self.actions,
            "verification": self.verification,
            "success": self.success,
            "error": self.error,
        }


class TaskComplexityRouter:
    """Classifies tasks into Tier 0/1/2 before planner invocation."""

    _COMPLEX_KEYWORDS = {
        "workflow", "orchestrate", "pipeline", "research", "summarize",
        "generate", "webpage", "preview", "multi-app", "multi step",
        "code generation", "document", "docs", "pdf", "docx",
        "write code", "refactor", "debug", "compile",
    }
    _HIGH_REASONING_KEYWORDS = {
        "analyze", "compare", "tradeoff", "strategy", "plan",
        "latest", "benchmark", "investigate", "design",
    }
    _MULTI_STEP_MARKERS = (" and ", " then ", " after ", " before ", ",")
    _BROWSER_APPS = {"browser", "chrome", "edge", "firefox", "brave", "opera"}
    _STOP_WORDS = {
        "the", "a", "an", "my", "to", "in", "on", "for", "with", "from",
        "at", "please", "app", "application",
    }
    _ASCII_ACTION_KEYWORDS = ("draw", "generate", "create", "make")
    _ASCII_DESCRIPTOR_KEYWORDS = ("ascii", "diagram", "sketch", "art")

    def classify(self, query: str) -> TaskRoutingDecision:
        normalized = " ".join(query.lower().strip().split())
        intents = tuple(self.extract_intents(query))
        intent_count = len(intents)
        has_multi_step = self._has_multi_step(normalized, intent_count)
        uses_external_dependencies = self._uses_external_dependencies(normalized)
        reasoning_depth = "high" if self._needs_high_reasoning(normalized) else "simple"

        if intent_count == 0:
            return TaskRoutingDecision(
                tier=ExecutionTier.FULL_RUNTIME,
                reason="No deterministic intent detected; using full runtime",
                intents=intents,
                has_multi_step=has_multi_step,
                uses_external_dependencies=uses_external_dependencies,
                reasoning_depth=reasoning_depth,
            )

        if self._is_chained_ascii_output_flow(intents):
            return TaskRoutingDecision(
                tier=ExecutionTier.SEQUENTIAL,
                reason="Deterministic chained text+ASCII output flow",
                intents=intents,
                has_multi_step=True,
                uses_external_dependencies=False,
                reasoning_depth="simple",
            )

        if intent_count >= 3 or uses_external_dependencies or reasoning_depth == "high" and intent_count >= 2:
            return TaskRoutingDecision(
                tier=ExecutionTier.FULL_RUNTIME,
                reason=(
                    f"Complex request (intent_count={intent_count}, "
                    f"external_dependencies={uses_external_dependencies}, reasoning={reasoning_depth})"
                ),
                intents=intents,
                has_multi_step=has_multi_step,
                uses_external_dependencies=uses_external_dependencies,
                reasoning_depth=reasoning_depth,
            )

        if intent_count == 1 and not has_multi_step:
            only = intents[0]
            if only.kind in {
                "open_app",
                "open_browser",
                "close_app",
                "type_text",
                "press_key",
                "open_file",
                "open_folder",
                "launch_browser",
            }:
                return TaskRoutingDecision(
                    tier=ExecutionTier.DIRECT,
                    reason=f"Single atomic deterministic intent: {only.kind}",
                    intents=intents,
                    has_multi_step=False,
                    uses_external_dependencies=uses_external_dependencies,
                    reasoning_depth=reasoning_depth,
                )
            if only.kind == "search":
                # Search with actual content is treated as lightweight sequential
                if only.argument:
                    return TaskRoutingDecision(
                        tier=ExecutionTier.SEQUENTIAL,
                        reason="Search request requires lightweight browser orchestration",
                        intents=intents,
                        has_multi_step=False,
                        uses_external_dependencies=uses_external_dependencies,
                        reasoning_depth=reasoning_depth,
                    )
                return TaskRoutingDecision(
                    tier=ExecutionTier.DIRECT,
                    reason="Single atomic search launcher intent",
                    intents=intents,
                    has_multi_step=False,
                    uses_external_dependencies=uses_external_dependencies,
                    reasoning_depth=reasoning_depth,
                )
            if only.kind == "create_file":
                return TaskRoutingDecision(
                    tier=ExecutionTier.SEQUENTIAL,
                    reason="Single file creation intent requires content generation",
                    intents=intents,
                    has_multi_step=False,
                    uses_external_dependencies=uses_external_dependencies,
                    reasoning_depth=reasoning_depth,
                )

        if intent_count <= 2:
            supported = {
                "open_app",
                "open_browser",
                "launch_browser",
                "search",
                "type_text",
                "press_key",
                "generate_ascii_art",
                "open_file",
                "open_folder",
                "create_sheet",
                "close_app",
                "create_file",
            }
            if all(intent.kind in supported for intent in intents):
                return TaskRoutingDecision(
                    tier=ExecutionTier.SEQUENTIAL,
                    reason=f"Small structured flow with {intent_count} intent(s)",
                    intents=intents,
                    has_multi_step=has_multi_step,
                    uses_external_dependencies=uses_external_dependencies,
                    reasoning_depth=reasoning_depth,
                )

        return TaskRoutingDecision(
            tier=ExecutionTier.FULL_RUNTIME,
            reason="Defaulting to full runtime for safety",
            intents=intents,
            has_multi_step=has_multi_step,
            uses_external_dependencies=uses_external_dependencies,
            reasoning_depth=reasoning_depth,
        )

    def extract_intents(self, query: str) -> List[TaskIntent]:
        normalized = " ".join(query.lower().strip().split())
        clauses = self._split_clauses(normalized)
        intents: List[TaskIntent] = []

        for clause in clauses:
            clause = clause.strip(" .")
            if not clause:
                continue

            if "create" in clause and "sheet" in clause:
                intents.append(TaskIntent(kind="create_sheet", raw_clause=clause))
                continue

            file_topic = self._extract_file_creation_topic(clause)
            if file_topic is not None:
                intents.append(TaskIntent(kind="create_file", argument=file_topic, raw_clause=clause))
                continue

            open_file_path = self._extract_file_path(clause)
            if open_file_path and any(k in clause for k in ("open file", "open folder", "open directory", "open path")):
                kind = "open_folder" if os.path.isdir(open_file_path) else "open_file"
                intents.append(TaskIntent(kind=kind, argument=open_file_path, raw_clause=clause))
                continue

            if any(k in clause for k in ("open folder", "open directory")):
                folder_arg = self._extract_path_after_keyword(clause, ("open folder", "open directory"))
                intents.append(TaskIntent(kind="open_folder", argument=folder_arg, raw_clause=clause))
                continue

            if any(k in clause for k in ("open file", "open document")):
                file_arg = self._extract_path_after_keyword(clause, ("open file", "open document"))
                intents.append(TaskIntent(kind="open_file", argument=file_arg, raw_clause=clause))
                continue

            if any(k in clause for k in ("launch browser", "open browser")):
                intents.append(TaskIntent(kind="launch_browser", argument="chrome", raw_clause=clause))
                continue

            app_target = self._extract_open_target(clause)
            if app_target:
                if app_target in self._BROWSER_APPS:
                    intents.append(TaskIntent(kind="open_browser", argument=app_target, raw_clause=clause))
                else:
                    intents.append(TaskIntent(kind="open_app", argument=app_target, raw_clause=clause))
                continue

            close_target = self._extract_close_target(clause)
            if close_target:
                intents.append(TaskIntent(kind="close_app", argument=close_target, raw_clause=clause))
                continue

            search_query = self._extract_search_query(clause)
            if search_query is not None:
                intents.append(TaskIntent(kind="search", argument=search_query, raw_clause=clause))
                continue

            ascii_subject = self._extract_ascii_subject(clause)
            if ascii_subject is not None:
                if self._needs_newline_before_ascii(clause):
                    intents.append(TaskIntent(kind="press_key", argument="enter", raw_clause=clause))
                intents.append(TaskIntent(kind="generate_ascii_art", argument=ascii_subject, raw_clause=clause))
                continue

            typed_text = self._extract_typed_text(clause)
            if typed_text is not None:
                intents.append(TaskIntent(kind="type_text", argument=typed_text, raw_clause=clause))
                continue

        return intents

    def _split_clauses(self, normalized: str) -> List[str]:
        clauses = re.split(r"\b(?:and then|then|and)\b|,", normalized)
        return [c.strip() for c in clauses if c.strip()]

    def _has_multi_step(self, normalized: str, intent_count: int) -> bool:
        if intent_count > 1:
            return True
        return any(marker in normalized for marker in self._MULTI_STEP_MARKERS)

    def _uses_external_dependencies(self, normalized: str) -> bool:
        return any(keyword in normalized for keyword in self._COMPLEX_KEYWORDS)

    def _needs_high_reasoning(self, normalized: str) -> bool:
        return any(keyword in normalized for keyword in self._HIGH_REASONING_KEYWORDS)

    def _extract_open_target(self, clause: str) -> Optional[str]:
        match = re.search(r"\b(?:open|launch|start)\b\s+(?:the\s+)?([a-z0-9\.\-\s]+)", clause)
        if not match:
            return None
        target = match.group(1).strip()
        target = re.split(r"\b(?:and|then|to|for|with|in|on)\b", target)[0].strip()
        words = [w for w in target.split() if w not in self._STOP_WORDS]
        if not words:
            return None
        if len(words) > 3:
            words = words[:3]
        return " ".join(words)

    def _extract_close_target(self, clause: str) -> Optional[str]:
        match = re.search(r"\b(?:close|quit|exit)\b\s+(?:the\s+)?([a-z0-9\.\-\s]+)", clause)
        if not match:
            return None
        target = match.group(1).strip()
        target = re.split(r"\b(?:and|then|to|for|with|in|on)\b", target)[0].strip()
        words = [w for w in target.split() if w not in self._STOP_WORDS]
        if not words:
            return None
        return " ".join(words[:3])

    def _extract_search_query(self, clause: str) -> Optional[str]:
        if not any(k in clause for k in ("search", "google", "look up")):
            return None
        match = re.search(r"\b(?:search(?:\s+google)?|google|look\s+up)\b(?:\s+for)?\s*(.*)$", clause)
        if not match:
            return ""
        query = match.group(1).strip(" .")
        if query in {"", "google", "web"}:
            return ""
        return query

    def _extract_typed_text(self, clause: str) -> Optional[str]:
        if not any(k in clause for k in ("type", "write", "enter")):
            return None

        quoted = re.search(r"(?:type|write|enter(?:\s+text)?)\s+['\"]([^'\"]+)['\"]", clause)
        if quoted:
            return quoted.group(1).strip()

        unquoted = re.search(r"(?:type|write|enter(?:\s+text)?)\s+(.+)$", clause)
        if not unquoted:
            return ""
        text = unquoted.group(1).strip(" .")
        return text

    def _extract_ascii_subject(self, clause: str) -> Optional[str]:
        if not any(k in clause for k in self._ASCII_ACTION_KEYWORDS):
            return None
        if not any(k in clause for k in self._ASCII_DESCRIPTOR_KEYWORDS):
            return None

        match = re.search(r"\b(?:draw|generate|create|make)\b\s+(.+)$", clause)
        if not match:
            return ""

        subject = match.group(1).strip(" .")
        subject = re.sub(
            r"^(?:an?\s+)?(?:ascii\s+)?(?:(?:art|diagram|sketch)\s*)?(?:of\s+)?",
            "",
            subject,
        ).strip(" .")
        return subject or ""

    def _needs_newline_before_ascii(self, clause: str) -> bool:
        return any(marker in clause for marker in ("below", "next line", "new line", "newline"))

    def _is_chained_ascii_output_flow(self, intents: Sequence[TaskIntent]) -> bool:
        if not intents:
            return False
        supported = {"open_app", "type_text", "press_key", "generate_ascii_art"}
        kinds = [intent.kind for intent in intents]
        return (
            all(kind in supported for kind in kinds)
            and "open_app" in kinds
            and "type_text" in kinds
            and "generate_ascii_art" in kinds
        )

    def _extract_file_path(self, clause: str) -> Optional[str]:
        quoted = re.findall(r"['\"]([^'\"]+)['\"]", clause)
        for candidate in quoted:
            if os.path.isabs(candidate) or os.path.exists(candidate):
                return candidate

        absolute = re.search(r"([A-Za-z]:\\[^\s\"'<>]+|/(?:[^\s\"'<>]+/)*[^\s\"'<>]+)", clause)
        if absolute:
            return absolute.group(1)
        return None

    def _extract_path_after_keyword(self, clause: str, keywords: Sequence[str]) -> Optional[str]:
        for keyword in keywords:
            if keyword not in clause:
                continue
            after = clause.split(keyword, 1)[1].strip(" .")
            if not after:
                return None
            quoted = re.search(r"['\"]([^'\"]+)['\"]", after)
            if quoted:
                return quoted.group(1)
            return after

    def _extract_file_creation_topic(self, clause: str) -> Optional[str]:
        creation_keywords = ("create", "write", "generate", "make")
        file_keywords = ("file", "page", "html", "script", "document", "txt", "css", "js", "json")
        if not any(k in clause for k in creation_keywords):
            return None
        if not any(k in clause for k in file_keywords):
            return None
        # Try to extract the descriptive topic after creation keywords.
        match = re.search(r"\b(?:create|write|generate|make)\b\s+(?:a\s+)?(?:static\s+)?(?:html\s+)?(?:page|file|document)\s+(?:on|about|for|with|called|named)?\s*(.+)$", clause)
        if match:
            topic = match.group(1).strip(" .")
            # Remove trailing prepositional phrases like "on it", "for me"
            topic = re.split(r"\b(?:on it|for me|for us|please)\b", topic)[0].strip(" .")
            return topic or ""
        # Fallback: if clause is clearly about creating a file, return the whole clause.
        return clause
        return None


class DirectExecutor:
    """Tier 0 deterministic executor for atomic tasks."""

    async def execute(self, task_id: UUID, query: str, intent: TaskIntent) -> ExecutionReport:
        action_log: List[Dict[str, Any]] = []
        task_id_str = str(task_id)

        try:
            if intent.kind in {"open_app", "open_browser", "launch_browser"}:
                app_name = intent.argument or "chrome"
                result = await self._tool("desktop_env__open_application", {"app_name": app_name}, task_id_str)
                action_log.append(self._action("desktop_env__open_application", {"app_name": app_name}, result))
                return self._report(result, action_log, ExecutionTier.DIRECT)

            if intent.kind == "close_app":
                target = intent.argument or ""
                focus_result = await self._tool("desktop_env__focus_window", {"title": target}, task_id_str)
                action_log.append(self._action("desktop_env__focus_window", {"title": target}, focus_result))
                key_result = await self._tool("desktop_env__press_key", {"keys": "alt+f4"}, task_id_str)
                action_log.append(self._action("desktop_env__press_key", {"keys": "alt+f4"}, key_result))
                return self._report(key_result, action_log, ExecutionTier.DIRECT)

            if intent.kind == "type_text":
                text = intent.argument or ""
                result = await self._tool("desktop_env__type_text", {"text": text}, task_id_str)
                action_log.append(self._action("desktop_env__type_text", {"text": text}, result))
                return self._report(result, action_log, ExecutionTier.DIRECT)

            if intent.kind == "press_key":
                keys = (intent.argument or "enter").strip() or "enter"
                result = await self._tool("desktop_env__press_key", {"keys": keys}, task_id_str)
                action_log.append(self._action("desktop_env__press_key", {"keys": keys}, result))
                return self._report(result, action_log, ExecutionTier.DIRECT)

            if intent.kind == "generate_ascii_art":
                subject = (intent.argument or "").strip()
                ascii_art = self._generate_ascii_art(subject)
                action_log.append({
                    "tool": "ascii_art__generate",
                    "params": {"subject": subject},
                    "success": True,
                    "result": {"ascii": ascii_art},
                    "error": None,
                })
                type_result = await self._tool("desktop_env__type_text", {"text": ascii_art}, task_id_str)
                action_log.append(self._action("desktop_env__type_text", {"text": ascii_art}, type_result))
                return self._report(type_result, action_log, ExecutionTier.DIRECT)

            if intent.kind == "search":
                query_text = (intent.argument or "").strip()
                launch_result = await self._tool("browser_env__launch", {}, task_id_str)
                action_log.append(self._action("browser_env__launch", {}, launch_result))
                if not launch_result.success:
                    return self._report(launch_result, action_log, ExecutionTier.DIRECT)
                if query_text:
                    search_result = await self._tool("browser_env__search", {"query": query_text}, task_id_str)
                    action_log.append(self._action("browser_env__search", {"query": query_text}, search_result))
                    return self._report(search_result, action_log, ExecutionTier.DIRECT)
                nav_result = await self._tool("browser_env__navigate", {"url": "https://www.google.com"}, task_id_str)
                action_log.append(self._action("browser_env__navigate", {"url": "https://www.google.com"}, nav_result))
                return self._report(nav_result, action_log, ExecutionTier.DIRECT)

            if intent.kind == "open_file":
                file_path = intent.argument or ""
                result = await self._tool("desktop_env__launch_app_and_open_file", {"file_path": file_path}, task_id_str)
                action_log.append(self._action("desktop_env__launch_app_and_open_file", {"file_path": file_path}, result))
                return self._report(result, action_log, ExecutionTier.DIRECT)

            if intent.kind == "open_folder":
                folder_path = intent.argument or os.path.expanduser("~")
                result = await self._open_folder(folder_path)
                action_log.append(self._action("os__open_folder", {"path": folder_path}, result))
                return self._report(result, action_log, ExecutionTier.DIRECT)

            return ExecutionReport(
                success=False,
                execution_path="tier_0_direct",
                tier=ExecutionTier.DIRECT,
                actions=action_log,
                error=f"Unsupported Tier 0 intent: {intent.kind}",
            )
        except Exception as exc:
            logger.error(f"[DirectExecutor] task={task_id} failed: {exc}")
            return ExecutionReport(
                success=False,
                execution_path="tier_0_direct",
                tier=ExecutionTier.DIRECT,
                actions=action_log,
                error=str(exc),
            )

    async def _tool(self, name: str, params: Dict[str, Any], task_id: str) -> ToolOutput:
        payload = dict(params)
        payload["_task_id"] = task_id
        return await tool_registry.execute(name, payload)

    async def _open_folder(self, folder_path: str) -> ToolOutput:
        abs_path = os.path.abspath(os.path.expanduser(folder_path))
        try:
            if not os.path.isdir(abs_path):
                return ToolOutput(success=False, error=f"Folder not found: {abs_path}")

            if sys.platform == "win32":
                os.startfile(abs_path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", abs_path])
            else:
                subprocess.Popen(["xdg-open", abs_path])

            return ToolOutput(success=True, result={"path": abs_path, "message": f"Opened folder: {abs_path}"})
        except Exception as exc:
            return ToolOutput(success=False, error=str(exc))

    def _generate_ascii_art(self, subject: str) -> str:
        label = (subject or "ascii sketch").strip()
        lower_label = label.lower()

        if "cat" in lower_label:
            return (
                " /\\_/\\\n"
                "( o.o )\n"
                " > ^ <"
            )

        if "doctor doom" in lower_label or ("doom" in lower_label and "throne" in lower_label):
            return (
                "          _____________\n"
                "         /  THRONE OF  \\\n"
                "        /     DOOM      \\\n"
                "       |      ____       |\n"
                "       |     / __ \\      |\n"
                "       |    | |  | |     |\n"
                "       |    | |__| |     |\n"
                "       |    |  /\\  |     |\n"
                "       |    | /  \\ |     |\n"
                "       |    |/____\\|     |\n"
                "   ____|______||_________|____\n"
                "  /____|_________________|____\\"
            )

        return (
            " +----------------------------+\n"
            f" | ASCII sketch: {label[:20]:<20} |\n"
            " +----------------------------+"
        )

    def _action(self, tool_name: str, params: Dict[str, Any], result: ToolOutput) -> Dict[str, Any]:
        return {
            "tool": tool_name,
            "params": params,
            "success": result.success,
            "result": result.result,
            "error": result.error,
        }

    def _report(self, result: ToolOutput, action_log: List[Dict[str, Any]], tier: ExecutionTier) -> ExecutionReport:
        return ExecutionReport(
            success=result.success,
            execution_path="tier_0_direct",
            tier=tier,
            actions=action_log,
            error=result.error,
            verification={"all_actions_succeeded": result.success},
        )


class LightweightSequentialExecutor:
    """Tier 1 executor for small deterministic multi-step requests."""

    def __init__(self):
        self._direct = DirectExecutor()

    async def execute(self, task_id: UUID, query: str, intents: Sequence[TaskIntent]) -> ExecutionReport:
        action_log: List[Dict[str, Any]] = []

        if not intents:
            return ExecutionReport(
                success=False,
                execution_path="tier_1_sequential",
                tier=ExecutionTier.SEQUENTIAL,
                actions=action_log,
                error="No intents available for lightweight sequential execution",
            )

        for intent in intents:
            if intent.kind == "create_sheet":
                # Assumes spreadsheet app is foregrounded (e.g., Excel).
                key_result = await self._direct._tool("desktop_env__press_key", {"keys": "shift+f11"}, str(task_id))
                action_log.append(self._direct._action("desktop_env__press_key", {"keys": "shift+f11"}, key_result))
                if not key_result.success:
                    return ExecutionReport(
                        success=False,
                        execution_path="tier_1_sequential",
                        tier=ExecutionTier.SEQUENTIAL,
                        actions=action_log,
                        error=key_result.error,
                        verification={"all_actions_succeeded": False},
                    )
                continue

            if intent.kind == "create_file":
                topic = intent.argument or query
                # Determine default output path on Desktop
                desktop = os.path.join(os.path.expanduser("~"), "Desktop")
                safe_name = re.sub(r"[^\w\s-]", "", topic).strip().replace(" ", "-")[:40]
                file_path = os.path.join(desktop, f"{safe_name}.html")
                # Generate content via LLM
                try:
                    llm = _get_llm_client()
                    messages = [
                        {"role": "system", "content": "You are a helpful web developer. Return only raw HTML without markdown fences."},
                        {"role": "user", "content": (
                            f"Create a complete, self-contained HTML page about: {topic}\n\n"
                            "Requirements:\n"
                            "- Use inline CSS only (no external files)\n"
                            "- Responsive, modern, clean design\n"
                            "- Include a title, content sections, and basic styling\n"
                            "- Return ONLY the raw HTML string, no markdown code blocks, no explanations\n"
                        )},
                    ]
                    content = await llm.complete(messages)
                    # Strip markdown code fences if the model wrapped output
                    content = re.sub(r"^```(?:html)?\s*", "", content, flags=re.IGNORECASE)
                    content = re.sub(r"\s*```$", "", content)
                except Exception as exc:
                    return ExecutionReport(
                        success=False,
                        execution_path="tier_1_sequential",
                        tier=ExecutionTier.SEQUENTIAL,
                        actions=action_log,
                        error=f"LLM content generation failed: {exc}",
                        verification={"all_actions_succeeded": False},
                    )
                write_result = await self._direct._tool("filesystem__write_file", {"path": file_path, "content": content}, str(task_id))
                action_log.append(self._direct._action("filesystem__write_file", {"path": file_path}, write_result))
                if not write_result.success:
                    return ExecutionReport(
                        success=False,
                        execution_path="tier_1_sequential",
                        tier=ExecutionTier.SEQUENTIAL,
                        actions=action_log,
                        error=write_result.error,
                        verification={"all_actions_succeeded": False},
                    )
                continue

            if intent.kind == "search" and intent.argument:
                launch_result = await self._direct._tool("browser_env__launch", {}, str(task_id))
                action_log.append(self._direct._action("browser_env__launch", {}, launch_result))
                if not launch_result.success:
                    return ExecutionReport(
                        success=False,
                        execution_path="tier_1_sequential",
                        tier=ExecutionTier.SEQUENTIAL,
                        actions=action_log,
                        error=launch_result.error,
                        verification={"all_actions_succeeded": False},
                    )
                search_result = await self._direct._tool("browser_env__search", {"query": intent.argument}, str(task_id))
                action_log.append(self._direct._action("browser_env__search", {"query": intent.argument}, search_result))
                if not search_result.success:
                    return ExecutionReport(
                        success=False,
                        execution_path="tier_1_sequential",
                        tier=ExecutionTier.SEQUENTIAL,
                        actions=action_log,
                        error=search_result.error,
                        verification={"all_actions_succeeded": False},
                    )
                continue

            report = await self._direct.execute(task_id=task_id, query=query, intent=intent)
            action_log.extend(report.actions)
            if not report.success:
                return ExecutionReport(
                    success=False,
                    execution_path="tier_1_sequential",
                    tier=ExecutionTier.SEQUENTIAL,
                    actions=action_log,
                    error=report.error,
                    verification={"all_actions_succeeded": False},
                )

        return ExecutionReport(
            success=True,
            execution_path="tier_1_sequential",
            tier=ExecutionTier.SEQUENTIAL,
            actions=action_log,
            verification={
                "all_actions_succeeded": True,
                "steps_executed": len(action_log),
            },
        )


def summarize_intents(intents: Sequence[TaskIntent]) -> str:
    if not intents:
        return "none"
    return ", ".join(f"{i.kind}:{i.argument or ''}".rstrip(":") for i in intents)
