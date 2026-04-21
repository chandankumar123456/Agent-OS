from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from .config.settings import settings
from .api import api_router
from .logs.logger import logger
from .memory.long_term import db
from .memory.short_term import redis_client
from .middleware.auth import APIKeyMiddleware, get_api_keys
from .middleware.rate_limit import RateLimitMiddleware, get_rate_limit


metrics_data = {
    "request_count": 0,
    "error_count": 0,
    "total_response_time": 0.0
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Agent-OS starting up")
    
    try:
        await db.connect()
    except Exception as e:
        logger.warning(f"Database connection failed: {e}")
    
    try:
        await redis_client.connect()
    except Exception as e:
        logger.warning(f"Redis connection failed: {e}")
    
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


@app.middleware("http")
async def metrics_middleware(request, call_next):
    import time
    start_time = time.time()
    
    response = await call_next(request)
    
    process_time = time.time() - start_time
    metrics_data["request_count"] += 1
    metrics_data["total_response_time"] += process_time
    
    if response.status_code >= 400:
        metrics_data["error_count"] += 1
    
    return response


@app.get("/health")
async def health():
    return {"status": "healthy", "version": settings.VERSION}


@app.get("/metrics")
async def get_metrics():
    avg_response = (
        metrics_data["total_response_time"] / metrics_data["request_count"]
        if metrics_data["request_count"] > 0 else 0
    )
    error_rate = (
        metrics_data["error_count"] / metrics_data["request_count"]
        if metrics_data["request_count"] > 0 else 0
    )
    
    return {
        "requests_total": metrics_data["request_count"],
        "errors_total": metrics_data["error_count"],
        "error_rate": error_rate,
        "avg_response_time": avg_response
    }