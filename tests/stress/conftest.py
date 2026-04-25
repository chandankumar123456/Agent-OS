"""Fixtures for stress tests."""
from __future__ import annotations

import pytest
from .runner import StressTestRunner


@pytest.fixture
async def stress_runner():
    """Provide a StressTestRunner pointing at the local test server.

    Override BASE_URL via env var AGENTOS_STRESS_URL if the server
    is running on a non-default port.
    """
    import os
    base_url = os.getenv("AGENTOS_STRESS_URL", "http://localhost:8000")
    runner = StressTestRunner(base_url=base_url)
    yield runner
