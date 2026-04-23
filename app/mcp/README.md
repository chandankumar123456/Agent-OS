# app/mcp/

MCP communication primitives for inter-agent messaging.

## Files

- `message.py`: typed message payload/metadata/envelope.
- `bus.py`: abstract bus + in-memory and Redis-backed implementations.
- `router.py`: channel registration and message routing to agent handlers.
- `protocol.py`: protocol facade, message creation, send/history APIs.

## Default Transport

`MemoryMCPBus` is default; Redis bus is scaffolded for production extensions.
