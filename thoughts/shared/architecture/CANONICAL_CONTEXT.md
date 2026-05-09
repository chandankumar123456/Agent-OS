# Canonical Context

## Purpose
Defines the currently approved architecture and active implementation direction. This file prevents architectural drift, outdated plan usage, and conflicting implementations.

---

## Current Approved Architecture

**Document:** `thoughts/shared/designs/2026-05-09-agentos-local-native-redesign.md`  
**Status:** ACTIVE  
**Authority:** CANONICAL  
**Approved By:** User  
**Date Approved:** 2026-05-09  

---

## Active Migration Phase

**Phase:** Phase 1 - Foundation  
**Status:** NOT STARTED  
**Next Phase:** Phase 2 - Desktop Native

---

## Current Authoritative Runtime Assumptions

1. **Supervisor-Runtime Pattern**: Go supervisor process manages Python LangGraph runtime subprocess
2. **Local-First Execution**: All core automation executes on local machine, no cloud dependency
3. **CLI is Primary Interface**: GUI is optional, CLI/TUI are authoritative
4. **Runtime Survives UI Closure**: UI is view/controller, runtime is model
5. **Deterministic First**: Action V1 (deterministic) preferred over LLM for known patterns
6. **Windows Primary Target**: All design decisions optimize for Windows first
7. **SQLite Primary Persistence**: PostgreSQL/Redis are optional/cache layers
8. **MCP Ecosystem Preserved**: Tool namespacing {server}__{tool} maintained

---

## Active Implementation Direction

**Short-term (Current Sprint):**
1. Establish persistent engineering memory system (this file structure)
2. Complete codebase audit for extraction boundaries
3. Design Go supervisor + SQLite persistence layer

**Medium-term (Phase 1):**
1. Go supervisor implementation
2. SQLite schema and persistence layer
3. CLI skeleton with cobra framework
4. IPC between supervisor and runtime
5. Basic runtime lifecycle management

**Long-term (Phases 2-5):**
1. Rust desktop automation engine
2. Tauri GUI
3. Go worker pool
4. Performance optimizations
5. Polish and distribution

---

## Approved Technologies

| Component | Technology | Status |
|-----------|------------|--------|
| Supervisor | Go | APPROVED |
| Runtime Core | Python (LangGraph) | APPROVED |
| Desktop Automation | Rust | APPROVED |
| CLI/TUI | Rust (crossterm/ratatui) | APPROVED |
| GUI | Tauri + React | APPROVED |
| Workers | Go | APPROVED |
| Persistence | SQLite | APPROVED |
| IPC | gRPC | APPROVED |
| Event Bus | NATS (optional) | APPROVED |

---

## Current Subsystem Focus

**Primary:** Documentation and memory system establishment  
**Secondary:** Codebase audit and extraction analysis  
**Tertiary:** Phase 1 detailed planning

---

## Superseded Plans/Documents

| Document | Status | Superseded By | Reason |
|----------|--------|---------------|--------|
| None | - | - | This is the initial architecture |

---

## Active Runtime Philosophy

**Local-Native Autonomous Agent Runtime:**
- AgentOS is not a web application
- AgentOS is not a cloud service
- AgentOS is a local-first runtime that executes on the user's machine
- The browser is never the executor
- Core automation is local-only
- Cloud integration is optional for AI inference, not required for execution

---

## Last Updated

**Date:** 2026-05-09  
**By:** Agent  
**Session:** Initial memory system establishment
