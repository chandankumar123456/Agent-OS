import json
import re
from dataclasses import dataclass
from typing import List, Dict, Any

from .models import ActionSeverity
from .approval_store import approval_store
from ..logs.logger import logger
from ..observability.bus import observability_bus
from ..observability.models import ObservabilityEventType


_CREDENTIAL_PATTERNS = [
    re.compile(r'password\s*[=:]\s*\S+', re.IGNORECASE),
    re.compile(r'passwd\s*[=:]\s*\S+', re.IGNORECASE),
    re.compile(r'pwd\s*[=:]\s*\S+', re.IGNORECASE),
    re.compile(r'secret\s*[=:]\s*\S+', re.IGNORECASE),
    re.compile(r'api_key\s*[=:]\s*\S+', re.IGNORECASE),
    re.compile(r'token\s*[=:]\s*\S+', re.IGNORECASE),
    re.compile(r'access_key\s*[=:]\s*\S+', re.IGNORECASE),
    re.compile(r'private_key\s*[=:]\s*\S+', re.IGNORECASE),
]


@dataclass
class SafetyResult:
    blocked: bool
    reason: str = ""


class SafetyGate:
    """Intercepts irreversible actions before execution."""

    IRREVERSIBLE_TOOLS = frozenset({
        "filesystem__delete_file",
        "filesystem__delete_directory",
        "email__send",
        "email__send_bulk",
        "slack__post_message",
        "slack__send_message",
        "discord__send_message",
        "sms__send",
        "payment__process",
        "payment__charge",
        "payment__transfer",
        "wallet__transfer",
        "crypto__transfer",
        "purchase__execute",
        "buy__execute",
        "database__drop_table",
        "database__drop_schema",
        "database__delete_rows",
        "user__delete_account",
        "github__delete_repository",
        "github__force_push",
        "aws__terminate_instance",
        "aws__delete_bucket",
        "docker__remove_container",
        "docker__remove_image",
        "kubernetes__delete_pod",
        "kubernetes__delete_namespace",
    })

    FORBIDDEN_PREFIXES = (
        "filesystem__delete", "database__drop", "database__delete",
        "user__delete", "github__delete", "github__force",
        "aws__terminate", "aws__delete",
        "docker__remove", "kubernetes__delete",
    )

    DANGEROUS_PATTERNS = [
        "rm -rf",
        "drop",
        "delete",
        "payment",
        "purchase",
        "buy",
        "transfer",
        "send email",
        "post message",
    ]

    def _is_forbidden(self, tool_name: str) -> bool:
        """Check if a tool name matches forbidden exact names or prefixes."""
        if tool_name in self.IRREVERSIBLE_TOOLS:
            return True
        if tool_name.startswith(("payment__", "crypto__", "purchase__", "buy__")):
            return True
        if tool_name.startswith(("email__send", "slack__send", "slack__post", "discord__send", "sms__send")):
            return True
        if any(tool_name.startswith(p) for p in self.FORBIDDEN_PREFIXES):
            return True
        return False

    def check_tool_call(self, tool_name: str, params: dict, query: str) -> ActionSeverity:
        """Classify a single tool invocation by severity."""
        # Always block forbidden tools (exact + prefix match)
        if self._is_forbidden(tool_name):
            # Emit audit event for blocked action
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    task_id = params.get("_task_id", "unknown")
                    asyncio.ensure_future(
                        observability_bus.emit_safe(
                            ObservabilityEventType.SAFETY_CHECK,
                            task_id=task_id,
                            payload={
                                "tool": tool_name,
                                "params": {k: v for k, v in params.items() if not k.startswith("_")},
                                "severity": "irreversible",
                                "action": "blocked",
                                "query_preview": query[:200],
                            },
                            source="safety_gate",
                        )
                    )
            except Exception as e:
                logger.warning(f"Failed to emit safety audit event: {e}")
            return ActionSeverity.IRREVERSIBLE

        # Check if full-trust mode applies
        task_id = params.get("_task_id", "")
        if task_id and approval_store.should_auto_approve(task_id, tool_name, "warning"):
            # Full trust mode: auto-approve safe and warning actions
            approval_store.log_auto_approval(
                task_id, tool_name, params,
                reason="full_trust_mode: severity was safe/warning"
            )
            return ActionSeverity.SAFE

        combined_text = " ".join(str(v) for v in params.values()) + " " + query
        combined_text_lower = combined_text.lower()
        if any(pattern in combined_text_lower for pattern in self.DANGEROUS_PATTERNS):
            return ActionSeverity.WARNING

        return ActionSeverity.SAFE

    def check_plan(self, plan: List[Dict[str, Any]], query: str) -> List[ActionSeverity]:
        """Check each step in a plan and return a list of severity results."""
        results = []
        for step in plan:
            tool = step.get("tool") or ""
            params = {k: v for k, v in step.items() if k != "tool"}
            results.append(self.check_tool_call(tool, params, query))
        return results

    def validate_desktop_params(self, params: dict) -> SafetyResult:
        """Check desktop tool parameters for credential-like strings."""
        params_text = json.dumps(params)
        for pattern in _CREDENTIAL_PATTERNS:
            match = pattern.search(params_text)
            if match:
                credential_type = match.group().split("=")[0].split(":")[0].strip()
                return SafetyResult(
                    blocked=True,
                    reason=f"Credential pattern detected in desktop tool parameters: {credential_type}"
                )
        return SafetyResult(blocked=False)


# Module-level singleton
safety_gate = SafetyGate()
