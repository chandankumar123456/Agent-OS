from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Dict, Any, Union
from ...config.settings import settings
from ...api.deps import get_current_user
from ...memory.long_term import config_repo
from ...orchestrator.errors import ErrorCode

router = APIRouter(prefix="/config", tags=["config"])


def _is_admin(user: object) -> bool:
    return getattr(user, "role", "user") == "admin"


class ConfigUpdate(BaseModel):
    key: str
    value: Union[int, float, bool, str, None] = Field(...)


class ConfigResponse(BaseModel):
    success: bool
    message: str


DEFAULT_CONFIG: Dict[str, Any] = {
    "MAX_STEPS_DEFAULT": settings.MAX_STEPS_DEFAULT,
    "TIMEOUT_DEFAULT": settings.TIMEOUT_DEFAULT,
    "MAX_RETRIES": settings.MAX_RETRIES,
    "OPENAI_MODEL": settings.OPENAI_MODEL,
    "USE_CELERY": settings.USE_CELERY,
    "RATE_LIMIT_PER_MINUTE": settings.RATE_LIMIT_PER_MINUTE,
    "MAX_ACTIVE_TASKS_PER_USER": settings.MAX_ACTIVE_TASKS_PER_USER,
    "MAX_TASK_EXECUTION_ATTEMPTS": settings.MAX_TASK_EXECUTION_ATTEMPTS,
}

VALID_CONFIG_TYPES = {
    "MAX_STEPS_DEFAULT": (int, 1, 100),
    "TIMEOUT_DEFAULT": (int, 1, 3600),
    "MAX_RETRIES": (int, 0, 10),
    "OPENAI_MODEL": (str, None, None),
    "USE_CELERY": (bool, None, None),
    "RATE_LIMIT_PER_MINUTE": (int, 1, None),
    "MAX_ACTIVE_TASKS_PER_USER": (int, 1, None),
    "MAX_TASK_EXECUTION_ATTEMPTS": (int, 1, 10),
}


def _validate_config_value(key: str, value: Any) -> None:
    if key not in VALID_CONFIG_TYPES:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": ErrorCode.CONFIG_INVALID.value,
                    "message": f"Unknown config key: {key}",
                    "context": {}
                }
            }
        )

    expected_type, min_val, max_val = VALID_CONFIG_TYPES[key]

    if not isinstance(value, expected_type):
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": ErrorCode.CONFIG_INVALID.value,
                    "message": f"Invalid type for {key}, expected {expected_type.__name__}",
                    "context": {"key": key, "expected_type": expected_type.__name__}
                }
            }
        )

    if min_val is not None and value < min_val:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": ErrorCode.CONFIG_INVALID.value,
                    "message": f"Value for {key} must be >= {min_val}",
                    "context": {"key": key, "min": min_val}
                }
            }
        )

    if max_val is not None and value > max_val:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": ErrorCode.CONFIG_INVALID.value,
                    "message": f"Value for {key} must be <= {max_val}",
                    "context": {"key": key, "max": max_val}
                }
            }
        )


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
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": ErrorCode.CONFIG_KEY_NOT_FOUND.value,
                    "message": f"Config key {key} not found",
                    "context": {"key": key}
                }
            }
        )
    return {"key": key, "value": config[key]}


@router.post("", response_model=ConfigResponse)
async def update_config(config: ConfigUpdate, current_user: object = Depends(get_current_user)):
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Forbidden")
    _validate_config_value(config.key, config.value)
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
