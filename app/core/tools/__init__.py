"""Tool system re-exports.

Provides unified access to the tool registry and local fallback
implementations through app.core.tools.

Usage:
    from app.core.tools import tool_registry
"""
from __future__ import annotations

from ...tools.registry import tool_registry
from ...tools import local_fallbacks

__all__ = [
    "tool_registry",
    "local_fallbacks",
]
