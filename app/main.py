from fastapi import FastAPI, Depends, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from .config.settings import settings
from .api import api_router
from .api.routes.health import router as health_router
from .logs.logger import logger
from .memory.long_term import db
from .memory.short_term import redis_client
from .migrations.runner import run_pending_migrations
from .middleware.auth import APIKeyMiddleware, get_api_keys
from .middleware.rate_limit import RateLimitMiddleware, get_rate_limit
from .api.deps import get_current_user
from .runtime.runtime import AgentRuntime
from .logs.metrics import metrics_collector
from fastapi.exceptions import RequestValidationError
from fastapi import HTTPException
from .orchestrator.errors import AgentOSError, ErrorCode


async def _check_dependencies() -> None:
    if not settings.DATABASE_URL:
        raise RuntimeError("DATABASE_URL is required but not set")
    if not settings.REDIS_URL:
        raise RuntimeError("REDIS_URL is required but not set")
    if not settings.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is required but not set")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Agent-OS starting up")

    await _check_dependencies()

    try:
        await db.connect()
        logger.info("Database connected successfully")
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        raise RuntimeError(f"Database connection failed: {e}") from e

    try:
        await run_pending_migrations()
        logger.info("Database migrations applied")
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise RuntimeError(f"Migration failed: {e}") from e

    try:
        await redis_client.connect()
        logger.info("Redis connected successfully")
    except Exception as e:
        logger.error(f"Redis connection failed: {e}")
        raise RuntimeError(f"Redis connection failed: {e}") from e

    try:
        runtime = AgentRuntime()
        await runtime.initialize()
        logger.info("AgentRuntime initialized")
    except Exception as e:
        logger.error(f"AgentRuntime initialization failed: {e}")
        raise RuntimeError(f"AgentRuntime initialization failed: {e}") from e

    yield

    try:
        await db.disconnect()
    except Exception as e:
        logger.warning(f"Database disconnect failed: {e}")

    try:
        await redis_client.disconnect()
    except Exception as e:
        logger.warning(f"Redis disconnect failed: {e}")

    logger.info("Agent-OS shutting down")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    description="MCP-Based Multi-Agent Operating System",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS.split(",") if settings.CORS_ORIGINS != "*" else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(RateLimitMiddleware, requests_per_minute=get_rate_limit())

api_keys = get_api_keys()
if api_keys:
    app.add_middleware(APIKeyMiddleware, api_keys=api_keys)

app.include_router(api_router, prefix="/api/v1")
app.include_router(health_router)


@app.exception_handler(AgentOSError)
async def agent_error_handler(_: Request, exc: AgentOSError):
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
    import time
    start_time = time.time()

    response = await call_next(request)

    process_time = time.time() - start_time
    path = request.url.path
    method = request.method
    status = str(response.status_code)

    metrics_collector.inc_counter("http_requests_total", {"method": method, "path": path, "status": status})
    metrics_collector.observe_histogram("http_request_duration_seconds", process_time, {"method": method, "path": path})

    if response.status_code >= 400:
        metrics_collector.inc_counter("http_errors_total", {"method": method, "path": path, "status": status})

    return response


@app.get("/health")
async def health():
    return {"status": "healthy", "version": settings.VERSION}
