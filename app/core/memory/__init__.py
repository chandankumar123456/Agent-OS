"""Memory subsystem re-exports.

Provides unified access to the memory hierarchy and in-memory fallbacks.

Usage:
    from app.core.memory import memory_hierarchy, InMemoryShortTermMemory
"""
from __future__ import annotations

from ...desktop_native.memory_hierarchy import memory_hierarchy
from ...memory.in_memory import InMemoryShortTermMemory

__all__ = [
    "memory_hierarchy",
    "InMemoryShortTermMemory",
]
