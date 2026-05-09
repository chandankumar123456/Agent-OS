# Architecture

## Canonical Source of Truth for System Design

This document defines the runtime philosophy, process topology, and architectural principles that govern AgentOS.

---

## Runtime Philosophy

### AgentOS is NOT a Web Application

**Traditional web apps:**
- Browser renders UI
- UI talks to backend API
- Backend executes logic
- State lives in database
- Browser closes = session ends

**AgentOS local-native model:**
- CLI/GUI renders UI
- UI talks to local supervisor
- Supervisor delegates to runtime
- Runtime executes automation
- State lives in SQLite (local)
- UI closes = runtime continues
- Browser is NEVER the executor

### Local-First Execution Principles

1. **Execute Where Data Lives**
   - Automation happens on the machine where the desktop exists
   - No network round-trip for mouse clicks
   - <5ms latency requirement for desktop actions

2. **Runtime is the Model**
   - UI is view/controller
   - Runtime owns all state
   - UI can close, runtime persists
   - Multiple UIs can attach/detach

3. **Deterministic Over Probabilistic**
   - Action V1 (deterministic) for known patterns
   - LLM only for novel situations
   - ~90% success rate target for automation

4. **Cloud is Optional**
   - Core automation works offline
   - AI inference can be local (Ollama) or remote
   - No cloud dependency for basic functionality

---

## Process Topology

### Single-Machine Process Model

