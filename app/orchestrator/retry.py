import asyncio
from typing import Callable, Any, Optional, Dict
from functools import wraps
from ..logs.logger import logger
from ..config.settings import settings


class RetryConfig:
    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        exponential_base: float = 2.0
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base


async def retry_with_backoff(
    func: Callable,
    config: Optional[RetryConfig] = None,
    *args,
    **kwargs
) -> Any:
    config = config or RetryConfig(max_retries=settings.MAX_RETRIES)
    
    last_error = None
    
    for attempt in range(config.max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            last_error = e
            
            if attempt < config.max_retries:
                delay = min(
                    config.base_delay * (config.exponential_base ** attempt),
                    config.max_delay
                )
                logger.warning(
                    f"Retry {attempt + 1}/{config.max_retries} "
                    f"after {delay}s delay: {e}"
                )
                await asyncio.sleep(delay)
            else:
                logger.error(f"All retries exhausted: {e}")
    
    raise last_error


def with_retry(
    max_retries: int = 3,
    base_delay: float = 1.0
):
    config = RetryConfig(max_retries=max_retries, base_delay=base_delay)
    
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await retry_with_backoff(func, config, *args, **kwargs)
        return wrapper
    return decorator