# AgentOS Local-Native Agent Runtime Research
## Systems Research: Executive Summary

**Research Date:** 2025-01-10
**Purpose:** Extract architectural patterns from 7 classes of agent systems for AgentOS's local-native agent runtime design

---

## Systems Analyzed

### 1. Claude Code (Anthropic)
**Type:** CLI-first agent coding tool  
**Key Pattern:** Session-based interactive agent loop with desktop integration

**Architecture Highlights:**
- **Multi-surface deployment**: Terminal, VS Code extension, Desktop app, Web, JetBrains
- **Agent Loop Pattern**: observe-decide-act-verify-recover with tool invocations
- **Tool System**: MCP (Model Context Protocol) standard for external integrations
- **Session Management**: 
  - Persistent sessions across surfaces via teleport (`claude --teleport`)
  - Session handoff between environments (`/desktop`, Remote Control, Dispatch)
- **State Management**:
  - CLAUDE.md files for project-level persistent instructions
  - Auto-memory for learned patterns across sessions
  - No explicit database persistence - state is implicit in session files and context
- **CLI Philosophy**: Unix composable - pipe input/output, scriptable automation
- **Sub-agent Pattern**: Lead agent + parallel sub-agents for task decomposition
- **Execution Locality**: Local file system access, local shell execution, optional cloud session routing
- **Safety Layer**: Human confirmation for sensitive operations, rate limiting

**Strengths for AgentOS to Learn:**
1. Seamless session migration across surfaces (terminal → web → desktop)
2. CLAUDE.md as declarative agent configuration
3. Tool results feed back into context for iterative refinement
4. `/commands` for structured workflows (`/schedule`, `/loop`, `/desktop`)

**Weaknesses to Avoid:**
1. Requires multiple surfaces for full experience (fragmentation)
2. Session persistence tied to Anthropic cloud (not truly local-first)
3. No clear isolation boundaries for multi-tenant scenarios

---

### 2. OpenAI Codex CLI
**Type:** Terminal-native coding agent
**Key Pattern:** Rust-based CLI focused on high-performance local execution

**Architecture Highlights:**
- **Technology Stack**: Rust (96.4%), Python (2.6%) - performance-first language choice
- **Distribution Model**: Native binaries + npm distribution (`npm i -g @openai/codex`)
- **Process Model**: Single executable, no daemon required
- **Cloud Integration**: Sign in with ChatGPT account, API key optional
- **Execution Locality**: Runs locally, connects to OpenAI APIs
- **Extension Points**: Codex App for desktop experience, IDE integrations

**Strengths for AgentOS to Learn:**
1. Single-binary distribution model (simpler than multi-process)
2. Performance-first language choice for CLI tools
3. Clear separation: CLI for terminal, App for desktop, IDE extensions for editors

**Weaknesses to Avoid:**
1. Cloud-dependent (requires OpenAI account/API)
2. Limited local intelligence - thin client pattern
3. No MCP/tool integration mentioned

---

### 3. Computer Use Systems (Anthropic)
**Type:** Desktop automation via API
**Key Pattern:** Screenshot → action → screenshot feedback loop

**Architecture Highlights:**
- **Agent Loop**: "Computer sees → decides → acts → observes → loops"
- **Tool Schema**: Standardized actions (screenshot, click, type, scroll, key)
- **Environment**: Sandboxed container/VM with virtual display (Xvfb)
- **Safety Layers**:
  - Virtual machine/container isolation
  - Prompt injection classifiers
  - Human confirmation for sensitive actions
- **Coordinate System**: Display-relative coordinates (requires resolution management)
- **Image Processing**: Screenshots downsampled to ~1.15MP max, coordinate scaling required
- **Tool Integration**: Can be augmented with bash and text editor tools

**Strengths for AgentOS to Learn:**
1. Sandboxed execution environment for safety
2. Standardized action vocabulary across applications
3. Image + text multimodal context for decisions
4. Iteration limits to prevent runaway execution

**Weaknesses to Avoid:**
1. High latency (screenshot round-trip)
2. Fragile coordinate-based interactions
3. Vision accuracy limitations
4. Requires significant compute for image processing

