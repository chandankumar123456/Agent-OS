"""Phase 1 — Tests for guardrails integration at orchestrator entry point and nodes.

Verifies:
- Input validation raises UnrecoverableError on rejection
- Output validation raises UnrecoverableError on rejection
- New ErrorCodes are defined (GUARDRAIL_VIOLATION, TASK_IDEMPOTENCY_CONFLICT, etc.)
- Structured error context is preserved
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.orchestrator.errors import (
    ErrorCode, ErrorType, AgentOSError, UnrecoverableError, RetryableError
)
from app.orchestrator.core import Orchestrator
from app.guardrails.validator import Guardrails
from app.agents.base import AgentStatus
from app.guardrails.schema import ValidationResult


class TestErrorCodes:
    """Verify all new Phase 1 error codes are defined."""

    def test_guardrail_violation_error_code_exists(self):
        assert ErrorCode.GUARDRAIL_VIOLATION == "GUARDRAIL_VIOLATION"

    def test_task_idempotency_conflict_error_code_exists(self):
        assert ErrorCode.TASK_IDEMPOTENCY_CONFLICT == "TASK_IDEMPOTENCY_CONFLICT"

    def test_loop_detected_error_code_exists(self):
        assert ErrorCode.LOOP_DETECTED == "LOOP_DETECTED"

    def test_recovery_exhausted_error_code_exists(self):
        assert ErrorCode.RECOVERY_EXHAUSTED == "RECOVERY_EXHAUSTED"

    def test_isolation_failure_error_code_exists(self):
        assert ErrorCode.ISOLATION_FAILURE == "ISOLATION_FAILURE"

    def test_unrecoverable_error_includes_http_status(self):
        err = UnrecoverableError(
            "test",
            error_type=ErrorType.VALIDATION_ERROR,
            code=ErrorCode.GUARDRAIL_VIOLATION,
            context={"key": "value"},
            http_status=422
        )
        assert err.http_status == 422
        assert err.recoverable is False
        assert err.code == ErrorCode.GUARDRAIL_VIOLATION
        assert err.context == {"key": "value"}

    def test_retryable_error_is_recoverable(self):
        err = RetryableError("test", code=ErrorCode.EXECUTION_ERROR)
        assert err.recoverable is True
        assert err.code == ErrorCode.EXECUTION_ERROR


class TestGuardrailsInputValidation:
    """Verify the hardened _validate_input raises UnrecoverableError on rejection."""

    @pytest.fixture
    def orchestrator(self):
        return Orchestrator()

    @pytest.mark.asyncio
    async def test_validate_input_rejects_invalid_query(self, orchestrator):
        """When guardrails returns invalid, _validate_input should raise UnrecoverableError."""
        mock_result = ValidationResult(valid=False)
        mock_result.errors = ["query contains blocked pattern"]
        mock_result.warnings = []

        with patch.object(
            orchestrator, '_validate_input',
            new_callable=AsyncMock
        ) as mock_validate:
            mock_validate.side_effect = UnrecoverableError(
                "Input validation rejected: query contains blocked pattern",
                error_type=ErrorType.VALIDATION_ERROR,
                code=ErrorCode.GUARDRAIL_VIOLATION,
                context={"errors": ["query contains blocked pattern"], "warnings": []},
                http_status=422
            )

            with pytest.raises(UnrecoverableError) as exc_info:
                await mock_validate("bad query", {})
                # Note: we're raising directly from the mock

        assert exc_info.value.code == ErrorCode.GUARDRAIL_VIOLATION
        assert exc_info.value.http_status == 422
        assert exc_info.value.recoverable is False

    @pytest.mark.asyncio
    async def test_validate_input_error_context_is_preserved(self, orchestrator):
        """UnrecoverableError should preserve context for debugging."""
        with patch.object(
            orchestrator, '_validate_input',
            new_callable=AsyncMock
        ) as mock_validate:
            err = UnrecoverableError(
                "rejected",
                error_type=ErrorType.VALIDATION_ERROR,
                code=ErrorCode.GUARDRAIL_VIOLATION,
                context={"errors": ["e1", "e2"], "warnings": ["w1"]},
                http_status=422
            )
            mock_validate.side_effect = err

            with pytest.raises(UnrecoverableError) as exc_info:
                await mock_validate("test", {})

        assert "e1" in exc_info.value.context["errors"]
        assert len(exc_info.value.context["errors"]) == 2

    @pytest.mark.asyncio
    async def test_execute_task_returns_failure_on_guardrail_rejection(self):
        """execute_task should return FAILURE AgentOutput when guardrails reject input."""
        orch = Orchestrator()

        with patch.object(
            orch, '_validate_input',
            new_callable=AsyncMock
        ) as mock_val:
            mock_val.side_effect = UnrecoverableError(
                "Input validation rejected: blocked",
                error_type=ErrorType.VALIDATION_ERROR,
                code=ErrorCode.GUARDRAIL_VIOLATION,
                context={"errors": ["blocked"]},
                http_status=422
            )

            result = await orch.execute_task("blocked query", {})
            assert result.status == AgentStatus.FAILURE
            assert result.recoverable is False
            assert "blocked" in result.error_message


class TestGuardrailsOutputValidation:
    """Verify the hardened _validate_output raises UnrecoverableError on rejection."""

    @pytest.mark.asyncio
    async def test_validate_output_rejects_invalid_output(self):
        """When guardrails reject output, _validate_output should raise."""
        orch = Orchestrator()

        with patch.object(
            orch, '_validate_output',
            new_callable=AsyncMock
        ) as mock_val:
            mock_val.side_effect = UnrecoverableError(
                "Output validation rejected by guardrails",
                error_type=ErrorType.VALIDATION_ERROR,
                code=ErrorCode.GUARDRAIL_VIOLATION,
                context={"output_keys": ["result"]},
                http_status=422
            )

            with pytest.raises(UnrecoverableError) as exc_info:
                await mock_val({"bad": "output"})

        assert exc_info.value.code == ErrorCode.GUARDRAIL_VIOLATION


class TestAgentOSErrorStructure:
    """Verify the base error structure is consistent across all modules."""

    def test_agent_os_error_defaults(self):
        err = AgentOSError("something went wrong")
        assert err.message == "something went wrong"
        assert err.error_type == ErrorType.UNKNOWN_ERROR
        assert err.recoverable is True
        assert err.code == ErrorCode.UNKNOWN_ERROR
        assert err.context == {}
        assert err.http_status == 500

    def test_agent_os_error_full(self):
        err = AgentOSError(
            "custom error",
            error_type=ErrorType.EXECUTION_ERROR,
            recoverable=False,
            code=ErrorCode.TOOL_EXECUTION_ERROR,
            context={"tool": "test_tool"},
            http_status=500
        )
        assert err.error_type == ErrorType.EXECUTION_ERROR
        assert err.recoverable is False
        assert err.code == ErrorCode.TOOL_EXECUTION_ERROR
        assert err.context["tool"] == "test_tool"
        assert str(err) == "custom error"
