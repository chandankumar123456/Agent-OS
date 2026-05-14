# Phase 1: Foundation & Baseline — Design Specification

**Date:** 2026-05-12  
**Author:** AgentOS Architecture Team  
**Status:** Approved  
**Scope:** Stabilize and baseline the existing desktop-native execution path (gRPC mode) before any architectural changes.

---

## 1. Objective

Establish a stable, fully tested baseline of the current desktop-native path so that all subsequent migration phases have a reliable foundation to build upon. This phase is purely about **auditing, stabilizing, and documenting** — no new architecture is introduced.

---

## 2. Principles

1.  **Do No Harm:** We will not redesign anything in Phase 1. We only fix what is broken or stubbed.
2.  **Fail Fast:** The connection audit must fail the build if any Redis or PostgreSQL connection is initiated in gRPC mode. Hidden couplings must be exposed, not papered over.
3.  **Test-Driven Baseline:** All validation is via automated tests. Manual verification is supplementary.
4.  **Document Everything:** Every hidden coupling, every stub fixed, every test skipped or fixed must be documented.

---

## 3. Systems Involved

| System | File(s) | Responsibility in Phase 1 |
|--------|---------|---------------------------|
| Python Desktop Entry | `app/desktop_entry.py` | Ensure it forces gRPC mode and skips web initialization |
| Bootstrap | `app/bootstrap.py` | Audit all Redis/PG touchpoints; ensure conditional skip in gRPC mode |
| gRPC Server | `app/runtime/grpc_server.py` | Verify it starts and serves without web dependencies |
| SQLite Checkpointer | `app/langgraph/sqlite_checkpointer.py` | Ensure it is selected in gRPC mode and is async-safe |
| Go Supervisor | `supervisor/*.go` | Verify it compiles, starts, and accepts gRPC connections |
| Tauri Daemon Commands | `gui/src-tauri/src/commands/daemon.rs` | Implement real start/stop/status commands |
| Tauri Main | `gui/src-tauri/src/main.rs` | Wire daemon commands into system tray / shortcuts |
| Test Suite | `tests/` | Run with gRPC + SQLite config; fix blockers |

---

## 4. Deliverables

### 4.1 Deliverable 1: Connection Audit Test Framework

**What:** A pytest plugin / test fixture that monkeypatches `redis.asyncio.Redis` and `asyncpg.connect` (and any other PG drivers) to raise `RuntimeError` with a descriptive message.

**Where:** `tests/conftest.py` (autouse fixture when `AGENTOS_RUNTIME_MODE=grpc`)

**Behavior:**
- If any code path in gRPC mode attempts to instantiate a Redis connection or PostgreSQL connection, the test fails immediately.
- The error message must include the stack trace so the violating code can be located.
- This fixture runs for ALL tests when `RUNTIME_MODE=grpc`.

**Code Sketch:**
```python
# tests/conftest.py
@pytest.fixture(autouse=True)
def block_external_connections_in_grpc_mode(monkeypatch):
    if os.environ.get("AGENTOS_RUNTIME_MODE", "").lower() == "grpc":
        import redis.asyncio as redis_async
        original_redis_init = redis_async.Redis.__init__
        def blocked_redis_init(*args, **kwargs):
            raise RuntimeError(
                "REDIS CONNECTION BLOCKED IN GRPC MODE. "
                "Stack trace:\n" + "".join(traceback.format_stack())
            )
        monkeypatch.setattr(redis_async.Redis, "__init__", blocked_redis_init)
        # Similar for asyncpg, sqlalchemy async engine creation pointing to postgres
```

**Success Criteria:**
- [ ] Running `pytest tests/` with `AGENTOS_RUNTIME_MODE=grpc` fails if any Redis/PG connection is attempted.
- [ ] A report is generated listing every violation found.

### 4.2 Deliverable 2: Hidden Coupling Remediation

**What:** Fix or document every Redis/PG connection violation found by the audit.

**Remediation Rules:**
1.  **If the connection is in code that should not run in gRPC mode** (e.g., FastAPI middleware, Celery tasks), ensure it is gated by `is_http_mode()` or equivalent.
2.  **If the connection is in shared code** (e.g., `bootstrap.py`, `settings.py`), make the dependency lazy or conditional.
3.  **If the connection is in a test that should use SQLite**, update the test's `DATABASE_URL` to use SQLite.

**Success Criteria:**
- [ ] `pytest tests/` with `AGENTOS_RUNTIME_MODE=grpc` and `REDIS_URL=""` passes with zero connection violations.

### 4.3 Deliverable 3: Tauri Daemon Lifecycle Commands

**What:** Implement real daemon start/stop/status commands in the Tauri Rust backend.

**Where:** `gui/src-tauri/src/commands/daemon.rs`

**Commands to Implement:**

```rust
#[tauri::command]
async fn get_daemon_status() -> Result<DaemonStatus, String> {
    // Check if Supervisor process is running on expected port
    // Return: { running: bool, pid: Option<u32>, uptime_secs: Option<u64> }
}

#[tauri::command]
async fn start_daemon(app_handle: AppHandle) -> Result<DaemonStatus, String> {
    // Spawn Go Supervisor binary as child process
    // Set environment: AGENTOS_RUNTIME_MODE=grpc, DATABASE_URL=sqlite://...
    // Wait for health check on gRPC port
    // Return status
}

#[tauri::command]
async fn stop_daemon() -> Result<DaemonStatus, String> {
    // Send graceful shutdown signal to Supervisor process
    // Wait for process exit
    // Return status
}
```

