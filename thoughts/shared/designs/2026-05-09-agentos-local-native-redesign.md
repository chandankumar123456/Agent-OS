# Agent-OS Local-Native Runtime Redesign

**Date:** 2026-05-09  
**Status:** Architecture Design  
**Scope:** Complete architectural transformation from web-app to local-native autonomous agent runtime

---

## Executive Summary

Agent-OS is undergoing a fundamental transformation from a **cloud-centric SaaS** to a **local-native autonomous agent runtime platform**. This is not a UI migration or an Electron wrapper—this is a complete architectural reimagining focused on **runtime locality, process boundaries, and OS-level execution**.

**Primary Goal:** Desktop automation as the core capability, with the runtime as the product and UI as merely an interface.

---

## 1. Project Identity Reassessment

### What Agent-OS Fundamentally Is

Agent-OS is an **autonomous agent operating system** that executes AI-driven tasks on behalf of users through a closed-loop execution model: **observe → decide → act → verify → recover**.

Core identity statements:
- **Primary capability:** Desktop automation via accessibility APIs, UI tree inspection, and OS-level control
- **Execution model:** Local, persistent, stateful, and recoverable
- **Interface philosophy:** Runtime is the product; UI is an interface
- **Target environment:** Local machine with optional cloud AI assistance

### Why Current Assumptions Are Incomplete

The current architecture assumes:
1. **Browser-first:** Frontend is React, requiring a browser and HTTP server
2. **Cloud-centric:** Redis and PostgreSQL required for basic operation
3. **Request-response:** HTTP API patterns dominate execution flow
4. **SaaS-shaped:** Multi-tenancy, user accounts, JWT auth as primary model

These assumptions are **fundamentally incompatible** with desktop automation because:
- **Browser restrictions:** Cannot access OS-level APIs, window management, or desktop state
- **Network dependency:** Requires external services for core functionality
- **Ephemeral execution:** HTTP request lifecycle doesn't support long-running tasks
- **UI-coupled:** Runtime dies when browser closes

### Reframing as Local-Native Autonomous Agent Runtime

Agent-OS must be reframed as:
```
┌─────────────────────────────────────────────────────────────┐
│  Agent-OS: Local-Native Autonomous Agent Runtime           │
├─────────────────────────────────────────────────────────────┤
│  Core Philosophy:                                            │
│  - The runtime IS the product                                │
│  - UI is only an interface layer                             │
│  - Execution is local, persistent, and OS-aware             │
│  - Desktop automation is PRIMARY                            │
│  - Other features are supporting layers                     │
└─────────────────────────────────────────────────────────────┘
```

Key shifts:
- From "web app with agent features" → "agent runtime with optional web UI"
- From "cloud service" → "local service with optional cloud AI"
- From "frontend-driven" → "runtime-driven with frontend as viewer"
- From "HTTP request lifecycle" → "daemon process with persistent state"

---

## 2. Current Architecture Analysis

### What Currently Exists

Agent-OS v2 (current) has these runtime-native strengths:
- **LangGraph orchestration:** Graph-native execution with checkpoint/resume
- **Action V1 fast path:** Deterministic execution for simple tasks
- **DesktopGoalLoop:** observe-decide-act-verify-recover cycle
- **MCP tool ecosystem:** 7 stdio-based MCP servers, 60+ tools
- **Safety layer:** RBAC, guardrails, audit trails
- **RecoveryEngine:** Automatic failure recovery with strategies
- **ActionStabilizer:** Retry logic with stabilization
- **Checkpoint persistence:** PostgreSQL-based state recovery

### What Is Already Runtime-Native

These components are already designed for runtime operation:
- **LangGraph StateGraph:** Checkpoint-based, resumable, stateful
- **Desktop automation layer:** Uses Windows accessibility APIs (uiautomation)
- **MCP stdio transport:** Subprocess-based tool execution
- **ToolRegistry:** Singleton-based tool management
- **AgentPool:** Semaphore-based concurrency control
- **Recovery patterns:** Self-healing execution with retry

### What Is Still Web-App-Shaped

These components assume web-app patterns:
- **FastAPI API Gateway:** HTTP request/response model
- **JWT authentication:** Session-based auth for web requests
- **React frontend:** Browser-based UI requiring HTTP
- **WebSocket layer:** Real-time communication over network
- **Redis dependency:** Required for singleton coordination
- **PostgreSQL requirement:** Database for core operation
- **Docker deployment:** Container-based cloud deployment
- **CORS configuration:** Cross-origin web request handling

### Architectural Bottlenecks

1. **Redis singleton coordination:** Network dependency for local singleton
2. **HTTP request lifecycle:** Execution tied to HTTP connection
3. **Frontend coupling:** Runtime state exposed through React state
4. **Database bottleneck:** PostgreSQL required for checkpoints
5. **Python GIL:** Single-threaded asyncio for desktop automation
6. **MCP stdio overhead:** 50-100ms JSON-RPC overhead per tool call
7. **Browser sandbox:** Cannot access OS-level APIs

### Browser-Centric Assumptions Blocking Desktop Automation

| Assumption | Problem | Impact |
|------------|---------|--------|
| HTTP API as primary interface | Cannot stream desktop state | Desktop actions invisible to web UI |
| Browser-based UI | Cannot show desktop context | User loses situational awareness |
| Request-response model | Execution stops when HTTP timeout | Long tasks fail unpredictably |
| Frontend state management | Runtime state coupled to React | Runtime dies when browser closes |
| External database required | Offline execution impossible | Desktop automation requires network |
| Cloud deployment model | Cannot access local desktop | Desktop tools fail in cloud |

---

## 3. Core Architectural Problem

### Why Browser-First Architecture Is Insufficient

Desktop automation requires:
1. **OS-level access:** Window management, focus control, accessibility APIs
2. **Low latency:** <50ms for UI interactions
3. **Persistent execution:** Tasks survive UI closure
4. **Local state:** Screenshots, UI trees, process handles
5. **Offline operation:** No network dependency for core features

Browser architecture provides:
1. **Sandboxed access:** No OS-level APIs
2. **High latency:** HTTP roundtrips + JSON serialization
3. **Ephemeral execution:** Request lifecycle only
4. **Remote state:** DOM != desktop state
5. **Online requirement:** Web apps need servers

### Why Local Execution Matters for Desktop Automation

Desktop automation is **inherently local**:
- **Screenshots:** Must capture local display
- **UI interactions:** Must control local windows
- **Process management:** Must spawn local subprocesses
- **File access:** Must read local filesystem
- **Permissions:** Must have local user context

Moving these to the cloud creates:
- Security vulnerabilities (remote desktop access)
- Latency issues (network roundtrips)
- Reliability problems (network failures)
- Privacy concerns (desktop streamed to cloud)

### Why Execution Runtime Must Survive UI Lifecycle

Real desktop automation scenarios:
- **Long-running tasks:** Install software, process files, batch operations (hours)
- **Background monitoring:** Watch for events, trigger actions (days)
- **Scheduled execution:** Run at specific times (cron-like)
- **Failure recovery:** Retry after network outage (persistent)
- **Multi-step workflows:** Complex sequences (hundreds of steps)

If runtime dies when UI closes:
- User cannot close "dashboard" without killing automation
- Cannot run tasks overnight
- Cannot recover from UI crashes
- Cannot use automation while doing other work

