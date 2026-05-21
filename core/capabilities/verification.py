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

_PROCESS_ALIASES: Dict[str, List[str]] = {
    "notepad": ["notepad.exe", "notepad"],
    "calc": ["calc.exe", "calculator.exe", "calc", "calculator"],
    "calculator": ["calc.exe", "calculator.exe", "calc", "calculator"],
    "chrome": ["chrome.exe", "google chrome"],
    "google chrome": ["chrome.exe", "google chrome"],
    "edge": ["msedge.exe", "microsoft edge"],
    "microsoft edge": ["msedge.exe", "microsoft edge"],
    "vscode": ["code.exe", "visual studio code"],
    "visual studio code": ["code.exe", "visual studio code"],
    "whatsapp": ["whatsapp.exe", "whatsapp"],
    "teams": ["teams.exe", "microsoft teams"],
    "microsoft teams": ["teams.exe", "microsoft teams"],
}

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
        self._verifiers["window_focused"] = self._verify_window_focused

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
            step_id = step.get("id", step.get("step_number", "unknown"))
            desc = step.get("step", step.get("description", "")).lower()

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

            if any(k in desc for k in ("open notepad", "open calculator", "open app", "launch app", "start app", "open ", "open_application")):
                app_name = self._extract_app_name(desc)
                if app_name:
                    aliases = _PROCESS_ALIASES.get(app_name.lower(), [app_name])
                    reports.append(await self.verify(
                        task_id, step_id, "desktop_app_opened", {"app_name": app_name, "process_name": app_name, "window_title": aliases}
                    ))

            if any(k in desc for k in ("type", "enter text", "input text", "write text")):
                expected_text = self._extract_typed_text(desc)
                if expected_text:
                    reports.append(await self.verify(
                        task_id, step_id, "desktop_text_typed", {"text": expected_text}
                    ))

            if any(k in desc for k in ("focus", "bring to front", "activate window")):
                reports.append(await self.verify(
                    task_id, step_id, "window_focused", {}
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
        """Verify that a desktop application process is running or window exists.

        Uses deterministic checks in order:
        1. Process list (tasklist / pgrep) for all aliases
        2. app_launcher.is_process_running utility for all aliases
        3. Window existence (pygetwindow) for all aliases
        """
        process_name = criteria.get("process_name", "")
        window_title = criteria.get("window_title", "")
        app_name = criteria.get("app_name", "")
        if not process_name and not window_title and not app_name:
            return VerificationResult.FAIL, {"error": "No process_name, window_title, or app_name provided"}

        try:
            from ..environments.app_launcher import is_process_running, _normalize_app_name

            # Build alias list from all provided criteria
            aliases = []
            if isinstance(window_title, list):
                aliases.extend(window_title)
            elif window_title:
                aliases.append(window_title)
            if app_name:
                aliases.extend(_PROCESS_ALIASES.get(app_name.lower(), [app_name]))
            if process_name:
                aliases.extend(_PROCESS_ALIASES.get(process_name.lower(), [process_name]))
            # Deduplicate while preserving order
            seen = set()
            unique_aliases = []
            for a in aliases:
                a_lower = a.lower()
                if a_lower not in seen:
                    seen.add(a_lower)
                    unique_aliases.append(a)
            aliases = unique_aliases

            # Derive a primary process name if not provided
            if not process_name and app_name:
                from ..environments.app_launcher import _APP_NAME_MAP
                normalized = _normalize_app_name(app_name)
                process_name = _APP_NAME_MAP.get(normalized, app_name)
                if not process_name.lower().endswith(".exe"):
                    process_name += ".exe"
                if process_name.lower() not in seen:
                    aliases.append(process_name)

            # Check 1: Process list for any alias
            process_found = False
            if sys.platform == "win32":
                import subprocess
                for alias in aliases:
                    result = subprocess.run(
                        ["tasklist", "/FI", f"IMAGENAME eq {alias}"],
                        capture_output=True, text=True, timeout=5
                    )
                    if alias.lower() in result.stdout.lower():
                        process_found = True
                        break
                    # Also try with .exe suffix if missing
                    if not alias.lower().endswith(".exe"):
                        result2 = subprocess.run(
                            ["tasklist", "/FI", f"IMAGENAME eq {alias}.exe"],
                            capture_output=True, text=True, timeout=5
                        )
                        if f"{alias}.exe".lower() in result2.stdout.lower():
                            process_found = True
                            break
            else:
                import subprocess
                for alias in aliases:
                    result = subprocess.run(["pgrep", "-f", alias], capture_output=True, timeout=5)
                    if result.returncode == 0:
                        process_found = True
                        break

            if process_found:
                return VerificationResult.PASS, {"process": process_name or aliases[0], "method": "tasklist" if sys.platform == "win32" else "pgrep"}

            # Check 2: app_launcher utility for any alias
            for alias in aliases:
                if is_process_running(alias):
                    return VerificationResult.PASS, {"process": alias, "method": "app_launcher"}

            # Check 3: Window existence for any alias
            try:
                import pygetwindow as gw
                all_windows = gw.getAllWindows()
                for alias in aliases:
                    windows = gw.getWindowsWithTitle(alias)
                    if windows:
                        return VerificationResult.PASS, {"window_title": alias, "method": "pygetwindow"}
                    for w in all_windows:
                        if alias.lower() in w.title.lower():
                            return VerificationResult.PASS, {"window_title": w.title, "method": "pygetwindow_partial"}
            except Exception:
                pass

            return VerificationResult.FAIL, {"error": f"App not found: process={process_name}, window={window_title}, app={app_name}", "retryable": True}
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

    async def _verify_window_focused(self, criteria: Dict[str, Any]) -> tuple:
        """Verify that a specific window is the foreground window."""
        window_title = criteria.get("window_title", "")
        hwnd = criteria.get("hwnd")
        if not window_title and not hwnd:
            return VerificationResult.FAIL, {"error": "No window_title or hwnd provided"}
        try:
            if sys.platform == "win32":
                import ctypes
                user32 = ctypes.WinDLL("user32", use_last_error=True)
                fg_hwnd = user32.GetForegroundWindow()

                if hwnd and fg_hwnd == hwnd:
                    return VerificationResult.PASS, {"hwnd": hwnd, "method": "ctypes"}

                if window_title:
                    try:
                        import pygetwindow as gw
                        matches = gw.getWindowsWithTitle(window_title)
                        if matches:
                            target_hwnd = getattr(matches[0], "_hWnd", None)
                            if target_hwnd and target_hwnd == fg_hwnd:
                                return VerificationResult.PASS, {"window_title": window_title, "method": "ctypes_pygetwindow"}
                    except Exception:
                        pass

                return VerificationResult.FAIL, {"error": f"Window '{window_title or hwnd}' is not focused", "retryable": True}
            else:
                # Non-Windows: just check if window exists
                try:
                    import pygetwindow as gw
                    if window_title and gw.getWindowsWithTitle(window_title):
                        return VerificationResult.PASS, {"window_title": window_title, "method": "pygetwindow"}
                except Exception:
                    pass
                return VerificationResult.FAIL, {"error": "Window focus verification not fully supported on this platform", "retryable": True}
        except Exception as e:
            return VerificationResult.FAIL, {"error": str(e)}

    def _extract_app_name(self, desc: str) -> Optional[str]:
        """Heuristic to extract app name from 'open X' descriptions."""
        match = re.search(r"open\s+(?:the\s+)?([a-zA-Z0-9_\-\s]+?)(?:\s+(?:and|to|from|in|on|with|for)|$)", desc.lower())
        if match:
            return match.group(1).strip().strip(".,;:!?")
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
