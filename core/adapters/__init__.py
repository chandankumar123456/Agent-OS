"""core.adapters - Optional protocol adapters for the AgentOS kernel.

Each adapter wraps the unified AgentKernel and exposes it over a
particular transport (HTTP/REST, WebSocket, etc.).  They are never
required for core operation; the kernel always communicates via gRPC IPC.
"""