### Why Desktop Automation Is a Systems Problem, Not Only an AI Problem

Desktop automation requires:
- **OS integration:** Accessibility APIs, window management, focus control
- **Process management:** Subprocess lifecycle, supervision, restart
- **State persistence:** Checkpoints, recovery, resume
- **Resource management:** Memory, CPU, handles, cleanup
- **Safety:** Sandboxing, capability escalation, human override
- **Observability:** Traces, metrics, replay, debugging
- **Reliability:** Deterministic execution, verification, recovery

These are **systems engineering** problems, not AI problems. The AI is just the decision-maker—the runtime is what makes automation reliable.

---

## 4. Target System Identity

### Agent-OS as Local-Native Autonomous Agent Runtime Platform

```
┌─────────────────────────────────────────────────────────────┐
│  AGENT-OS: Local-Native Autonomous Agent Runtime           │
├─────────────────────────────────────────────────────────────┤
│  Primary Capability: Desktop Automation                      │
│  Secondary Capabilities:                                     │
│    - Browser automation (via Playwright)                     │
│    - Shell execution                                         │
│    - File operations                                         │
│    - Workflow orchestration                                  │
│    - Multi-agent collaboration                               │
├─────────────────────────────────────────────────────────────┤
│  Execution Principles:                                       │
│    - Local-first, cloud-optional                             │
│    - Runtime survives UI                                     │
│    - Deterministic by default, autonomous when needed        │
│    - Verification before success                             │
│    - Recovery on failure                                     │
│    - Observable and replayable                               │
└─────────────────────────────────────────────────────────────┘
```

### Desktop Automation as Primary Capability

Desktop automation is the **core value proposition**:
- **Target:** Windows (primary), macOS, Linux (future)
- **Mechanism:** Accessibility APIs + Vision fallback
- **Scope:** UI interactions, window management, application control
- **Safety:** Capability escalation, human approval, emergency stop
- **Verification:** Screenshot comparison, UI state validation

Other capabilities (browser, shell, files) are **supporting features** that enable desktop automation workflows.

### Preserving Features as Supporting Layers

Existing features become layers, not identities:
- **LangGraph:** Orchestration layer, not the product
- **Multi-agent:** Collaboration mode, not default
- **Web UI:** Optional interface, not primary
- **MCP:** Tool protocol, not product identity
- **Recovery:** Safety layer, not feature

---

## 5. Runtime-First Architecture

### Runtime as Primary System

The **runtime is the product**. Everything else is optional.

```
┌─────────────────────────────────────────────────────────────┐
│  AGENT-OS RUNTIME CORE (The Product)                       │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Execution Engine                                    │   │
│  │  - Task scheduler                                    │   │
│  │  - Action V1 deterministic path                    │   │
│  │  - LangGraph orchestration path                      │   │
│  │  - Checkpoint/resume                               │   │
│  └─────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Desktop Automation Layer                            │   │
│  │  - Accessibility API integration                     │   │
│  │  - UI tree inspection                                  │   │
│  │  - Vision/OCR fallback                                 │   │
│  │  - Window management                                   │   │
│  │  - Focus control                                       │   │
│  └─────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Tool & MCP Layer                                    │   │
│  │  - Tool registry                                     │   │
│  │  - MCP server lifecycle                              │   │
│  │  - Sandboxed execution                               │   │
│  └─────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Safety & Governance                                 │   │
│  │  - Capability escalation                             │   │
│  │  - Human approval gates                              │   │
│  │  - Audit trails                                      │   │
│  │  - Emergency stop                                    │   │
│  └─────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Persistence Layer                                   │   │
│  │  - Local SQLite (primary)                            │   │
│  │  - Optional PostgreSQL                               │   │
│  │  - Optional Redis (distributed)                      │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### Daemon/Local Service Model

Agent-OS runs as a **local daemon/service**:

**Windows:**
- Windows Service with auto-start option
- Named pipes for IPC
- System tray icon for status

**macOS:**
- LaunchDaemon for background operation
- Unix sockets for IPC
- Menu bar icon for status

**Linux:**
- systemd service
- Unix sockets for IPC
- D-Bus integration (optional)

### Worker/Lifecycle/Orchestration Boundaries

```
┌─────────────────────────────────────────────────────────────┐
│  SUPERVISOR (Go) - Process Management                       │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐       │
│  │  Worker 1   │  │  Worker 2   │  │  Worker N   │       │
│  │  (Python)   │  │  (Python)   │  │  (Python)   │       │
│  │  LangGraph  │  │  LangGraph  │  │  LangGraph  │       │
│  └─────────────┘  └─────────────┘  └─────────────┘       │
│         ↑                ↑                ↑                │
│         └────────────────┴────────────────┘                │
│                      Runtime Core                          │
│                  (Python + LangGraph)                      │
└─────────────────────────────────────────────────────────────┘
```

**Supervisor responsibilities:**
- Start/stop/restart workers
- Health monitoring
- Crash recovery
- Resource limits
- Logging aggregation

**Worker responsibilities:**
- Execute LangGraph graphs
- Handle MCP tool calls
- Manage checkpoints
- Report status

### Where Components Live

| Component | Location | Rationale |
|-----------|----------|-----------|
| **Memory** | Runtime core + SQLite | Fast access, persistence |
| **Tools** | MCP subprocesses | Isolation, sandboxing |
| **Perception** | Desktop layer | Direct OS access |
| **Verification** | Runtime core | Before persistence |
| **Recovery** | Runtime core | Core responsibility |

### Execution Is Local and Persistent

Key guarantees:
1. **Local execution:** All desktop actions execute on local machine
2. **Persistent state:** Checkpoints survive process crashes
3. **Offline capable:** Core features work without network
4. **UI independent:** Runtime continues when UI closes
5. **Recoverable:** Failed tasks can resume from checkpoints

---

## 6. Interface Hierarchy

### CLI as Primary Interface

The **CLI is the primary interface** for Agent-OS:

```bash
# Task execution
agentos task create "Install Chrome" --watch
agentos task list --status running
agentos task get <id>
agentos task cancel <id>

# Desktop control
agentos desktop screenshot
agentos desktop click --x 100 --y 200
agentos desktop type "Hello World"
agentos desktop focus --window "Notepad"

# Configuration
agentos config set --key openai.api_key --value "..."
agentos config get --key openai.model

# Daemon management
agentos daemon start
agentos daemon stop
agentos daemon status
agentos daemon logs --follow
```

**CLI design principles:**
- Single binary, no dependencies
- Fast startup (<100ms)
- Rich output (colors, progress bars, spinners)
- Scriptable (JSON output mode)
- Consistent with POSIX conventions

### TUI as Operational Interface

The **TUI is for operational monitoring**:

```
┌─────────────────────────────────────────────────────────────┐
│  Agent-OS TUI - Operational Dashboard                       │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────┐ │
│  │  Task List (real-time)                               │ │
│  │  ▶ chrome_install    running    45%                  │ │
│  │  ○ file_cleanup      queued     --                 │ │
│  │  ✓ backup_docs       completed  2m ago             │ │
│  └─────────────────────────────────────────────────────┘ │
│  ┌─────────────────────────────────────────────────────┐ │
│  │  Live Logs                                          │ │
│  │  [14:32:01] Taking screenshot...                     │ │
│  │  [14:32:02] Click detected at (100, 200)            │ │
│  │  [14:32:03] Waiting for window...                    │ │
│  └─────────────────────────────────────────────────────┘ │
│  ┌─────────────────────────────────────────────────────┐ │
│  │  System Metrics                                     │ │
│  │  CPU: 12%  Memory: 256MB  Tasks: 3/10             │ │
│  └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

