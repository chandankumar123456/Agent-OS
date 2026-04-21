from fastapi import APIRouter
from .routes import tasks, auth, tools, agents, config

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(tasks.router)
api_router.include_router(tools.router)
api_router.include_router(agents.router)
api_router.include_router(config.router)