**Integration:**
- Wire `start_daemon` into system tray "Start Daemon" menu item.
- Wire `stop_daemon` into system tray "Stop Daemon" menu item.
- `get_daemon_status` is polled every 5 seconds by the frontend and on app startup.

**Success Criteria:**
- [ ] Tauri GUI can start the Go Supervisor process.
- [ ] Tauri GUI can stop the Go Supervisor process.
- [ ] Tauri GUI displays correct daemon status (running/stopped).
- [ ] If the daemon crashes, the GUI reflects this within 10 seconds.

### 4.4 Deliverable 4: gRPC End-to-End Validation

**What:** A dedicated integration test that verifies the full chain:

```
Tauri (or test client) → Supervisor HTTP API → Supervisor gRPC → Python Runtime
→ Task Execution → SQLite Checkpoint → Event Stream → Supervisor WS → Client
```

**Where:** `tests/integration/test_desktop_e2e.py`

**Steps:**
1.  Start Go Supervisor process (or mock it if necessary for pytest).
2.  Start Python gRPC server (`app/desktop_entry.py`).
3.  Create a simple task via gRPC `RuntimeService.CreateTask`.
4.  Verify task is stored in SQLite.
5.  Verify task execution completes (use a no-op or simple tool).
6.  Verify events are emitted via gRPC streaming.
7.  Clean up processes.

**Success Criteria:**
- [ ] Test passes consistently (3/3 runs).
- [ ] No Redis or PostgreSQL connections initiated during test execution.

### 4.5 Deliverable 5: Phase 1 Report

**What:** A markdown report documenting everything found and fixed.

**Where:** `docs/superpowers/phase1_report.md`

**Contents:**
1.  **Connection Violations Found:** Table with violation location, root cause, and fix applied.
2.  **Stubs Fixed:** List of Tauri commands implemented.
3.  **Tests Fixed:** List of tests modified to work in gRPC/SQLite mode.
4.  **Tests Skipped:** List of tests that are inherently web-specific and must be skipped in gRPC mode (with justification).
5.  **Remaining Risks:** Any couplings that could not be fully resolved in Phase 1.

---

## 5. Test Configuration

All Phase 1 testing uses the following environment:

```bash
export AGENTOS_RUNTIME_MODE=grpc
export DATABASE_URL=sqlite+aiosqlite:///:memory:
export REDIS_URL=""
export SECRET_KEY=test-secret-key-for-phase1-only-32bytesx
export OPENAI_API_KEY=test-key-placeholder
export AGENTOS_ENV=test
```

**Command to run tests:**
```bash
pytest tests/ -v --tb=short
```

**Command to run with connection audit strictly enforced:**
```bash
pytest tests/ -v --tb=long -x  # fail on first violation
```

---

## 6. Validation Criteria (Exit Conditions)

Phase 1 is **complete** when ALL of the following are true:

- [ ] **D1:** Connection audit framework is implemented and merged.
- [ ] **D2:** `pytest tests/unit/` passes with zero Redis/PG violations in gRPC mode.
- [ ] **D3:** `pytest tests/integration/` passes with zero Redis/PG violations in gRPC mode (web-specific integration tests may be skipped with documented justification).
- [ ] **D4:** Tauri `start_daemon`, `stop_daemon`, and `get_daemon_status` commands are implemented and functional.
- [ ] **D5:** gRPC end-to-end test passes (Supervisor → Python Runtime → SQLite → Events).
- [ ] **D6:** Phase 1 report is written and committed.

---

## 7. Out of Scope

The following are explicitly NOT part of Phase 1:
-   Replacing Redis with local alternatives (Phase 2)
-   Rewriting the orchestrator or task runner (Phase 3)
-   Implementing capability-based security (Phase 4)
-   Redesigning observability (Phase 5)
-   UI polish beyond daemon lifecycle (Phase 6)
-   Performance optimization (Phase 7)
-   Any cloud features (Phase 8)

---

## 8. Risk Register

| Risk | Mitigation |
|------|------------|
| Audit reveals 50+ hidden couplings, making Phase 1 unbounded | Timebox Phase 1 to 2 weeks. If >20 couplings found, escalate to user for reprioritization. |
| Tauri daemon commands require platform-specific process management | Use `std::process::Command` for spawning; use `sysinfo` crate for cross-platform process detection. |
| Go Supervisor does not compile on current machine | Verify in CI. Document build dependencies. |
| SQLite checkpointer has async/threading bugs | Add dedicated unit test for concurrent checkpoint read/write in `tests/unit/`. |
| Tests depend on external LLM APIs | Ensure all Phase 1 tests use mocked LLM responses or no-op agents. |

---

## 9. Dependencies

| Dependency | Source | Condition |
|------------|--------|-----------|
| Go toolchain | System | Required for building Supervisor |
| Rust toolchain | System | Required for building Tauri |
| Node.js + npm | System | Required for Tauri frontend build |
| Python 3.11+ | System | Required for running tests |
| pytest, pytest-asyncio | `requirements.txt` | Test framework |

---

*Design approved by user on 2026-05-12.*  
*Next step: Write implementation plan via `writing-plans` skill.*