**TUI features:**
- Real-time task monitoring
- Live log streaming
- Resource metrics
- Quick actions (pause, cancel, approve)
- Keyboard-driven navigation

### GUI as Optional and Secondary

The **GUI is optional** for users who prefer graphical interfaces:

**Technology:** Tauri (Rust-based) + existing React
- Single binary (~5-15MB vs 300MB+ Electron)
- Native system tray, notifications
- Auto-updater built-in
- Access to OS APIs via Rust

**GUI use cases:**
- Workflow visualization (xyflow)
- Task history browsing
- Configuration UI
- Approval dialogs
- Desktop preview (screenshot viewer)

### APIs/WebSockets as Integration Surfaces

HTTP API and WebSocket remain for:
- **Third-party integrations:** External tools can trigger tasks
- **Monitoring:** Prometheus metrics endpoint
- **Programmatic access:** Scripts can call REST API
- **Future web UI:** Optional browser-based dashboard

**Design principle:** API is for integration, not primary usage.

---

## 7. Execution Model

### How Tasks Enter the Runtime

```
┌─────────┐    ┌─────────┐    ┌──────────────┐    ┌─────────────┐
│   CLI   │    │   TUI   │    │  API/HTTP    │    │ Scheduled   │
│ Command │    │  Action │    │   Request    │    │   Task      │
└────┬────┘    └────┬────┘    └──────┬───────┘    └──────┬──────┘
     │              │                │                   │
     └──────────────┴────────────────┴───────────────────┘
                         │
                    ┌────▼────┐
                    │ Runtime │
                    │  Core   │
                    └────┬────┘
                         │
              ┌──────────┼──────────┐
              ▼          ▼          ▼
        ┌─────────┐ ┌─────────┐ ┌─────────┐
        │ Action  │ │LangGraph│ │ Workflow│
        │   V1    │ │  Path   │ │ Engine  │
        └─────────┘ └─────────┘ └─────────┘
```

**Task entry methods:**
1. **CLI:** Direct command invocation
2. **TUI:** Interactive task creation
3. **API:** HTTP POST /api/v1/tasks
4. **Schedule:** Cron-like scheduler
5. **Trigger:** Event-driven (file change, window open)

### How Tools Are Executed Locally

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  Task       │────▶│  Tool        │────▶│  MCP        │
│  Execution  │     │  Registry    │     │  Server     │
└─────────────┘     └──────────────┘     └──────┬──────┘
                                                │
                    ┌───────────────────────────┼───────────┐
                    ▼                           ▼           ▼
              ┌─────────┐               ┌──────────┐ ┌─────────┐
              │Desktop  │               │ Filesystem│ │  Shell  │
              │  Layer   │               └──────────┘ └─────────┘
              └────┬────┘
                   │
        ┌──────────┼──────────┐
        ▼          ▼          ▼
   ┌─────────┐ ┌─────────┐ ┌─────────┐
   │  UIA    │ │ Vision  │ │ Window  │
   │  APIs   │ │  OCR    │ │ Manager │
   └─────────┘ └─────────┘ └─────────┘
```

**Tool execution flow:**
1. Task requests tool execution
2. ToolRegistry resolves tool → MCP server
3. MCP subprocess executes tool
4. For desktop tools: Native layer accesses OS APIs
5. Result returns through stack

### How State Is Persisted

**Checkpoint hierarchy:**

```
┌─────────────────────────────────────────────────────────────┐
│  CHECKPOINT LAYER                                           │
├─────────────────────────────────────────────────────────────┤
│  Level 1: Runtime Memory (ephemeral)                        │
│  - Current execution state                                  │
│  - Active AgentState TypedDict                             │
│  - In-flight tool calls                                     │
├─────────────────────────────────────────────────────────────┤
│  Level 2: LangGraph Checkpoints (SQLite)                    │
│  - Graph node state                                         │
│  - Resume points                                            │
│  - Config/metadata                                          │
├─────────────────────────────────────────────────────────────┤
│  Level 3: Task Persistence (SQLite)                         │
│  - Task records                                             │
│  - Execution history                                        │
│  - Audit trails                                             │
├─────────────────────────────────────────────────────────────┤
│  Level 4: Artifact Storage (filesystem)                     │
│  - Screenshots                                              │
│  - Downloads                                                │
│  - Logs                                                     │
└─────────────────────────────────────────────────────────────┘
```

### How Execution Continues Independently of UI

**Runtime lifecycle:**
```
┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐
│ System  │───▶│ Service │───▶│ Runtime │───▶│ Workers │
│  Boot   │    │  Start  │    │  Init   │    │  Spawn  │
└─────────┘    └─────────┘    └─────────┘    └─────────┘
     │              │              │              │
     ▼              ▼              ▼              ▼
  OS boots    Service runs    Runtime core   Task execution
  (once)      (daemon)        (singleton)    (continues)
```

**UI attachment/detachment:**
```
┌─────────┐         ┌─────────┐         ┌─────────┐
│  UI     │◄───────▶│ Runtime │◄───────▶│ Execution│
│ (CLI/   │  attach │  Core   │  drives │ (Workers)│
│  GUI)   │         │         │         │          │
└─────────┘         └─────────┘         └─────────┘
     │                    │                  │
     │ UI Closes          │                  │
     ▼                    ▼                  ▼
┌─────────┐         ┌─────────┐         ┌─────────┐
│Detached │         │Runtime  │         │Execution│
│  State  │         │Continues│         │Continues│
└─────────┘         └─────────┘         └─────────┘
```

### How IPC/Local Communication Works

**Inter-process communication:**

```
┌─────────────────────────────────────────────────────────────┐
│  IPC ARCHITECTURE                                           │
├─────────────────────────────────────────────────────────────┤
│  Supervisor ◄───────────────────────────────────────────────│
│     │                                                       │
│     │ Unix Sockets / Named Pipes                           │
│     ▼                                                       │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐       │
│  │Runtime  │  │ Worker  │  │ Worker  │  │ Desktop │       │
│  │  Core   │  │   1     │  │   2     │  │ Engine  │       │
│  │(Python) │  │(Python) │  │(Python) │  │ (Rust)  │       │
│  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘       │
│       │            │            │            │            │
│       │            │ gRPC       │            │ gRPC       │
│       │            └────────────┘            │            │
│       │                                      │            │
│       └──────────────────────────────────────┘            │
│                                                              │
│  Event Bus: In-process (runtime) + Unix sockets (cross)    │
└─────────────────────────────────────────────────────────────┘
```

**Communication methods:**
- **In-process:** asyncio queues, channels (fastest)
- **Cross-process:** Unix sockets (macOS/Linux), named pipes (Windows)
- **Services:** gRPC for typed, versioned APIs
- **Events:** Broadcast bus for observability

---

## 8. Desktop Automation Layer

### Accessibility APIs

**Platform abstraction:**

```rust
// Rust desktop engine (agentos-desktop)
pub trait AccessibilityEngine {
    fn get_window_list(&self) -> Vec<Window>;
    fn get_ui_tree(&self, window: &Window) -> UITree;
    fn find_element(&self, criteria: ElementCriteria) -> Option<Element>;
    fn click(&self, element: &Element) -> Result<(), AutomationError>;
    fn type_text(&self, text: &str) -> Result<(), AutomationError>;
    fn get_focused_element(&self) -> Option<Element>;
}

