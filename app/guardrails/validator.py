from typing import Dict, Any, List, Optional
from uuid import UUID
from fastapi import Depends, HTTPException, Query, Path
from .schema import GuardrailSchema, ValidationResult, CustomRule
from ..logs.logger import logger
from ..orchestrator.errors import ErrorCode, UnrecoverableError


class InputValidator:
    """Validate all API route inputs before reaching the orchestrator."""
    
    # Blocked query patterns (high-risk or abuse keywords)
    BLOCKED_QUERY_PATTERNS = [
        r"rm\s+-rf\s+/",
        r"DROP\s+TABLE",
        r"DELETE\s+FROM",
        r"FORMAT\s+C:",
        r"shutdown\s+/s",
        r"dd\s+if=/dev/zero",
        r"mkfs\.",
        r">\s*/dev/sda",
    ]
    
    # Max lengths for different input fields
    MAX_QUERY_LENGTH = 10000
    MAX_MODE_LENGTH = 50
    
    # Allowed modes
    ALLOWED_MODES = {"task", "workflow", "autonomous", "collaboration"}
    
    @classmethod
    def validate_request(cls, query: str, config: dict = None, mode: str = "task") -> None:
        """Validate all request parameters. Raises UnrecoverableError on failure.
        
        Args:
            query: The user's query string
            config: Optional task configuration dict
            mode: Execution mode string
            
        Raises:
            UnrecoverableError: If any validation fails, with structured error context
        """
        errors = []
        context = {}
        
        # 1. Query validation
        if not query or not query.strip():
            errors.append("Query is empty")
            context["field"] = "query"
        elif len(query) > cls.MAX_QUERY_LENGTH:
            errors.append(f"Query exceeds maximum length of {cls.MAX_QUERY_LENGTH} characters")
            context["field"] = "query"
            context["actual_length"] = len(query)
            context["max_length"] = cls.MAX_QUERY_LENGTH
        
        if query:
            import re
            for pattern in cls.BLOCKED_QUERY_PATTERNS:
                if re.search(pattern, query, re.IGNORECASE):
                    errors.append(f"Query contains blocked pattern: {pattern}")
                    context["field"] = "query"
                    context["blocked_pattern"] = pattern
                    break
        
        # 2. Mode validation
        if mode not in cls.ALLOWED_MODES:
            errors.append(f"Invalid mode '{mode}'. Allowed: {', '.join(sorted(cls.ALLOWED_MODES))}")
            context["field"] = "mode"
            context["provided_mode"] = mode
            context["allowed_modes"] = sorted(cls.ALLOWED_MODES)
        elif mode and len(mode) > cls.MAX_MODE_LENGTH:
            errors.append(f"Mode exceeds maximum length of {cls.MAX_MODE_LENGTH}")
            context["field"] = "mode"
        
        # 3. Config validation (if provided)
        if config:
            if not isinstance(config, dict):
                errors.append("Config must be a dictionary")
                context["field"] = "config"
            else:
                max_steps = config.get("max_steps")
                if max_steps is not None:
                    if not isinstance(max_steps, int) or max_steps < 1 or max_steps > 100:
                        errors.append("max_steps must be between 1 and 100")
                        context["field"] = "config.max_steps"
                        context["actual_value"] = max_steps
                
                timeout = config.get("timeout")
                if timeout is not None:
                    if not isinstance(timeout, int) or timeout < 1 or timeout > 3600:
                        errors.append("timeout must be between 1 and 3600 seconds")
                        context["field"] = "config.timeout"
                        context["actual_value"] = timeout
        
        if errors:
            raise UnrecoverableError(
                message="; ".join(errors),
                code=ErrorCode.GUARDRAIL_VIOLATION,
                context=context,
            )


