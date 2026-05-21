from typing import Annotated, Any, Dict, Optional
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from jose.exceptions import ExpiredSignatureError

from ..auth.rbac import (
    AuthorizationError,
    Permission,
    Role,
    check_permission,
    check_role,
)
from ..auth.utils import decode_access_token
from ..guardrails.validator import InputValidator
from ..memory.long_term import user_repo
from ..orchestrator.core import Orchestrator, orchestrator as _orchestrator_singleton
from ..orchestrator.errors import ErrorCode, UnrecoverableError


def get_orchestrator() -> Orchestrator:
    """Return the module-level orchestrator singleton.

    This ensures that AgentRuntime, WorkflowEngine, and RetryConfig
    are shared across all requests.
    """
    return _orchestrator_singleton


OrchestratorDep = Annotated[Orchestrator, Depends(get_orchestrator)]


async def get_current_user(request: Request):
    # Fast path: middleware already authenticated this request
    user_state = getattr(request.state, "user", None)
    auth_error = getattr(request.state, "auth_error", None)

    if auth_error == "token_expired":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="token_expired",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user_state:
        user_id = str(user_state.get("sub", ""))
        if user_id:
            user = await user_repo.get_by_id(user_id)
            if user and getattr(user, "is_active", True):
                return user
    else:
        authorization = request.headers.get("authorization", "")
        if authorization and authorization.startswith("Bearer "):
            token = authorization.removeprefix("Bearer ").strip()
            try:
                payload = decode_access_token(token)
            except ExpiredSignatureError:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="token_expired",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            if payload and payload.get("sub"):
                user = await user_repo.get_by_id(str(payload["sub"]))
                if user and getattr(user, "is_active", True):
                    return user

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unauthorized",
    )


CurrentUserDep = Annotated[Any, Depends(get_current_user)]


# ---------------------------------------------------------------------------
# RBAC dependencies (FastAPI glue around app.auth.rbac).
# ---------------------------------------------------------------------------


def require_permission(permission: Permission):
    """FastAPI dependency that enforces ``permission`` on the current user."""

    async def _check_permission(
        request: Request,
        current_user: Any = Depends(get_current_user),
    ):
        try:
            check_permission(
                current_user,
                permission,
                auth_type=getattr(request.state, "auth_type", None),
                api_key_permissions=getattr(request.state, "api_key_permissions", []),
            )
        except AuthorizationError as e:
            raise HTTPException(
                status_code=e.status_code,
                detail=e.message,
            )
        return current_user

    return _check_permission


def require_role(role: Role):
    """FastAPI dependency that enforces a specific role on the current user."""

    async def _check_role(current_user: Any = Depends(get_current_user)):
        try:
            check_role(current_user, role)
        except AuthorizationError as e:
            raise HTTPException(
                status_code=e.status_code,
                detail=e.message,
            )
        return current_user

    return _check_role


# ---------------------------------------------------------------------------
# Guardrail / input-validation dependencies (FastAPI glue around InputValidator).
# ---------------------------------------------------------------------------


async def validate_task_request(
    query: str,
    mode: Optional[str] = "task",
    config: Optional[Dict] = None,
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
                    "context": e.context,
                }
            },
        )


def validate_task_id(task_id: str) -> UUID:
    """Validate and convert a ``task_id`` string to UUID.

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
                    "context": {"task_id": task_id},
                }
            },
        )


def validate_tool_execution_params(
    tool_name: str,
    arguments: Optional[Dict[str, Any]] = None,
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
                    "context": {},
                }
            },
        )

    # Validate tool name format: {server}__{tool}
    if "__" not in tool_name:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": ErrorCode.VALIDATION_ERROR.value,
                    "message": (
                        f"Invalid tool name format: {tool_name}. "
                        "Expected {server}__{tool}"
                    ),
                    "context": {"tool_name": tool_name},
                }
            },
        )

    return arguments or {}