// Platform implementations
#[cfg(target_os = "windows")]
impl AccessibilityEngine for WindowsEngine {
    // windows-rs + UI Automation
}

#[cfg(target_os = "macos")]
impl AccessibilityEngine for MacOSEngine {
    // cocoa + AX API
}
```

**Benefits of native Rust implementation:**
- <5ms latency to accessibility APIs (vs 50-200ms Python)
- Native COM/Objective-C interop
- No Python GIL contention
- Type-safe API boundaries

### UI Tree Inspection

**Capabilities:**
- **Element discovery:** Find by name, role, ID, position
- **Property access:** Name, value, bounds, state, focus
- **Hierarchy traversal:** Parent, children, siblings
- **Pattern support:** Invoke, Toggle, Value, Selection

**Caching strategy:**
- Cache UI tree for 100ms (reduces API calls)
- Invalidate on window events
- Background refresh for stable elements

### Vision/OCR Fallback

**When accessibility fails:**
- Element not exposing accessibility info
- Custom UI frameworks
- Games or non-standard apps
- Coordinate-based interactions

**Vision pipeline:**
```
Screenshot ──▶ Preprocessing ──▶ OCR/Detection ──▶ Element Match ──▶ Action
```

**Platform-native OCR:**
- **Windows:** Windows.Media.Ocr
- **macOS:** Apple Vision framework
- **Linux:** Tesseract (fallback)

**Latency target:** <100ms for full-screen OCR

### Stabilization and Retries

**ActionStabilizer logic:**
```python
class ActionStabilizer:
    def execute_with_stabilization(self, action, max_retries=3):
        for attempt in range(max_retries):
            before = capture_desktop_state()
            action.execute()
            after = capture_desktop_state()
            
            if after.has_changed_from(before):
                return Success(result)
            
            sleep(stabilization_delay * (2 ** attempt))  # Exponential backoff
        
        return Failure("Action did not produce visible change")
```

### Window Management and Focus Control

**Window operations:**
- **Find:** By title, class, PID, position
- **Focus:** Activate, bring to front
- **Move/Resize:** Set bounds, maximize, minimize
- **Monitor:** Track creation, destruction, focus changes
- **Virtual Desktops:** Switch, create, destroy (Windows 10+, macOS Spaces)

**Focus management:**
- Restore focus after automation
- Handle focus stealing gracefully
- Detect focus loss mid-automation

### Verification and Recovery

**Verification strategies:**
```
Before Action:    After Action:
- Screenshot      - Screenshot comparison
- UI tree         - Expected element exists
- Window state    - State changed correctly
```

**Recovery strategies:**
| Failure | Recovery |
|---------|----------|
| Element not found | Retry with fuzzy matching → Vision fallback |
| Click missed | Retry with adjusted coordinates → Stabilization |
| Window closed | Reopen → Resume from checkpoint |
| Focus lost | Refocus → Retry action |
| App crashed | Restart → Replay from checkpoint |

### Safety and Permission Handling

**Permission model:**
- **Accessibility permission:** Required on macOS, optional on Windows
- **Screen recording:** Required for vision fallback
- **Admin elevation:** Required for some actions (optional escalation)

**Safety gates:**
- Block credential patterns in text input
- Confirm destructive actions (delete, format)
- Rate-limit interactions (prevent spam)
- Detect automation loops (infinite retry)

---

## 9. What Must Be Preserved

### LangGraph Orchestration

**Why preserve:**
- Graph-native execution is correct for complex tasks
- Checkpoint/resume is production-grade
- Human-in-the-loop support via interrupt
- No mature alternative in other languages

**Preservation strategy:**
- Keep LangGraph in Python
- Expose via gRPC to other languages
- Maintain checkpoint compatibility

### DesktopGoalLoop

**Core loop:** observe → decide → act → verify → recover

**Preservation:**
- Keep logic in Python (decision-making)
- Move low-level access to Rust (observation/action)
- Maintain same interface

### ActionStabilizer

**Purpose:** Ensure actions produce visible changes before proceeding

**Preservation:**
- Keep retry logic
- Enhance with faster native state capture
- Same API contract

### RecoveryEngine

**Purpose:** Automatic failure recovery with strategies

**Preservation:**
- Keep strategy selection logic
- Enhance with native crash detection
- Expand recovery options

### Verification Engine

**Purpose:** Validate execution before marking success

**Preservation:**
- Keep verification criteria
- Enhance with native screenshot comparison
- Same verification API

### MCP Architecture

**Current:** 7 stdio-based MCP servers, 60+ tools

**Preservation:**
- Keep MCP protocol
- Keep tool definitions
- Move some servers to native for performance
- Maintain {server}__{tool} naming

### Action V1 Fast Path

**Purpose:** Deterministic execution for simple tasks

**Preservation:**
- Keep capability classification
- Keep direct execution path
- Enhance with native desktop layer

### Checkpointing and Memory

**Purpose:** Resume execution after crashes

**Preservation:**
- Keep LangGraph checkpoint format
- Keep SQLite persistence
- Maintain backward compatibility

### Observability and Metrics

**Purpose:** Understand runtime behavior

**Preservation:**
- Keep metric definitions
- Keep trace format
- Enhance with native performance data

### Safety Gates

**Purpose:** Prevent dangerous actions

**Preservation:**
- Keep credential blocking
- Keep approval gates
- Keep audit trails

---

## 10. What Must Change

### Remove Browser-First Assumptions

**Changes:**
- React is optional, not required
- HTTP API is integration surface, not primary interface
- WebSocket is for real-time updates, not execution control
- Frontend state is view-only, not source of truth

### Remove Backend-Service Thinking

**Changes:**
- No request/response lifecycle for execution
- No session-based authentication for local runtime
- No multi-tenancy (single-user local)
- No horizontal scaling (single instance)

### Separate UI from Runtime

**Changes:**
- Runtime starts before any UI attaches
- UI can detach without stopping execution
- Multiple UIs can attach simultaneously
- Runtime owns all state

### Move OS-Level Execution into Local Runtime

**Changes:**
- Desktop automation runs in native layer, not Python
- Window management uses OS APIs directly
- Screenshots use native capture (GDI/Core Graphics)
- OCR uses platform-native engines

### Rework Architecture Assuming Browser Is Executor

**Changes:**
- Execution entry point is runtime, not HTTP handler
- State changes flow runtime → UI, not UI → runtime
- Long-running tasks are native, not HTTP requests
- Recovery happens in runtime, not frontend

---

## 11. Runtime Process Topology

### Daemon/Runtime Core

```
┌─────────────────────────────────────────────────────────────┐
│  AGENTOS SUPERVISOR (Go)                                   │
│  - System service / user service                          │
│  - Process manager                                          │
│  - Health monitoring                                        │
│  - Auto-restart                                               │
│  - Resource limits                                            │
└──────────────────────────┬──────────────────────────────────┘
                           │ manages
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  RUNTIME CORE (Python)                                      │
│  - LangGraph orchestration                                  │
│  - Task scheduling                                          │
│  - Checkpoint management                                    │
│  - Memory management                                        │
└──────────────────────────┬──────────────────────────────────┘
                           │ spawns
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  WORKER POOL (Python subprocesses)                          │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐        │
│  │ Worker 1│  │ Worker 2│  │ Worker 3│  │ Worker N│        │
│  │ (warm)  │  │ (warm)  │  │ (busy)  │  │ (idle)  │        │
│  └─────────┘  └─────────┘  └─────────┘  └─────────┘        │
└─────────────────────────────────────────────────────────────┘
```

### Subprocesses and Worker Model

**Worker lifecycle:**
1. **Warm pool:** Pre-spawned Python processes ready for tasks
2. **Task assignment:** Worker picks up task from queue
3. **Execution:** Worker runs LangGraph graph
4. **Result:** Worker reports completion/failure
5. **Return:** Worker returns to warm pool or respawns

**Isolation benefits:**
- Memory leak containment (worker respawn)
- Crash containment (one worker dies, others continue)
- CPU parallelism (true multi-core execution)
- GIL bypass (each worker has own GIL)

### MCP Server Lifecycle

```
┌─────────────┐
│  MCP Client │
│  Manager    │
└──────┬──────┘
       │ spawns on demand
       ▼
