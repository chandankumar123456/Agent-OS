"""Action V1 Deterministic Execution Layer.

Executes tasks without LLM reasoning for obvious cases.
Browser: DOM-first via MCP.
Desktop: Accessibility API first via MCP.
Filesystem: Direct MCP calls.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from .models import Capability, ExecutionContext, ActionResult, ActionStatus
from ..tools.registry import tool_registry
from ..logs.logger import logger
from ..utils.paths import get_desktop_path


class DeterministicExecutor:
    """Executes actions deterministically using available MCP tools."""

    def __init__(self, llm_client=None):
        self._tool_registry = tool_registry
        self._llm_client = llm_client

    @property
    def _llm(self):
        if self._llm_client is None:
            from ..agents.llm_client import get_llm_client
            self._llm_client = get_llm_client()
        return self._llm_client

    async def execute(self, ctx: ExecutionContext) -> ActionResult:
        """Route to the appropriate deterministic executor."""
        if ctx.capability == Capability.BROWSER:
            return await self._execute_browser(ctx)
        if ctx.capability == Capability.DESKTOP:
            return await self._execute_desktop(ctx)
        if ctx.capability == Capability.FILESYSTEM:
            return await self._execute_filesystem(ctx)
        if ctx.capability == Capability.MULTI_STEP:
            return await self._execute_multi_step(ctx)
        return await self._execute_general(ctx)

    # ── Browser Execution ──────────────────────────────────────────────

    async def _execute_browser(self, ctx: ExecutionContext) -> ActionResult:
        query = ctx.query.lower()
        steps: List[Dict[str, Any]] = []

        # 1. Launch if not already launched
        launch_result = await self._invoke_tool("browser_env__launch", {"task_id": ctx.task_id}, ctx)
        steps.append({"tool": "browser_env__launch", "result": launch_result})
        if not launch_result.get("success"):
            return ActionResult(
                status=ActionStatus.FAILURE,
                task_id=ctx.task_id,
                error=f"Browser launch failed: {launch_result.get('error')}",
                steps_executed=steps,
            )

        # 2. Determine action
        url = self._extract_url(ctx.query)
        if url and ("navigate" in query or "go to" in query or "open" in query):
            nav_result = await self._invoke_tool(
                "browser_env__navigate", {"task_id": ctx.task_id, "url": url}, ctx
            )
            steps.append({"tool": "browser_env__navigate", "result": nav_result})
        elif "search" in query or "google" in query:
            search_q = self._extract_search_query(ctx.query)
            nav_result = await self._invoke_tool(
                "browser_env__navigate",
                {"task_id": ctx.task_id, "url": "https://www.google.com"},
                ctx,
            )
            steps.append({"tool": "browser_env__navigate", "result": nav_result})
            type_result = await self._invoke_tool(
                "browser_env__type",
                {"task_id": ctx.task_id, "selector": "textarea[name='q']", "text": search_q},
                ctx,
            )
            steps.append({"tool": "browser_env__type", "result": type_result})
            click_result = await self._invoke_tool(
                "browser_env__click",
                {"task_id": ctx.task_id, "selector": "input[name='btnK']"},
                ctx,
            )
            steps.append({"tool": "browser_env__click", "result": click_result})
        else:
            nav_result = await self._invoke_tool(
                "browser_env__navigate", {"task_id": ctx.task_id, "url": "https://www.google.com"}, ctx
            )
            steps.append({"tool": "browser_env__navigate", "result": nav_result})

        # 3. Extract page text
        text_result = await self._invoke_tool(
            "browser_env__get_text",
            {"task_id": ctx.task_id, "selector": "body"},
            ctx,
        )
        steps.append({"tool": "browser_env__get_text", "result": text_result})

        return ActionResult(
            status=ActionStatus.SUCCESS,
            task_id=ctx.task_id,
            output={"message": "Browser action completed", "steps": steps},
            steps_executed=steps,
        )

    # ── Desktop Execution ──────────────────────────────────────────────

    async def _execute_desktop(self, ctx: ExecutionContext) -> ActionResult:
        query = ctx.query.lower()
        steps: List[Dict[str, Any]] = []

        # 1. Open application
        app_name = None
        if "notepad" in query:
            app_name = "notepad"
        elif "calculator" in query or "calc" in query:
            app_name = "calc"
        elif "chrome" in query:
            app_name = "chrome"
        else:
            # Extract app name after "open"
            app_name = self._extract_after(query, "open")

        if app_name:
            open_result = await self._invoke_tool(
                "desktop_env__open_application", {"app_name": app_name, "_task_id": ctx.task_id}, ctx
            )
            steps.append({"tool": "desktop_env__open_application", "result": open_result})
            if not open_result.get("success"):
                return ActionResult(
                    status=ActionStatus.FAILURE,
                    task_id=ctx.task_id,
                    error=f"Open app failed: {open_result.get('error')}",
                    steps_executed=steps,
                )

        # 2. Type text if requested
        if "write" in query or "type" in query:
            text = self._extract_text_to_type(ctx.query)
            if text:
                type_result = await self._invoke_tool(
                    "desktop_env__type_text", {"text": text, "_task_id": ctx.task_id}, ctx
                )
                steps.append({"tool": "desktop_env__type_text", "result": type_result})

        # 3. Save if requested
        if "save" in query:
            save_result = await self._invoke_tool(
                "desktop_env__press_key", {"keys": "ctrl+s", "_task_id": ctx.task_id}, ctx
            )
            steps.append({"tool": "desktop_env__press_key", "result": save_result})

        return ActionResult(
            status=ActionStatus.SUCCESS,
            task_id=ctx.task_id,
            output={"message": "Desktop action completed", "steps": steps},
            steps_executed=steps,
        )

    # ── Filesystem Execution ───────────────────────────────────────────

    async def _execute_filesystem(self, ctx: ExecutionContext) -> ActionResult:
        query = ctx.query.lower()
        steps: List[Dict[str, Any]] = []
        desktop = get_desktop_path()

        # Determine operation
        if "create" in query or "write" in query or "save" in query or "static page" in query:
            # File creation
            filename = self._extract_filename(ctx.query)
            if not filename:
                if "html" in query or "page" in query:
                    filename = "index.html"
                else:
                    filename = "output.txt"

            path = os.path.join(desktop, filename)

            # Generate content via LLM instead of hardcoded templates
            try:
                prompt = f"Generate content for a file based on this request. Respond with only the raw file content, no markdown fences or explanations.\n\nRequest: {ctx.query}"
                content = await self._generate_content_llm(prompt, task_id=ctx.task_id)
            except Exception as e:
                logger.warning(f"[ActionV1] LLM content generation failed: {e}, using minimal fallback")
                content = f"<!-- Generated content for: {ctx.query} -->\n"

            write_result = await self._invoke_tool(
                "filesystem__write_file", {"path": path, "content": content, "_task_id": ctx.task_id}, ctx
            )
            steps.append({"tool": "filesystem__write_file", "result": write_result})

            if write_result.get("success"):
                return ActionResult(
                    status=ActionStatus.SUCCESS,
                    task_id=ctx.task_id,
                    output={"file_path": path, "message": f"File created: {path}"},
                    steps_executed=steps,
                )
            return ActionResult(
                status=ActionStatus.FAILURE,
                task_id=ctx.task_id,
                error=f"Write failed: {write_result.get('error')}",
                steps_executed=steps,
            )

        if "read" in query or "open file" in query:
            path = self._extract_path(ctx.query) or desktop
            read_result = await self._invoke_tool(
                "filesystem__read_file", {"path": path, "_task_id": ctx.task_id}, ctx
            )
            steps.append({"tool": "filesystem__read_file", "result": read_result})
            return ActionResult(
                status=ActionStatus.SUCCESS if read_result.get("success") else ActionStatus.FAILURE,
                task_id=ctx.task_id,
                output=read_result.get("result") if read_result.get("success") else None,
                error=read_result.get("error"),
                steps_executed=steps,
            )

        if "list" in query or "show" in query:
            path = self._extract_path(ctx.query) or desktop
            list_result = await self._invoke_tool(
                "filesystem__list_directory", {"path": path, "_task_id": ctx.task_id}, ctx
            )
            steps.append({"tool": "filesystem__list_directory", "result": list_result})
            return ActionResult(
                status=ActionStatus.SUCCESS if list_result.get("success") else ActionStatus.FAILURE,
                task_id=ctx.task_id,
                output=list_result.get("result") if list_result.get("success") else None,
                error=list_result.get("error"),
                steps_executed=steps,
            )

        # Default: list desktop
        list_result = await self._invoke_tool(
            "filesystem__list_directory", {"path": desktop, "_task_id": ctx.task_id}, ctx
        )
        steps.append({"tool": "filesystem__list_directory", "result": list_result})
        return ActionResult(
            status=ActionStatus.SUCCESS,
            task_id=ctx.task_id,
            output=list_result.get("result"),
            steps_executed=steps,
        )

    # ── Multi-step Execution ───────────────────────────────────────────

    async def _execute_multi_step(self, ctx: ExecutionContext) -> ActionResult:
        """Execute multi-step workflows by decomposing into sequential deterministic steps."""
        query = ctx.query.lower()
        steps: List[Dict[str, Any]] = []
        desktop = get_desktop_path()

        # Pattern: search → summarize → save file
        if "search" in query and ("summarize" in query or "save" in query or "create" in query):
            # Step 1: Search web
            search_q = self._extract_between(ctx.query, "search", "summarize") or self._extract_after(query, "search")
            search_result = await self._invoke_tool(
                "cloud_api__search_web", {"query": search_q or ctx.query}, ctx
            )
            steps.append({"tool": "cloud_api__search_web", "result": search_result})

            # Step 2: Generate summary via LLM
            search_output = search_result.get("result", "") if search_result.get("success") else ""
            try:
                prompt = (
                    f"Summarize the following search results about '{search_q or ctx.query}' into a concise report.\n\n"
                    f"{str(search_output)[:3000]}\n\n"
                    f"Respond with only the summary text, no markdown fences or explanations."
                )
                summary = await self._generate_content_llm(prompt, task_id=ctx.task_id)
            except Exception as e:
                logger.warning(f"[ActionV1] LLM summary failed: {e}, using raw fallback")
                summary = f"Summary of '{search_q or ctx.query}':\n\n{str(search_output)[:2000]}"

            # Step 3: Save file
            filename = self._extract_filename(ctx.query) or "summary.txt"
            path = os.path.join(desktop, filename)
            write_result = await self._invoke_tool(
                "filesystem__write_file", {"path": path, "content": summary, "_task_id": ctx.task_id}, ctx
            )
            steps.append({"tool": "filesystem__write_file", "result": write_result})

            if write_result.get("success"):
                return ActionResult(
                    status=ActionStatus.SUCCESS,
                    task_id=ctx.task_id,
                    output={"file_path": path, "summary": summary},
                    steps_executed=steps,
                )
            return ActionResult(
                status=ActionStatus.FAILURE,
                task_id=ctx.task_id,
                error=f"Save failed: {write_result.get('error')}",
                steps_executed=steps,
            )

        # Pattern: find X → create static webpage → save file
        if "find" in query and ("page" in query or "html" in query or "webpage" in query):
            topic = self._extract_between(ctx.query, "find", "create") or self._extract_after(query, "find")
            # Search for info
            search_result = await self._invoke_tool(
                "cloud_api__search_web", {"query": topic or ctx.query}, ctx
            )
            steps.append({"tool": "cloud_api__search_web", "result": search_result})

            # Generate HTML via LLM
            search_output = search_result.get("result", "") if search_result.get("success") else ""
            try:
                content = await self._generate_html_llm(
                    query=ctx.query,
                    topic=topic or "Results",
                    search_results=str(search_output),
                    task_id=ctx.task_id,
                )
            except Exception as e:
                logger.warning(f"[ActionV1] LLM HTML generation failed: {e}, using minimal fallback")
                content = f"<!DOCTYPE html><html><body><h1>{topic or 'Results'}</h1><p>{ctx.query}</p></body></html>"

            filename = self._extract_filename(ctx.query) or "page.html"
            path = os.path.join(desktop, filename)
            write_result = await self._invoke_tool(
                "filesystem__write_file", {"path": path, "content": content, "_task_id": ctx.task_id}, ctx
            )
            steps.append({"tool": "filesystem__write_file", "result": write_result})

            if write_result.get("success"):
                return ActionResult(
                    status=ActionStatus.SUCCESS,
                    task_id=ctx.task_id,
                    output={"file_path": path, "message": f"Static page created: {path}"},
                    steps_executed=steps,
                )
            return ActionResult(
                status=ActionStatus.FAILURE,
                task_id=ctx.task_id,
                error=f"Write failed: {write_result.get('error')}",
                steps_executed=steps,
            )

        # Fallback: treat as filesystem
        return await self._execute_filesystem(ctx)

    # ── General Execution ──────────────────────────────────────────────

    async def _execute_general(self, ctx: ExecutionContext) -> ActionResult:
        """Fallback for unclassified tasks — try filesystem first."""
        return await self._execute_filesystem(ctx)

    # ── LLM Content Generation ─────────────────────────────────────────

    async def _generate_content_llm(self, prompt_text: str, task_id: str = "") -> str:
        messages = [
            {"role": "system", "content": "You are a helpful assistant that generates raw content. Respond with only the requested content, no markdown fences or explanations unless asked."},
            {"role": "user", "content": prompt_text},
        ]
        return await self._llm.complete(messages, max_tokens=2000, task_id=task_id)

    async def _generate_html_llm(self, query: str, topic: str, search_results: str, task_id: str = "") -> str:
        prompt = (
            f"Create a complete, self-contained HTML page about: {topic}\n"
            f"Original user request: {query}\n"
            f"Include relevant information from these search results:\n{search_results[:4000]}\n\n"
            f"Respond with ONLY the raw HTML code (no markdown fences, no explanations)."
        )
        messages = [
            {"role": "system", "content": "You are a web developer that creates clean, semantic HTML pages with inline CSS."},
            {"role": "user", "content": prompt},
        ]
        return await self._llm.complete(messages, max_tokens=4000, task_id=task_id)

    # ── Helpers ────────────────────────────────────────────────────────

    async def _invoke_tool(self, name: str, params: Dict[str, Any], ctx: ExecutionContext) -> Dict[str, Any]:
        """Invoke a tool and return a normalized dict."""
        try:
            output = await self._tool_registry.execute(name, params)
            return {"success": output.success, "result": output.result, "error": output.error}
        except Exception as e:
            logger.error(f"[ActionV1] Tool {name} failed: {e}")
            return {"success": False, "error": str(e)}

    @staticmethod
    def _extract_after(text: str, keyword: str) -> Optional[str]:
        idx = text.lower().find(keyword)
        if idx == -1:
            return None
        rest = text[idx + len(keyword):].strip()
        # Remove leading filler words
        for filler in ("for", "to", "the", "a", "an", "and"):
            if rest.lower().startswith(filler + " "):
                rest = rest[len(filler) + 1:].strip()
        return rest.split(".")[0].split(",")[0].strip() or None

    @staticmethod
    def _extract_between(text: str, start: str, end: str) -> Optional[str]:
        s = text.lower().find(start)
        if s == -1:
            return None
        e = text.lower().find(end, s + len(start))
        if e == -1:
            return None
        return text[s + len(start):e].strip(" →->,.:;")

    @staticmethod
    def _extract_url(text: str) -> Optional[str]:
        import re
        m = re.search(r"https?://[^\s\"'<>]+", text)
        return m.group(0) if m else None

    @staticmethod
    def _extract_path(text: str) -> Optional[str]:
        import re
        matches = re.findall(r"([A-Za-z]:\\[^\s\"'<>]+|/[^\s\"'<>]+)", text)
        return matches[0] if matches else None

    @staticmethod
    def _extract_filename(text: str) -> Optional[str]:
        import re
        # Look for quoted filenames or words with extensions
        quoted = re.findall(r'"([^"]+\.[a-zA-Z0-9]+)"', text)
        if quoted:
            return quoted[0]
        ext_patterns = re.findall(r'\b\S+\.(html|txt|csv|json|md|py|js|css)\b', text, re.IGNORECASE)
        if ext_patterns:
            # Find the full word containing the extension
            for m in re.finditer(r'\S+\.' + ext_patterns[0], text, re.IGNORECASE):
                return m.group(0)
        return None

    @staticmethod
    def _extract_text_to_type(text: str) -> str:
        # Extract text after "write" or "type"
        for marker in ("write", "type"):
            idx = text.lower().find(marker)
            if idx != -1:
                rest = text[idx + len(marker):].strip()
                for filler in ("the following", "this", "text", ":"):
                    if rest.lower().startswith(filler):
                        rest = rest[len(filler):].strip()
                # Remove trailing instructions
                rest = rest.split(" and ")[0].split(" then ")[0]
                return rest.strip('"').strip("'")
        return text

    @staticmethod
    def _extract_search_query(text: str) -> str:
        query_lower = text.lower()
        for prefix in ("search for", "search", "google"):
            idx = query_lower.find(prefix)
            if idx != -1:
                rest = text[idx + len(prefix):].strip()
                for filler in ("for", "to", "the", "a", "an", "and", "in browser", "on google"):
                    if rest.lower().startswith(filler + " "):
                        rest = rest[len(filler) + 1:].strip()
                return rest.split(".")[0].split(",")[0].strip() or rest
        return text
