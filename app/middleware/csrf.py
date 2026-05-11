"""CSRF protection middleware for AgentOS API.

Provides token-based CSRF protection for state-changing requests.
Tokens are generated on GET requests (set as a cookie), stored in Redis
with 1-hour expiry, and validated on POST/PUT/PATCH/DELETE requests
by comparing the X-CSRF-Token header against the Redis-stored value.

Skip CSRF for:
- API key authenticated requests (machine-to-machine)
- Health check endpoints
- Auth endpoints (login/signup use their own validation)
"""
import secrets
from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from ..logs.logger import logger
from ..memory.short_term import redis_client


CSRF_TOKEN_HEADER = "X-CSRF-Token"
CSRF_COOKIE_NAME = "agentos_csrf"
CSRF_SKIP_PATHS = {"/health", "/api/v1/auth/login", "/api/v1/auth/signup"}
CSRF_TOKEN_EXPIRY = 3600  # 1 hour


def generate_csrf_token() -> str:
    """Generate a cryptographically secure CSRF token."""
    return secrets.token_urlsafe(32)


def _build_session_id(request: Request) -> str:
    """Build a stable session identifier from client IP + User-Agent."""
    if request.client:
        raw = request.client.host + request.headers.get("user-agent", "")
        return str(hash(raw))
    return "anon"


class CSRFMiddleware(BaseHTTPMiddleware):
    """Middleware that validates CSRF tokens on state-changing requests.

    Flow:
    - GET requests: generate a token, store in Redis, set as cookie.
    - POST/PUT/PATCH/DELETE: validate header matches cookie AND Redis-stored value.
    - API key auth is skipped (machine-to-machine).
    - If Redis is unavailable, fail CLOSED — reject the request.
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        method = request.method.upper()

        # Skip non-state-changing methods and whitelisted paths
        if method in ("GET", "HEAD", "OPTIONS") or path.rstrip("/") in {p.rstrip("/") for p in CSRF_SKIP_PATHS}:
            response = await call_next(request)
            # On GET requests, generate a fresh CSRF token and set it as a cookie
            if method == "GET":
                token = generate_csrf_token()
                session_id = _build_session_id(request)
                # Store token in Redis with 1-hour expiry
                if redis_client and redis_client.client:
                    try:
                        await redis_client.client.setex(
                            f"agentos:csrf:{session_id}:{token}",
                            CSRF_TOKEN_EXPIRY,
                            token,
                        )
                    except Exception:
                        logger.warning("Failed to store CSRF token in Redis; cookie will still be set")
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

        # --- CSRF validation for state-changing requests ---
        csrf_header = request.headers.get(CSRF_TOKEN_HEADER, "")
        csrf_cookie = request.cookies.get(CSRF_COOKIE_NAME, "")

        # Basic check: header and cookie must both be present and match
        if not csrf_header or not csrf_cookie or csrf_header != csrf_cookie:
            logger.warning(f"CSRF validation failed for {method} {path}: token mismatch or missing")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF validation failed",
            )

        # Verify the token exists in Redis (fail-closed if Redis is down)
        if not redis_client or not redis_client.client:
            logger.error("Redis client unavailable; rejecting state-changing request")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Security service unavailable",
            )

        try:
            session_id = _build_session_id(request)
            stored = await redis_client.client.get(f"agentos:csrf:{session_id}:{csrf_cookie}")
            # redis_client.client has decode_responses=True, so `stored` is a str or None
            if not stored or stored != csrf_cookie:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="CSRF token invalid or expired",
                )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Redis CSRF verification failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Security service unavailable",
            )

        return await call_next(request)
