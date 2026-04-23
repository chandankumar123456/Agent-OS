# app/mcp/ Technical Documentation

## Purpose
Defines inter-agent message contracts and delivery infrastructure.

## Modules
- `message.py`: strongly typed MCP message payload/metadata envelope.
- `bus.py`: abstract bus + in-memory + Redis pub/sub implementations.
- `router.py`: receiver-channel registration and routing.
- `protocol.py`: facade for message creation, send, and history management.

## Runtime Use
- Collaboration mode emits MCP messages per step.
- Agent workers register inbox handlers with protocol router.

## Transport Notes
Default implementation uses in-memory bus; Redis bus is scaffolded for production extension.
