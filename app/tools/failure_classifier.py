"""Tool failure classification for recovery behavior.

Classifies tool failures as retryable, fatal, or fallback-available
to drive correct recovery behavior.
"""
import asyncio
from enum import Enum
from typing import Any, Dict, List, Optional, Type

from pydantic import BaseModel, Field

from ..logs.logger import logger
from ..orchestrator.errors import AgentOSError, ErrorCode, ErrorType


class FailureType(str, Enum):
    """Types of tool failure classifications."""
    RETRYABLE = "retryable"
    FATAL = "fatal"
    FALLBACK_AVAILABLE = "fallback_available"
    TRANSIENT = "transient"
    PERMISSION_DENIED = "permission_denied"


class FailureClassification(BaseModel):
    """Classification result for a tool failure."""
    tool_name: str
    failure_type: FailureType
    retryable: bool
    fallback_tools: List[str] = Field(default_factory=list)
    max_retries: int = 0
    retry_delay_seconds: float = 1.0
    reason: str = ""
    suggested_action: Optional[str] = None


class ToolFailureClassifier:
    """Classifies tool failures to determine recovery strategy.

    Usage:
        classifier = ToolFailureClassifier()
        classification = classifier.classify_failure("shell__execute_command", TimeoutError())
        if classification.retryable:
            # Retry with backoff
            pass
    """

    # Error type to classification mapping
    RETRYABLE_EXCEPTIONS: List[Type[Exception]] = [
        asyncio.TimeoutError,
        ConnectionError,
        ConnectionRefusedError,
        ConnectionResetError,
        OSError,
        TimeoutError,
    ]

    FATAL_EXCEPTIONS: List[Type[Exception]] = [
        PermissionError,
        FileNotFoundError,
        NotADirectoryError,
        ValueError,
        TypeError,
    ]

    # Tool-specific fallback mappings
    TOOL_FALLBACKS: Dict[str, List[str]] = {
        "desktop_env__click_element": ["desktop_env__click_coordinates", "desktop_env__type_text"],
        "desktop_env__type_text": ["desktop_env__send_keys"],
        "browser_env__navigate": ["browser__http_request"],
        "browser_env__get_text": ["browser__scrape_page"],
        "filesystem__read_file": ["shell__execute_command"],
        "shell__execute_command": ["filesystem__write_file"],
    }

    def __init__(self, default_max_retries: int = 3):
        self.default_max_retries = default_max_retries

    def classify_failure(
        self,
        tool_name: str,
        error: Exception,
        context: Optional[Dict[str, Any]] = None,
    ) -> FailureClassification:
        """Classify a tool failure.

        Args:
            tool_name: Name of the tool that failed.
            error: The exception that occurred.
            context: Additional execution context.

        Returns:
            FailureClassification.
        """
        error_type = type(error)
        error_message = str(error).lower()
        context = context or {}

        # Check for permission-related errors
        if isinstance(error, PermissionError) or "permission" in error_message or "access denied" in error_message:
            return FailureClassification(
                tool_name=tool_name,
                failure_type=FailureType.PERMISSION_DENIED,
                retryable=False,
                fallback_tools=[],
                max_retries=0,
                reason=f"Permission denied executing {tool_name}: {error}",
                suggested_action="Check agent permissions or escalate to human approval",
            )

        # Check for known retryable exceptions
        for retryable_type in self.RETRYABLE_EXCEPTIONS:
            if isinstance(error, retryable_type):
                return self._retryable_classification(tool_name, error, context)

        # Check for known fatal exceptions
        for fatal_type in self.FATAL_EXCEPTIONS:
            if isinstance(error, fatal_type):
                return self._fatal_classification(tool_name, error, context)

        # Check for specific error message patterns
        if any(pattern in error_message for pattern in ["timeout", "timed out", "connection refused", "reset by peer", "temporarily unavailable"]):
            return self._retryable_classification(tool_name, error, context)

        if any(pattern in error_message for pattern in ["not found", "does not exist", "invalid", "cannot access", "no such file"]):
            return self._fatal_classification(tool_name, error, context)

        if any(pattern in error_message for pattern in ["rate limit", "too many requests", "quota exceeded"]):
            return FailureClassification(
                tool_name=tool_name,
                failure_type=FailureType.TRANSIENT,
                retryable=True,
                fallback_tools=self._get_fallbacks(tool_name),
                max_retries=5,
                retry_delay_seconds=5.0,
                reason=f"Rate limit or quota exceeded for {tool_name}: {error}",
                suggested_action="Wait and retry with exponential backoff",
            )

        # Default: treat unknown errors as retryable once, then fatal
        return FailureClassification(
            tool_name=tool_name,
            failure_type=FailureType.RETRYABLE,
            retryable=True,
            fallback_tools=self._get_fallbacks(tool_name),
            max_retries=1,
            retry_delay_seconds=2.0,
            reason=f"Unknown error type for {tool_name}: {error}",
            suggested_action="Retry once, then escalate if failure persists",
        )

    def _retryable_classification(
        self,
        tool_name: str,
        error: Exception,
        context: Dict[str, Any],
    ) -> FailureClassification:
        """Create a retryable classification.

        Args:
            tool_name: Tool name.
            error: The error.
            context: Context dict.

        Returns:
            FailureClassification.
        """
        retry_count = context.get("retry_count", 0)
        fallback_tools = self._get_fallbacks(tool_name)

        # If we've already retried several times, suggest fallback
        if retry_count >= self.default_max_retries - 1 and fallback_tools:
            return FailureClassification(
                tool_name=tool_name,
                failure_type=FailureType.FALLBACK_AVAILABLE,
                retryable=False,
                fallback_tools=fallback_tools,
                max_retries=retry_count,
                retry_delay_seconds=0,
                reason=f"Max retries exceeded for {tool_name}: {error}",
                suggested_action=f"Use fallback tool: {fallback_tools[0]}",
            )

        return FailureClassification(
            tool_name=tool_name,
            failure_type=FailureType.RETRYABLE,
            retryable=True,
            fallback_tools=fallback_tools,
            max_retries=self.default_max_retries,
            retry_delay_seconds=min(2 ** retry_count, 30.0),
            reason=f"Transient error in {tool_name}: {error}",
            suggested_action="Retry with exponential backoff",
        )

    def _fatal_classification(
        self,
        tool_name: str,
        error: Exception,
        context: Dict[str, Any],
    ) -> FailureClassification:
        """Create a fatal classification.

        Args:
            tool_name: Tool name.
            error: The error.
            context: Context dict.

        Returns:
            FailureClassification.
        """
        fallback_tools = self._get_fallbacks(tool_name)

        return FailureClassification(
            tool_name=tool_name,
            failure_type=FailureType.FATAL,
            retryable=False,
            fallback_tools=fallback_tools,
            max_retries=0,
            retry_delay_seconds=0,
            reason=f"Fatal error in {tool_name}: {error}",
            suggested_action=(
                f"Use fallback tool: {fallback_tools[0]}" if fallback_tools else "Escalate to human operator"
            ),
        )

    def _get_fallbacks(self, tool_name: str) -> List[str]:
        """Get fallback tools for a given tool.

        Args:
            tool_name: Tool name.

        Returns:
            List of fallback tool names.
        """
        return self.TOOL_FALLBACKS.get(tool_name, [])

    def add_fallback_mapping(self, tool_name: str, fallbacks: List[str]) -> None:
        """Add or update fallback tool mapping.

        Args:
            tool_name: Primary tool name.
            fallbacks: List of fallback tool names.
        """
        self.TOOL_FALLBACKS[tool_name] = fallbacks

    def should_retry(self, classification: FailureClassification, current_retry: int = 0) -> bool:
        """Determine if a retry should be attempted.

        Args:
            classification: Failure classification.
            current_retry: Current retry count.

        Returns:
            True if retry should be attempted.
        """
        if not classification.retryable:
            return False
        return current_retry < classification.max_retries

    def get_retry_delay(self, classification: FailureClassification, current_retry: int = 0) -> float:
        """Get the delay before next retry.

        Args:
            classification: Failure classification.
            current_retry: Current retry count.

        Returns:
            Delay in seconds.
        """
        base_delay = classification.retry_delay_seconds
        return min(base_delay * (2 ** current_retry), 60.0)


# Module-level singleton
tool_failure_classifier = ToolFailureClassifier()
