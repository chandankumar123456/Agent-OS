from typing import List, Dict, Any

from .models import ActionSeverity


class SafetyGate:
    """Intercepts irreversible actions before execution."""

    IRREVERSIBLE_TOOLS = {
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
    }

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

    def check_tool_call(self, tool_name: str, params: dict, query: str) -> ActionSeverity:
        """Classify a single tool invocation by severity."""
        if tool_name in self.IRREVERSIBLE_TOOLS:
            return ActionSeverity.IRREVERSIBLE

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


# Module-level singleton
safety_gate = SafetyGate()
