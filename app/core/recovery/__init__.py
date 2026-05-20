"""Recovery subsystem re-exports.

Provides unified access to crash recovery from the desktop-native kernel.

Usage:
    from app.core.recovery import crash_recovery
    await crash_recovery.scan_and_resume(kernel)
"""
from __future__ import annotations

from ...desktop_native.crash_recovery import crash_recovery

__all__ = [
    "crash_recovery",
]