---

### 4. VSCode Extension Host
**Type:** Extension runtime with process isolation
**Key Pattern:** Extension host process separate from main editor

**Architecture Highlights:**
- **Process Model**: Multi-process architecture
  - Main process (Electron)
  - Renderer process (UI)
  - Extension host process (Node.js)
  - Language server processes (separate per language)
- **Extension Lifecycle**:
  - Activation events (on startup, on file open, on command)
  - Proposed API → Stable API progression
  - Versioned API surface (vscode.d.ts)
- **Communication**: Message passing between main and extension host
- **Isolation**: Extensions run in separate process, crash doesn't bring down editor
- **API Governance**: Weekly API calls, proposal stages, breaking change management

**Strengths for AgentOS to Learn:**
1. Process isolation for extensions/tools (crash safety)
2. Activation events reduce startup overhead
3. Versioned API with deprecation strategy
4. Weekly API review process for governance

**Weaknesses to Avoid:**
1. Extension host startup overhead
2. Message passing overhead for synchronous operations
3. Complex debugging across process boundaries

---

### 5. Temporal
**Type:** Durable execution platform
**Key Pattern:** "Workflow as code" with automatic persistence and replay

**Architecture Highlights:**
- **Core Concept**: Durable execution - workflows survive process crashes
- **Programming Model**: 
  - Workflows (deterministic, replayable)
  - Activities (side effects, idempotent)
  - Workers (execute workflows/activities)
- **State Management**:
  - Event sourcing - all state changes recorded
  - Automatic persistence to database
  - Replay-based recovery after crashes
- **Execution Guarantees**: Exactly-once execution, timeouts, retries
- **Architecture**: 
  - Temporal Server (orchestrates)
  - Worker processes (execute code)
  - Persistence layer (database)
- **Local Development**: `temporal dev server` for local workflows

**Strengths for AgentOS to Learn:**
1. Durable execution - agent state survives crashes
2. Event sourcing for complete audit trail
3. Deterministic replay for debugging
4. Separation of orchestration (server) from execution (workers)

**Weaknesses to Avoid:**
1. Complexity - requires understanding workflow constraints
2. Deterministic code requirements (no random, no time without marking)
3. Heavy infrastructure for simple use cases

---

### 6. Celery
**Type:** Distributed task queue
**Key Pattern:** Async task execution with broker and result backend

**Architecture Highlights:**
- **Components**:
  - Producers (create tasks)
  - Broker (message queue - Redis/RabbitMQ)
  - Workers (execute tasks)
  - Result backend (store results)
- **Execution Models**:
  - Direct: `task.delay()` or `task.apply_async()`
  - Canvas: chains, groups, chords for workflow composition
  - Periodic: Celery Beat for scheduling
- **Features**:
  - Task routing (queues)
  - Rate limiting
  - Retries with exponential backoff
  - Task states (PENDING, SUCCESS, FAILURE, etc.)
  - Monitoring (Flower)
- **Local Mode**: Can run with `CELERY_ALWAYS_EAGER` for synchronous execution

**Strengths for AgentOS to Learn:**
1. Flexible task routing and prioritization
2. Canvas primitives for workflow composition
3. Built-in retries and error handling
4. Monitoring and observability (Flower)

**Weaknesses to Avoid:**
1. Complexity with multiple moving parts (broker, workers, backend)
2. Visibility timeout issues with long-running tasks
3. Result backend can become bottleneck

---

## Cross-Cutting Patterns Analysis

### Runtime Model Comparison

| System | Runtime Model | Process Model | State Persistence |
|--------|--------------|---------------|-------------------|
| Claude Code | Interactive session | Single process | File-based (CLAUDE.md) + cloud |
| Codex CLI | Interactive CLI | Single binary | None (stateless) |
| Computer Use | Agent loop | Container/VM | None (ephemeral) |
| VSCode ExtHost | Event-driven | Multi-process | Extension-specific |
| Temporal | Durable workflows | Worker processes | Event-sourced database |
| Celery | Task queue | Worker pool | Result backend |

