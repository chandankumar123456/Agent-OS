from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Any, Dict
from enum import Enum


class ValidationType(str, Enum):
    SCHEMA = "schema"
    LOGICAL = "logical"
    CONSTRAINT = "constraint"


class ValidationResult(BaseModel):
    valid: bool
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    confidence: float = 1.0


class OutputSchema(BaseModel):
    result: Optional[Any] = None
    status: str = "success"
    details: Optional[Dict[str, Any]] = None


class CustomRule(BaseModel):
    name: str
    rule_type: str
    condition: Dict[str, Any]
    action: str = "block"

    model_config = ConfigDict(extra="ignore")


class GuardrailSchema:
    @staticmethod
    def validate_output(output: Dict[str, Any]) -> ValidationResult:
        errors = []
        warnings = []

        if not output:
            errors.append("Output is empty")
            return ValidationResult(
                valid=False,
                errors=errors,
                confidence=0.0
            )

        if "status" in output:
            if output["status"] not in {"success", "failure", "pending", "running",
                                         "completed", "failed", "cancelled",
                                         "step_executed", "step_failed",
                                         "requires_approval", "approved", "rejected",
                                         "planning_complete", "execution_complete",
                                         "guardrail_blocked", "verification_complete"}:
                errors.append(f"Invalid status: {output['status']}")

        if "result" in output and not output["result"]:
            warnings.append("Result is empty")

        is_valid = len(errors) == 0
        confidence = 1.0 - (len(errors) * 0.3) - (len(warnings) * 0.1)

        return ValidationResult(
            valid=is_valid,
            errors=errors,
            warnings=warnings,
            confidence=max(0.0, confidence)
        )

    @staticmethod
    def validate_steps(steps: List[Dict[str, Any]]) -> ValidationResult:
        errors = []

        if not steps:
            errors.append("No steps in workflow")
            return ValidationResult(valid=False, errors=errors)

        for i, step in enumerate(steps):
            if "step" not in step:
                errors.append(f"Step {i} missing 'step' field")
            if "agent_type" not in step:
                errors.append(f"Step {i} missing 'agent_type' field")

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            confidence=1.0 if len(errors) == 0 else 0.5
        )

    @staticmethod
    def validate_context(context: Dict[str, Any]) -> ValidationResult:
        warnings = []

        if not context:
            warnings.append("Context is empty")

        if "query" not in context:
            warnings.append("Context missing 'query'")

        return ValidationResult(
            valid=True,
            warnings=warnings,
            confidence=1.0 - (len(warnings) * 0.2)
        )

    @staticmethod
    def validate_with_rules(output: Dict[str, Any], rules: List[CustomRule]) -> ValidationResult:
        errors = []
        warnings = []

        if not output:
            errors.append("Output is empty")
            return ValidationResult(valid=False, errors=errors, confidence=0.0)

        for rule in rules:
            rule_errors, rule_warnings = GuardrailSchema._apply_rule(output, rule)
            errors.extend(rule_errors)
            warnings.extend(rule_warnings)

        is_valid = len(errors) == 0
        confidence = 1.0 - (len(errors) * 0.3) - (len(warnings) * 0.1)

        return ValidationResult(
            valid=is_valid,
            errors=errors,
            warnings=warnings,
            confidence=max(0.0, confidence)
        )

    @staticmethod
    def _apply_rule(output: Dict[str, Any], rule: CustomRule) -> tuple[List[str], List[str]]:
        errors = []
        warnings = []

        condition = rule.condition or {}
        result_text = ""
        if isinstance(output.get("result"), str):
            result_text = output["result"]

        if rule.rule_type == "blocked_keywords":
            keywords = condition.get("keywords", [])
            for keyword in keywords:
                if keyword.lower() in result_text.lower():
                    msg = f"Blocked keyword '{keyword}' found by rule '{rule.name}'"
                    if rule.action == "block":
                        errors.append(msg)
                    else:
                        warnings.append(msg)

        elif rule.rule_type == "max_length":
            max_len = condition.get("max_length")
            if max_len is not None and len(result_text) > max_len:
                msg = f"Output length {len(result_text)} exceeds max {max_len} by rule '{rule.name}'"
                if rule.action == "block":
                    errors.append(msg)
                else:
                    warnings.append(msg)

        elif rule.rule_type == "required_fields":
            fields = condition.get("fields", [])
            for field in fields:
                if field not in output:
                    msg = f"Required field '{field}' missing by rule '{rule.name}'"
                    if rule.action == "block":
                        errors.append(msg)
                    else:
                        warnings.append(msg)

        elif rule.rule_type == "allowed_tools":
            allowed = condition.get("tools", [])
            tool_calls = output.get("tool_calls") or []
            if not tool_calls and output.get("details"):
                tool_calls = output["details"].get("tool_calls") or []
            for tc in tool_calls:
                tool_name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None)
                if tool_name and tool_name not in allowed:
                    msg = f"Tool '{tool_name}' not allowed by rule '{rule.name}'"
                    if rule.action == "block":
                        errors.append(msg)
                    else:
                        warnings.append(msg)

        return errors, warnings
