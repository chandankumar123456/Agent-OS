# Decisions

## Architectural Decision Records

This document preserves WHY major design decisions were made, including rejected alternatives and tradeoff analysis.

---

## Technology Selections

### DECISION-001: Go for Supervisor Process

**Date:** 2026-05-09  
**Status:** APPROVED  
**Decision:** Use Go for the supervisor/daemon process

**Context:**
Need a process to manage runtime lifecycle, handle UI connections, and coordinate between components. Must be reliable, fast-starting, and resource-efficient.

**Options Considered:**

1. **Go (Chosen)**
   - Pros: Goroutines for concurrency, single binary, fast startup, good IPC story, strong standard library, Windows service support
   - Cons: Another language to maintain
   - Verdict: Best fit for supervisor duties

2. **Rust**
   - Pros: Memory safety, performance, single binary
   - Cons: Steeper learning curve, longer compile times, complex async
   - Verdict: Better suited for desktop automation

3. **Python**
   - Pros: Familiar, fast development
   - Cons: Slow startup, GIL limits, resource-heavy, deployment complexity
   - Verdict: Rejected - supervisor needs to be lightweight

4. **Node.js**
   - Pros: JavaScript ecosystem
   - Cons: Heavy runtime, slow startup, complex deployment
   - Verdict: Rejected - wrong tool for system process

**Consequences:**
- Team must learn Go
- gRPC as IPC standard
- Single static binary deployment
- Windows service integration straightforward

---

### DECISION-002: Python LangGraph for Runtime Core

**Date:** 2026-05-09  
**Status:** APPROVED  
**Decision:** Keep Python with LangGraph for agent runtime, not rewrite in Go or Rust

**Context:**
Current codebase uses Python with LangGraph. Need to decide whether to port to another language for local-native architecture.

**Options Considered:**

1. **Keep Python (Chosen)**
   - Pros: Ecosystem lock-in (LangGraph, LangChain, OpenAI SDK), rapid AI evolution, team expertise, existing working code, subprocess model isolates it
   - Cons: Slower than Go/Rust, GIL limits, memory usage
   - Verdict: Ecosystem and velocity outweigh performance concerns

2. **Rewrite in Go**
   - Pros: Performance, concurrency, single binary
   - Cons: Would need to rewrite LangGraph, lose ecosystem, slow development
   - Verdict: Rejected - ecosystem too valuable

3. **Rewrite in Rust**
   - Pros: Performance, safety
   - Cons: AI ecosystem limited, development speed
   - Verdict: Rejected - ecosystem gap

4. **Hybrid: Go orchestration + Python tools**
   - Pros: Go for coordination
   - Cons: Complexity, adds latency
   - Verdict: Rejected - simpler to keep Python runtime

**Consequences:**
- Python as subprocess managed by Go
- Inter-process communication overhead
- Need IPC design
- Performance acceptable for AI workloads (LLM is bottleneck)

---

### DECISION-003: Rust for Desktop Automation

**Date:** 2026-05-09  
**Status:** APPROVED  
**Decision:** Use Rust for desktop automation engine

**Context:**
Current DesktopGoalLoop uses Python with pyautogui. Need <5ms latency for reliable automation.

**Options Considered:**

1. **Rust (Chosen)**
   - Pros: <5ms latency, direct OS APIs, memory safety, Tesseract integration, single binary
   - Cons: Learning curve, build complexity
   - Verdict: Required for pixel-perfect automation

2. **Keep Python (pyautogui)**
   - Pros: Existing code, familiar
   - Cons: 50-200ms latency, unreliable, limited API
   - Verdict: Rejected - insufficient performance

3. **Go**
   - Pros: Good concurrency
   - Cons: Limited desktop automation libraries
   - Verdict: Rejected - ecosystem gap

4. **C++**
   - Pros: Performance
   - Cons: Unsafe, complex build, maintenance burden
   - Verdict: Rejected - Rust provides same performance with safety

**Consequences:**
- New Rust codebase
- gRPC interface to Python
- Tesseract OCR integration
- Cross-platform: Windows first, then macOS/Linux

---

### DECISION-004: Tauri for GUI

**Date:** 2026-05-09  
**Status:** APPROVED  
**Decision:** Use Tauri (Rust + React) for optional GUI

**Context:**
Need a GUI that feels native but can be closed without stopping runtime.

**Options Considered:**

1. **Tauri (Chosen)**
   - Pros: ~15MB bundle, native feel, fast, secure, sidecar pattern for runtime
   - Cons: Newer framework, smaller community
   - Verdict: Best balance of size and capability

2. **Electron**
   - Pros: Mature, large ecosystem
   - Cons: 100MB+ bundle, memory hungry, slow startup
   - Verdict: Rejected - too heavy

3. **Native Rust (egui/iced)**
   - Pros: Single language, small binary
   - Cons: UI development slower, less familiar
   - Verdict: Rejected - development velocity