### Interface Hierarchy Patterns

1. **CLI → IDE → Web** (Claude Code, Codex): Progressive enhancement from terminal to rich UI
2. **Local → Remote** (Computer Use, Temporal): Local execution with optional cloud orchestration
3. **Single → Multi-Process** (VSCode): Scale from single process to isolated extensions

### Execution Locality Spectrum

```
Fully Local ←-----------------------→ Fully Cloud
├─ Codex (local binary, cloud API)
├─ Claude Code (local execution, cloud sessions)
├─ Computer Use (local VM, cloud model)
├─ Temporal (local workers, can be self-hosted)
└─ Celery (fully self-hosted)
```

### State Management Approaches

| Pattern | Examples | Best For |
|---------|----------|----------|
| Ephemeral | Codex, Computer Use | Stateless operations |
| File-based | Claude Code (CLAUDE.md) | Project-level configuration |
| Event-sourced | Temporal | Audit trails, replay |
| Database-backed | Temporal, Celery | Persistence, queries |
| Memory-only | VSCode extensions | Fast access, session-scoped |

### Tool/Plugin Systems

| System | Tool Model | Registration | Namespacing |
|--------|------------|--------------|-------------|
| Claude Code | MCP (external) | Config file | `{server}__{tool}` |
| VSCode | Extensions | Marketplace | Extension ID |
| Temporal | Activities | Code | Package-level |
| Celery | Tasks | Decorator | Module-level |

### IPC Patterns

1. **Stdio** (MCP): Simple, works across languages, no network required
2. **Message Passing** (VSCode): Structured, typed, extensible
3. **API Calls** (Claude Code, Codex): HTTP/gRPC to external services
4. **Message Queue** (Celery, Temporal): Async, durable, scalable

---

## Architectural Recommendations for AgentOS

### 1. Runtime Model: Hybrid Session-Based

**Recommendation:** Combine Temporal's durable execution with Claude Code's interactive session model.

```
┌─────────────────────────────────────────────────────────────┐
│                    AgentOS Runtime                          │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    │
│  │   Session   │    │   Session   │    │   Session   │    │
│  │   Manager   │    │   Manager   │    │   Manager   │    │
│  │   (Active)  │    │   (Active)  │    │  (Paused)   │    │
│  └──────┬──────┘    └──────┬──────┘    └──────┬──────┘    │
│         │                  │                  │            │
│         └──────────────────┴──────────────────┘            │
│                          │                                │
│              ┌───────────▼───────────┐                     │
│              │   Session Store       │                    │
│              │   (Redis/PostgreSQL)  │                    │
│              └───────────────────────┘                     │
└─────────────────────────────────────────────────────────────┘
```

**Key Features:**
- Sessions can be active (in memory) or persisted (on disk)
- Event-sourced session state for durability and replay
- Migration between local and remote execution contexts

### 2. Interface Hierarchy: Terminal → API → Web

**Recommendation:** Prioritize CLI/API surface, then add web UI as secondary interface.

```
Priority 1: CLI (claude --teleport pattern)
Priority 2: API (FastAPI endpoints)
Priority 3: Web (gradual enhancement)
Priority 4: IDE Extensions (VSCode, JetBrains)
```

### 3. Execution Locality: Local-First with Cloud Bridge

**Recommendation:** AgentOS should be fully functional locally, with optional cloud model bridging.

```
Local Execution Stack:
├── Local LLM support (ollama, llama.cpp)
├── Local tool execution (MCP, shell, filesystem)
├── Local state (SQLite, file-based)
└── Optional: Cloud model API fallback
```

### 4. Process Model: VSCode-style Isolation

**Recommendation:** Multi-process with clear boundaries:

