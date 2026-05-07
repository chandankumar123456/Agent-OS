"""Phase 3.2 — ReviewerAgent: Output validation against schemas and rules.

Reviews agent outputs for correctness, completeness, and compliance. Validates
outputs against role-specific schemas, detects missing fields, and scores quality.

Spec: Build Plan Task 3.2.2, Section 6.1
Input Contract:  review(AgentOutput, schema=None) → ReviewResult
Output Contract: ReviewResult with pass/fail, issues list, quality score
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from ..logs.logger import logger
from ..orchestrator.errors import AgentOSError, ErrorCode, ErrorType
from .base import AgentInput, AgentOutput, AgentRole, AgentStatus


# ── Pydantic Models ──────────────────────────────────────────────────────────

class ReviewIssue(BaseModel):
    """A single issue found during review."""

    field: str = Field(..., description="Field or aspect with the issue")
    severity: str = Field(
        default="error",
        description="Issue severity: error, warning, info"
    )
    message: str = Field(..., description="Human-readable issue description")
    expected: Optional[str] = None
    actual: Optional[str] = None
    suggestion: Optional[str] = None


class ReviewResult(BaseModel):
    """Result of a review operation."""

    review_id: str = Field(default_factory=lambda: str(UUID(int=0)))
    task_id: str = ""
    step_id: str = ""
    passed: bool = False
    issues: List[ReviewIssue] = Field(default_factory=list)
    quality_score: float = Field(default=0.0, ge=0.0, le=1.0)
    warnings_count: int = 0
    errors_count: int = 0
    reviewed_by: str = "reviewer"
    reviewed_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    summary: str = ""


# ── Output Schemas Per Role ──────────────────────────────────────────────────

# Expected output schemas define what fields each agent role should produce.
# These are used for structural validation during review.

OUTPUT_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "planner": {
        "required_fields": ["plan", "steps"],
        "optional_fields": ["reasoning", "assumptions", "constraints"],
        "expected_types": {
            "plan": dict,
            "steps": list,
        },
        "max_steps": 50,
    },
    "executor": {
        "required_fields": ["step_results", "tool_calls"],
        "optional_fields": ["metadata", "duration_ms"],
        "expected_types": {
            "step_results": dict,
            "tool_calls": list,
        },
        "max_tool_calls": 100,
    },
    "verifier": {
        "required_fields": ["verified", "verification_notes"],
        "optional_fields": ["verification_reports", "confidence"],
        "expected_types": {
            "verified": bool,
            "verification_notes": str,
        },
        "min_confidence": 0.5,
    },
    "reviewer": {
        "required_fields": ["passed", "issues", "quality_score"],
        "optional_fields": ["suggestions", "summary"],
        "expected_types": {
            "passed": bool,
            "issues": list,
            "quality_score": (int, float),
        },
        "min_quality_score": 0.0,
    },
    "coordinator": {
        "required_fields": ["overall_status", "step_results"],
        "optional_fields": ["handoff_log", "error_summary"],
        "expected_types": {
            "overall_status": str,
            "step_results": dict,
        },
    },
}

# Rules for semantic checks (content quality, not just structure)
QUALITY_RULES = {
    "empty_output_check": {
        "description": "Output must not be empty",
        "check": lambda output: (
            bool(output.output_data) if isinstance(output.output_data, dict)
            else True
        ),
        "severity": "error",
    },
    "confidence_check": {
        "description": "Confidence should be >= 0.0",
        "check": lambda output: output.confidence >= 0.0,
        "severity": "warning",
    },
    "error_message_check": {
        "description": "Failed outputs must include error message",
        "check": lambda output: (
            output.status != AgentStatus.FAILURE
            or bool(output.error_message)
        ),
        "severity": "error",
    },
    "output_size_check": {
        "description": "Output data should be under 10MB",
        "check": lambda output: (
            len(str(output.output_data)) < 10_000_000
        ),
        "severity": "warning",
    },
}


# ── ReviewerAgent ────────────────────────────────────────────────────────────

class ReviewerAgent:
    """Validates agent outputs against role-specific schemas and quality rules.

    Performs two layers of validation:
    1. Structural: Checks required fields, types, and size constraints.
    2. Quality: Applies quality rules (non-empty, confidence, error completeness).

    Produces a ReviewResult with pass/fail status and actionable issues.
    """

    name: str = "reviewer"
    role: AgentRole = AgentRole.PLANNER  # Reuse PLANNER enum for reviewer

    def __init__(self, strict_mode: bool = False):
        """Initialize the ReviewerAgent.

        Args:
            strict_mode: If True, warnings are treated as errors.
        """
        self._strict_mode = strict_mode
        self._review_count: int = 0

    # ── Public API ───────────────────────────────────────────────────────

    async def review(
        self,
        output: AgentOutput,
        target_role: Optional[str] = None,
        custom_schema: Optional[Dict[str, Any]] = None,
    ) -> ReviewResult:
        """Review an agent output against schema and quality rules.

        Args:
            output: The AgentOutput to review.
            target_role: The agent role that produced the output (used for
                         role-specific schema validation).
            custom_schema: Optional custom validation schema.

        Returns:
            ReviewResult with pass/fail status and issue details.
        """
        import uuid

        self._review_count += 1
        issues: List[ReviewIssue] = []
        role = target_role or output.output_data.get("role", "executor")

        # 1. Structural validation
        schema = custom_schema or OUTPUT_SCHEMAS.get(role, {})
        if schema:
            struct_issues = self._validate_structure(output, schema)
            issues.extend(struct_issues)

        # 2. Quality validation
        qual_issues = self._validate_quality(output)
        issues.extend(qual_issues)

        # 3. Classify issues
        errors = [i for i in issues if i.severity == "error"]
        warnings = [i for i in issues if i.severity == "warning"]

        if self._strict_mode:
            errors.extend(warnings)
            warnings.clear()

        passed = len(errors) == 0

        # 4. Compute quality score
        quality_score = self._compute_quality_score(
            output=output,
            issues=issues,
            passed=passed,
        )

        summary = (
            f"Review {'PASSED' if passed else 'FAILED'}: "
            f"{len(errors)} errors, {len(warnings)} warnings. "
            f"Quality score: {quality_score:.2f}"
        )

        logger.info(
            f"Reviewer: {summary} (role={role}, task={output.task_id})",
            extra={"task_id": str(output.task_id), "review_passed": passed},
        )

        return ReviewResult(
            review_id=str(uuid.uuid4()),
            task_id=str(output.task_id),
            step_id=str(output.step_id),
            passed=passed,
            issues=issues,
            quality_score=quality_score,
            warnings_count=len(warnings),
            errors_count=len(errors),
            summary=summary,
        )

    async def execute(self, input_data: AgentInput) -> AgentOutput:
        """Execute a review task. Implements the BaseAgent protocol."""
        output_dict = input_data.input_data.get("output", {})
        target_role = input_data.input_data.get("target_role")
        custom_schema = input_data.input_data.get("custom_schema")

        # Convert dict to AgentOutput if needed
        if isinstance(output_dict, dict) and output_dict:
            try:
                output = AgentOutput(**output_dict)
            except Exception as e:
                return AgentOutput(
                    task_id=input_data.task_id,
                    step_id=input_data.step_id,
                    status=AgentStatus.FAILURE,
                    error_type="review_error",
                    error_message=f"Invalid output format: {e}",
                    recoverable=False,
                )
        else:
            return AgentOutput(
                task_id=input_data.task_id,
                step_id=input_data.step_id,
                status=AgentStatus.FAILURE,
                error_type="review_error",
                error_message="No output data provided for review",
                recoverable=False,
            )

        result = await self.review(output, target_role, custom_schema)

        return AgentOutput(
            task_id=input_data.task_id,
            step_id=input_data.step_id,
            status=AgentStatus.SUCCESS if result.passed else AgentStatus.FAILURE,
            output_data=result.model_dump(),
            confidence=result.quality_score,
            reasoning_trace=[
                f"Reviewed {target_role or 'unknown'} agent output",
                f"Found {result.errors_count} errors, {result.warnings_count} warnings",
                f"Quality score: {result.quality_score:.2f}",
            ],
            error_message=result.summary if not result.passed else None,
            recoverable=True,
        )

    # ── Internal: Structural Validation ──────────────────────────────────

    def _validate_structure(
        self,
        output: AgentOutput,
        schema: Dict[str, Any],
    ) -> List[ReviewIssue]:
        """Validate output against a structural schema.

        Checks required fields, field types, and size constraints.

        Args:
            output: The AgentOutput to validate.
            schema: Schema dict with required_fields, expected_types, etc.

        Returns:
            List of ReviewIssue objects.
        """
        issues: List[ReviewIssue] = []
        data = output.output_data

        # Check required fields
        for field in schema.get("required_fields", []):
            if field not in data or data[field] is None:
                issues.append(ReviewIssue(
                    field=field,
                    severity="error",
                    message=f"Missing required field: '{field}'",
                    expected=f"Field '{field}' must be present and non-null",
                    actual="None or missing",
                    suggestion=f"Ensure output_data includes '{field}'",
                ))

        # Check field types
        for field, expected_type in schema.get("expected_types", {}).items():
            if field in data and data[field] is not None:
                actual_value = data[field]
                if isinstance(expected_type, tuple):
                    if not isinstance(actual_value, expected_type):
                        issues.append(ReviewIssue(
                            field=field,
                            severity="error",
                            message=f"Wrong type for field '{field}'",
                            expected=str(expected_type),
                            actual=type(actual_value).__name__,
                            suggestion=f"Convert '{field}' to one of {expected_type}",
                        ))
                elif not isinstance(actual_value, expected_type):
                    issues.append(ReviewIssue(
                        field=field,
                        severity="error",
                        message=f"Wrong type for field '{field}'",
                        expected=expected_type.__name__,
                        actual=type(actual_value).__name__,
                        suggestion=f"Ensure '{field}' is of type {expected_type.__name__}",
                    ))

        # Size constraints
        if "max_steps" in schema and "steps" in data and isinstance(data["steps"], list):
            if len(data["steps"]) > schema["max_steps"]:
                issues.append(ReviewIssue(
                    field="steps",
                    severity="warning",
                    message=f"Step count ({len(data['steps'])}) exceeds maximum ({schema['max_steps']})",
                    suggestion="Consider splitting into multiple sub-plans",
                ))

        if "max_tool_calls" in schema and "tool_calls" in data and isinstance(data["tool_calls"], list):
            if len(data["tool_calls"]) > schema["max_tool_calls"]:
                issues.append(ReviewIssue(
                    field="tool_calls",
                    severity="warning",
                    message=f"Tool call count ({len(data['tool_calls'])}) exceeds maximum ({schema['max_tool_calls']})",
                    suggestion="Consider batching or reducing tool calls",
                ))

        return issues

    # ── Internal: Quality Validation ─────────────────────────────────────

    def _validate_quality(self, output: AgentOutput) -> List[ReviewIssue]:
        """Apply quality rules to the output.

        Args:
            output: The AgentOutput to check.

        Returns:
            List of ReviewIssue objects.
        """
        issues: List[ReviewIssue] = []

        for rule_name, rule in QUALITY_RULES.items():
            try:
                passed = rule["check"](output)
                if not passed:
                    issues.append(ReviewIssue(
                        field="output",
                        severity=rule.get("severity", "warning"),
                        message=f"Quality rule '{rule_name}' failed: {rule.get('description', 'Unknown')}",
                    ))
            except Exception as e:
                # Rule check itself errored — log and add a warning
                issues.append(ReviewIssue(
                    field="output",
                    severity="warning",
                    message=f"Quality rule '{rule_name}' check error: {e}",
                ))

        return issues

    # ── Internal: Scoring ────────────────────────────────────────────────

    def _compute_quality_score(
        self,
        output: AgentOutput,
        issues: List[ReviewIssue],
        passed: bool,
    ) -> float:
        """Compute a quality score (0.0 - 1.0) based on issues.

        Args:
            output: The reviewed output.
            issues: List of review issues found.
            passed: Whether the review passed.

        Returns:
            Quality score between 0.0 and 1.0.
        """
        if not issues:
            return 1.0

        penalty_per_error = 0.15
        penalty_per_warning = 0.05

        errors = sum(1 for i in issues if i.severity == "error")
        warnings = sum(1 for i in issues if i.severity == "warning")

        score = 1.0 - (errors * penalty_per_error) - (warnings * penalty_per_warning)

        # Boost for passing outputs (minimum 0.6 if passed)
        if passed and score < 0.6:
            score = 0.6

        # Confidence adjustment
        score *= output.confidence if output.confidence > 0 else 1.0

        return max(0.0, min(1.0, score))
