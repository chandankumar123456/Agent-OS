"""Unit tests for orchestrator error classes: AgentOSError, RetryableError, UnrecoverableError."""
import pytest

from app.orchestrator.errors import (
    AgentOSError,
    RetryableError,
    UnrecoverableError,
    ErrorType,
    ErrorCode,
)


# ═════════════════════════════════════════════════════════════════════════════
# ErrorType Enum Tests
# ═════════════════════════════════════════════════════════════════════════════

class TestErrorType:
    """Verify ErrorType enum values."""

    def test_error_types_are_strings(self):
        """All ErrorType values must be strings."""
        for et in ErrorType:
            assert isinstance(et.value, str)

    def test_error_types_contain_key_types(self):
        """ErrorType must contain the core error categories."""
        types = {t.value for t in ErrorType}
        assert "execution_error" in types
        assert "auth_error" in types
        assert "validation_error" in types
        assert "timeout_error" in types
        assert "rate_limit_error" in types
        assert "unknown_error" in types


# ═════════════════════════════════════════════════════════════════════════════
# ErrorCode Enum Tests
# ═════════════════════════════════════════════════════════════════════════════

class TestErrorCode:
    """Verify ErrorCode uses SCREAMING_SNAKE_CASE strings."""

    def test_error_codes_are_screaming_snake_case(self):
        """All ErrorCode values must be uppercase with underscores."""
        for code in ErrorCode:
            assert code.value == code.value.upper(), f"{code.value} is not uppercase"
            assert " " not in code.value, f"{code.value} contains spaces"

    def test_error_codes_contain_key_codes(self):
        """ErrorCode must contain the core error codes."""
        codes = {c.value for c in ErrorCode}
        assert "EXECUTION_ERROR" in codes
        assert "VALIDATION_ERROR" in codes
        assert "AUTH_UNAUTHORIZED" in codes
        assert "TOOL_NOT_FOUND" in codes
        assert "TIMEOUT_ERROR" in codes
        assert "RATE_LIMIT_EXCEEDED" in codes
        assert "UNKNOWN_ERROR" in codes


# ═════════════════════════════════════════════════════════════════════════════
# AgentOSError Tests
# ═════════════════════════════════════════════════════════════════════════════

class TestAgentOSError:
    """Base error class creation and attributes."""

    def test_create_basic_error(self):
        """message is the first positional param; defaults apply for the rest."""
        err = AgentOSError("Tool execution failed")
        assert str(err) == "Tool execution failed"
        assert err.message == "Tool execution failed"
        assert err.error_type == ErrorType.UNKNOWN_ERROR
        assert err.recoverable is True
        assert err.code == ErrorCode.UNKNOWN_ERROR
        assert err.context == {}
        assert err.http_status == 500

    def test_create_error_with_error_type(self):
        """Can specify error_type explicitly."""
        err = AgentOSError(
            "Execution failed",
            error_type=ErrorType.EXECUTION_ERROR,
        )
        assert err.error_type == ErrorType.EXECUTION_ERROR

    def test_create_error_with_recoverable_flag(self):
        """Can set recoverable to False."""
        err = AgentOSError(
            "Access denied",
            error_type=ErrorType.AUTH_ERROR,
            recoverable=False,
        )
        assert err.recoverable is False

    def test_create_error_with_code(self):
        """Can specify an ErrorCode."""
        err = AgentOSError(
            "Tool not found",
            error_type=ErrorType.EXECUTION_ERROR,
            code=ErrorCode.TOOL_NOT_FOUND,
        )
        assert err.code == ErrorCode.TOOL_NOT_FOUND

    def test_create_error_with_context(self):
        """Can pass a context dict."""
        err = AgentOSError(
            "Invalid input",
            error_type=ErrorType.VALIDATION_ERROR,
            code=ErrorCode.VALIDATION_ERROR,
            context={"field": "email", "value": "bad"},
        )
        assert err.context == {"field": "email", "value": "bad"}

    def test_default_context_is_empty_dict(self):
        """When no context is provided, it defaults to an empty dict."""
        err = AgentOSError("test")
        assert err.context == {}

    def test_default_http_status_is_500(self):
        """Default http_status is 500."""
        err = AgentOSError("default status")
        assert err.http_status == 500

    def test_is_exception_subclass(self):
        """AgentOSError is a subclass of Exception."""
        err = AgentOSError("test")
        assert isinstance(err, Exception)

    def test_can_be_raised_and_caught(self):
        """AgentOSError can be raised and caught as Exception."""
        with pytest.raises(AgentOSError) as exc_info:
            raise AgentOSError(
                "boom",
                error_type=ErrorType.EXECUTION_ERROR,
                code=ErrorCode.EXECUTION_ERROR,
            )
        assert str(exc_info.value) == "boom"
        assert exc_info.value.error_type == ErrorType.EXECUTION_ERROR