┌────────────────────────────────────────────┐
│  MCP Server Pool                           │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐     │
│  │Desktop  │ │ Filesys │ │  Shell  │     │
│  │ (Rust)  │ │ (Rust)  │ │ (Rust)  │     │
│  └─────────┘ └─────────┘ └─────────┘     │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐     │
│  │ Browser │ │ Document│ │  Code   │     │
│  │(Python) │ │(Python) │ │(Python) │     │
│  └─────────┘ └─────────┘ └─────────┘     │
└────────────────────────────────────────────┘
```

**Server types:**
- **Native (Rust):** Desktop, Filesystem (performance-critical)
- **Hybrid (Go):** Shell, Network (process management)
- **Python:** Browser, Document, Code (existing ecosystem)

### Supervision and Restart Behavior

**Supervisor policies:**
| Component | Failure Action | Restart Policy |
|-----------|---------------|----------------|
| Runtime Core | Log, alert | Always restart |
| Worker | Report to core | Restart after N failures |
| MCP Server | Mark unhealthy | Restart with backoff |
| Desktop Engine | Alert user | Manual intervention |

**Health checks:**
- Runtime: Heartbeat every 30s
- Workers: ACK within 5s of assignment
- MCP: Ping before each call

### Communication Between Runtime and Interfaces

**Attachment protocol:**
```
UI ──▶ Runtime: attach(session_id)
Runtime ──▶ UI: welcome(current_state)
UI ◄──▶ Runtime: bidirectional events
UI ──▶ Runtime: detach()
Runtime continues execution
```

**Event types:**
- Task created/updated/completed
- Log messages
- Metric updates
- Approval requests
- System alerts

---

## 12. Packaging and Distribution Strategy

### How the Runtime Is Installed

**Windows (.msi installer):**
```
AgentOS.msi
├── agentosd.exe (supervisor service)
├── agentos.exe (CLI)
├── agentos-tui.exe (TUI)
├── AgentOS.exe (GUI - optional)
├── runtime/ (Python embedded)
│   ├── python.exe
│   └── site-packages/
└── resources/
    └── config/
```

**macOS (.dmg installer):**
```
AgentOS.dmg
├── AgentOS.app (GUI)
├── agentosd (daemon)
├── agentos (CLI)
└── agentos-tui (TUI)
```

**Linux (.deb/.rpm/.AppImage):**
```
agentos.deb
├── /usr/bin/agentosd (daemon)
├── /usr/bin/agentos (CLI)
├── /usr/bin/agentos-tui (TUI)
├── /opt/agentos/runtime/
└── /etc/systemd/system/agentosd.service
```

### How the CLI Starts and Connects

**CLI startup:**
```bash
# CLI detects if daemon is running
agentos task create "..."
  ↓
Check: Is agentosd running?
  ├─ No: Start agentosd (if --auto-start)
  └─ Yes: Connect via socket
  ↓
Send command to runtime
  ↓
Stream results to terminal
```

**Connection methods:**
- **Windows:** Named pipe (`\\.\pipe\agentos`)
- **macOS/Linux:** Unix socket (`~/.agentos/runtime.sock`)
- **Fallback:** TCP localhost (if configured)

### How Optional GUI/TUI Layers Attach

**Attachment flow:**
```
GUI/TUI starts
  ↓
Connect to runtime socket
  ↓
Runtime sends current state snapshot
  ↓
Subscribe to events
  ↓
UI renders current state
  ↓
