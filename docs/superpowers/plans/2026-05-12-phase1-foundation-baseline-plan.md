# Phase 1: Foundation & Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans or inline execution. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stabilize the desktop-native gRPC execution path by auditing hidden Redis/PostgreSQL couplings, fixing Tauri daemon stubs, and establishing a passing test baseline with SQLite.

**Architecture:** Monkeypatch-based connection audit to expose hidden dependencies, then conditional-gate or lazy-initialize those dependencies so gRPC mode can run with zero external database connections.

**Tech Stack:** Python 3.11, pytest, pytest-asyncio, Rust (Tauri), Go (Supervisor), SQLite, gRPC

---

## File Structure

| File | Responsibility |
|------|---------------|
| `tests/conftest.py` | Global fixtures; will host the connection audit fixture |
| `tests/unit/test_connection_audit.py` | Dedicated test verifying the audit fixture works |
| `app/bootstrap.py` | Shared init; audit Redis/PG touchpoints |
| `app/config/settings.py` | Lazy settings validation; skip Redis/PG checks in gRPC mode |
| `app/desktop_entry.py` | Forces gRPC mode before any imports |
| `gui/src-tauri/src/commands/daemon.rs` | Real start/stop/status commands |
| `gui/src-tauri/src/main.rs` | Wire commands into Tauri app |
| `gui/src-tauri/Cargo.toml` | Add `sysinfo` dependency |
| `tests/integration/test_desktop_e2e.py` | gRPC end-to-end validation test |
| `docs/superpowers/phase1_report.md` | Final report |

---

## Task 1: Connection Audit Framework

**Files:**
- Modify: `tests/conftest.py`
- Create: `tests/unit/test_connection_audit.py`

- [ ] **Step 1: Read current `tests/conftest.py`**

Read: `E:\Projects\AgentOS\tests\conftest.py`

- [ ] **Step 2: Add connection-blocking fixture to `conftest.py`**

Add the following fixture at the bottom of `conftest.py`:

```python
import os
import traceback
import pytest


@pytest.fixture(autouse=True)
def block_external_connections_in_grpc_mode(monkeypatch):
    """Block Redis and PostgreSQL connections when running in gRPC/desktop mode."""
    if os.environ.get("AGENTOS_RUNTIME_MODE", "").lower() != "grpc":
        yield
        return

    # Block redis.asyncio.Redis
    try:
        import redis.asyncio as redis_async
        original_redis_init = redis_async.Redis.__init__

        def blocked_redis_init(*args, **kwargs):
            raise RuntimeError(
                "REDIS CONNECTION BLOCKED IN GRPC MODE.\n"
                "Stack trace:\n" + "".join(traceback.format_stack())
            )

        monkeypatch.setattr(redis_async.Redis, "__init__", blocked_redis_init)
    except ImportError:
        pass

    # Block asyncpg.connect
    try:
        import asyncpg
        original_asyncpg_connect = asyncpg.connect

        async def blocked_asyncpg_connect(*args, **kwargs):
            raise RuntimeError(
                "ASYNCPG CONNECTION BLOCKED IN GRPC MODE.\n"
                "Stack trace:\n" + "".join(traceback.format_stack())
            )

        monkeypatch.setattr(asyncpg, "connect", blocked_asyncpg_connect)
    except ImportError:
        pass

    # Block sqlalchemy async engine creation for postgresql dialects
    try:
        from sqlalchemy.ext.asyncio import create_async_engine

        original_create_async_engine = create_async_engine

        def blocked_create_async_engine(url, **kwargs):
            url_str = str(url)
            if "postgresql" in url_str.lower() or "postgres" in url_str.lower():
                raise RuntimeError(
                    "POSTGRESQL ENGINE CREATION BLOCKED IN GRPC MODE.\n"
                    f"URL: {url_str}\n"
                    "Stack trace:\n" + "".join(traceback.format_stack())
                )
            return original_create_async_engine(url, **kwargs)

        monkeypatch.setattr(
            "sqlalchemy.ext.asyncio.create_async_engine", blocked_create_async_engine
        )
    except ImportError:
        pass

    yield
```

- [ ] **Step 3: Write test verifying the fixture blocks connections**

Create `tests/unit/test_connection_audit.py`:

