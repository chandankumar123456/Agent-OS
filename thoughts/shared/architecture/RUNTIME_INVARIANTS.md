# Runtime Invariants

## Non-Negotiable Runtime Rules

These invariants must NEVER be violated during implementation. They form the foundation of the AgentOS architecture.

---

## Core Invariants

### 1. Runtime Survives UI Closure

**Rule:** The agent runtime must continue executing even when all user interfaces are closed.

**Rationale:**
- Users should be able to start a long-running task and close their laptop
- Automation should continue in background
- UI is view/controller, runtime is model
- Sessions are independent of UI attachment

**Implications:**
- Runtime runs as daemon/service, not child of UI process
- UI connects/disconnects to running runtime
- State persists in SQLite, not UI memory
- Multiple UIs can attach to same session

**Enforcement:**
- Supervisor process owns runtime
- UI is just a client
- Runtime has its own lifecycle
- System service registration on Windows

---

### 2. Desktop Automation is Local-First

**Rule:** All desktop automation must execute on the local machine, not in the cloud.

**Rationale:**
- Network latency makes desktop automation unreliable (>100ms vs <5ms)
- Security: screen data shouldn't leave local machine
- Cost: no cloud compute for basic automation
- Reliability: works offline

**Implications:**
- Rust desktop engine runs locally
- No remote desktop protocols for core automation
- Cloud AI can provide guidance, not execution
- Screenshots stay local

**Enforcement:**
- Desktop automation code in Rust, not Python web services
- Supervisor validates local execution
- Network-dependent features fail gracefully

---

### 3. Runtime Owns State

**Rule:** The runtime process is the single source of truth for all agent state.

**Rationale:**
- Multiple UIs need consistent view
- State must survive UI crashes
- Concurrent access requires coordination
- SQLite is storage, runtime is authority

**Implications:**
- All state changes go through runtime
- UIs are read-only for state (except user input)
- Runtime validates all transitions
- Database is checkpoint, not active state

**Enforcement:**
- gRPC API for state queries
- Event stream for updates
- Optimistic UI with runtime confirmation

---

### 4. GUI is Optional

**Rule:** All functionality must be accessible via CLI. GUI is an enhancement, not a requirement.

**Rationale:**
- Power users prefer CLI
- Remote access via SSH
- Headless servers
- Automation and scripting

**Implications:**
- Every GUI feature has CLI equivalent
- GUI is thin client over same API
- No GUI-exclusive features
- TUI fills middle ground

**Enforcement:**
- CLI-first design
- GUI uses same gRPC calls
- Feature parity testing

---

### 5. Deterministic Execution Preferred

**Rule:** Known patterns should execute via deterministic code, not LLM reasoning.

**Rationale:**
- Deterministic: faster, cheaper, more reliable
- LLM: slower, expensive, probabilistic
- Use right tool for right job
- Learn from success

**Implications:**
- Action V1 preserved for common patterns
- Pattern library grows over time
- LLM fallback for novel situations
- Confidence-based routing

**Enforcement:**
- Pattern matching before LLM
- Success tracking
- Automatic pattern extraction
- Capability escalation

---

### 6. Browser is Never the Executor

**Rule:** The web browser cannot execute desktop automation actions.

**Rationale:**
- Browser sandbox prevents desktop access
- Security model incompatible
- Web-to-desktop bridges are fragile
- Electron is just a GUI, not executor

**Implications:**
- Browser-based UI is view only
- Tauri/Electron delegate to local runtime
- No Playwright/Puppeteer for desktop automation
- Rust code for native execution

**Enforcement:**
- Tauri uses sidecar for execution
- All desktop actions go through supervisor
- Browser communicates via IPC only

---

### 7. No Cloud Dependency for Core Automation

**Rule:** Basic automation must work without internet connection.

**Rationale:**
- Offline functionality
- Privacy
- Reliability
- Cost control

**Implications:**
- Local AI options (Ollama)
- All core tools local
- Cloud features clearly marked as optional
- Graceful degradation

**Enforcement:**
- Feature flags for cloud features
- Offline mode testing
- Clear dependency documentation
- Local-first architecture

---

## Safety Invariants

### 8. Verification Before Success

**Rule:** Every automation action must be verified before being marked successful.

**Rationale:**
- "Click" doesn't mean "worked"
- False positives break workflows
- Verification catches silent failures

