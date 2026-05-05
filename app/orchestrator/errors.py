from enum import Enum
from typing import Optional, Dict, Any


class ErrorCode(str, Enum):
    # Auth
    AUTH_UNAUTHORIZED = "AUTH_UNAUTHORIZED"
    AUTH_FORBIDDEN = "AUTH_FORBIDDEN"
    AUTH_INVALID_TOKEN = "AUTH_INVALID_TOKEN"
    # Rate limiting
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    # Tasks
    TASK_NOT_FOUND = "TASK_NOT_FOUND"
    TASK_ACCESS_DENIED = "TASK_ACCESS_DENIED"
    TASK_QUEUE_UNAVAILABLE = "TASK_QUEUE_UNAVAILABLE"
    TASK_IDEMPOTENCY_CONFLICT = "TASK_IDEMPOTENCY_CONFLICT"
    # Validation
    VALIDATION_ERROR = "VALIDATION_ERROR"
    GUARDRAIL_VIOLATION = "GUARDRAIL_VIOLATION"
    # Execution
    EXECUTION_ERROR = "EXECUTION_ERROR"
    TIMEOUT_ERROR = "TIMEOUT_ERROR"
    LOOP_DETECTED = "LOOP_DETECTED"
    # Dependencies
    DEPENDENCY_UNAVAILABLE = "DEPENDENCY_UNAVAILABLE"
    # Tools
    TOOL_NOT_FOUND = "TOOL_NOT_FOUND"
    TOOL_EXECUTION_ERROR = "TOOL_EXECUTION_ERROR"
    # Agents
    AGENT_NOT_FOUND = "AGENT_NOT_FOUND"
    # Config
    CONFIG_INVALID = "CONFIG_INVALID"
    CONFIG_KEY_NOT_FOUND = "CONFIG_KEY_NOT_FOUND"
    # Recovery
    RECOVERY_EXHAUSTED = "RECOVERY_EXHAUSTED"
    ISOLATION_FAILURE = "ISOLATION_FAILURE"
    # Internal
    INTERNAL_ERROR = "INTERNAL_ERROR"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"


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
        recoverable: bool = True,
        code: Optional[ErrorCode] = None,
        context: Optional[Dict[str, Any]] = None,
        http_status: int = 500
    ):
        self.message = message
        self.error_type = error_type
        self.recoverable = recoverable
        self.code = code or ErrorCode.UNKNOWN_ERROR
        self.context = context or {}
        self.http_status = http_status
        super().__init__(message)


class RetryableError(AgentOSError):
    def __init__(
        self,
        message: str,
        error_type: ErrorType = ErrorType.UNKNOWN_ERROR,
        code: Optional[ErrorCode] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            error_type=error_type,
            recoverable=True,
            code=code,
            context=context,
            http_status=500
        )


class UnrecoverableError(AgentOSError):
    def __init__(
        self,
        message: str,
        error_type: ErrorType = ErrorType.UNKNOWN_ERROR,
        code: Optional[ErrorCode] = None,
        context: Optional[Dict[str, Any]] = None,
        http_status: int = 400
    ):
        super().__init__(
            message=message,
            error_type=error_type,
            recoverable=False,
            code=code,
            context=context,
            http_status=http_status
        )


class WorkflowPausedForApproval(Exception):
    def __init__(self, node_id: str, approval_config: Optional[Dict[str, Any]] = None):
        self.node_id = node_id
        self.approval_config = approval_config or {}
        super().__init__(f"Workflow paused for approval at node {node_id}")