Live updates as events arrive
```

**Multi-UI support:**
- Multiple UIs can attach simultaneously
- Each UI gets its own event stream
- State changes broadcast to all UIs
- No UI is "primary"—runtime is primary

### How Updates and Startup Work

**Auto-updater (Tauri built-in):**
1. Check for updates on startup
2. Download in background
3. Notify user of available update
4. Apply on next restart

**Startup options:**
- **System service:** Start on boot (Windows Service, LaunchDaemon, systemd)
- **User service:** Start on login
- **Manual:** Start on first CLI command (if --auto-start enabled)

---

## 13. Migration Phases

### Phase 1: Foundation (2-3 months)

**Goal:** Create local-native runtime foundation

**Tasks:**
1. Create Go supervisor (`agentosd`)
2. Wrap existing Python runtime as subprocess
3. Replace Redis singleton with OS file locks/named mutexes
4. Add local SQLite as primary persistence
5. Make PostgreSQL/Redis optional (for distributed mode)
6. Create CLI skeleton (`agentos` command)

**Validation:**
- Runtime starts as service
- CLI can connect
- Tasks execute via new path
- Existing tests pass

### Phase 2: Desktop Native (3-4 months)

**Goal:** High-performance desktop automation

**Tasks:**
1. Build Rust desktop automation engine
2. Port MCP desktop server to Rust
3. gRPC bridge between Rust ↔ Python
4. Replace Python uiautomation with native layer
5. Add platform-native OCR
6. Optimize screenshot capture (<20ms target)

**Validation:**
- Desktop automation latency <50ms
- All existing desktop tests pass
- Vision fallback works

### Phase 3: Interfaces (2-3 months)

**Goal:** Complete interface hierarchy

**Tasks:**
1. Port React frontend to Tauri
2. Build Rust CLI with clap
3. Build Rust TUI with ratatui
4. System tray integration
5. Global hotkeys
6. Notifications

**Validation:**
- CLI works independently
- TUI shows real-time updates
- GUI renders correctly
- All can attach simultaneously

### Phase 4: Performance (2-3 months)

**Goal:** Optimize for local-native operation

**Tasks:**
1. Replace Python worker pool with Go
2. Replace Redis event bus with native IPC
3. Optimize vision layer with platform APIs
4. Reduce memory footprint
5. Improve startup time (<1s target)

**Validation:**
- Startup <1 second
- Memory <100MB base
- Desktop automation <50ms

### Phase 5: Polish (1-2 months)

**Goal:** Production-ready distribution

**Tasks:**
1. Create installers for all platforms
2. Auto-updater integration
3. Documentation
4. Migration guide for existing users
5. Performance benchmarks

---

## 14. Final Target Architecture

### Complete End-State Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    INTERFACE LAYER                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │    CLI      │  │     TUI     │  │  GUI (Tauri/React)  │ │
│  │  (Primary)  │  │(Operational)│  │    (Optional)       │ │
│  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘ │
│         │                │                     │            │
│         └────────────────┴─────────────────────┘            │
│                          │                                  │
│                    Unix Socket / Named Pipe                │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                    SUPERVISOR (Go)                          │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  - Service management                                   ││
│  │  - Process supervision                                  ││
│  │  - Health monitoring                                    ││
│  │  - Resource enforcement                                 ││
│  └─────────────────────────────────────────────────────────┘│
└──────────────────────────┬──────────────────────────────────┘
                           │ manages
┌──────────────────────────▼──────────────────────────────────┐
│                  RUNTIME CORE (Python)                      │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  EXECUTION ENGINE                                       ││
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐  ││
│  │  │ Action V1   │  │  LangGraph  │  │  Workflow       │  ││
│  │  │  Path       │  │   Engine    │  │  Engine         │  ││
│  │  └─────────────┘  └─────────────┘  └─────────────────┘  ││
│  └─────────────────────────────────────────────────────────┘│
│  ┌─────────────────────────────────────────────────────────┐│
│  │  COGNITIVE LAYER                                        ││
│  │  - Planning (PlannerAgent)                              ││
│  │  - Execution (ExecutorAgent)                            ││
│  │  - Verification (VerifierAgent)                         ││
│  │  - Recovery (RecoveryEngine)                            ││
│  └─────────────────────────────────────────────────────────┘│
│  ┌─────────────────────────────────────────────────────────┐│
│  │  ORCHESTRATION                                          ││
│  │  - Task scheduler                                       ││
│  │  - Worker pool manager                                  ││
│  │  - Checkpoint manager                                   ││
│  │  - State machine                                        ││
│  └─────────────────────────────────────────────────────────┘│
└──────────────────────────┬──────────────────────────────────┘
                           │ spawns
┌──────────────────────────▼──────────────────────────────────┐
│                  WORKER POOL (Python)                       │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐       │
│  │ Worker 1│  │ Worker 2│  │ Worker 3│  │ Worker N│       │
│  │ (task)  │  │ (task)  │  │ (task)  │  │ (idle)  │       │
│  └─────────┘  └─────────┘  └─────────┘  └─────────┘       │
└─────────────────────────────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                    MCP LAYER                                │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │  Desktop    │  │  Filesystem │  │  Shell              │ │
│  │  (Rust)     │  │  (Rust)     │  │  (Go)               │ │
│  └─────────────┘  └─────────────┘  └─────────────────────┘ │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │  Browser    │  │  Document   │  │  Code               │ │
│  │  (Python)   │  │  (Python)   │  │  (Python)           │ │
│  └─────────────┘  └─────────────┘  └─────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│              DESKTOP AUTOMATION (Rust)                      │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  - Accessibility API integration (windows-rs, cocoa)    ││
│  │  - UI tree inspection                                   ││
│  │  - Window management                                    ││
│  │  - Focus control                                        │
│  │  - Platform-native OCR                                  ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│              PERSISTENCE LAYER                              │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  PRIMARY: SQLite (local)                                ││
│  │  ├─ Checkpoints                                         ││
│  │  ├─ Task history                                        ││
│  │  ├─ Audit trails                                        ││
│  │  └─ Configuration                                       ││
│  └─────────────────────────────────────────────────────────┘│
│  ┌─────────────────────────────────────────────────────────┐│
│  │  OPTIONAL: PostgreSQL (distributed mode)                ││
│  │  OPTIONAL: Redis (caching, distributed)                 ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│              SAFETY & GOVERNANCE                            │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  - Capability escalation                                  ││
│  │  - Human approval gates                                 ││
│  │  - Emergency stop                                         ││
│  │  - Audit logging                                          ││
│  │  - Sandboxing                                             ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│              OBSERVABILITY                                  │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  - Metrics (Prometheus endpoint)                          ││
│  │  - Traces (execution flow)                                ││
│  │  - Replay (checkpoints + screenshots)                     ││
│  │  - Logs (structured JSON)                                 ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

### Runtime Hierarchy

```
┌─────────────────────────────────────────────────────────────┐
│  SYSTEM LEVEL                                               │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  OS Services / Systemd / LaunchDaemon / Windows Service ││
│  └─────────────────────────────────────────────────────────┘│
├─────────────────────────────────────────────────────────────┤
│  SUPERVISOR LEVEL (Go)                                      │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  Process management, health, restart                  ││
│  └─────────────────────────────────────────────────────────┘│
├─────────────────────────────────────────────────────────────┤
│  RUNTIME LEVEL (Python)                                     │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  LangGraph, orchestration, scheduling                 ││
│  └─────────────────────────────────────────────────────────┘│
├─────────────────────────────────────────────────────────────┤
│  WORKER LEVEL (Python)                                      │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  Task execution, MCP calls                             ││
│  └─────────────────────────────────────────────────────────┘│
├─────────────────────────────────────────────────────────────┤
│  MCP LEVEL (Mixed)                                          │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  Tool execution (Rust/Go/Python)                       ││
│  └─────────────────────────────────────────────────────────┘│
├─────────────────────────────────────────────────────────────┤
│  NATIVE LEVEL (Rust)                                        │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  Desktop automation, OS integration                    ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

### Interface Hierarchy

```
┌─────────────────────────────────────────────────────────────┐
│  PRIMARY: CLI                                               │
│  - Task creation, management                                │
│  - Configuration                                            │
│  - Daemon control                                             │
│  - Scriptable, composable                                     │
├─────────────────────────────────────────────────────────────┤
│  OPERATIONAL: TUI                                           │
│  - Real-time monitoring                                     │
│  - Live logs                                                │
│  - Quick actions                                            │
│  - Keyboard-driven                                          │
├─────────────────────────────────────────────────────────────┤
│  OPTIONAL: GUI (Tauri)                                      │
│  - Workflow visualization                                   │
│  - Task history                                             │
│  - Configuration UI                                         │
│  - Approval dialogs                                         │
├─────────────────────────────────────────────────────────────┤
│  INTEGRATION: API/WebSocket                                 │
│  - Third-party integrations                                 │
│  - Monitoring endpoints                                     │
│  - Programmatic access                                      │
└─────────────────────────────────────────────────────────────┘
```

### Automation Ownership

**Desktop automation is owned by:**
1. **Rust Desktop Engine** - Low-level OS access
2. **DesktopGoalLoop** - High-level goal achievement
3. **ActionStabilizer** - Reliability layer
4. **Verification Engine** - Success validation
5. **Recovery Engine** - Failure handling

### Persistence, Recovery, Safety, Observability

**Ownership matrix:**

| Capability | Owner | Technology |
|------------|-------|------------|
| **Persistence** | Runtime Core | SQLite (local) |
| **Checkpoints** | LangGraph | SQLite via checkpointer |
| **Recovery** | RecoveryEngine | Python + strategies |
| **Safety** | SafetyGate | Python + Rust (critical paths) |
| **Observability** | MetricsCollector | Prometheus + tracing |
| **Replay** | CheckpointManager | SQLite + screenshots |

