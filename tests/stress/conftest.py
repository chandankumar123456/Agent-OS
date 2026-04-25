"""Fixtures for stress tests."""
from __future__ import annotations

import os

import httpx
import pytest

from app.auth.utils import create_access_token
from .runner import StressTestRunner


@pytest.fixture(scope="session")
def stress_test_token():
    """Generate a valid JWT for stress test authentication."""
    token = create_access_token({"sub": "stress-test-user", "role": "admin"})
    return token


@pytest.fixture(scope="session")
def server_available():
    """Check if the AgentOS server is running locally."""
    base_url = os.getenv("AGENTOS_STRESS_URL", "http://localhost:8000")
    try:
        resp = httpx.get(f"{base_url}/health", timeout=5.0)
        return resp.status_code == 200
    except Exception:
        return False


@pytest.fixture
def stress_runner(stress_test_token, server_available):
    """Provide a StressTestRunner pointing at the local test server.

    Skips the test if the server is not reachable or rejects our JWT.
    """
    if not server_available:
        pytest.skip("AgentOS server is not running (checked /health)")
    base_url = os.getenv("AGENTOS_STRESS_URL", "http://localhost:8000")
    # Verify token is accepted by the server before running stress scenarios
    try:
        resp = httpx.get(
            f"{base_url}/api/v1/tasks",
            headers={"Authorization": f"Bearer {stress_test_token}"},
            timeout=5.0,
        )
        if resp.status_code == 401:
            pytest.skip(
                "Server rejected stress-test JWT (401). "
                "Ensure the running server shares the same SECRET_KEY as the test environment."
            )
    except Exception as exc:
        pytest.skip(f"Could not verify auth with server: {exc}")
    runner = StressTestRunner(base_url=base_url, token=stress_test_token)
    return runner
