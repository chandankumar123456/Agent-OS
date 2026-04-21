from fastapi import APIRouter
from .routes import tasks, auth

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(tasks.router)