```
┌──────────────────────────────────────────────────────┐
│                   Main Process                       │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────┐ │
│  │  API Server  │  │  Orchestrator │  │  Web UI    │ │
│  └──────────────┘  └──────────────┘  └────────────┘ │
└──────────────────────────────────────────────────────┘
                        │
┌───────────────────────▼──────────────────────────────┐
│                 Agent Pool                         │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────┐│
│  │ Agent Worker │  │ Agent Worker │  │   ...      ││
│  │  (isolated)  │  │  (isolated)  │  │            ││
│  └──────────────┘  └──────────────┘  └────────────┘│
└──────────────────────────────────────────────────────┘
                        │
┌───────────────────────▼──────────────────────────────┐
│              Tool Runtime (MCP)                      │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────┐│
│  │ MCP Server    │  │ MCP Server   │  │   Shell    ││
│  │ (stdio)       │  │ (stdio)      │  │            ││
│  └──────────────┘  └──────────────┘  └────────────┘│
└──────────────────────────────────────────────────────┘
```

### 5. State Management: Hybrid Approach

**Recommendation:** Combine multiple patterns based on use case:

| Use Case | Pattern | Implementation |
|----------|---------|----------------|
| Session history | Event-sourced | Append-only log |
| Agent configuration | File-based | CLAUDE.md equivalent |
| Tool results | Ephemeral | In-memory with TTL |
| Workflow state | Database | SQLite/PostgreSQL |

### 6. Tool System: MCP-First with Extensions

**Recommendation:** Build on MCP standard, add AgentOS-specific enhancements.

```
Tool Registry Hierarchy:
├── MCP Tools (external, stdio)
│   └── {server}__{tool} namespacing
├── Built-in Tools (filesystem, shell, web)
├── AgentOS Extensions
│   ├── Desktop automation (computer-use pattern)
│   ├── IDE integrations
│   └── Custom toolchains
└── Dynamic Tool Loading (future)
```

### 7. IPC: Multi-Transport Support

**Recommendation:** Support multiple IPC patterns:

```
Communication Patterns:
├── In-process: Direct calls (within Agent worker)
├── Inter-process: Message queue (Redis)
├── External: Stdio (MCP)
├── Remote: HTTP/gRPC (API)
└── Streaming: WebSocket (real-time updates)
```

---

## Implementation Priorities

### Phase 1: Foundation (Current)
- [x] 8-layer stack architecture
- [x] Action V1 fast path
- [x] LangGraph full path
- [x] MCP tool integration (stdio)
- [x] Basic session management

### Phase 2: Local-Native Features
- [ ] Session persistence (Temporal-style event sourcing)
- [ ] Local LLM support (ollama integration)
- [ ] CLAUDE.md equivalent (project-level configuration)
- [ ] Session teleport/migration

### Phase 3: Advanced Runtime
- [ ] Agent Pool with isolation (VSCode Extension Host pattern)
- [ ] Durable execution (Temporal-style workflows)
- [ ] Advanced tool composition (Celery Canvas pattern)
- [ ] Desktop automation integration

### Phase 4: Distribution
- [ ] Desktop app (Electron/Tauri)
- [ ] IDE extensions (VSCode, JetBrains)
- [ ] Web interface (optional)
- [ ] Cloud bridge (for remote model access)

---

## Open Questions

1. **Model Routing**: How should AgentOS handle local vs cloud model selection? Automatic fallback? User-configured?

2. **Session Granularity**: Should sessions be per-conversation, per-project, or per-task? How do they nest?

3. **Tool Security**: What sandboxing is needed for MCP tools? Container-based? Permission-based?

4. **State Encryption**: Should persisted session data be encrypted? At-rest only or end-to-end?

5. **Multi-tenancy**: Can multiple users share an AgentOS instance? Or is it strictly single-user?

---

## Conclusion

The research reveals that successful agent systems combine:

1. **Clear separation of concerns** (orchestration vs execution vs tools)
2. **Flexible execution locality** (local-first with cloud bridging)
3. **Appropriate state persistence** (match pattern to use case)
4. **Strong isolation boundaries** (process-level for tools/extensions)
5. **Unix philosophy** (composable, scriptable, CLI-first)

AgentOS's existing 8-layer architecture is well-positioned to incorporate these patterns. The key next steps are:

1. Implement session persistence with event sourcing
2. Add local LLM support for true local-first operation
3. Build out the tool system with proper isolation
4. Create the project configuration system (CLAUDE.md equivalent)
5. Design the migration/teleport system for session continuity