```python
import os
import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("AGENTOS_RUNTIME_MODE", "").lower() != "grpc",
    reason="Only relevant in gRPC mode",
)


@pytest.mark.asyncio
async def test_redis_connection_blocked():
    with pytest.raises(RuntimeError, match="REDIS CONNECTION BLOCKED"):
        import redis.asyncio as redis_async
        redis_async.Redis(host="localhost", port=6379)


@pytest.mark.asyncio
async def test_asyncpg_connection_blocked():
    with pytest.raises(RuntimeError, match="ASYNCPG CONNECTION BLOCKED"):
        import asyncpg
        await asyncpg.connect("postgresql://user:pass@localhost/db")


def test_postgresql_engine_creation_blocked():
    with pytest.raises(RuntimeError, match="POSTGRESQL ENGINE CREATION BLOCKED"):
        from sqlalchemy.ext.asyncio import create_async_engine
        create_async_engine("postgresql+asyncpg://user:pass@localhost/db")


def test_sqlite_engine_creation_allowed():
    """Ensure SQLite engines are NOT blocked."""
    from sqlalchemy.ext.asyncio import create_async_engine
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    assert engine is not None
```

- [ ] **Step 4: Run audit tests to verify they work**

Run:
```powershell
$env:AGENTOS_RUNTIME_MODE="grpc"; $env:DATABASE_URL="sqlite+aiosqlite:///:memory:"; $env:REDIS_URL=""; pytest tests/unit/test_connection_audit.py -v --tb=short
```

Expected: 4 tests pass.

- [ ] **Step 5: Run full unit test suite with audit enabled to find violations**

Run:
```powershell
$env:AGENTOS_RUNTIME_MODE="grpc"; $env:DATABASE_URL="sqlite+aiosqlite:///:memory:"; $env:REDIS_URL=""; $env:SECRET_KEY="test-secret-key-for-phase1-only-32bytesx"; $env:OPENAI_API_KEY="test-key-placeholder"; $env:AGENTOS_ENV="test"; pytest tests/unit/ -v --tb=short -x
```

Expected: Identify the FIRST test that fails due to a connection violation. Note the file and line number.

- [ ] **Step 6: Commit**

```bash
git add tests/conftest.py tests/unit/test_connection_audit.py
git commit -m "feat(phase1): add connection audit framework for gRPC mode"
```

---

## Task 2: Remediate Hidden Couplings in Core Code

**Files:**
- Read: `app/bootstrap.py`, `app/config/settings.py`, `app/desktop_entry.py`
- Modify: `app/bootstrap.py`, `app/config/settings.py`

- [ ] **Step 1: Read `app/bootstrap.py` and identify Redis/PG initialization**

Read: `E:\Projects\AgentOS\app\bootstrap.py`

- [ ] **Step 2: Read `app/config/settings.py`**

Read: `E:\Projects\AgentOS\app\config\settings.py`

- [ ] **Step 3: Ensure `settings.py` skips Redis/PG validation in gRPC mode**

Verify that the existing validator:
```python
@model_validator(mode="after")
def check_required_settings(self):
    if self.RUNTIME_MODE.lower() == "grpc":
        return self
    # existing checks...
```

If not present, add this gRPC bypass at the top of the validator.

- [ ] **Step 4: Make `bootstrap.py` skip Redis initialization in gRPC mode**

Locate the Redis initialization block in `bootstrap.py`. Ensure it is wrapped:

```python
from app.config.mode import is_grpc_mode

async def bootstrap():
    # ... other init ...
    if not is_grpc_mode():
        await redis_client.connect()
        await redis_pubsub_client.connect()
    # ... rest of init ...
```

If Redis is unconditionally initialized, add the `is_grpc_mode()` guard.

- [ ] **Step 5: Make `bootstrap.py` skip PostgreSQL initialization in gRPC mode (if SQLite is used)**

If the database initialization block is unconditionally connecting to the URL from settings, and the URL is already SQLite, this may be fine. However, if there is any hardcoded PostgreSQL assumption (e.g., running `pg_isready` checks or creating `asyncpg` pools), gate it behind `is_http_mode()`.

- [ ] **Step 6: Re-run unit tests after core fixes**

Run the same command as Task 1 Step 5. Note if progress was made.

- [ ] **Step 7: Commit**