**Implications:**
- Screenshot before/after
- State assertion where possible
- Retry on verification failure
- Human confirmation for critical actions

**Enforcement:**
- Verify node in LangGraph
- Action V1 verification built-in
- Tool returns success + evidence

---

### 9. Recovery Before Failure

**Rule:** Every error condition must attempt recovery before failing.

**Rationale:**
- Transient failures are common in UI automation
- Retry with backoff solves most issues
- Automatic recovery reduces human intervention
- Graceful degradation

**Implications:**
- Retry loops with exponential backoff
- Alternative strategies
- Escalation on max retries
- Human fallback as last resort

**Enforcement:**
- Recoverer node in graph
- Tool-level retry logic
- Error classification (recoverable vs fatal)

---

### 10. Capability Escalation Boundaries

**Rule:** Escalation to higher-capability methods must be explicit and justified.

**Rationale:**
- Don't use LLM when deterministic works
- Cost and latency matter
- Track what requires advanced capabilities
- Improve pattern library

**Implications:**
- Try Action V1 first
- Escalate on failure
- Log escalation reasons
- Learn from escalations

**Enforcement:**
- Escalation decisions logged
- Cost tracking by method
- Pattern improvement from escalations
- Confidence thresholds

---

## Execution Invariants

### 11. Safety-First Execution

**Rule:** Dangerous actions require explicit confirmation.

**Rationale:**
- Prevent accidents
- User control over risky operations
- Compliance
- Trust

**Implications:**
- Delete, modify system, network actions blocked by default
- Human checkpoint before execution
- Undo where possible
- Clear audit trail

**Enforcement:**
- Safety node in graph
- Tool classification (safe vs dangerous)
- Confirmation UI/CLI flow
- Audit logging

---

### 12. Atomic Operations

**Rule:** Multi-step operations must be atomic or rollback-capable.

**Rationale:**
- Partial completion is failure
- State consistency
- Recovery from interruption

**Implications:**
- Transactions where possible
- Compensation actions for rollback
- Checkpoint before multi-step
- State validation after

**Enforcement:**
- Transaction wrapper
- Compensation pattern
- Rollback testing

---

### 13. Bounded Execution

**Rule:** All operations must have time and resource bounds.

**Rationale:**
- Prevent infinite loops
- Resource exhaustion protection
- Fairness
- Predictability

**Implications:**
- Timeouts on all operations
- Memory limits
- CPU throttling
- Cancellation support

**Enforcement:**
- Context with timeout
- Resource monitoring
- Cancellation tokens
- Quotas and limits

---

## Data Invariants

### 14. Data Locality

**Rule:** User data stays local unless explicitly shared.

**Rationale:**
- Privacy
- Security
- Compliance (GDPR, etc.)
- User trust

**Implications:**
- SQLite database local
- Screenshots local
- Logs local
- Encryption at rest

**Enforcement:**
- No automatic cloud sync
- Opt-in sharing only
- Local-first storage
- Audit cloud access

---

### 15. Schema Stability

**Rule:** Database schema changes are backward-compatible or migratable.

**Rationale:**
- Data preservation
- Upgrade path
- No data loss
- Rollback capability

**Implications:**
- Migrations with rollback
- Version tracking
- Compatibility layers
- Backup before migration

**Enforcement:**
- Migration framework
- Schema versioning
- Compatibility tests
- Backup automation

---

## Performance Invariants

### 16. Sub-100ms UI Response

**Rule:** CLI commands must respond in under 100ms (excluding actual work time).

**Rationale:**
- Snappy feel
- Scripting friendly
- Perceived performance
- Efficiency

**Implications:**
- Async where possible
- Caching
- Optimized startup
- Deferred work

**Enforcement:**
- Performance tests
- Benchmarking
- Latency monitoring
- Profiling

---

### 17. Bounded Memory

**Rule:** No component grows memory unboundedly.

**Rationale:**
- Stability
- Multi-session support
- Resource sharing
- Predictability

**Implications:**
- LRU caches
- Streaming for large data
- Periodic cleanup
- Memory limits

**Enforcement:**
- Memory monitoring
- Leak detection
- Limit enforcement
- Profiling

---

## Last Updated

**Date:** 2026-05-09  
**By:** Agent  
**Version:** 1.0.0
