"""CSRF protection middleware for AgentOS API.

Provides token-based CSRF protection for state-changing requests.
Tokens are generated on GET requests (set as a cookie), stored in Redis
with 1-hour expiry, and validated on POST/PUT/PATCH/DELETE requests
by comparing the X-CSRF-Token header against the Redis-stored value.

Skip CSRF for:
- API key authenticated requests (machine-to-machine)
- Health check endpoints
- Auth endpoints (login/signup use their own validation)
- Desktop-native mode (local IPC, no browser)
"""
import os
import secrets
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from ..logs.logger import logger
from ..memory.short_term import redis_client


CSRF_TOKEN_HEADER = "X-CSRF-Token"
CSRF_COOKIE_NAME = "agentos_csrf"
CSRF_SKIP_PATHS = {"/health", "/api/v1/auth/login", "/api/v1/auth/signup"}
CSRF_TOKEN_EXPIRY = 3600  # 1 hour

# Hard-coded HTTP status codes so this module does not need fastapi.status.
_HTTP_403 = 403
_HTTP_503 = 503


class CSRFValidationError(Exception):
    """Raised by the pure CSRF logic when a request fails validation.

    The Starlette wrapper catches this and turns it into a JSONResponse.
    """

    def __init__(self, message: str, status_code: int = _HTTP_403):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _is_desktop_mode() -> bool:
    """Check if running in desktop-native gRPC mode."""
    mode = os.environ.get("AGENTOS_RUNTIME_MODE", os.environ.get("RUNTIME_MODE", "http"))
    return mode.lower() == "grpc"


def generate_csrf_token() -> str:
    """Generate a cryptographically secure CSRF token."""
    return secrets.token_urlsafe(32)


def build_session_id(client_host: Optional[str], user_agent: str) -> str:
    """Build a stable session identifier from client IP + User-Agent."""
    if client_host:
        return str(hash(client_host + (user_agent or "")))
    return "anon"


async def store_csrf_token(session_id: str, token: str) -> None:
    """Persist a freshly issued CSRF token in Redis (best effort)."""
    if redis_client and redis_client.client:
        try:
            await redis_client.client.setex(
                f"agentos:csrf:{session_id}:{token}",
                CSRF_TOKEN_EXPIRY,
                token,
            )
        except Exception:
            logger.warning("Failed to store CSRF token in Redis; cookie will still be set")


async def verify_csrf_token(
    *,
    method: str,
    path: str,
    csrf_header: str,
    csrf_cookie: str,
    session_id: str,
) -> None:
    """Pure CSRF check.

    Raises :class:`CSRFValidationError` on failure; returns ``None`` on
    success.  Knows nothing about FastAPI types.
    """
    if not csrf_header or not csrf_cookie or csrf_header != csrf_cookie:
        logger.warning(f"CSRF validation failed for {method} {path}: token mismatch or missing")
        raise CSRFValidationError("CSRF validation failed", status_code=_HTTP_403)

    if not redis_client or not redis_client.client:
        logger.error("Redis client unavailable; rejecting state-changing request")
        raise CSRFValidationError("Security service unavailable", status_code=_HTTP_503)

    try:
        stored = await redis_client.client.get(f"agentos:csrf:{session_id}:{csrf_cookie}")
        # redis_client.client has decode_responses=True, so stored is str|None.
        if not stored or stored != csrf_cookie:
            raise CSRFValidationError("CSRF token invalid or expired", status_code=_HTTP_403)
    except CSRFValidationError:
        raise
    except Exception as e:
        logger.error(f"Redis CSRF verification failed: {e}")
        raise CSRFValidationError("Security service unavailable", status_code=_HTTP_503)


def _csrf_failure_response(error: CSRFValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content={"detail": error.message},
    )


class CSRFMiddleware(BaseHTTPMiddleware):
    """Middleware that validates CSRF tokens on state-changing requests.

    Flow:
    - GET requests: generate a token, store in Redis, set as cookie.
    - POST/PUT/PATCH/DELETE: validate header matches cookie AND Redis-stored value.
    - API key auth is skipped (machine-to-machine).
    - If Redis is unavailable, fail CLOSED, reject the request.
    - Desktop mode: CSRF is skipped entirely (no browser, local IPC).
    """

    async def dispatch(self, request: Request, call_next):
        # In desktop mode, skip CSRF entirely (local IPC, not browser)
        if _is_desktop_mode():
            return await call_next(request)

        path = request.url.path
        method = request.method.upper()

        client_host = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent", "")
        session_id = build_session_id(client_host, user_agent)

        # Skip non-state-changing methods and whitelisted paths
        if (
            method in ("GET", "HEAD", "OPTIONS")
            or path.rstrip("/") in {p.rstrip("/") for p in CSRF_SKIP_PATHS}
        ):
            response = await call_next(request)
            # On GET requests, generate a fresh CSRF token and set it as a cookie
            if method == "GET":
                token = generate_csrf_token()
                await store_csrf_token(session_id, token)
                response.set_cookie(
                    key=CSRF_COOKIE_NAME,
                    value=token,
                    httponly=True,
                    samesite="lax",
                    max_age=CSRF_TOKEN_EXPIRY,
                )
            return response

        # Skip CSRF for API key authenticated requests (machine-to-machine)
        auth_type = getattr(request.state, "auth_type", None)
        if auth_type == "api_key":
            return await call_next(request)

        try:
            await verify_csrf_token(
                method=method,
                path=path,
                csrf_header=request.headers.get(CSRF_TOKEN_HEADER, ""),
                csrf_cookie=request.cookies.get(CSRF_COOKIE_NAME, ""),
                session_id=session_id,
            )
        except CSRFValidationError as e:
            return _csrf_failure_response(e)

        return await call_next(request)
