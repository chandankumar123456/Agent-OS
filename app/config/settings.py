import os
import secrets
from pydantic_settings import BaseSettings
from pydantic import field_validator, model_validator
from typing import Optional


class Settings(BaseSettings):
    APP_NAME: str = "Agent-OS"
    VERSION: str = "0.2.0"

    DATABASE_URL: Optional[str] = None
    REDIS_URL: Optional[str] = None

    POSTGRES_USER: str = "agentos"
    POSTGRES_PASSWORD: str = "agentos"
    POSTGRES_DB: str = "agentos"

    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4o"
    ANTHROPIC_API_KEY: Optional[str] = None
    GOOGLE_API_KEY: Optional[str] = None
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    ENABLED_PROVIDERS: str = "openai"
    EXA_API_KEY: Optional[str] = None

    MAX_STEPS_DEFAULT: int = 10
    TIMEOUT_DEFAULT: int = 300
    MAX_RETRIES: int = 3

    API_V1_PREFIX: str = "/api/v1"
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000,http://localhost:8000,http://localhost:4173"

    USE_CELERY: bool = True
    API_KEYS: Optional[str] = None
    RATE_LIMIT_PER_MINUTE: int = 60
    MAX_ACTIVE_TASKS_PER_USER: int = 5
    MAX_TASK_EXECUTION_ATTEMPTS: int = 3

    SECRET_KEY: str = ""
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    @field_validator("MAX_STEPS_DEFAULT")
    @classmethod
    def validate_max_steps(cls, v: int) -> int:
        if v < 1 or v > 100:
            raise ValueError("MAX_STEPS_DEFAULT must be between 1 and 100")
        return v

    @field_validator("TIMEOUT_DEFAULT")
    @classmethod
    def validate_timeout(cls, v: int) -> int:
        if v < 1 or v > 3600:
            raise ValueError("TIMEOUT_DEFAULT must be between 1 and 3600")
        return v

    @field_validator("MAX_RETRIES")
    @classmethod
    def validate_max_retries(cls, v: int) -> int:
        if v < 0 or v > 10:
            raise ValueError("MAX_RETRIES must be between 0 and 10")
        return v

    @field_validator("RATE_LIMIT_PER_MINUTE")
    @classmethod
    def validate_rate_limit(cls, v: int) -> int:
        if v < 1:
            raise ValueError("RATE_LIMIT_PER_MINUTE must be at least 1")
        return v

    @field_validator("MAX_ACTIVE_TASKS_PER_USER")
    @classmethod
    def validate_max_active_tasks(cls, v: int) -> int:
        if v < 1:
            raise ValueError("MAX_ACTIVE_TASKS_PER_USER must be at least 1")
        return v

    @field_validator("MAX_TASK_EXECUTION_ATTEMPTS")
    @classmethod
    def validate_max_attempts(cls, v: int) -> int:
        if v < 1 or v > 10:
            raise ValueError("MAX_TASK_EXECUTION_ATTEMPTS must be between 1 and 10")
        return v

    @model_validator(mode="after")
    def validate_required_urls(self) -> "Settings":
        if not self.DATABASE_URL:
            raise ValueError("DATABASE_URL is required")
        if not self.REDIS_URL:
            raise ValueError("REDIS_URL is required")
        enabled = [p.strip().lower() for p in self.ENABLED_PROVIDERS.split(",") if p.strip()]
        if "openai" in enabled and not self.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is required when OpenAI provider is enabled")
        if "anthropic" in enabled and not self.ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY is required when Anthropic provider is enabled")
        if "google" in enabled and not self.GOOGLE_API_KEY:
            raise ValueError("GOOGLE_API_KEY is required when Google provider is enabled")
        if not self.SECRET_KEY:
            raise ValueError(
                "SECRET_KEY is required. Set a persistent SECRET_KEY in your environment "
                "so that all processes (FastAPI, Celery workers, runtime) share the same key."
            )
        return self

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
