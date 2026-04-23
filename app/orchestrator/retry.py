import asyncio
from typing import Callable, Any, Optional, Dict, Type
from functools import wraps
from ..logs.logger import logger
from ..config.settings import settings
from ..orchestrator.errors import RetryableError, UnrecoverableError, AgentOSError


class RetryConfig:
    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        exponential_base: float = 2.0,
        retryable_exceptions: Optional[tuple] = None
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.retryable_exceptions = retryable_exceptions or (RetryableError, ConnectionError, TimeoutError)


def is_retryable(error: Exception, config: Optional[RetryConfig] = None) -> bool:
    if isinstance(error, UnrecoverableError):
        return False
    if isinstance(error, RetryableError):
        return True
    if config and config.retryable_exceptions:
        return isinstance(error, config.retryable_exceptions)
    return isinstance(error, (ConnectionError, TimeoutError, OSError))


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

            if not is_retryable(e, config):
                logger.error(f"Unrecoverable error, no retries: {e}")
                raise

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
                logger.error(f"All {config.max_retries} retries exhausted: {e}")

    raise last_error


def with_retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    retryable_exceptions: Optional[tuple] = None
):
    config = RetryConfig(
        max_retries=max_retries,
        base_delay=base_delay,
        retryable_exceptions=retryable_exceptions
    )

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await retry_with_backoff(func, config, *args, **kwargs)
        return wrapper
    return decorator
