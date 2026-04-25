"""Deterministic Verification Engine — replaces weak LLM verification with concrete checks."""
import os
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
