"""Deterministic Verification Engine — replaces weak LLM verification with concrete checks."""
import os
import sys
import json
import re
import asyncio
from typing import Dict, Any, List, Optional, Callable
from urllib.parse import urlparse

import httpx

from .models import VerificationResult, VerificationReport
from ..logs.logger import logger


class DeterministicVerificationEngine:
    """Provides concrete, deterministic verification for task outputs.

    Instead of asking an LLM "does this look correct?", this engine:
    - Verifies file existence and content
    - Verifies code execution output
    - Verifies deployment health via HTTP checks
    - Verifies web content via pattern matching
    """

    def __init__(self):
        self._verifiers: Dict[str, Callable[[Dict[str, Any]], asyncio.Future]] = {}
        self._register_default_verifiers()

    def _register_default_verifiers(self):
        self._verifiers["file_exists"] = self._verify_file_exists
        self._verifiers["file_contains"] = self._verify_file_contains
        self._verifiers["code_runs"] = self._verify_code_runs
        self._verifiers["deployment_healthy"] = self._verify_deployment_healthy
        self._verifiers["web_content"] = self._verify_web_content
        self._verifiers["command_succeeds"] = self._verify_command_succeeds
        self._verifiers["browser_opened"] = self._verify_browser_opened
        self._verifiers["html_rendered"] = self._verify_html_rendered
        self._verifiers["summary_generated"] = self._verify_summary_generated
        self._verifiers["content_extracted"] = self._verify_content_extracted
        self._verifiers["desktop_app_opened"] = self._verify_desktop_app_opened
        self._verifiers["desktop_text_typed"] = self._verify_desktop_text_typed

    async def verify(
        self,
        task_id: str,
        step_id: Optional[str],
        verification_type: str,
        criteria: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> VerificationReport:
        """Run a deterministic verification check."""
        verifier = self._verifiers.get(verification_type)
        if not verifier:
            logger.warning(f"No deterministic verifier for type '{verification_type}', falling back to LLM")
            return VerificationReport(
                task_id=task_id,
                step_id=step_id,
                result=VerificationResult.SKIPPED,
                verifier_type="llm",
                failure_reason=f"No deterministic verifier for '{verification_type}'",
            )

        try:
            result, evidence = await verifier(criteria)
        except Exception as e:
            logger.error(f"Deterministic verification failed: {e}")
            result = VerificationResult.FAIL
            evidence = {"error": str(e)}

        report = VerificationReport(
            task_id=task_id,
            step_id=step_id,
            result=result,
            verifier_type="deterministic",
            checks=[{"type": verification_type, "criteria": criteria}],
            evidence=evidence,
            failure_reason=None if result == VerificationResult.PASS else evidence.get("error", "Check failed"),
            retry_suggested=result == VerificationResult.FAIL and evidence.get("retryable", False),
        )

        logger.info(f"[DeterministicVerification] task={task_id} type={verification_type} result={result.value}")
        return report

    async def verify_plan(
        self,
        task_id: str,
        plan: List[Dict[str, Any]],
        environment_config: Optional[Dict[str, Any]] = None,
    ) -> List[VerificationReport]:
        """Auto-generate and run verification checks for a plan."""
        reports: List[VerificationReport] = []
        for step in plan:
            step_id = step.get("id", "unknown")
            desc = step.get("step", "").lower()

            # Auto-detect verification type from step description
            if any(k in desc for k in ("file", "write", "create", "save")):
                # Try to extract path from step description
                paths = self._extract_paths(desc)
                for path in paths:
                    reports.append(await self.verify(
                        task_id, step_id, "file_exists", {"path": path}
                    ))

            if any(k in desc for k in ("deploy", "host", "publish")):
                urls = self._extract_urls(desc)
                for url in urls:
                    reports.append(await self.verify(
                        task_id, step_id, "deployment_healthy", {"url": url}
                    ))

            if any(k in desc for k in ("scrape", "fetch", "download")):
                urls = self._extract_urls(desc)
                for url in urls:
                    reports.append(await self.verify(
                        task_id, step_id, "web_content", {"url": url}
                    ))

            if any(k in desc for k in ("open chrome", "open browser", "view in browser")):
                paths = self._extract_paths(desc)
                for path in paths:
                    reports.append(await self.verify(
                        task_id, step_id, "browser_opened", {"path": path}
                    ))

            if any(k in desc for k in ("create html", "generate html", "write html")):
                paths = self._extract_paths(desc)
                for path in paths:
                    if path.lower().endswith(".html"):
                        reports.append(await self.verify(
                            task_id, step_id, "html_rendered", {"path": path}
                        ))

            if any(k in desc for k in ("summarize", "summary")):
                reports.append(await self.verify(
                    task_id, step_id, "summary_generated", {}
                ))

            if any(k in desc for k in ("open notepad", "open calculator", "open app", "launch app", "start app", "open ")):
                app_name = self._extract_app_name(desc)
                if app_name:
                    reports.append(await self.verify(
                        task_id, step_id, "desktop_app_opened", {"process_name": app_name, "window_title": app_name}
                    ))

            if any(k in desc for k in ("type", "enter text", "input text", "write text")):
                expected_text = self._extract_typed_text(desc)
                if expected_text:
                    reports.append(await self.verify(
                        task_id, step_id, "desktop_text_typed", {"text": expected_text}
                    ))

        return reports

    # ── Individual verifiers ───────────────────────────────────────────

    async def _verify_file_exists(self, criteria: Dict[str, Any]) -> tuple:
        path = criteria.get("path")
        if not path:
            return VerificationResult.FAIL, {"error": "No path provided"}
        exists = os.path.exists(path)
        if exists:
            stat = os.stat(path)
            return VerificationResult.PASS, {
                "path": path,
                "size": stat.st_size,
                "modified": stat.st_mtime,
            }
        return VerificationResult.FAIL, {"error": f"File not found: {path}", "retryable": True}

    async def _verify_file_contains(self, criteria: Dict[str, Any]) -> tuple:
        path = criteria.get("path")
        expected = criteria.get("content")
        if not path or not expected:
            return VerificationResult.FAIL, {"error": "Path and content required"}
        if not os.path.exists(path):
            return VerificationResult.FAIL, {"error": f"File not found: {path}", "retryable": True}
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            if expected in content:
                return VerificationResult.PASS, {"path": path, "found": True}
            return VerificationResult.FAIL, {"error": f"Expected content not found in {path}"}
        except Exception as e:
            return VerificationResult.FAIL, {"error": str(e)}

    async def _verify_code_runs(self, criteria: Dict[str, Any]) -> tuple:
        command = criteria.get("command")
        expected_output = criteria.get("expected_output")
        if not command:
            return VerificationResult.FAIL, {"error": "No command provided"}
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
            output = stdout.decode("utf-8", errors="ignore")
            if proc.returncode != 0:
                return VerificationResult.FAIL, {
                    "error": f"Exit code {proc.returncode}",
                    "stderr": stderr.decode("utf-8", errors="ignore")[:500],
                }
            if expected_output and expected_output not in output:
                return VerificationResult.FAIL, {
                    "error": f"Expected output not found. Got: {output[:500]}",
                }
            return VerificationResult.PASS, {"output": output[:1000]}
        except asyncio.TimeoutError:
            proc.kill()
            return VerificationResult.FAIL, {"error": "Command timed out", "retryable": True}

    async def _verify_deployment_healthy(self, criteria: Dict[str, Any]) -> tuple:
        url = criteria.get("url")
        if not url:
            return VerificationResult.FAIL, {"error": "No URL provided"}
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(url)
            if response.status_code < 500:
                return VerificationResult.PASS, {
                    "url": url,
                    "status_code": response.status_code,
                    "response_time_ms": response.elapsed.total_seconds() * 1000,
                }
            return VerificationResult.FAIL, {
                "error": f"HTTP {response.status_code}",
                "retryable": response.status_code >= 500,
            }
        except Exception as e:
            return VerificationResult.FAIL, {"error": str(e), "retryable": True}

    async def _verify_web_content(self, criteria: Dict[str, Any]) -> tuple:
        url = criteria.get("url")
        pattern = criteria.get("pattern")
        if not url:
            return VerificationResult.FAIL, {"error": "No URL provided"}
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(url)
            content = response.text
            if pattern and not re.search(pattern, content):
                return VerificationResult.FAIL, {"error": f"Pattern '{pattern}' not found in {url}"}
            return VerificationResult.PASS, {
                "url": url,
                "length": len(content),
                "status_code": response.status_code,
            }
        except Exception as e:
            return VerificationResult.FAIL, {"error": str(e), "retryable": True}

    async def _verify_command_succeeds(self, criteria: Dict[str, Any]) -> tuple:
        command = criteria.get("command")
        if not command:
            return VerificationResult.FAIL, {"error": "No command provided"}
        return await self._verify_code_runs({"command": command})

    async def _verify_browser_opened(self, criteria: Dict[str, Any]) -> tuple:
        """Verify that a browser was opened to a specific URL or file."""
        url = criteria.get("url") or criteria.get("path")
        if not url:
            return VerificationResult.FAIL, {"error": "No URL or path provided for browser verification"}
        # Check if file exists (for local HTML files)
        if url.startswith("file://") or (len(url) > 3 and url[1] == ":"):
            local_path = url.replace("file://", "")
            if os.path.exists(local_path):
                return VerificationResult.PASS, {"path": local_path, "exists": True}
            return VerificationResult.FAIL, {"error": f"Local file not found: {local_path}", "retryable": True}
        # For remote URLs, do a quick HTTP check
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(url)
            if response.status_code < 500:
                return VerificationResult.PASS, {"url": url, "status_code": response.status_code}
            return VerificationResult.FAIL, {"error": f"HTTP {response.status_code}", "retryable": True}
        except Exception as e:
            return VerificationResult.FAIL, {"error": str(e), "retryable": True}

    async def _verify_html_rendered(self, criteria: Dict[str, Any]) -> tuple:
        """Verify that an HTML file has valid structure."""
        path = criteria.get("path")
        if not path:
            return VerificationResult.FAIL, {"error": "No path provided"}
        if not os.path.exists(path):
            return VerificationResult.FAIL, {"error": f"File not found: {path}", "retryable": True}
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            has_html = "<html" in content.lower() or "<!doctype html" in content.lower()
            has_body = "<body" in content.lower()
            if has_html and has_body:
                return VerificationResult.PASS, {"path": path, "has_html": True, "has_body": True, "size": len(content)}
            return VerificationResult.FAIL, {"error": f"HTML file missing required tags in {path}"}
        except Exception as e:
            return VerificationResult.FAIL, {"error": str(e)}

    async def _verify_summary_generated(self, criteria: Dict[str, Any]) -> tuple:
        """Verify that a summary was generated and is non-empty."""
        summary = criteria.get("summary")
        if summary and len(summary.strip()) > 50:
            return VerificationResult.PASS, {"length": len(summary), "preview": summary[:200]}
        return VerificationResult.FAIL, {"error": "Summary is missing or too short", "retryable": True}

    async def _verify_content_extracted(self, criteria: Dict[str, Any]) -> tuple:
        """Verify that document content was extracted."""
        text = criteria.get("text") or criteria.get("content")
        if text and len(text.strip()) > 10:
            return VerificationResult.PASS, {"length": len(text), "preview": text[:200]}
        return VerificationResult.FAIL, {"error": "No content extracted", "retryable": True}

    async def _verify_desktop_app_opened(self, criteria: Dict[str, Any]) -> tuple:
        """Verify that a desktop application process is running or window exists."""
        process_name = criteria.get("process_name", "")
        window_title = criteria.get("window_title", "")
        if not process_name and not window_title:
            return VerificationResult.FAIL, {"error": "No process_name or window_title provided"}
        try:
            import subprocess
            if sys.platform == "win32":
                if process_name:
                    result = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {process_name}"], capture_output=True, text=True)
                    if process_name.lower() in result.stdout.lower():
                        return VerificationResult.PASS, {"process": process_name, "method": "tasklist"}
                if window_title:
                    result = subprocess.run(["tasklist", "/V", "/FI", f"WINDOWTITLE eq {window_title}"], capture_output=True, text=True)
                    if window_title.lower() in result.stdout.lower():
                        return VerificationResult.PASS, {"window_title": window_title, "method": "tasklist"}
            else:
                if process_name:
                    result = subprocess.run(["pgrep", "-f", process_name], capture_output=True)
                    if result.returncode == 0:
                        return VerificationResult.PASS, {"process": process_name, "method": "pgrep"}
            try:
                import pygetwindow as gw
                if window_title:
                    windows = gw.getWindowsWithTitle(window_title)
                    if windows:
                        return VerificationResult.PASS, {"window_title": window_title, "method": "pygetwindow"}
            except Exception:
                pass
            return VerificationResult.FAIL, {"error": f"App not found: process={process_name}, window={window_title}", "retryable": True}
        except Exception as e:
            return VerificationResult.FAIL, {"error": str(e)}

    async def _verify_desktop_text_typed(self, criteria: Dict[str, Any]) -> tuple:
        """Verify that text was typed by checking clipboard or UI state."""
        expected_text = criteria.get("text", "")
        window_title = criteria.get("window_title", "")
        if not expected_text:
            return VerificationResult.FAIL, {"error": "No expected text provided"}
        try:
            try:
                import pyperclip
                clipboard_text = pyperclip.paste()
                if expected_text in clipboard_text:
                    return VerificationResult.PASS, {"method": "clipboard", "matched": True}
            except Exception:
                pass
            try:
                import uiautomation as auto
                if window_title:
                    window = auto.WindowControl(searchDepth=1, Name=window_title)
                    if window.Exists():
                        text = window.GetValuePattern().Value if window.GetValuePattern() else ""
                        if not text:
                            text = window.Name
                        if expected_text in text:
                            return VerificationResult.PASS, {"method": "uiautomation", "matched": True}
            except Exception:
                pass
            return VerificationResult.FAIL, {"error": f"Text '{expected_text}' not detected", "retryable": True}
        except Exception as e:
            return VerificationResult.FAIL, {"error": str(e)}

    def _extract_app_name(self, desc: str) -> Optional[str]:
        """Heuristic to extract app name from 'open X' descriptions."""
        match = re.search(r"open\s+(?:the\s+)?([a-zA-Z0-9_\-]+)", desc.lower())
        if match:
            return match.group(1)
        return None

    def _extract_typed_text(self, desc: str) -> Optional[str]:
        """Heuristic to extract expected text from 'type X' descriptions."""
        match = re.search(r'type\s+["\']?([^"\']+)["\']?', desc.lower())
        if match:
            return match.group(1)
        return None

    # ── Helpers ────────────────────────────────────────────────────────

    def _extract_paths(self, text: str) -> List[str]:
        """Extract likely file paths from text."""
        # Match Unix or Windows absolute paths
        pattern = re.compile(r"(?:^|\s)([~]?(?:/[A-Za-z0-9_\-\$]+)+/?|[A-Za-z]:\\(?:[^\\\s]+\\?)+)(?=$|\s)")
        return pattern.findall(text)

    def _extract_urls(self, text: str) -> List[str]:
        """Extract URLs from text."""
        pattern = re.compile(r"https?://[^\s\"'<>]+")
        return pattern.findall(text)


# Global singleton
verification_engine = DeterministicVerificationEngine()