4. **Keep React Web App**
   - Pros: Existing code
   - Cons: Browser is not executor, requires backend
   - Verdict: Rejected - wrong architecture

**Consequences:**
- React skills reusable
- Rust sidecar for runtime
- Small distribution size
- Windows installer with Tauri bundler

---

### DECISION-005: CLI is Primary Interface

**Date:** 2026-05-09  
**Status:** APPROVED  
**Decision:** CLI is the primary interface, GUI is optional

**Context:**
Need to decide which interface gets priority for features and design.

**Options Considered:**

1. **CLI Primary (Chosen)**
   - Pros: Scriptable, works anywhere, fast, power-user friendly, automation
   - Cons: Learning curve for some users
   - Verdict: Correct for agent automation tool

2. **GUI Primary**
   - Pros: Visual, discoverable
   - Cons: Less automatable, heavier, requires display
   - Verdict: Rejected - limits use cases

3. **Equal Priority**
   - Pros: User choice
   - Cons: Double maintenance, feature parity challenges
   - Verdict: Rejected - CLI is clearly primary for this tool

**Consequences:**
- CLI gets features first
- GUI is thin client over CLI API
- Documentation prioritizes CLI
- TUI as middle ground

---

### DECISION-006: Runtime Survives UI Closure

**Date:** 2026-05-09  
**Status:** APPROVED  
**Decision:** Runtime runs as daemon/service, UI is just a view

**Context:**
Should closing the UI stop the automation?

**Options Considered:**

1. **Runtime Survives (Chosen)**
   - Pros: Long-running tasks, background operation, multiple UIs, headless mode
   - Cons: More complex lifecycle management
   - Verdict: Required for agent workflows

2. **UI Owns Runtime**
   - Pros: Simpler lifecycle, matches web apps
   - Cons: Automation stops when UI closes
   - Verdict: Rejected - doesn't match agent use case

**Consequences:**
- Windows service registration
- UI attach/detach model
- State in SQLite, not UI memory
- Supervisor owns lifecycle

---

### DECISION-007: SQLite as Primary Persistence

**Date:** 2026-05-09  
**Status:** APPROVED  
**Decision:** Use SQLite as primary persistence, make PostgreSQL optional

**Context:**
Current cloud architecture uses PostgreSQL. Local-native needs simpler persistence.

**Options Considered:**

1. **SQLite (Chosen)**
   - Pros: Zero config, single file, portable, sufficient for local use, built-in
   - Cons: Concurrent write limits, not for multi-user
   - Verdict: Perfect for local-first single-user

2. **Keep PostgreSQL**
   - Pros: Existing setup, familiar
   - Cons: Requires server setup, complex deployment
   - Verdict: Rejected - overkill for local

3. **Embedded PostgreSQL**
   - Pros: Same SQL
   - Cons: Large binary, complex
   - Verdict: Rejected - SQLite is simpler

4. **Flat Files (JSON/YAML)**
   - Pros: Simple, human readable
   - Cons: No queries, no transactions, corruption risk
   - Verdict: Rejected - need database features

**Consequences:**
- Single-file database
- Migration from cloud to local
- PostgreSQL support as enterprise option
- Backup is file copy

---

### DECISION-008: gRPC for IPC

**Date:** 2026-05-09  
**Status:** APPROVED  
**Decision:** Use gRPC for inter-process communication

**Context:**
Need IPC between Go supervisor, Python runtime, Rust desktop, and UIs.

**Options Considered:**

1. **gRPC (Chosen)**
   - Pros: Type-safe, efficient, streaming, code generation, cross-language
   - Cons: HTTP/2 complexity, requires .proto
   - Verdict: Industry standard for reason

2. **REST/HTTP**
   - Pros: Simple, universal
   - Cons: Verbose, slower, no streaming
   - Verdict: Rejected - IPC needs efficiency

3. **Unix Domain Sockets / Named Pipes**
   - Pros: Fast, simple
   - Cons: No type safety, custom protocol needed
   - Verdict: Rejected - gRPC provides more

4. **Message Queue (NATS)**
   - Pros: Decoupled, pub/sub
   - Cons: Additional dependency, latency
   - Verdict: Optional, not primary IPC

**Consequences:**
- .proto definitions
- Generated code for each language
- HTTP/2 transport
- Streaming for events

---

## Migration Decisions

### DECISION-009: 5-Phase Migration Over 12 Months

**Date:** 2026-05-09  
**Status:** APPROVED  
**Decision:** Migrate in 5 phases over 12 months, not big-bang rewrite

**Context:**
Current system is working cloud SaaS. Need to transform to local-native without losing functionality.

**Options Considered:**

1. **5-Phase Migration (Chosen)**
   - Pros: Gradual, reversible, testable, lower risk
   - Cons: Longer timeline, hybrid state
   - Verdict: Only sane approach for production system

2. **Big-Bang Rewrite**
   - Pros: Clean slate, faster completion
   - Cons: High risk, extended downtime, feature loss
   - Verdict: Rejected - too risky

