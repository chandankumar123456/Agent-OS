"""Unit tests for reviewer agent: ReviewIssue, ReviewResult, ReviewerAgent."""
import pytest
from uuid import uuid4, UUID

from app.agents.base import AgentInput, AgentOutput, AgentRole, AgentStatus
from app.agents.reviewer import (
    ReviewIssue,
    ReviewResult,
    ReviewerAgent,
    OUTPUT_SCHEMAS,
    QUALITY_RULES,
)


# ═════════════════════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════════════════════

def _make_output(output_data=None, status=AgentStatus.SUCCESS, confidence=1.0,
                 error_message=None):
    """Create a minimal AgentOutput for testing."""
    return AgentOutput(
        task_id=uuid4(),
        step_id=uuid4(),
        status=status,
        output_data=output_data or {},
        confidence=confidence,
        error_message=error_message,
    )


# ═════════════════════════════════════════════════════════════════════════════
# ReviewIssue Tests
# ═════════════════════════════════════════════════════════════════════════════

class TestReviewIssue:
    """Model creation and validation."""

    def test_create_warning_issue(self):
        issue = ReviewIssue(
            field="notes",
            severity="warning",
            message="Optional field 'notes' not present",
        )
        assert issue.field == "notes"
        assert issue.severity == "warning"
        assert issue.message == "Optional field 'notes' not present"
        assert issue.suggestion is None
        assert issue.expected is None
        assert issue.actual is None

    def test_create_error_issue_with_suggestion(self):
        issue = ReviewIssue(
            field="output",
            severity="error",
            message="Output is empty",
            expected="At least one output field populated",
            actual="{}",
            suggestion="Ensure at least one output field is populated",
        )
        assert issue.field == "output"
        assert issue.severity == "error"
        assert issue.message == "Output is empty"
        assert issue.expected == "At least one output field populated"
        assert issue.actual == "{}"
        assert issue.suggestion == "Ensure at least one output field is populated"


# ═════════════════════════════════════════════════════════════════════════════
# ReviewResult Tests
# ═════════════════════════════════════════════════════════════════════════════

class TestReviewResult:
    """Model creation and status logic."""

    def test_create_pass_result(self):
        result = ReviewResult(
            passed=True,
            issues=[],
            quality_score=1.0,
        )
        assert result.passed is True
        assert result.issues == []
        assert result.quality_score == 1.0
        assert isinstance(result.review_id, str)
        assert result.reviewed_by == "reviewer"
        assert result.reviewed_at  # auto-generated ISO string

    def test_create_fail_result(self):
        issue = ReviewIssue(
            field="plan", severity="error", message="missing required field",
        )
        result = ReviewResult(
            passed=False,
            issues=[issue],
            quality_score=0.5,
            errors_count=1,
        )
        assert result.passed is False
        assert len(result.issues) == 1
        assert result.quality_score == 0.5
        assert result.errors_count == 1


# ═════════════════════════════════════════════════════════════════════════════
# OUTPUT_SCHEMAS Tests
# ═════════════════════════════════════════════════════════════════════════════

class TestOutputSchemas:
    """Verify schema definitions exist and are structured."""

    def test_schemas_have_expected_role_keys(self):
        expected_keys = {"planner", "executor", "verifier", "reviewer", "coordinator"}
        assert set(OUTPUT_SCHEMAS.keys()) == expected_keys

    def test_each_schema_has_required_and_optional_fields(self):
        for name, schema in OUTPUT_SCHEMAS.items():
            assert "required_fields" in schema, f"{name} missing required_fields"
            assert "optional_fields" in schema, f"{name} missing optional_fields"
            assert "expected_types" in schema, f"{name} missing expected_types"


# ═════════════════════════════════════════════════════════════════════════════
# QUALITY_RULES Tests
# ═════════════════════════════════════════════════════════════════════════════

class TestQualityRules:
    """Verify quality rule constants."""

    def test_rules_have_expected_keys(self):
        expected_keys = {
            "empty_output_check",
            "confidence_check",
            "error_message_check",
            "output_size_check",
        }
        assert set(QUALITY_RULES.keys()) == expected_keys

    def test_rules_are_callable(self):
        for rule_name, rule in QUALITY_RULES.items():
            assert callable(rule["check"]), f"{rule_name} check is not callable"
            assert "description" in rule, f"{rule_name} missing description"
            assert "severity" in rule, f"{rule_name} missing severity"


# ═════════════════════════════════════════════════════════════════════════════
# ReviewerAgent._validate_structure Tests
# ═════════════════════════════════════════════════════════════════════════════

class TestValidateStructure:
    """Validate output schema conformance."""

    def setup_method(self):
        self.reviewer = ReviewerAgent()

    def test_valid_output_passes_validation(self):
        output = _make_output(output_data={
            "plan": {"goal": "test"},
            "steps": ["step1"],
        })
        schema = OUTPUT_SCHEMAS["planner"]
        issues = self.reviewer._validate_structure(output, schema)
        assert issues == []

    def test_missing_required_field(self):
        output = _make_output(output_data={})  # empty - missing required fields
        schema = OUTPUT_SCHEMAS["planner"]
        issues = self.reviewer._validate_structure(output, schema)
        assert len(issues) > 0
        missing_fields = {i.field for i in issues}
        assert "plan" in missing_fields
        assert "steps" in missing_fields
        assert all(i.severity == "error" for i in issues)

    def test_catches_wrong_type(self):
        output = _make_output(output_data={
            "plan": "not a dict",  # should be dict
            "steps": "not a list",  # should be list
        })
        schema = OUTPUT_SCHEMAS["planner"]
        issues = self.reviewer._validate_structure(output, schema)
        type_issues = [i for i in issues if "Wrong type" in i.message]
        assert len(type_issues) >= 2


