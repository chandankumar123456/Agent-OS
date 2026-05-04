"""Fixtures and marker registration for desktop benchmarks."""

from __future__ import annotations

import shutil
from typing import Callable

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers for desktop benchmarks."""
    config.addinivalue_line("markers", "win32: Windows-native desktop application benchmark (Notepad, Explorer)")
    config.addinivalue_line("markers", "uwp: UWP/Store application benchmark (Calculator)")
    config.addinivalue_line("markers", "canvas: Canvas/graphics application benchmark (Paint)")
    config.addinivalue_line("markers", "electron: Electron-based application benchmark (VS Code)")


@pytest.fixture
def skip_if_not_installed() -> Callable[[str], None]:
    """Return a callable that skips a test if the given executable is not found on PATH.

    Usage::

        def test_something(skip_if_not_installed):
            skip_if_not_installed("notepad.exe")
            ...
    """

    def _skip(executable: str) -> None:
        if shutil.which(executable) is None:
            pytest.skip(f"{executable!r} not found on PATH — skipping benchmark")

    return _skip


@pytest.fixture
def desktop_session_manager():
    """Placeholder fixture for future desktop session lifecycle management.

    In a future iteration this could provide:
    - A headless or real desktop session instance
    - Session-level setup/teardown hooks
    - Screenshot capture on failure
    """
    return None