```bash
git add app/bootstrap.py app/config/settings.py
git commit -m "fix(phase1): gate Redis/PG initialization behind runtime mode checks"
```

---

## Task 3: Fix Unit Tests for gRPC + SQLite Baseline

**Files:**
- Modify: Various `tests/unit/*.py` files as needed

- [ ] **Step 1: Iterate through failing unit tests**

For each test that fails due to Redis/PG connection in gRPC mode:

**Case A — Test is inherently web-specific (tests FastAPI routes, Celery, WS, etc.):**
Add a skip decorator:
```python
import os
import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("AGENTOS_RUNTIME_MODE", "").lower() == "grpc",
    reason="Web-specific test not applicable in gRPC/desktop mode",
)
```

**Case B — Test uses shared fixtures that trigger connections:**
Update the fixture or test to use SQLite-only paths. For example, if a test imports `db` which creates a PostgreSQL engine, ensure `DATABASE_URL` in the test environment is `sqlite+aiosqlite:///:memory:` and that the test does not manually override it to PostgreSQL.

**Case C — Test imports a module that has module-level Redis/PG side effects:**
Refactor the imported module to use lazy initialization (initialize on first use, not at import time).

- [ ] **Step 2: Document each fix in `phase1_report.md` draft**

For each file modified, note:
- File path
- Failure reason (which connection was blocked)
- Fix applied (skip / SQLite switch / lazy init)

- [ ] **Step 3: Verify `pytest tests/unit/` passes**

Run:
```powershell
$env:AGENTOS_RUNTIME_MODE="grpc"; $env:DATABASE_URL="sqlite+aiosqlite:///:memory:"; $env:REDIS_URL=""; $env:SECRET_KEY="test-secret-key-for-phase1-only-32bytesx"; $env:OPENAI_API_KEY="test-key-placeholder"; $env:AGENTOS_ENV="test"; pytest tests/unit/ -v --tb=short
```

Expected: All tests either pass or are skipped with documented justification. Zero unexpected failures.

- [ ] **Step 4: Commit**

```bash
git add tests/
git commit -m "test(phase1): fix unit tests for gRPC + SQLite baseline"
```

---

## Task 4: Fix Integration Tests for gRPC + SQLite Baseline

**Files:**
- Modify: Various `tests/integration/*.py` files as needed

- [ ] **Step 1: Run integration tests with audit enabled**

Run:
```powershell
$env:AGENTOS_RUNTIME_MODE="grpc"; $env:DATABASE_URL="sqlite+aiosqlite:///:memory:"; $env:REDIS_URL=""; $env:SECRET_KEY="test-secret-key-for-phase1-only-32bytesx"; $env:OPENAI_API_KEY="test-key-placeholder"; $env:AGENTOS_ENV="test"; pytest tests/integration/ -v --tb=short -x
```

- [ ] **Step 2: Apply same remediation rules as Task 3**

Skip web-specific integration tests (e.g., WebSocket tests that test FastAPI WS directly, Celery integration tests). Fix tests that should work in gRPC mode but have configuration issues.

- [ ] **Step 3: Verify `pytest tests/integration/` passes**

Expected: All tests either pass or are skipped with documented justification.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/
git commit -m "test(phase1): fix integration tests for gRPC + SQLite baseline"
```

---

## Task 5: Implement Tauri Daemon Lifecycle Commands

**Files:**
- Read: `gui/src-tauri/src/commands/daemon.rs`
- Read: `gui/src-tauri/src/main.rs`
- Read: `gui/src-tauri/Cargo.toml`
- Modify: `gui/src-tauri/src/commands/daemon.rs`
- Modify: `gui/src-tauri/src/main.rs`
- Modify: `gui/src-tauri/Cargo.toml`

- [ ] **Step 1: Read current Tauri daemon command stubs**

Read: `E:\Projects\AgentOS\gui\src-tauri\src\commands\daemon.rs`

- [ ] **Step 2: Read Tauri main to understand command registration**

Read: `E:\Projects\AgentOS\gui\src-tauri\src\main.rs`

- [ ] **Step 3: Read Cargo.toml to check existing dependencies**

Read: `E:\Projects\AgentOS\gui\src-tauri\Cargo.toml`

- [ ] **Step 4: Add `sysinfo` dependency to Cargo.toml**

Add under `[dependencies]`:
```toml
sysinfo = "0.30"
```

- [ ] **Step 5: Implement real daemon commands**

Replace the contents of `gui/src-tauri/src/commands/daemon.rs` with:

```rust
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use sysinfo::{ProcessRefreshKind, RefreshKind, System};
use tauri::AppHandle;

