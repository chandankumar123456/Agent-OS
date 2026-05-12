# Architecture Audit & Migration Blueprint

## Project: AI-Powered Autonomous Desktop Agent Platform
## Current State: Web-based distributed architecture
## Target State: Desktop-native autonomous runtime

---

## Goals

1.  Perform a holistic, first-principles architecture audit of the entire existing stack.
2.  Identify web-specific, distributed, and over-engineered patterns unsuited for a local desktop runtime.
3.  Design a production-ready desktop-native runtime architecture.
4.  Produce a phased migration roadmap with clear milestones, risks, and validation criteria.
5.  Prioritize runtime correctness, stability, and local-first execution.

---

## Phases

### Phase 0: Deep Codebase Reverse Engineering
**Status:** `complete`
**Goal:** Map every file, dependency, subsystem, and execution flow in the current codebase.
**Deliverables:**
- Complete dependency tree and tech stack inventory. → `findings.md`
- Directory structure map with architectural responsibility per module. → `findings.md`
- Execution flow diagrams (API calls, queue flows, agent runs, websocket events). → `findings.md`
- Inventory of all infrastructure configs (Docker, env vars, compose files). → `findings.md`
**Validation:** Can trace any user request from entry point (API/WS) to OS action and back. ✅

### Phase 1: Subsystem Audit & Evaluation
**Status:** `complete`
**Goal:** Evaluate every major component against desktop-native requirements.
**Deliverables:**
- Component-by-component decision matrix (Keep/Simplify/Replace/Remove). → `DESKTOP_NATIVE_MIGRATION_BLUEPRINT.md` Section 2 & Appendix B
- Runtime overhead and complexity analysis per subsystem. → `DESKTOP_NATIVE_MIGRATION_BLUEPRINT.md` Section 2
- Identification of distributed-system assumptions and web-specific anti-patterns. → `DESKTOP_NATIVE_MIGRATION_BLUEPRINT.md` Section 2
- Security and sandboxing gap analysis. → `DESKTOP_NATIVE_MIGRATION_BLUEPRINT.md` Section 2.5
**Validation:** Every dependency has a documented justification or elimination plan. ✅

### Phase 2: Desktop-Native Architecture Design
**Status:** `complete`
**Goal:** Design the target architecture from first principles.
**Deliverables:**
- Core Runtime design (Agent Kernel, Task Scheduler, Execution Engine, Lifecycle). → `DESKTOP_NATIVE_MIGRATION_BLUEPRINT.md` Section 4.2
- Agent System design (Multi-agent, IPC, State Sync, Memory Hierarchy). → `DESKTOP_NATIVE_MIGRATION_BLUEPRINT.md` Section 4.3
- Desktop Control Layer design (UI Automation, OS Interaction, Browser Control). → `DESKTOP_NATIVE_MIGRATION_BLUEPRINT.md` Section 4.4
- Infrastructure design (Event Bus, Streaming, Observability, Crash Recovery). → `DESKTOP_NATIVE_MIGRATION_BLUEPRINT.md` Section 4.7
- AI Runtime design (Local/Cloud routing, Model Management, Context/Window). → `DESKTOP_NATIVE_MIGRATION_BLUEPRINT.md` Section 4.5
- Security Architecture (Sandboxing, Capabilities, Human-in-the-loop). → `DESKTOP_NATIVE_MIGRATION_BLUEPRINT.md` Section 4.6
- Extensibility design (Plugins, Tool SDK, Modules). → `DESKTOP_NATIVE_MIGRATION_BLUEPRINT.md` Section 4.3 (Tool routing)
**Validation:** Target architecture satisfies all functional requirements with minimal operational complexity. ✅

### Phase 3: Migration Strategy & Roadmap
**Status:** `complete`
**Goal:** Produce the executable migration plan.
**Deliverables:**
- Phased refactoring roadmap with strict sequencing. → `DESKTOP_NATIVE_MIGRATION_BLUEPRINT.md` Section 5
- Dependency elimination plan. → `DESKTOP_NATIVE_MIGRATION_BLUEPRINT.md` Section 6
- Runtime simplification strategy. → `DESKTOP_NATIVE_MIGRATION_BLUEPRINT.md` Section 4 & 5
- Risk analysis, bottleneck analysis, technical debt analysis. → `DESKTOP_NATIVE_MIGRATION_BLUEPRINT.md` Section 7
- Testing and stability phases. → `DESKTOP_NATIVE_MIGRATION_BLUEPRINT.md` Phase 1, 7
- Production hardening plan. → `DESKTOP_NATIVE_MIGRATION_BLUEPRINT.md` Phase 7
**Validation:** Roadmap is granular enough to be executed ticket-by-ticket. ✅

### Phase 1 Implementation: Foundation & Baseline
**Status:** `complete`
**Goal:** Stabilize and baseline the existing desktop-native execution path (gRPC mode).
**Deliverables:**
- Connection audit framework with monkeypatch blocking. ✅
- All unit tests pass (124 passed, 0 Redis/PG violations). ✅
- All integration tests pass (15 passed, 5 skipped with documented justification). ✅
- Tauri daemon commands implemented and compiling. ✅
- gRPC server/client proto mismatches fixed. ✅
- Phase 1 report committed. → `docs/superpowers/phase1_report.md` ✅

### Phase 2 Implementation: Decoupling & Dependency Elimination
**Status:** `pending`
**Goal:** Remove hard dependencies on Redis and PostgreSQL in desktop mode.
**Key Tasks:**
- Implement `LocalEventBus` (asyncio Queue-based)
- Implement `LocalTaskQueue` with SQLite persistence
- Rewrite `TaskStateMachine` to use SQLite exclusively
- Replace Redis locks/timeouts with asyncio equivalents
- Disable distributed coordinators and web middleware in desktop mode
- Rewrite `CostTracker` to use SQLite aggregates
**Validation:** Desktop runtime starts and executes tasks with no Redis/PG connections.

---

## Critical Path

1.  Complete Phase 0: Without full understanding, all decisions are speculative.
2.  Agent Runtime Kernel Design: This is the heart of the new system.
3.  IPC & State Ownership Design: Desktop-native runtimes fail here most often.
4.  Dependency Elimination: Remove distributed/web cruft before building new features.
5.  Integration & Stability Testing: Long-running autonomous execution is the ultimate validation.

---

## Risks

-   **Hidden Coupling:** Web architectures often have implicit dependencies via shared queues/databases that are hard to untangle.
-   **State Ownership Ambiguity:** Migrating from stateless APIs to persistent desktop runtime requires clear state boundaries.
-   **Over-Simplification:** Removing too much infrastructure too fast may break existing functionality before replacements are ready.
-   **Agent Recursion/Runaway:** Autonomous desktop agents have real-world side effects; architectural safety mechanisms are critical.

---

## Notes

-   Do NOT assume existing code is correct.
-   Challenge every queue, broker, network call, and container.
-   Local-first, low-latency, persistent execution is the North Star.
