from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Dict, Any
from ...config.settings import settings
from ...api.deps import get_current_user
from ...memory.long_term import config_repo

router = APIRouter(prefix="/config", tags=["config"])


def _is_admin(user: object) -> bool:
    return getattr(user, "role", "user") == "admin"


class ConfigUpdate(BaseModel):
    key: str
    value: Any


class ConfigResponse(BaseModel):
    success: bool
    message: str


DEFAULT_CONFIG: Dict[str, Any] = {
    "MAX_STEPS_DEFAULT": settings.MAX_STEPS_DEFAULT,
    "TIMEOUT_DEFAULT": settings.TIMEOUT_DEFAULT,
    "MAX_RETRIES": settings.MAX_RETRIES,
    "OPENAI_MODEL": settings.OPENAI_MODEL,
    "USE_CELERY": settings.USE_CELERY,
}


def _apply_runtime_config(key: str, value: Any) -> None:
    setattr(settings, key, value)


@router.get("")
async def get_config(current_user: object = Depends(get_current_user)):
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Forbidden")
    config = await config_repo.get_all()
    if not config:
        for key, value in DEFAULT_CONFIG.items():
            await config_repo.upsert(key, value)
        config = await config_repo.get_all()
    return config


@router.get("/{key}")
async def get_config_value(key: str, current_user: object = Depends(get_current_user)):
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Forbidden")
    config = await config_repo.get_all()
    if key not in config:
        raise HTTPException(status_code=404, detail=f"Config key {key} not found")
    return {"key": key, "value": config[key]}


@router.post("", response_model=ConfigResponse)
async def update_config(config: ConfigUpdate, current_user: object = Depends(get_current_user)):
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Forbidden")
    if config.key not in DEFAULT_CONFIG:
        raise HTTPException(status_code=404, detail=f"Config key {config.key} not found")
    await config_repo.upsert(config.key, config.value)
    _apply_runtime_config(config.key, config.value)
    return ConfigResponse(success=True, message=f"Updated {config.key}")


@router.post("/reset", response_model=ConfigResponse)
async def reset_config(current_user: object = Depends(get_current_user)):
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Forbidden")
    await config_repo.reset(DEFAULT_CONFIG)
    for key, value in DEFAULT_CONFIG.items():
        _apply_runtime_config(key, value)
    return ConfigResponse(success=True, message="Config reset to defaults")
