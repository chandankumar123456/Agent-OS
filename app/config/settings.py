from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    APP_NAME: str = "Agent-OS"
    VERSION: str = "0.1.0"
    
    DATABASE_URL: Optional[str] = None
    REDIS_URL: Optional[str] = None
    
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "3716"
    POSTGRES_DB: str = "agentos"
    
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-5.4-mini"
    
    MAX_STEPS_DEFAULT: int = 10
    TIMEOUT_DEFAULT: int = 300
    MAX_RETRIES: int = 3
    
    API_V1_PREFIX: str = "/api/v1"
    CORS_ORIGINS: str = "*"
    
    USE_CELERY: bool = False
    API_KEYS: Optional[str] = None
    RATE_LIMIT_PER_MINUTE: int = 60
    
    SECRET_KEY: str = "change-me-in-production-use-secure-random-key"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()