3. **Fork and Maintain Both**
   - Pros: No disruption to existing users
   - Cons: Double maintenance, divergent codebases
   - Verdict: Rejected - unsustainable

**Migration Phases:**
1. Foundation (2-3mo): Go supervisor, SQLite, CLI skeleton
2. Desktop Native (3-4mo): Rust desktop, gRPC bridge, native OCR
3. Interfaces (2-3mo): Tauri GUI, Rust CLI/TUI, system tray
4. Performance (2-3mo): Go workers, native IPC, optimizations
5. Polish (1-2mo): Installers, docs, benchmarks

---

### DECISION-010: Preserve DesktopGoalLoop Pattern

**Date:** 2026-05-09  
**Status:** APPROVED  
**Decision:** Preserve existing DesktopGoalLoop pattern during migration

**Context:**
Current `app/desktop/goal_loop.py` implements observe-decide-act-verify-recover pattern.

**Options Considered:**

1. **Preserve Pattern (Chosen)**
   - Pros: Works, proven, team understands it
   - Cons: Migration effort to port
   - Verdict: Pattern is correct, implementation changes

2. **New Pattern**
   - Pros: Could be better
   - Cons: Unknown, unproven, risk
   - Verdict: Rejected - if it ain't broke

**Consequences:**
- Port to Rust desktop engine
- Keep observe-decide-act-verify-recover
- LangGraph nodes map to phases

---

### DECISION-011: MCP Ecosystem Preserved

**Date:** 2026-05-09  
**Status:** APPROVED  
**Decision:** Preserve MCP tool ecosystem with {server}__{tool} namespacing

**Context:**
Current system uses MCP (Model Context Protocol) for tool integration.

**Options Considered:**

1. **Preserve MCP (Chosen)**
   - Pros: Ecosystem, working tools, standard
   - Cons: Requires MCP server subprocess management
   - Verdict: Ecosystem too valuable

2. **Custom Tool System**
   - Pros: Simpler, custom fit
   - Cons: Lose ecosystem, rewrite tools
   - Verdict: Rejected - ecosystem lock-in

**Consequences:**
- MCPClientManager continues to work
- Same namespacing
- Server lifecycle management in runtime

---

## Design Decisions

### DECISION-012: Action V1 Deterministic Fast Path

**Date:** 2026-05-09  
**Status:** APPROVED  
**Decision:** Preserve Action V1 as deterministic fast path, use LLM fallback

**Context:**
Current system has Action V1 for deterministic automation vs LLM planning.

**Options Considered:**

1. **Preserve Both (Chosen)**
   - Pros: Fast path for known patterns, fallback for novel
   - Cons: Two systems to maintain
   - Verdict: Performance and reliability benefit

2. **LLM Only**
   - Pros: Simpler, unified
   - Cons: Slower, less reliable, more expensive
   - Verdict: Rejected - deterministic has 95% success rate

3. **Deterministic Only**
   - Pros: Fast, reliable
   - Cons: Can't handle novel situations
   - Verdict: Rejected - limits capability

**Consequences:**
- Pattern library maintained
- Escalation logic
- Success tracking
- Cost savings

---

### DECISION-013: Windows Primary Target

**Date:** 2026-05-09  
**Status:** APPROVED  
**Decision:** Windows is primary target, macOS/Linux secondary

**Context:**
Desktop automation requires OS-specific code. Need to prioritize.

**Options Considered:**

1. **Windows First (Chosen)**
   - Pros: Largest market, primary user base
   - Cons: macOS/Linux users wait
   - Verdict: Business reality

2. **Cross-Platform from Day 1**
   - Pros: Broader appeal
   - Cons: Slower, triple implementation
   - Verdict: Rejected - stretch timeline

3. **macOS First**
   - Pros: Developer-friendly
   - Cons: Smaller market
   - Verdict: Rejected - not aligned with user base

**Consequences:**
- Windows APIs first
- Conditional compilation for platform
- macOS/Linux in Phase 5+
- Installer for Windows first

---

### DECISION-014: Single-Binary Deployment Preferred

**Date:** 2026-05-09  
**Status:** APPROVED  
**Decision:** Prefer single-binary deployment where possible

**Context:**
Want easy installation and distribution.

**Options Considered:**

1. **Single Binary (Rust/Go) (Chosen)**
   - Pros: Easy install, no dependencies, portable
   - Cons: Larger binary, build complexity
   - Verdict: Better user experience

2. **Multi-Binary + Dependencies**
   - Pros: Smaller individual binaries
   - Cons: Complex installation, dependency hell
   - Verdict: Rejected - complicates distribution

3. **Container-Based**
   - Pros: Isolation
   - Cons: Heavy, not native, desktop access issues
   - Verdict: Rejected - desktop automation needs native

**Consequences:**
- Static linking where possible
- Bundle Python runtime
- Embedded resources
- Windows installer

---

## Last Updated

**Date:** 2026-05-09  
**By:** Agent  
**Version:** 1.0.0
