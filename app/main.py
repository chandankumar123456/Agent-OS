"""AgentOS FastAPI Web Server Entry Point

This module provides the HTTP API and WebSocket interface for AgentOS.
It is now a thin wrapper around the shared bootstrap module, adding
only FastAPI-specific components (routes, middleware, CORS, etc.).

For desktop-native mode, use `app.desktop_entry` instead.

Usage:
    # Development
    python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
    
    # Production
    python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from .config.settings import settings
from .api import api_router
from .api.routes.health import router as health_router
from .logs.logger import logger
from .middleware.auth import APIKeyMiddleware, get_api_keys
from .middleware.rate_limit import RateLimitMiddleware, get_rate_limit
from .middleware.request_logging import RequestLoggingMiddleware
from .middleware.validation import InputValidationMiddleware
from .orchestrator.errors import AgentOSError, ErrorCode
from .logs.metrics import metrics_collector

from fastapi.exceptions import RequestValidationError
from fastapi import HTTPException


# Import bootstrap for shared initialization
from .bootstrap import bootstrap, BootstrapContext, setup_signal_handlers


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan manager using shared bootstrap.
    
    This lifespan handler uses the shared bootstrap module for all
    initialization, keeping FastAPI-specific code minimal.
    """
    import sys
    sys.stdout.write("[LIFESPAN] Agent-OS starting up\n")
    sys.stdout.flush()
    logger.info("Agent-OS starting up")
    
    # Bootstrap all components via shared module
    ctx = await bootstrap()
    
    # Store context in app state for access in routes
    app.state.bootstrap_ctx = ctx
    app.state.runtime = ctx.runtime
    app.state.grpc_client = ctx.grpc_client
    
    # Setup signal handlers for graceful shutdown
    setup_signal_handlers(ctx)
    
    logger.info(f"Agent-OS startup complete. Initialized: {', '.join(ctx.initialized)}")
    
    yield
    
    # Shutdown is handled by bootstrap context
    logger.info("Agent-OS shutting down")


# Create FastAPI app with lifespan
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    description="MCP-Based Multi-Agent Operating System",
    docs_url=None,  # Disable docs
    redoc_url=None,  # Disable redoc
    openapi_url=None,  # Disable openapi
    lifespan=lifespan
)

# CORS: avoid wildcard + credentials combination (browser security anti-pattern)
_cors_origins = settings.CORS_ORIGINS.split(",") if settings.CORS_ORIGINS != "*" else ["*"]
_allow_credentials = False if _cors_origins == ["*"] else True

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(InputValidationMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(RateLimitMiddleware, requests_per_minute=get_rate_limit())

api_keys = get_api_keys()
if api_keys:
    app.add_middleware(APIKeyMiddleware, api_keys=api_keys)

app.include_router(api_router, prefix="/api/v1")
app.include_router(health_router)

# WebSocket endpoint
from .api.ws import websocket_endpoint
app.add_api_websocket_route("/ws/tasks/{task_id}", websocket_endpoint)


@app.get("/metrics", response_class=PlainTextResponse)
async def prometheus_metrics():
    """Prometheus metrics endpoint."""
    return metrics_collector.get_prometheus_format()


@app.exception_handler(AgentOSError)
async def agent_error_handler(_: Request, exc: AgentOSError):
    """Handle AgentOSError exceptions."""
    logger.log_error(exc)
    return JSONResponse(
        status_code=exc.http_status,
        content={
            "error": {
                "code": exc.code.value if hasattr(exc.code, "value") else str(exc.code),
                "message": exc.message,
                "context": exc.context
            }
        }
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException):
    """Handle HTTPException."""
    logger.log_error(exc)
    code_map = {
        401: ErrorCode.AUTH_UNAUTHORIZED.value,
        403: ErrorCode.AUTH_FORBIDDEN.value,
        404: ErrorCode.TASK_NOT_FOUND.value,
        422: ErrorCode.VALIDATION_ERROR.value,
        429: ErrorCode.RATE_LIMIT_EXCEEDED.value,
        503: ErrorCode.TASK_QUEUE_UNAVAILABLE.value,
    }
    code = code_map.get(exc.status_code, ErrorCode.UNKNOWN_ERROR.value)
    detail = exc.detail if isinstance(exc.detail, str) else "Error"
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": code,
                "message": detail,
                "context": {}
            }
        }
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError):
    """Handle request validation errors."""
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": ErrorCode.VALIDATION_ERROR.value,
                "message": "Validation error",
                "context": {"details": exc.errors()}
            }
        }
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(_: Request, exc: Exception):
    """Handle unhandled exceptions."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": ErrorCode.INTERNAL_ERROR.value,
                "message": "Internal server error",
                "context": {}
            }
        }
    )


@app.middleware("http")
async def metrics_middleware(request, call_next):
    """Collect HTTP metrics."""
    import time
    start_time = time.time()

    exc_to_reraise = None
    try:
        response = await call_next(request)
        status = str(response.status_code)
    except Exception as exc:
        status = "500"
        response = None
        exc_to_reraise = exc

    process_time = time.time() - start_time
    path = request.url.path
    method = request.method

    metrics_collector.inc_counter("http_requests_total", {"method": method, "path": path, "status": status})
    metrics_collector.observe_histogram("http_request_duration_seconds", process_time, {"method": method, "path": path})

    if int(status) >= 400:
        metrics_collector.inc_counter("http_errors_total", {"method": method, "path": path, "status": status})

    if exc_to_reraise is not None:
        raise exc_to_reraise
    return response


@app.get("/health")
async def health():
    """Basic health check endpoint."""
    return {"status": "healthy", "version": settings.VERSION}
