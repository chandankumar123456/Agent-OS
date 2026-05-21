"""Tool input validation pipeline.

Validates tool inputs through a multi-stage pipeline:
Schema Validation → Type Check → Safety Check → Permission Check → Execution
"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from ..logs.logger import logger
from ..safety.gate import SafetyGate
from ..safety.rbac import AgentRole
from .permissions import ToolPermissions, tool_permissions as default_permissions
from .registry import ToolRegistry


class ValidationResult(BaseModel):
    """Result of tool input validation."""
    valid: bool
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    sanitized_args: Dict[str, Any] = Field(default_factory=dict)
    tool_name: str


class ToolInputValidator:
    """Multi-stage tool input validation pipeline.

    Usage:
        validator = ToolInputValidator()
        result = await validator.validate("filesystem__read_file", {"path": "/tmp/test.txt"})
        if result.valid:
            # Execute with sanitized args
            pass
    """

    def __init__(
        self,
        registry: Optional[ToolRegistry] = None,
        safety_gate: Optional[SafetyGate] = None,
        permissions: Optional[ToolPermissions] = None,
    ):
        self.registry = registry or ToolRegistry()
        self.safety_gate = safety_gate or SafetyGate()
        self.permissions = permissions or default_permissions

    async def validate(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        agent_id: Optional[str] = None,
        agent_role: Optional[AgentRole] = None,
        query: Optional[str] = None,
    ) -> ValidationResult:
        """Run the full validation pipeline on tool input.

        Args:
            tool_name: Name of the tool.
            arguments: Tool arguments dict.
            agent_id: Agent identifier for permission check.
            agent_role: Agent role for permission check.
            query: Original user query for safety context.

        Returns:
            ValidationResult.
        """
        errors = []
        warnings = []
        sanitized = dict(arguments)

        # Stage 1: Schema validation
        schema_errors = self._validate_schema(tool_name, sanitized)
        errors.extend(schema_errors)

        # Stage 2: Type checking
        type_errors = self._validate_types(tool_name, sanitized)
        errors.extend(type_errors)

        # Stage 3: Safety check
        safety_result = self._check_safety(tool_name, sanitized, query or "")
        if safety_result.blocked:
            errors.append(f"Safety check failed: {safety_result.reason}")
        elif safety_result.reason:
            warnings.append(f"Safety warning: {safety_result.reason}")

        # Stage 4: Permission check
        if agent_role:
            perm_result = await self.permissions.check_permission(
                tool_name, agent_id, agent_role
            )
            if not perm_result.allowed:
                errors.append(f"Permission denied: {perm_result.reason}")

        # Sanitize: remove internal params
        sanitized = {k: v for k, v in sanitized.items() if not k.startswith("_")}

        valid = len(errors) == 0

        if not valid:
            logger.warning(
                "Tool validation failed",
                extra={
                    "tool_name": tool_name,
                    "errors": errors,
                    "warnings": warnings,
                    "agent_id": agent_id,
                },
            )

        return ValidationResult(
            valid=valid,
            errors=errors,
            warnings=warnings,
            sanitized_args=sanitized,
            tool_name=tool_name,
        )

    def _validate_schema(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> List[str]:
        """Validate arguments against tool schema.

        Args:
            tool_name: Tool name.
            arguments: Arguments dict.

        Returns:
            List of error messages.
        """
        errors = []
        tool = self.registry.get(tool_name)
        if not tool:
            errors.append(f"Tool '{tool_name}' not found in registry")
            return errors

        schema = tool.get_schema()
        parameters = schema.get("parameters", {})
        properties = parameters.get("properties", {})
        required = parameters.get("required", [])

        # Check required fields
        for req_field in required:
            if req_field not in arguments or arguments[req_field] is None:
                errors.append(f"Missing required parameter: '{req_field}'")

        # Check for unknown fields
        for key in arguments:
            if key.startswith("_"):
                continue  # Internal params are allowed
            if key not in properties:
                errors.append(f"Unknown parameter: '{key}'")

        return errors

    def _validate_types(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> List[str]:
        """Validate argument types against schema.

        Args:
            tool_name: Tool name.
            arguments: Arguments dict.

        Returns:
            List of error messages.
        """
        errors = []
        tool = self.registry.get(tool_name)
        if not tool:
            return errors

        schema = tool.get_schema()
        properties = schema.get("parameters", {}).get("properties", {})

        for key, value in arguments.items():
            if key.startswith("_"):
                continue
            prop = properties.get(key, {})
            expected_type = prop.get("type")
            if not expected_type:
                continue

            type_match = self._check_type(value, expected_type)
            if not type_match:
                errors.append(
                    f"Type mismatch for '{key}': expected {expected_type}, got {type(value).__name__}"
                )

        return errors

    def _check_type(self, value: Any, expected_type: str) -> bool:
        """Check if a value matches an expected JSON Schema type.

        Args:
            value: Value to check.
            expected_type: JSON Schema type string.

        Returns:
            True if types match.
        """
        if expected_type == "string":
            return isinstance(value, str)
        elif expected_type == "integer":
            return isinstance(value, int) and not isinstance(value, bool)
        elif expected_type == "number":
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        elif expected_type == "boolean":
            return isinstance(value, bool)
        elif expected_type == "array":
            return isinstance(value, list)
        elif expected_type == "object":
            return isinstance(value, dict)
        return True  # Unknown types pass

    def _check_safety(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        query: str,
    ) -> Any:
        """Run safety checks on tool input.

        Args:
            tool_name: Tool name.
            arguments: Arguments dict.
            query: User query.

        Returns:
            SafetyResult.
        """
        return self.safety_gate.check_tool_call(tool_name, arguments, query)

    async def validate_batch(
        self,
        tool_calls: List[Dict[str, Any]],
        agent_id: Optional[str] = None,
        agent_role: Optional[AgentRole] = None,
        query: Optional[str] = None,
    ) -> List[ValidationResult]:
        """Validate multiple tool calls.

        Args:
            tool_calls: List of dicts with 'tool_name' and 'arguments'.
            agent_id: Agent identifier.
            agent_role: Agent role.
            query: User query.

        Returns:
            List of ValidationResult.
        """
        results = []
        for call in tool_calls:
            result = await self.validate(
                tool_name=call.get("tool_name", ""),
                arguments=call.get("arguments", {}),
                agent_id=agent_id,
                agent_role=agent_role,
                query=query,
            )
            results.append(result)
        return results


# Module-level singleton
tool_input_validator = ToolInputValidator()