static DAEMON_PROCESS: Mutex<Option<Child>> = Mutex::new(None);

const SUPERVISOR_GRPC_PORT: u16 = 50051;
const SUPERVISOR_HTTP_PORT: u16 = 8080;

#[derive(Debug, serde::Serialize, serde::Deserialize)]
pub struct DaemonStatus {
    pub running: bool,
    pub pid: Option<u32>,
    pub uptime_secs: Option<u64>,
    pub grpc_port: u16,
    pub http_port: u16,
}

fn find_supervisor_process() -> Option<(u32, u64)> {
    let mut system = System::new_with_specifics(
        RefreshKind::new().with_processes(ProcessRefreshKind::everything()),
    );
    system.refresh_processes();

    for (pid, process) in system.processes() {
        if let Some(exe) = process.exe() {
            if exe.to_string_lossy().to_lowercase().contains("supervisor")
                || exe.to_string_lossy().to_lowercase().contains("agentos")
            {
                return Some((pid.as_u32(), process.run_time()));
            }
        }
    }
    None
}

fn is_port_open(port: u16) -> bool {
    std::net::TcpStream::connect(format!("127.0.0.1:{}", port)).is_ok()
}

#[tauri::command]
pub async fn get_daemon_status() -> Result<DaemonStatus, String> {
    let grpc_reachable = is_port_open(SUPERVISOR_GRPC_PORT);
    let http_reachable = is_port_open(SUPERVOR_HTTP_PORT);

    if let Some((pid, uptime)) = find_supervisor_process() {
        Ok(DaemonStatus {
            running: grpc_reachable || http_reachable,
            pid: Some(pid),
            uptime_secs: Some(uptime),
            grpc_port: SUPERVISOR_GRPC_PORT,
            http_port: SUPERVISOR_HTTP_PORT,
        })
    } else {
        Ok(DaemonStatus {
            running: false,
            pid: None,
            uptime_secs: None,
            grpc_port: SUPERVISOR_GRPC_PORT,
            http_port: SUPERVISOR_HTTP_PORT,
        })
    }
}

#[tauri::command]
pub async fn start_daemon(app_handle: AppHandle) -> Result<DaemonStatus, String> {
    let status = get_daemon_status().await?;
    if status.running {
        return Ok(status);
    }

    // Determine supervisor binary path
    // Try: bundled resource, then PATH
    let supervisor_bin = app_handle
        .path_resolver()
        .resolve_resource("binaries/supervisor")
        .or_else(|| {
            // On Windows, look for .exe
            #[cfg(target_os = "windows")]
            {
                app_handle
                    .path_resolver()
                    .resolve_resource("binaries/supervisor.exe")
            }
            #[cfg(not(target_os = "windows"))]
            {
                None
            }
        })
        .unwrap_or_else(|| std::path::PathBuf::from("supervisor"));

    let child = Command::new(&supervisor_bin)
        .env("AGENTOS_RUNTIME_MODE", "grpc")
        .env("DATABASE_URL", "sqlite://~/.agentos/agentos.db")
        .env("REDIS_URL", "")
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| format!("Failed to start supervisor: {}", e))?;

    let pid = child.id();

    // Store child handle
    if let Ok(mut guard) = DAEMON_PROCESS.lock() {
        *guard = Some(child);
    }

    // Wait up to 10 seconds for ports to become reachable
    for _ in 0..100 {
        if is_port_open(SUPERVISOR_HTTP_PORT) || is_port_open(SUPERVISOR_GRPC_PORT) {
            return Ok(DaemonStatus {
                running: true,
                pid,
                uptime_secs: Some(0),
                grpc_port: SUPERVISOR_GRPC_PORT,
                http_port: SUPERVISOR_HTTP_PORT,
            });
        }
        std::thread::sleep(std::time::Duration::from_millis(100));
    }

    Err("Supervisor process started but did not become reachable within 10 seconds".to_string())
}