---

## 15. Validation Criteria

### Runtime Survives UI Closure

**Test:**
1. Start runtime
2. Start UI (CLI/TUI/GUI)
3. Create long-running task
4. Close UI
5. Verify task continues
6. Reopen UI
7. Verify task progress shown

**Pass criteria:** Task completes successfully

### Desktop Automation Works Locally

**Test:**
1. Take screenshot
2. Click at coordinates
3. Type text
4. Get window list
5. Find element by name
6. Verify action results

**Pass criteria:** All operations <50ms latency, 100% reliability

### MCP Tools Execute Locally

**Test:**
1. Execute filesystem__read_file
2. Execute shell__execute_command
3. Execute desktop__screenshot
4. Verify no network calls
5. Verify <100ms execution time

**Pass criteria:** Local execution, fast response

### Recovery Works on Failures

**Test:**
1. Start task
2. Trigger failure (close target window)
3. Verify recovery strategy selected
4. Verify task resumes

**Pass criteria:** Automatic recovery, no manual intervention

### Verification Happens Before Success

**Test:**
1. Execute desktop action
2. Verify screenshot comparison
3. Verify state validation
4. Confirm success only after verification

**Pass criteria:** No false positives

### CLI Works Independently

**Test:**
1. Install Agent-OS (no GUI)
2. Start daemon
3. Create task via CLI
4. Monitor via CLI
5. No GUI/TUI needed

**Pass criteria:** Full functionality via CLI alone

### TUI Works Independently

**Test:**
1. Start TUI
2. Create task
3. Watch real-time updates
4. Interact (pause, resume)

**Pass criteria:** Rich operational interface

### GUI Remains Optional

**Test:**
1. Uninstall GUI
2. Verify runtime works
3. Verify CLI/TUI work
4. No missing functionality

**Pass criteria:** GUI is truly optional

### System Is Clearly Local-Native

**Qualitative criteria:**
- No browser required for core functionality
- No external services for desktop automation
- Runtime continues when all UIs closed
- Fast startup (<1s)
- Low resource usage (<100MB base)
- Works offline
- OS-native look and feel

---

## 16-35. Additional Architectural Requirements

### 16. Deterministic vs Autonomous Boundary

**Strict separation:**
- **Action V1:** Deterministic execution for known tasks
- **LangGraph:** Autonomous execution for complex/ambiguous tasks

**Escalation criteria:**
| Condition | Path |
|-----------|------|
| Task matches known pattern | Action V1 |
| Confidence >90% | Action V1 |
| Simple UI interaction | Action V1 |
| Multi-step reasoning needed | LangGraph |
| Ambiguous goal | LangGraph |
| Collaboration required | LangGraph |

### 17. Capability Escalation Model

**Risk levels:**
```
┌─────────────────────────────────────────────────────────────┐
│  LOW RISK (No approval)                                     │
│  - Screenshot                                               │
│  - Get window list                                          │
│  - Read file (non-sensitive)                                │
├─────────────────────────────────────────────────────────────┤
│  MEDIUM RISK (Log only)                                     │
│  - Click element                                            │
│  - Type text (non-credential)                               │
│  - Browser navigation                                       │
├─────────────────────────────────────────────────────────────┤
│  HIGH RISK (Approval required)                              │
│  - Delete file                                              │
│  - Execute shell command                                    │
│  - Install software                                         │
│  - Modify system settings                                   │
├─────────────────────────────────────────────────────────────┤
│  DANGEROUS (Explicit confirmation)                          │
│  - Format drive                                             │
│  - Delete system files                                      │
│  - Execute as admin                                         │
│  - Network access to sensitive                              │
└─────────────────────────────────────────────────────────────┘
```

### 18. Unified Environment Abstraction

**Environment interface:**
```rust
trait Environment {
    fn observe(&self) -> State;
    fn execute(&self, action: Action) -> Result<State, Error>;
    fn verify(&self, expected: State) -> bool;
    fn snapshot(&self) -> Checkpoint;
    fn recover(&self, from: Error) -> Result<State, Error>;
}

// Implementations
struct DesktopEnvironment;    // Windows/macOS/Linux
struct BrowserEnvironment;    // Playwright
struct FilesystemEnvironment; // Local filesystem
struct ShellEnvironment;      // Command execution
```

### 19. Runtime Cognitive Architecture

**Responsibility boundaries:**
- **Planning:** PlannerAgent (decompose goals)
- **Execution:** ExecutorAgent (invoke tools)
- **Verification:** VerifierAgent (validate results)
- **Recovery:** RecoveryEngine (handle failures)
- **Reflection:** FeedbackLoop (learn patterns)
- **Memory:** PersistentMemoryManager (retain context)

### 20. Interruptibility and Control Model

**Supported operations:**
- **Pause:** Suspend execution, resume later
- **Resume:** Continue from checkpoint
- **Cancel:** Stop execution, clean up
- **Emergency stop:** Immediate halt, no cleanup
- **Manual takeover:** Human assumes control

**Safe interruption points:**
- Between actions (not during)
- After verification (not before)
- On tool completion (not during)

### 21. Runtime Trust and Governance

**Trust boundaries:**
- Agents cannot modify runtime code
- Tools cannot register other tools
- Workflows cannot spawn workflows (unless configured)
- Autonomous mode cannot escalate permissions

**Governance rules:**
- Immutable core runtime
- Signed tool packages
- Reviewed workflow changes
- Audit all permission changes

### 22. Cross-Platform Runtime Strategy

**Architecture:**
```
┌─────────────────────────────────────────────────────────────┐
│  Runtime Core (Portable)                                    │
├─────────────────────────────────────────────────────────────┤
│  Platform Adapters                                          │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐                     │
│  │ Windows │  │  macOS  │  │  Linux  │                     │
│  └─────────┘  └─────────┘  └─────────┘                     │
├─────────────────────────────────────────────────────────────┤
│  Platform-Specific Automation                               │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐                     │
│  │ UIA/COM │  │  AX API │  │  AT-SPI │                     │
│  └─────────┘  └─────────┘  └─────────┘                     │
└─────────────────────────────────────────────────────────────┘
```

**Windows-first:**
- Primary development on Windows
- Abstract interfaces for macOS/Linux
- No Windows-specific assumptions in core

### 23. Runtime Failure Containment

**Strategies:**
- **Worker crash:** Respawn worker, resume task
- **MCP failure:** Mark unhealthy, retry with backoff
- **Desktop engine failure:** Alert user, manual intervention
- **Runaway detection:** CPU/memory limits, automatic termination
- **Deadlock detection:** Timeout + watchdog

### 24. Event Bus and Internal Messaging

**Topology:**
```
┌─────────────────────────────────────────────────────────────┐
│  Event Bus (Rust tokio)                                     │
├─────────────────────────────────────────────────────────────┤
│  Execution Events ◄─── Runtime Core                       │
│  Observability Stream ◄─── Metrics/Tracing                │
│  Recovery Events ◄─── RecoveryEngine                        │
│  Lifecycle Events ◄─── Supervisor                         │
└─────────────────────────────────────────────────────────────┘
```

**Clarified ownership:**
- **Runtime memory:** Execution state
- **Event bus:** Observability streams
- **MCP bus:** Tool calls
- **Optional Redis:** Distributed mode only