# ═════════════════════════════════════════════════════════════════════════════
# RetryableError Tests
# ═════════════════════════════════════════════════════════════════════════════

class TestRetryableError:
    """Errors that can be retried."""

    def test_is_agentos_error_subclass(self):
        """RetryableError is a subclass of AgentOSError."""
        err = RetryableError("Temporary failure")
        assert isinstance(err, AgentOSError)

    def test_recoverable_is_always_true(self):
        """RetryableError always sets recoverable=True."""
        err = RetryableError(
            "Connection lost",
            error_type=ErrorType.TIMEOUT_ERROR,
            code=ErrorCode.TIMEOUT_ERROR,
        )
        assert err.recoverable is True

    def test_can_be_raised_and_caught(self):
        """RetryableError can be raised and caught."""
        with pytest.raises(RetryableError) as exc_info:
            raise RetryableError(
                "Rate limited",
                error_type=ErrorType.RATE_LIMIT_ERROR,
                code=ErrorCode.RATE_LIMIT_EXCEEDED,
            )
        assert exc_info.value.recoverable is True

    def test_retryable_error_with_context(self):
        """Can pass context to RetryableError."""
        err = RetryableError(
            "DNS resolution failed",
            error_type=ErrorType.EXECUTION_ERROR,
            code=ErrorCode.DEPENDENCY_UNAVAILABLE,
            context={"dns_server": "8.8.8.8", "attempt": 2},
        )
        assert err.context["dns_server"] == "8.8.8.8"
        assert err.context["attempt"] == 2


# ═════════════════════════════════════════════════════════════════════════════
# UnrecoverableError Tests
# ═════════════════════════════════════════════════════════════════════════════

class TestUnrecoverableError:
    """Errors that cannot be retried."""

    def test_is_agentos_error_subclass(self):
        """UnrecoverableError is a subclass of AgentOSError."""
        err = UnrecoverableError("Access permanently denied")
        assert isinstance(err, AgentOSError)

    def test_recoverable_is_always_false(self):
        """UnrecoverableError always sets recoverable=False."""
        err = UnrecoverableError(
            "Schema validation failed",
            error_type=ErrorType.VALIDATION_ERROR,
            code=ErrorCode.VALIDATION_ERROR,
        )
        assert err.recoverable is False

    def test_can_be_raised_and_caught(self):
        """UnrecoverableError can be raised and caught."""
        with pytest.raises(UnrecoverableError) as exc_info:
            raise UnrecoverableError(
                "Not authorized",
                error_type=ErrorType.AUTH_ERROR,
                code=ErrorCode.AUTH_UNAUTHORIZED,
            )
        assert exc_info.value.recoverable is False
        assert exc_info.value.code == ErrorCode.AUTH_UNAUTHORIZED

    def test_default_http_status_is_400(self):
        """UnrecoverableError defaults to http_status=400."""
        err = UnrecoverableError("Bad request")
        assert err.http_status == 400


# ═════════════════════════════════════════════════════════════════════════════
# Error Hierarchy Tests
# ═════════════════════════════════════════════════════════════════════════════

class TestErrorHierarchy:
    """Polymorphic catch behaviour."""

    def test_catch_retryable_as_agentos_error(self):
        """RetryableError can be caught as AgentOSError."""
        try:
            raise RetryableError(
                "timeout",
                error_type=ErrorType.TIMEOUT_ERROR,
                code=ErrorCode.TIMEOUT_ERROR,
            )
        except AgentOSError as e:
            assert e.recoverable is True
            assert isinstance(e, RetryableError)

    def test_distinguish_retryable_from_unrecoverable(self):
        """Can distinguish RetryableError from UnrecoverableError via recoverable flag."""
        errors = [
            RetryableError(
                "timeout err",
                error_type=ErrorType.TIMEOUT_ERROR,
                code=ErrorCode.TIMEOUT_ERROR,
            ),
            UnrecoverableError(
                "auth err",
                error_type=ErrorType.AUTH_ERROR,
                code=ErrorCode.AUTH_UNAUTHORIZED,
            ),
            RetryableError(
                "rate limit err",
                error_type=ErrorType.RATE_LIMIT_ERROR,
                code=ErrorCode.RATE_LIMIT_EXCEEDED,
            ),
        ]
        retryable = [e for e in errors if e.recoverable]
        unrecoverable = [e for e in errors if not e.recoverable]
        assert len(retryable) == 2
        assert len(unrecoverable) == 1
        assert isinstance(unrecoverable[0], UnrecoverableError)
