from enum import Enum
from typing import Optional


class ErrorType(str, Enum):
    VALIDATION_ERROR = "validation_error"
    EXECUTION_ERROR = "execution_error"
    TIMEOUT_ERROR = "timeout_error"
    RATE_LIMIT_ERROR = "rate_limit_error"
    AUTH_ERROR = "auth_error"
    UNKNOWN_ERROR = "unknown_error"


class AgentOSError(Exception):
    def __init__(
        self,
        message: str,
        error_type: ErrorType = ErrorType.UNKNOWN_ERROR,
        recoverable: bool = True
    ):
        self.message = message
        self.error_type = error_type
        self.recoverable = recoverable
        super().__init__(message)


class RetryableError(AgentOSError):
    def __init__(self, message: str, error_type: ErrorType = ErrorType.UNKNOWN_ERROR):
        super().__init__(message, error_type, recoverable=True)


class UnrecoverableError(AgentOSError):
    def __init__(self, message: str, error_type: ErrorType = ErrorType.UNKNOWN_ERROR):
        super().__init__(message, error_type, recoverable=False)