```
┌─────────────────────────────────────────────────────────────────┐
│                         User Machine                             │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │
│  │   CLI/TUI    │  │  Tauri GUI   │  │   External   │        │
│  │   (Rust)     │  │   (React)    │  │   Clients    │        │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘        │
│         │                 │                 │                  │
│         └─────────────────┼─────────────────┘                  │
│                           │                                    │
│                    gRPC / IPC                               │
│                           │                                    │
│              ┌────────────┴────────────┐                    │
│              │     Go Supervisor         │                    │
│              │     (main process)        │                    │
│              │                           │                    │
│              │  • Process lifecycle     │                    │
│              │  • State management      │                    │
│              │  • IPC coordination      │                    │
│              │  • Persistence layer     │                    │
│              └────────────┬────────────┘                    │
│                           │                                    │
│              ┌────────────┴────────────┐                    │
│              │  Python LangGraph        │                    │
│              │  Runtime (subprocess)    │                    │
│              │                           │                    │
│              │  • Agent orchestration   │                    │
│              │  • LLM integration       │                    │
│              │  • Tool execution        │                    │
│              │  • MCP management        │                    │
│              └────────────┬────────────┘                    │
│                           │                                    │
│              ┌────────────┴────────────┐                    │
│              │  Rust Desktop Engine   │                    │
│              │  (subprocess/worker)   │                    │
│              │                           │                    │
│              │  • Screen capture       │                    │
│              │  • Input simulation     │                    │
│              │  • Native OS APIs       │                    │
│              │  • OCR (Tesseract)      │                    │
│              └─────────────────────────┘                    │
│                                                                  │
│  ┌─────────────────────────────────────────────┐              │
│  │  SQLite Database (single file)              │              │
│  │  • Agent state                              │              │
│  │  • Session history                          │              │
│  │  • Configuration                            │              │
│  │  • Logs (optional)                          │              │
│  └─────────────────────────────────────────────┘              │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Process Relationships

**Supervisor (Go) - The Root Process:**
- Owns the runtime lifecycle
- Manages subprocesses (Python runtime, Rust desktop)
- Owns SQLite database
- Handles UI attach/detach
- Provides gRPC API
- Runs as daemon/service on Windows

**Runtime (Python) - The Brain:**
- LangGraph agent orchestration
- LLM integration (OpenAI, Ollama, etc.)
- Tool execution coordination
- MCP client management
- State machine management
- Runs as child process of supervisor

**Desktop Engine (Rust) - The Hands:**
- Native OS automation
- Screen capture and OCR
- Input simulation (mouse, keyboard)
- Window management
- Runs as subprocess or worker pool

---

## Interface Hierarchy

**Primary Interface: CLI**
- Authoritative command interface
- Scriptable and automatable
- Works in any terminal
- Fast startup (<50ms)
- Zero GUI dependencies

**Secondary Interface: TUI**
- Rich terminal UI for operational work
- Real-time status visualization
- Session management
- Log tailing
- Still works in terminal

**Tertiary Interface: GUI (Optional)**
- Tauri-based desktop application
- Visual workflow editor
- Session browser
- Settings management
- Can be closed without stopping runtime

**Integration Interface: API/gRPC**
- For external tools and scripts
- Type-safe contracts
- Language-agnostic
- Future IDE plugin support

---

## Runtime Ownership

### State Ownership

| State Type | Owner | Storage | Persistence |
|------------|-------|---------|-------------|
| Agent runtime state | Python Runtime | Memory | Checkpoints → SQLite |
| Session history | Go Supervisor | SQLite | Permanent |
| Configuration | Go Supervisor | SQLite | Permanent |
| MCP server state | Python Runtime | Memory | Reconstructed on restart |
| Desktop context | Rust Engine | Memory | Ephemeral |
| Tool registry | Python Runtime | Memory + SQLite | Reconstructed |
| UI state | UI Client | Memory | Ephemeral |

### Execution Model

**Supervisor as Resource Manager:**
- Allocates subprocesses
- Manages memory limits
- Handles process crashes
- Implements backoff/restart
- Coordinates shutdown

**Runtime as Execution Engine:**
- Receives tasks from supervisor
- Executes agent graphs
- Calls tools (including desktop)
- Returns results
- Reports state changes

**Desktop Engine as Capability Provider:**
- Provides automation primitives
- Stateless (mostly)
- Responds to commands
- Returns screenshots/confirmations

---

## IPC Model

### Communication Patterns

**1. Request/Response (gRPC):**
- UI → Supervisor: Start session, get status
- Supervisor → Runtime: Execute task
- Runtime → Desktop: Take screenshot, click

**2. Events (gRPC Streaming or NATS):**
- Runtime → Supervisor: State changes, logs
- Supervisor → UI: Progress updates
- Desktop → Runtime: Automation results

**3. Shared State (SQLite):**
- Configuration
- Session history
- Persistent state

### Serialization

- **gRPC:** Protocol Buffers (binary, efficient)
- **Events:** JSON for human readability, Protobuf for performance
- **Database:** SQLite native types

### Cross-Language Boundaries

| Boundary | Protocol | Data Format |
|----------|----------|-------------|
| CLI ↔ Supervisor | gRPC | Protobuf |
| GUI ↔ Supervisor | gRPC (Tauri sidecar) | Protobuf |
| Supervisor ↔ Runtime | gRPC | Protobuf + JSON fallback |
| Runtime ↔ Desktop | gRPC or stdio | Protobuf |
| Runtime ↔ MCP | stdio / HTTP | JSON-RPC |

---

## State Ownership

### Agent State Machine

**States:**
- `idle`: Waiting for input
- `planning`: LLM is planning actions
- `executing`: Running tools/actions
- `waiting_for_human`: Blocked on human input
- `paused`: User paused session
- `error`: Recoverable error, waiting for resolution
- `failed`: Unrecoverable error, session ending

**State Transitions:**
- Triggered by: user input, tool completion, human response, error
- Logged to: SQLite session history
- Recovered from: SQLite checkpoint on restart

### Session Persistence

**Hot Sessions:**
- Active runtime process
- State in memory
- Can be paused/resumed
- UI can detach/reattach

**Cold Sessions:**
- Serialized to SQLite
- Runtime not running
- Can be resumed later
- Full state reconstruction

---

## Automation Architecture

### DesktopGoalLoop Pattern

```
┌─────────┐    ┌──────────┐    ┌────────┐    ┌──────────┐    ┌─────────┐
│ OBSERVE │ -> │  DECIDE  │ -> │  ACT   │ -> │ VERIFY   │ -> │ RECOVER │
└────┬────┘    └────┬─────┘    └───┬────┘    └────┬─────┘    └────┬────┘
     │              │              │              │              │
     └──────────────┴──────────────┴──────────────┴──────────────┘
                                    │
                                    v
                              ┌──────────┐
                              │  CHECK   │
                              │  GOAL?   │
                              └────┬─────┘
                                   │
                    ┌───────────────┼───────────────┐
                    │ No            │ Yes           │ Error
                    v               v               v
              ┌──────────┐    ┌──────────┐    ┌──────────┐
              │ Continue │    │   DONE   │    │ Recover  │
              │  Loop    │    │          │    │ & Retry  │
              └──────────┘    └──────────┘    └──────────┘
