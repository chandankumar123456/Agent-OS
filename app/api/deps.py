from typing import Annotated, Any
from fastapi import Depends, HTTPException, Header, status, Request
from ..orchestrator.core import Orchestrator, orchestrator as _orchestrator_singleton
from ..auth.utils import decode_access_token
from jose.exceptions import ExpiredSignatureError
from ..memory.long_term import user_repo
from ..logs.logger import logger


def get_orchestrator() -> Orchestrator:
    """Return the module-level orchestrator singleton.

    This ensures that AgentRuntime, WorkflowEngine, and RetryConfig
    are shared across all requests.
    """
    return _orchestrator_singleton


OrchestratorDep = Annotated[Orchestrator, Depends(get_orchestrator)]


async def get_current_user(request: Request):
    # Check if middleware already authenticated and set user state
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
            logger.warning(f"Auth failed: user not found or inactive for sub={user_id}")
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
                logger.warning(f"Auth failed: user not found or inactive for sub={payload.get('sub')}")
            else:
                logger.warning("Auth failed: invalid token")
        else:
            logger.warning("Auth failed: missing or malformed Authorization header")

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unauthorized",
    )


CurrentUserDep = Annotated[Any, Depends(get_current_user)]
