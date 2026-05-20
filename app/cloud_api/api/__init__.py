"""Cloud API routes - re-exports from app.api for cloud deployment.

This module provides the same API router as app.api but within the
cloud_api package namespace for proper relative imports.
"""
from app.api import api_router
from app.api.deps import get_orchestrator, get_current_user, OrchestratorDep, CurrentUserDep

__all__ = [
    "api_router",
    "get_orchestrator",
    "get_current_user",
    "OrchestratorDep",
    "CurrentUserDep",
]