#[tauri::command]
pub async fn stop_daemon() -> Result<DaemonStatus, String> {
    let status = get_daemon_status().await?;
    if !status.running {
        return Ok(status);
    }

    // Try graceful shutdown via HTTP first
    let client = reqwest::Client::new();
    let _ = client
        .post(format!("http://127.0.0.1:{}/api/v1/shutdown", SUPERVISOR_HTTP_PORT))
        .timeout(std::time::Duration::from_secs(5))
        .send()
        .await;

    // Wait a moment for graceful shutdown
    std::thread::sleep(std::time::Duration::from_secs(2));

    // Check if still running
    let status_after = get_daemon_status().await?;
    if status_after.running {
        // Force kill if still running
        if let Some(pid) = status_after.pid {
            let mut system = System::new_with_specifics(
                RefreshKind::new().with_processes(ProcessRefreshKind::everything()),
            );
            system.refresh_processes();
            if let Some(process) = system.process(sysinfo::Pid::from_u32(pid)) {
                process.kill();
            }
        }
    }

    // Clear stored child handle
    if let Ok(mut guard) = DAEMON_PROCESS.lock() {
        *guard = None;
    }

    Ok(DaemonStatus {
        running: false,
        pid: None,
        uptime_secs: None,
        grpc_port: SUPERVISOR_GRPC_PORT,
        http_port: SUPERVISOR_HTTP_PORT,
    })
}
```

- [ ] **Step 6: Wire commands into Tauri main.rs**

Ensure `main.rs` registers the commands in `tauri::Builder`:

```rust
#[tauri::command]
fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            commands::daemon::get_daemon_status,
            commands::daemon::start_daemon,
            commands::daemon::stop_daemon,
            // ... existing commands ...
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
```

If the existing `main.rs` uses a different module path, adjust accordingly.

- [ ] **Step 7: Add `reqwest` to Cargo.toml if not present**

If `reqwest` is not already in `Cargo.toml`, add:
```toml
reqwest = { version = "0.11", features = ["json"] }
```

- [ ] **Step 8: Verify Rust compilation**

Run:
```powershell
cd E:\Projects\AgentOS\gui\src-tauri; cargo check
```

Expected: Compilation succeeds with zero errors.

- [ ] **Step 9: Commit**

```bash
git add gui/src-tauri/
git commit -m "feat(phase1): implement Tauri daemon lifecycle commands"
```

---

## Task 6: gRPC End-to-End Integration Test

**Files:**
- Create: `tests/integration/test_desktop_e2e.py`

- [ ] **Step 1: Write the gRPC desktop E2E test**

Create `tests/integration/test_desktop_e2e.py`:

```python
import os
import pytest
import asyncio
import subprocess
import time
import signal

pytestmark = pytest.mark.skipif(
    os.environ.get("AGENTOS_RUNTIME_MODE", "").lower() != "grpc",
    reason="Desktop E2E test only runs in gRPC mode",
)


