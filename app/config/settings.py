import os
from pydantic_settings import BaseSettings
from pydantic import field_validator, model_validator, ConfigDict
from typing import Optional


class Settings(BaseSettings):
    APP_NAME: str = "Agent-OS"
    VERSION: str = "0.3.0"

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

    # Runtime communication mode: "http" (FastAPI) or "grpc" (gRPC to supervisor)
    RUNTIME_MODE: str = "http"
    GRPC_HOST: str = "localhost"
    GRPC_PORT: int = 50051
    GRPC_CONNECTION_TIMEOUT: float = 5.0
    GRPC_KEEPALIVE_TIMEOUT: int = 60
    GRPC_MAX_MESSAGE_LENGTH_MB: int = 50

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
        # Check for default credentials in non-test/non-development environments
        env = os.environ.get("AGENTOS_ENV", "").lower()
        if self.POSTGRES_PASSWORD == "agentos" and env not in ("test", "development"):
            import warnings
            warnings.warn(
                "Using default PostgreSQL password. Set POSTGRES_PASSWORD to a secure value in production.",
                UserWarning,
            )
        # In test mode, skip strict validation to allow isolated unit tests
        if env == "test":
            return self
        if not self.DATABASE_URL:
            raise ValueError("DATABASE_URL is required")
        # Skip Redis check in gRPC mode (supervisor handles Redis)
        if self.RUNTIME_MODE.lower() != "grpc" and not self.REDIS_URL:
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

    model_config = ConfigDict(env_file=".env", case_sensitive=False)


_settings_instance: Optional[Settings] = None

def get_settings() -> Settings:
    """Get the global Settings instance (lazy-loaded).

    This function ensures Settings validation happens on FIRST ACCESS,
    not at module import time. This prevents the REDIS_URL validation
    race condition when RUNTIME_MODE is set after import but before use.

    In gRPC/desktop mode, set AGENTOS_RUNTIME_MODE=grpc (or RUNTIME_MODE=grpc)
    BEFORE calling get_settings() to bypass the REDIS_URL requirement.
    """
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = Settings()
    return _settings_instance


class _LazySettings:
    """Lazy proxy for Settings that delays validation until first attribute access.

    This allows imports like ``from app.config.settings import settings``
    to succeed even when environment variables haven't been set yet.
    Validation only runs when an actual setting is accessed.
    """

    def __getattr__(self, name: str):
        return getattr(get_settings(), name)

    def __setattr__(self, name: str, value):
        setattr(get_settings(), name, value)

    def __getitem__(self, key: str):
        return getattr(get_settings(), key)


# Module-level proxy that defers Settings() construction until first use.
# This solves the REDIS_URL validation race: as long as RUNTIME_MODE is set
# before any code reads a setting (not before the import), it will work.
settings: Settings = _LazySettings()  # type: ignore[assignment]
