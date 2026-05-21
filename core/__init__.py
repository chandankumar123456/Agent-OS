"""core - Unified desktop-native agent runtime.

This package is the single Python runtime for AgentOS. It replaces the
former app/ package with a consolidated architecture:

- Single asyncio event loop
- SQLite as single source of truth (WAL mode)
- asyncio.PriorityQueue for task scheduling
- Direct LangGraph invocation (no Celery/Redis)
- gRPC IPC for supervisor communication
"""
