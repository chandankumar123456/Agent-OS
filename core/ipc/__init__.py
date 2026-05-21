"""core.ipc - Inter-process communication layer.

Provides gRPC server and schema for supervisor communication.
Supports:
- TCP/localhost gRPC (default)
- Unix domain sockets (POSIX)
- Named pipes / TCP fallback (Windows)
"""