### 25. State Ownership and Source of Truth

**Canonical ownership:**
| State | Owner | Persistence |
|-------|-------|-------------|
| Execution state | Runtime Core | Memory + SQLite |
| LangGraph state | LangGraph | Checkpoints (SQLite) |
| Task state | Task Manager | SQLite |
| Perception snapshots | Desktop Engine | Filesystem |
| Memory | PersistentMemoryManager | SQLite |

**Synchronization:**
- Single writer per state type
- Event-driven updates to observers
- Consistency at checkpoint boundaries

### 26. Tool Isolation and Sandboxing

**Boundaries:**
- **Subprocess isolation:** Each MCP server in own process
- **Resource quotas:** CPU, memory, time limits
- **Capability-based access:** Declare capabilities, enforce at runtime
- **Filesystem boundaries:** Chroot, bind mounts

### 27. Scheduling and Persistent Task Infrastructure

**Features:**
- **Scheduled tasks:** Cron-like syntax
- **Recurring automation:** Every N minutes/hours/days
- **Event triggers:** File change, window open, network event
- **Background monitoring:** Watch for conditions

### 28. Human Override and Supervision

**Capabilities:**
- **Runtime intervention:** Pause running task
- **Live action interception:** Approve each action
- **Emergency override:** Stop immediately
- **Manual recovery:** Take over from failure
- **Operator supervision:** Multi-user oversight

### 29. Memory Hierarchy Design

**Levels:**
```
┌─────────────────────────────────────────────────────────────┐
│  L1: Short-term (Runtime memory)                            │
│  - Current task state                                       │
│  - Active tool calls                                        │
│  - Cache (LRU eviction)                                     │
├─────────────────────────────────────────────────────────────┤
│  L2: Task Memory (SQLite)                                   │
│  - Task history                                             │
│  - Step results                                             │
│  - Context across steps                                     │
├─────────────────────────────────────────────────────────────┤
│  L3: Long-term (SQLite + Filesystem)                      │
│  - User profiles                                            │
│  - Learned patterns                                         │
│  - Knowledge base                                           │
├─────────────────────────────────────────────────────────────┤
│  L4: Semantic (Optional vector DB)                        │
│  - Document embeddings                                      │
│  - Semantic search                                          │
└─────────────────────────────────────────────────────────────┘
```

### 30. Runtime Resource Management

**Managed resources:**
- Screenshots (auto-delete after 7 days)
- OCR artifacts (cache, LRU eviction)
- Traces (compress, archive after 30 days)
- Checkpoints (keep last 100 per task)
- Subprocesses (limit concurrent)
- Caches (memory + disk limits)

### 31. Local-First vs Cloud-Assisted Boundary

**MUST be local:**
- Desktop automation
- Filesystem access
- Shell execution
- Screenshots
- UI interactions

**MAY use cloud:**
- LLM reasoning (OpenAI, Anthropic)
- Search (optional, can be local)
- Model inference (if local model available)
- Analytics (optional)

**Tradeoffs analyzed:**
- Privacy: Local wins
- Latency: Local wins for automation
- Offline: Local required
- Reasoning quality: Cloud may be better (configurable)

### 32. Plugin and Extension System

**MCP-based:**
- Servers load dynamically
- Version compatibility checks
- Capability contracts
- Permission declarations
- Runtime registration

### 33. Agent Identity and Isolation

**Per-agent:**
- Unique identity
- Isolated memory
- Permission scope
- Audit trail

**Multi-agent:**
- Shared bus for communication
- Explicit collaboration mode
- No state contamination
- Observable interactions

### 34. State Replay and Time-Travel Debugging

**Replay architecture:**
- Checkpoints at every step
- Screenshots for visual replay
- Action history
- Verification results

**Capabilities:**
- Replay execution
- Step through history
- Debug failures
- Deterministic re-execution

### 35. Runtime Philosophy and Long-Term Direction

**Agent-OS is:**
A **runtime for autonomous agents** that:
- Executes tasks on behalf of users
- Operates primarily via desktop automation
- Maintains state and recovers from failures
- Verifies before completing
- Respects user control and safety

**Not:**
- An AI assistant with some automation
- A chatbot with tool access
- A cloud service

**Long-term direction:**
- Increasing autonomy for known tasks
- Better desktop understanding
- More reliable automation
- Better human-AI collaboration
- Broader environment support

---

## Technology Stack Decisions

### Subsystem-by-Subsystem Analysis

| Subsystem | Current | Recommended | Justification |
|-----------|---------|-------------|---------------|
| **Runtime Core** | Python | **Keep Python** | LangGraph ecosystem, AI integration |
| **Supervisor** | None | **Go** | Service management, cross-platform |
| **Desktop Automation** | Python | **Rust** | <5ms latency, native APIs |
| **CLI** | None | **Rust** | Single binary, fast startup |
| **TUI** | None | **Rust (ratatui)** | Async TUI, performance |
| **GUI** | React/Web | **Tauri + React** | Native feel, small footprint |
| **MCP Servers** | Python | **Rust/Go for perf-critical** | Latency reduction |
| **IPC/Event Bus** | Redis | **Rust tokio** | <100μs latency, no dependency |
| **Worker Pool** | Python | **Go** | True parallelism, goroutines |
| **Persistence** | PostgreSQL | **SQLite (primary)** | Local-first, zero config |
| **Sandbox** | AST validation | **Native OS** | Real isolation |
| **Scheduling** | None | **Go** | Cron-like, persistent |

### Hybrid Language Justification

**Why Python stays:**
- LangGraph is Python-native and mature
- AI/ML ecosystem is Python-dominant
- Existing 25,000+ lines of orchestration code
- Checkpointer, human-in-the-loop, interrupts

**Why Go is added:**
- Service management (kardianos/service)
- Process supervision
- Cross-platform daemon architecture
- Worker pool (goroutines vs Python GIL)

**Why Rust is added:**
- Desktop automation latency requirement (<50ms)
- Native OS API access (Windows COM, macOS AX)
- CLI/TUI performance (single binary, fast)
- Memory safety for systems code

**Why TypeScript/React stays (in Tauri):**
- Existing frontend investment
- Workflow visualization (xyflow)
- Cross-platform UI from single codebase
- Tauri provides native bridge

---

## Conclusion

This architecture transforms Agent-OS from a **cloud-centric SaaS** into a **local-native autonomous agent runtime platform** while preserving all existing capabilities.

**Key transformations:**
1. Runtime is the product, not the UI
2. Desktop automation is primary
3. Local-first, cloud-optional
4. CLI/TUI/GUI hierarchy
5. Hybrid language stack (Python + Go + Rust)

**Preserved:**
- LangGraph orchestration
- DesktopGoalLoop, ActionStabilizer, RecoveryEngine
- MCP architecture
- Safety and observability
- Checkpoint/resume

**Gained:**
- Local-native execution
- Runtime survives UI closure
- <50ms desktop automation
- No external dependencies for core
- Cross-platform foundation

**Migration approach:**
- Phased implementation (5 phases, ~12 months)
- Backward compatibility maintained
- Existing tests guide refactoring
- No full rewrite—strategic extraction

This architecture enables Agent-OS to become a true **agent operating system**—local, persistent, reliable, and capable of genuine desktop automation.
