from typing import Annotated
from fastapi import Depends, HTTPException, Header, status
from ..orchestrator.core import orchestrator as _orchestrator_singleton
from ..auth.utils import verify_access_token
from ..memory.long_term import user_repo


def get_orchestrator():
    """Return the module-level orchestrator singleton.

    This ensures that AgentRuntime, WorkflowEngine, and RetryConfig
    are shared across all requests.
    """
    return _orchestrator_singleton


OrchestratorDep = Annotated[type(_orchestrator_singleton), Depends(get_orchestrator)]


async def get_current_user(
    authorization: str | None = Header(default=None),
):
    if authorization and authorization.startswith("Bearer "):
        payload = verify_access_token(authorization.removeprefix("Bearer ").strip())
        if payload and payload.get("sub"):
            user = await user_repo.get_by_id(str(payload["sub"]))
            if user and getattr(user, "is_active", True):
                return user

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unauthorized",
    )


CurrentUserDep = Annotated[object, Depends(get_current_user)]