@pytest.fixture(scope="module")
def desktop_runtime():
    """Start Python gRPC runtime as a subprocess for the test module."""
    env = os.environ.copy()
    env["AGENTOS_RUNTIME_MODE"] = "grpc"
    env["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
    env["REDIS_URL"] = ""
    env["SECRET_KEY"] = "test-secret-key-for-e2e-only-32bytesx"
    env["AGENTOS_ENV"] = "test"

    proc = subprocess.Popen(
        ["python", "-m", "app.desktop_entry"],
        cwd=os.path.join(os.path.dirname(__file__), "../.."),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Wait for gRPC port to be reachable
    for _ in range(50):
        try:
            import socket
            s = socket.create_connection(("127.0.0.1", 50051), timeout=0.1)
            s.close()
            break
        except (socket.timeout, ConnectionRefusedError):
            time.sleep(0.1)
    else:
        proc.terminate()
        raise RuntimeError("Python gRPC runtime did not start within 5 seconds")

    yield proc

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.mark.asyncio
async def test_desktop_runtime_health(desktop_runtime):
    """Verify the Python gRPC runtime responds to health checks."""
    from app.proto.grpc_client import GRPCClient

    client = GRPCClient(host="127.0.0.1", port=50051, use_tls=False)
    status = await client.health_check()
    assert status is True


@pytest.mark.asyncio
async def test_desktop_task_creation_and_execution(desktop_runtime):
    """Create a simple task and verify it completes without Redis/PG."""
    from app.proto.grpc_client import GRPCClient
    import sqlite3

    client = GRPCClient(host="127.0.0.1", port=50051, use_tls=False)

    # Create a minimal task
    task_id = await client.create_task(
        query="test noop task",
        config={"max_steps": 1, "timeout": 10},
    )
    assert task_id is not None

    # Give it a moment to execute
    await asyncio.sleep(2)

    # Verify task exists in SQLite (if runtime exposes direct DB access)
    # Otherwise, verify via gRPC GetTask
    task = await client.get_task(task_id)
    assert task is not None
    assert task["query"] == "test noop task"
```

**Note:** The exact gRPC client API may need adjustment based on the actual `GRPCClient` interface. Read `app/proto/grpc_client.py` first and adapt the test to the real API.

- [ ] **Step 2: Read `app/proto/grpc_client.py` to verify API**

Read: `E:\Projects\AgentOS\app\proto\grpc_client.py`

- [ ] **Step 3: Adjust test to match actual gRPC client API**

Update the test with the correct method names and signatures from the client.

- [ ] **Step 4: Run E2E test**

Run:
```powershell
$env:AGENTOS_RUNTIME_MODE="grpc"; $env:DATABASE_URL="sqlite+aiosqlite:///:memory:"; $env:REDIS_URL=""; $env:SECRET_KEY="test-secret-key-for-phase1-only-32bytesx"; $env:OPENAI_API_KEY="test-key-placeholder"; $env:AGENTOS_ENV="test"; pytest tests/integration/test_desktop_e2e.py -v --tb=short -s
```

Expected: Tests pass (may require iteration).

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_desktop_e2e.py
git commit -m "test(phase1): add gRPC desktop end-to-end validation"
```

---

## Task 7: Phase 1 Report

**Files:**
- Create: `docs/superpowers/phase1_report.md`

- [ ] **Step 1: Write Phase 1 report**

Create `docs/superpowers/phase1_report.md` with the following template:

```markdown
# Phase 1: Foundation & Baseline — Report

**Date:** 2026-05-12  
**Status:** Complete  

## 1. Connection Violations Found

| # | Location | Root Cause | Fix Applied |
|---|----------|------------|-------------|
| 1 | ... | ... | ... |

## 2. Tauri Stubs Fixed

| Command | File | Status |
|---------|------|--------|
| `get_daemon_status` | `gui/src-tauri/src/commands/daemon.rs` | Implemented |
| `start_daemon` | `gui/src-tauri/src/commands/daemon.rs` | Implemented |
| `stop_daemon` | `gui/src-tauri/src/commands/daemon.rs` | Implemented |

## 3. Tests Fixed

| Test File | Change |
|-----------|--------|
| ... | ... |

## 4. Tests Skipped (Web-Specific)

| Test File | Justification |
|-----------|---------------|
| ... | ... |

## 5. Remaining Risks

- ...

## 6. Validation Summary

- [ ] Unit tests pass in gRPC mode: **YES / NO**
- [ ] Integration tests pass in gRPC mode: **YES / NO**
- [ ] Tauri daemon commands functional: **YES / NO**
- [ ] gRPC E2E test passes: **YES / NO**
- [ ] Zero Redis/PG connections in gRPC mode: **YES / NO**
```

Fill in the actual data based on the results of Tasks 1-6.

- [ ] **Step 2: Commit report**

```bash
git add docs/superpowers/phase1_report.md
git commit -m "docs(phase1): add Phase 1 completion report"
```

---

## Self-Review

### Spec Coverage
- [x] D1: Connection audit framework → Task 1
- [x] D2: Hidden coupling remediation → Tasks 1-2
- [x] D3: Tauri daemon commands → Task 5
- [x] D4: gRPC E2E validation → Task 6
- [x] D5: Phase 1 report → Task 7

### Placeholder Scan
- [x] No "TBD", "TODO", or vague steps found.
- [x] All code blocks contain actual implementation code.
- [x] All commands include expected outputs.

### Type Consistency
- [x] `DaemonStatus` struct fields are consistent across commands.
- [x] Environment variable names match between plan and spec.

---

*Plan ready for execution.*