class OutputValidator:
    def __init__(self):
        self.schema = GuardrailSchema()
    
    async def validate(
        self,
        output: Dict[str, Any],
        rules: List[CustomRule] = None
    ) -> ValidationResult:
        result = self.schema.validate_output(output)
        
        if rules:
            custom_result = self.schema.validate_with_rules(output, rules)
            result.errors.extend(custom_result.errors)
            result.warnings.extend(custom_result.warnings)
            result.valid = len(result.errors) == 0
            result.confidence = max(0.0, result.confidence - (len(custom_result.errors) * 0.3) - (len(custom_result.warnings) * 0.1))
        
        if not result.valid:
            logger.warning(f"Output validation failed: {result.errors}")
        
        return result
    
    async def validate_steps(
        self,
        steps: List[Dict[str, Any]]
    ) -> ValidationResult:
        result = self.schema.validate_steps(steps)
        
        if not result.valid:
            logger.warning(f"Steps validation failed: {result.errors}")
        
        return result


def validate_context(context: Dict[str, Any]) -> ValidationResult:
    return GuardrailSchema.validate_context(context)


class Guardrails:
    def __init__(self):
        self.input_validator = InputValidator()
        self.validator = OutputValidator()
    
    async def verify_output(self, output: Dict[str, Any]) -> bool:
        # 1. Run existing schema validation
        result = await self.validator.validate(output)
        
        # 2. Load active rules from DB (optional, resilient)
        rules = []
        try:
            from ..memory.long_term import guardrail_rule_repo
            active_rules = await guardrail_rule_repo.list_active()
            rules = [
                CustomRule(
                    name=rule.name,
                    rule_type=rule.rule_type,
                    condition=rule.condition or {},
                    action=rule.action,
                )
                for rule in active_rules
            ]
        except Exception as e:
            logger.debug(f"Guardrail rule DB load skipped or failed: {e}")
        
        # 3. Run custom rule validation if rules loaded
        if rules:
            custom_result = GuardrailSchema.validate_with_rules(output, rules)
            result.errors.extend(custom_result.errors)
            result.warnings.extend(custom_result.warnings)
            result.valid = len(result.errors) == 0
            result.confidence = max(0.0, result.confidence - (len(custom_result.errors) * 0.3) - (len(custom_result.warnings) * 0.1))
        
        # 4. Combine and return
        if not result.valid:
            logger.warning(f"Output validation failed: {result.errors}")
        
        return result.valid
    
    async def verify_steps(self, steps: List[Dict[str, Any]]) -> bool:
        result = await self.validator.validate_steps(steps)
        return result.valid
    
    async def check_confidence(
        self,
        confidence: float,
        threshold: float = 0.5
    ) -> bool:
        return confidence >= threshold


guardrails = Guardrails()


async def validate_task_request(
    query: str,
    mode: Optional[str] = "task",
    config: Optional[Dict] = None
) -> None:
    """FastAPI dependency: validate task creation request parameters.
    
    Raises HTTPException(400) on validation failure.
    """
    try:
        InputValidator.validate_request(query=query, config=config, mode=mode or "task")
    except UnrecoverableError as e:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": e.code.value if e.code else ErrorCode.GUARDRAIL_VIOLATION.value,
                    "message": e.message,
                    "context": e.context
                }
            }
        )


def validate_task_id(task_id: str) -> UUID:
    """Validate and convert a task_id string to UUID.
    
    Raises HTTPException(400) on invalid UUID format.
    """
    try:
        return UUID(task_id)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": ErrorCode.VALIDATION_ERROR.value,
                    "message": f"Invalid task_id format: {task_id}",
                    "context": {"task_id": task_id}
                }
            }
        )


def validate_tool_execution_params(
    tool_name: str,
    arguments: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Validate tool execution parameters.
    
    Returns sanitized arguments. Raises HTTPException(400) on failure.
    """
    if not tool_name or not tool_name.strip():
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": ErrorCode.VALIDATION_ERROR.value,
                    "message": "Tool name is required",
                    "context": {}
                }
            }
        )
    
    # Validate tool name format: {server}__{tool}
    if "__" not in tool_name:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": ErrorCode.VALIDATION_ERROR.value,
                    "message": f"Invalid tool name format: {tool_name}. Expected {{server}}__{{tool}}",
                    "context": {"tool_name": tool_name}
                }
            }
        )
    
    return arguments or {}