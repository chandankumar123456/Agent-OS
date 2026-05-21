import os
import hashlib
from datetime import datetime, timezone
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from jose.exceptions import ExpiredSignatureError
from sqlalchemy import select

from ..config.settings import settings
from ..logs.logger import logger
from ..auth.utils import decode_access_token
from ..memory.long_term import db
from ..memory.models import APIKeyModel


# HTTP status codes used by the pure auth logic.  Hard-coded ints so this
# module does not depend on the fastapi.status enum.
_HTTP_401 = 401

# Paths that bypass authentication entirely (login / signup).
_AUTH_BYPASS_PATHS = frozenset({"/api/v1/auth/login", "/api/v1/auth/signup"})


def _is_desktop_mode() -> bool:
    """Check if running in desktop-native gRPC mode."""
    mode = os.environ.get("AGENTOS_RUNTIME_MODE", os.environ.get("RUNTIME_MODE", "http"))
    return mode.lower() == "grpc"


class AuthDecision:
    """Result of an authentication attempt.

    The Starlette wrapper inspects the fields and either lets the request
    proceed (``allow=True``) or returns ``response`` to the client.  This is
    plain Python; nothing here imports FastAPI.
    """

    __slots__ = ("allow", "user", "auth_type", "api_key_permissions",
                 "auth_error", "status_code", "body", "headers")

    def __init__(
        self,
        *,
        allow: bool,
        user: Optional[dict] = None,
        auth_type: Optional[str] = None,
        api_key_permissions: Optional[list] = None,
        auth_error: Optional[str] = None,
        status_code: int = _HTTP_401,
        body: Optional[dict] = None,
        headers: Optional[dict] = None,
    ):
        self.allow = allow
        self.user = user
        self.auth_type = auth_type
        self.api_key_permissions = api_key_permissions or []
        self.auth_error = auth_error
        self.status_code = status_code
        self.body = body or {}
        self.headers = headers or {}


def _extract_bearer_token(authorization: str) -> Optional[str]:
    if authorization.startswith("Bearer "):
        return authorization.removeprefix("Bearer ").strip()
    return None


async def authenticate_request(
    *,
    path: str,
    authorization_header: str,
    api_key_header: str,
) -> AuthDecision:
    """Pure-ish authentication logic.

    Decides whether a request to ``path`` carrying the given headers should
    be allowed through.  Performs a DB lookup for API keys (the only
    side-effect) but does not depend on FastAPI types.

    - Returns ``AuthDecision(allow=True, ...)`` to accept the request.
    - Returns ``AuthDecision(allow=False, status_code=..., body=...)`` to
      reject it; the Starlette wrapper turns that into a JSONResponse.
    """
    # Desktop / local IPC mode bypasses HTTP auth entirely.
    if _is_desktop_mode():
        return AuthDecision(allow=True)

    # Login / signup are unauthenticated by design.
    if path in _AUTH_BYPASS_PATHS:
        return AuthDecision(allow=True)

    # Endpoints outside /api/v1 are public to this middleware.
    if not path.startswith("/api/v1"):
        return AuthDecision(allow=True)

    bearer_token = _extract_bearer_token(authorization_header or "")
    api_key = api_key_header or ""

    # 1. Bearer token path
    if bearer_token:
        try:
            payload = decode_access_token(bearer_token)
        except ExpiredSignatureError:
            return AuthDecision(
                allow=False,
                auth_error="token_expired",
                status_code=_HTTP_401,
                body={"error": "token_expired"},
                headers={"WWW-Authenticate": "Bearer"},
            )
        if payload:
            return AuthDecision(
                allow=True,
                user=payload,
                auth_type="bearer",
            )
        return AuthDecision(
            allow=False,
            status_code=_HTTP_401,
            body={"error": "invalid_token"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 2. API key path
    if api_key:
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        try:
            async with db.get_session() as session:
                result = await session.execute(
                    select(APIKeyModel).where(APIKeyModel.key_hash == key_hash)
                )
                key_obj = result.scalar_one_or_none()
                if key_obj:
                    key_obj.last_used_at = datetime.now(timezone.utc)
                    await session.commit()
                    return AuthDecision(
                        allow=True,
                        user={"sub": key_obj.user_id},
                        auth_type="api_key",
                        api_key_permissions=list(key_obj.permissions or []),
                    )
        except Exception as e:  # pragma: no cover - DB failure path
            logger.warning(f"API key validation error: {e}")

    return AuthDecision(
        allow=False,
        status_code=_HTTP_401,
        body={"error": "Unauthorized"},
    )


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Starlette wrapper that delegates to :func:`authenticate_request`."""

    def __init__(self, app, api_keys: Optional[list] = None):
        super().__init__(app)
        self.api_keys = api_keys or []

    async def dispatch(self, request: Request, call_next):
        decision = await authenticate_request(
            path=request.url.path,
            authorization_header=request.headers.get("authorization", ""),
            api_key_header=request.headers.get("x-api-key", ""),
        )

        if not decision.allow:
            if decision.auth_error:
                request.state.auth_error = decision.auth_error
            client_host = (
                getattr(request.client, "host", "unknown")
                if request.client
                else "unknown"
            )
            logger.warning(f"Invalid auth attempt from {client_host}")
            return JSONResponse(
                status_code=decision.status_code,
                content=decision.body,
                headers=decision.headers or None,
            )

        if decision.user is not None:
            request.state.user = decision.user
        if decision.auth_type is not None:
            request.state.auth_type = decision.auth_type
        if decision.auth_type == "api_key":
            request.state.api_key_permissions = decision.api_key_permissions

        return await call_next(request)


def get_api_keys() -> list:
    keys_str = getattr(settings, "API_KEYS", "")
    if keys_str:
        return [k.strip() for k in keys_str.split(",") if k.strip()]
    return []