# ═════════════════════════════════════════════════════════════════════════════
# ReviewerAgent._validate_quality Tests
# ═════════════════════════════════════════════════════════════════════════════

class TestValidateQuality:
    """Quality rule enforcement."""

    def setup_method(self):
        self.reviewer = ReviewerAgent()

    def test_empty_output_triggers_error(self):
        output = _make_output(output_data={})
        issues = self.reviewer._validate_quality(output)
        empty_issues = [i for i in issues if "empty_output_check" in i.message]
        assert len(empty_issues) > 0
        assert any(i.severity == "error" for i in empty_issues)

    def test_non_empty_output_passes(self):
        output = _make_output(output_data={"data": "valid output"})
        issues = self.reviewer._validate_quality(output)
        empty_issues = [i for i in issues if "empty_output_check" in i.message]
        assert len(empty_issues) == 0


# ═════════════════════════════════════════════════════════════════════════════
# ReviewerAgent._compute_quality_score Tests
# ═════════════════════════════════════════════════════════════════════════════

class TestComputeQualityScore:
    """Scoring: starts at 1.0, -0.15 per error, -0.05 per warning, min 0.0."""

    def setup_method(self):
        self.reviewer = ReviewerAgent()

    def test_no_issues_scores_one(self):
        output = _make_output()
        score = self.reviewer._compute_quality_score(output, [], passed=True)
        assert score == 1.0

    def test_one_error_scores_0_85(self):
        output = _make_output()
        issues = [ReviewIssue(field="f", severity="error", message="d")]
        score = self.reviewer._compute_quality_score(output, issues, passed=False)
        # 1.0 - 0.15 = 0.85, * confidence(1.0) = 0.85
        assert score == pytest.approx(0.85)

    def test_mixed_issues_reduce_score(self):
        output = _make_output()
        issues = [
            ReviewIssue(field="f1", severity="error", message="d1"),
            ReviewIssue(field="f2", severity="warning", message="d2"),
            ReviewIssue(field="f3", severity="warning", message="d3"),
        ]
        score = self.reviewer._compute_quality_score(output, issues, passed=False)
        # 1.0 - 0.15 - 0.05 - 0.05 = 0.75, * confidence(1.0) = 0.75
        assert score == pytest.approx(0.75)

    def test_score_floors_at_zero(self):
        output = _make_output()
        issues = [
            ReviewIssue(field=f"f{i}", severity="error", message="d")
            for i in range(20)
        ]
        score = self.reviewer._compute_quality_score(output, issues, passed=False)
        assert score == 0.0

    def test_passed_with_low_score_boosts_to_0_6(self):
        output = _make_output(confidence=1.0)
        # 7 errors: 1.0 - 7*0.15 = -0.05 -> 0.0, but passed=True so boost to 0.6
        issues = [
            ReviewIssue(field=f"f{i}", severity="error", message="d")
            for i in range(7)
        ]
        score = self.reviewer._compute_quality_score(output, issues, passed=True)
        assert score == pytest.approx(0.6)


# ═════════════════════════════════════════════════════════════════════════════
# ReviewerAgent.review() Tests
# ═════════════════════════════════════════════════════════════════════════════

class TestReviewMethod:
    """End-to-end review flow."""

    def setup_method(self):
        self.reviewer = ReviewerAgent()

    @pytest.mark.asyncio
    async def test_review_returns_review_result(self):
        output = _make_output(output_data={
            "plan": {"goal": "test"},
            "steps": ["step1"],
        })
        result = await self.reviewer.review(output, target_role="planner")
        assert isinstance(result, ReviewResult)
        assert result.passed is True
        assert result.quality_score > 0.0

    @pytest.mark.asyncio
    async def test_review_empty_output_fails(self):
        output = _make_output(output_data={})
        result = await self.reviewer.review(output, target_role="planner")
        assert result.passed is False
        assert len(result.issues) > 0
        assert result.errors_count > 0


# ═════════════════════════════════════════════════════════════════════════════
# ReviewerAgent.execute() Tests
# ═════════════════════════════════════════════════════════════════════════════

class TestExecuteMethod:
    """Verify execute delegates to review and returns AgentOutput."""

    def setup_method(self):
        self.reviewer = ReviewerAgent()

    @pytest.mark.asyncio
    async def test_execute_returns_agent_output(self):
        task_id = uuid4()
        step_id = uuid4()
        agent_input = AgentInput(
            task_id=task_id,
            step_id=step_id,
            role=AgentRole.EXECUTOR,
            input_data={
                "output": {
                    "task_id": str(uuid4()),
                    "step_id": str(uuid4()),
                    "status": "success",
                    "output_data": {
                        "plan": {"goal": "test"},
                        "steps": ["step1"],
                    },
                },
                "target_role": "planner",
            },
        )
        result = await self.reviewer.execute(agent_input)
        assert isinstance(result, AgentOutput)
        assert result.task_id == task_id
        assert result.step_id == step_id