```

**Action Selection Strategy:**
1. **Action V1 (Deterministic):** Pattern matching on current state
   - Fast (<100ms)
   - High success rate for known patterns
   - Used for: common UI interactions, navigation
   
2. **Vision + Action V1:** When pattern unclear, use OCR
   - Moderate speed (<500ms)
   - Good for text-based verification
   - Used for: finding buttons, reading values

3. **LLM Planning:** Novel situations requiring reasoning
   - Slower (1-3s)
   - Flexible but less reliable
   - Used for: complex multi-step tasks, error recovery

### Capability Escalation

```
┌─────────────────────────────────────────────────────────────┐
│                    CAPABILITY ESCALATION                     │
├─────────────────────────────────────────────────────────────┤
│ Level │ Method          │ Speed    │ Reliability │ Use Case│
├───────┼─────────────────┼──────────┼─────────────┼─────────┤
│ 1     │ Deterministic   │ <100ms   │ 95%         │ Common  │
│ 2     │ Pattern Match   │ <200ms   │ 90%         │ Known   │
│ 3     │ Vision + OCR    │ <500ms   │ 85%         │ Text    │
│ 4     │ LLM Planning    │ 1-3s     │ 70%         │ Novel   │
│ 5     │ Human Fallback  │ Variable │ 100%        │ Blocked │
└───────┴─────────────────┴──────────┴─────────────┴─────────┘
```

---

## Orchestration Model

### LangGraph Runtime

**Graph Structure:**
- Nodes: agent steps, tool calls, human checkpoints
- Edges: conditional routing based on state
- State: shared context across nodes
- Persistence: checkpoint to SQLite

**Key Nodes:**
- `planner`: LLM plans next actions
- `tool_executor`: Executes selected tools
- `human_checkpoint`: Pauses for approval
- `verifier`: Validates action success
- `recoverer`: Handles failures

**Interruption Points:**
- Before dangerous actions (delete, modify system)
- On low-confidence decisions
- When human input required
- On errors requiring resolution

---

## Memory Hierarchy

### Short-Term (Session)
- **Location:** Python runtime memory
- **Content:** Current agent state, active tools, conversation context
- **Lifetime:** Session duration
- **Recovery:** From SQLite checkpoint

### Medium-Term (Recent History)
- **Location:** SQLite
- **Content:** Last N sessions, recent actions, common patterns
- **Lifetime:** Configurable retention (default 30 days)
- **Use:** Pattern matching, learning, context

### Long-Term (Knowledge)
- **Location:** SQLite + File system
- **Content:** Successful patterns, learned behaviors, configurations
- **Lifetime:** Permanent
- **Use:** Action V1 matching, skill library

---

## Recovery Semantics

### Automatic Recovery

**Retry with Backoff:**
- Transient failures: network, temporary UI changes
- Exponential backoff: 100ms, 200ms, 400ms, 800ms
- Max 3 retries, then escalate

**Alternative Strategies:**
- If click fails: try slightly different coordinates
- If text input fails: try different method (clipboard vs typing)
- If window not found: wait and retry

### Human-Assisted Recovery

**When Triggered:**
- Max retries exceeded
- Novel error condition
- Safety-critical action
- Low confidence (<70%)

**Modes:**
1. **Show and Ask:** Screenshot + "What should I do?"
2. **Teach:** "Show me how to do this"
3. **Override:** "Do this instead"

---

## Observability Architecture

### Logging

**Structured JSON Logs:**
- Timestamp (RFC3339)
- Level (DEBUG, INFO, WARN, ERROR)
- Component (supervisor, runtime, desktop, tool)
- Session ID
- Correlation ID
- Message
- Context (key-value pairs)

**Log Destinations:**
- Console (development)
- File (production)
- SQLite (structured queries)
- Optional: External aggregation

### Metrics

**Runtime Metrics:**
- Session duration
- Action success rate
- LLM call latency
- Tool execution time
- Error rates by component

**System Metrics:**
- Memory usage by process
- CPU utilization
- SQLite database size
- IPC latency

### Tracing

**Distributed Tracing:**
- Request ID propagation
- Span timing across components
- Cross-language trace context
- Optional: Jaeger/Tempo export

---

## Governance Model

### Configuration Layers

**Layer 1: Defaults (Code)**
- Sensible defaults embedded in binaries
- No external dependencies

**Layer 2: System Config (SQLite)**
- User preferences
- API keys (encrypted)
- MCP server list
- Automation preferences

**Layer 3: Session Config (Runtime)**
- Per-session overrides
- Temporary settings
- Experimental features

**Layer 4: Environment Variables**
- Override any setting
- CI/CD friendly
- Docker friendly

### Safety Controls

**Default Deny:**
- New actions require explicit approval
- Whitelist approach for file access
- Network access opt-in

**Capability Sandbox:**
- Desktop automation isolated from system
- MCP tools run in subprocess
- Resource limits enforced

---

## Runtime Lifecycle

### Startup Sequence

```
1. Supervisor starts
   ├─ Load configuration from SQLite
   ├─ Initialize logging
   ├─ Start gRPC server
   └─ Spawn Python runtime subprocess

2. Runtime initializes
   ├─ Load LangGraph
   ├─ Initialize MCP clients
   ├─ Register tools
   └─ Report ready to supervisor

3. Runtime Ready
   ├─ Supervisor marks runtime as active
   ├─ UI can connect
   └─ Sessions can start
```

### Shutdown Sequence

```
1. Shutdown requested (SIGTERM or UI command)
2. Supervisor stops accepting new sessions
3. Wait for active sessions to complete (timeout: 30s)
4. Signal runtime to checkpoint state
5. Runtime persists active sessions to SQLite
6. Runtime shuts down MCP clients
7. Runtime exits
8. Supervisor closes database
9. Supervisor exits
```

### Crash Recovery

**Runtime Crash:**
1. Supervisor detects subprocess exit
2. Check for checkpoint in SQLite
3. Attempt to resume sessions
4. If unrecoverable: mark sessions as failed
5. Restart runtime subprocess

**Supervisor Crash:**
1. Windows service manager detects failure
2. Restart supervisor (if configured)
3. Supervisor reloads sessions from SQLite
4. Runtime restarts automatically

---

## Last Updated

**Date:** 2026-05-09  
**By:** Agent  
**Version:** 1.0.0
