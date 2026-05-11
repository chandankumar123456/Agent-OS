"""Test configuration with isolated database and async support."""
import os
import sys
from pathlib import Path

# Set test environment variables BEFORE any app imports
os.environ.setdefault("AGENTOS_ENV", "test")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "")
os.environ.setdefault("OPENAI_API_KEY", "test-key-placeholder")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-env-32chars!!")
os.environ.setdefault("RUNTIME_MODE", "http")
os.environ.setdefault("ENABLED_PROVIDERS", "openai")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


import pytest
from typing import AsyncGenerator


@pytest.fixture(scope="session")
def event_loop_policy():
    """Use default event loop policy for tests."""
    import asyncio
    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture(autouse=True)
def _test_env():
    """Ensure test environment variables are always set."""
    assert os.environ.get("DATABASE_URL") == "sqlite+aiosqlite:///:memory:"
    assert os.environ.get("SECRET_KEY", "").startswith("test-")
    yield
