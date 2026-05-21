# Phase 1 Baseline Test Report

This report captures the pre-refactor baseline for the unified core
runtime migration (branch: `refactor/unified-core-runtime`).  It is the
"freeze the world" snapshot used to detect regressions introduced by
later phases of the refactor.  The aim is to **capture**, not fix,
current failures.

| Field | Value |
| --- | --- |
| Branch | `refactor/unified-core-runtime` (off `main` @ `6d18e9f`) |
| Date | 2025-05-21 |
| Sandbox | Linux x86_64, headless (no display, no Windows automation) |
| Python | 3.11.15 (`.venv` created with `python -m venv`) |
| Pytest | 8.4.2 with `pytest-asyncio` 0.26.0, `pytest-mock` 3.15.1, `pytest-timeout` 2.4.0 |
| Go | 1.25.1 (mise `go@1.25.1`) |
| Rust | 1.92.0, cargo 1.92.0 |

---

## 1. Python (pytest) baseline

### 1.1 New end-to-end smoke test

A new desktop-native smoke test was added at `tests/e2e/test_desktop_smoke.py`.
It boots the existing `app.desktop_native.kernel.AgentKernel` with a stubbed
orchestrator (so it runs offline, no LLM/Redis/Postgres), submits one task,
and exercises the real scheduler, SQLite-backed task queue, state machine,
locks, timeouts, event bus, and resource monitor.

```
$ pytest tests/e2e/test_desktop_smoke.py -v
tests/e2e/test_desktop_smoke.py::test_desktop_kernel_smoke_reaches_terminal PASSED
tests/e2e/test_desktop_smoke.py::test_desktop_kernel_smoke_full_completion XFAIL
========================= 1 passed, 1 xfailed in 4.69s =========================
```

The strict `test_desktop_kernel_smoke_full_completion` is `xfail`'d because
the current `AgentKernel` worker calls
`local_task_state_machine.transition(EXECUTING, COMPLETED)` directly, which
is rejected by the state machine (the documented valid path is
`EXECUTING -> VERIFYING -> COMPLETED`; see
`app/desktop_native/state_machine.py::VALID_TRANSITIONS` and
`app/desktop_native/kernel.py::_worker_loop`).  The unification refactor
(Phase 3) must reroute completion through `VERIFYING`.  Once fixed, this
test should `XPASS` and the `xfail` marker can be removed.

### 1.2 Full suite baseline

Reproducible command (the one specified in `FEAT-001.json`):

```
.venv/bin/python -m pytest tests/ \
    --ignore=tests/stress \
    --ignore=tests/benchmarks \
    --maxfail=20 \
    --tb=line \
    --timeout=20 \
    --timeout-method=thread \
    --no-header \
    --asyncio-mode=auto \
    -p no:cacheprovider
```

`--timeout=20`, `--timeout-method=thread`, and `-p no:cacheprovider` were
added to keep the run within the ~10 minute budget; the spec allows
deviations of this kind.  The wall clock reported by pytest itself was
**10.97s**; the surrounding `timeout 120` cap fired (exit 124) only
because several integration tests leak background asyncio tasks that
prevent the interpreter from exiting cleanly after the test session
completes.  This is itself a baseline finding that the unification
refactor should address.

### 1.3 Numbers

| Metric | Value |
| --- | --- |
| Tests collected (excluding `tests/stress` and `tests/benchmarks`) | **815** |
| Tests run before `--maxfail=20` tripped | **100** |
| Failed | **20** |
| Passed | **67** |
| Skipped | **12** |
| xfailed | **1** (`tests/e2e/test_desktop_smoke.py::test_desktop_kernel_smoke_full_completion` — added in this commit; xfailed because of the kernel `EXECUTING -> COMPLETED` bug described in §1.1) |
| xpassed | 0 |
| Errors | 0 |
| Test execution wall time | 10.97 s |

Because `--maxfail=20` halted execution after 100/815 tests, the failures
listed below are an **incomplete snapshot** of the current failure
universe.  The remaining 715 tests were not exercised in this run.  The
refactor should drive failures toward zero for the modules it touches and
should not introduce new regressions in the modules it does not touch.

### 1.4 Failing tests, categorised

#### A. Test-fixture / DB schema (10 failures, sqlalchemy `no such table: tasks` / `workflows`)

These all fail because the test's in-memory SQLite (`DATABASE_URL=
sqlite+aiosqlite:///:memory:`) is created without running the production
schema migrations; the test infrastructure assumes `tasks` / `workflows`
tables exist but never creates them in the per-test fixture.

- `tests/test_advanced_production.py::test_concurrent_task_creates_do_not_collide`
- `tests/test_advanced_production.py::test_concurrent_status_updates_are_serialized`
- `tests/test_advanced_production.py::test_concurrent_workflow_node_creates`
- `tests/test_advanced_production.py::test_task_failed_state_is_permanent`
- `tests/test_advanced_production.py::test_db_task_create_latency`
- `tests/test_advanced_production.py::test_db_task_read_latency`
- `tests/test_advanced_production.py::test_batch_task_create_performance`
- `tests/test_advanced_production.py::test_no_fallback_data_in_task_result`
- `tests/test_advanced_production.py::test_user_id_isolation`
- `tests/test_advanced_production.py::test_workflow_data_integrity`

Root cause: missing schema bootstrap fixture for the in-memory DB.  Will
be naturally subsumed by the unified `core/` runtime since the new kernel
owns SQLite schema creation.

#### B. Headless / Windows-only desktop automation (8 failures)

Tests in `tests/test_desktop_env.py` assume a real display, `mss`, and
`pyautogui`/`uiautomation` resolve to working back-ends.  In the Linux
headless sandbox they bail out with "Desktop automation unavailable:
running headless (no display detected)".

- `tests/test_desktop_env.py::TestDesktopSession::test_screenshot_success`
- `tests/test_desktop_env.py::TestDesktopSession::test_screenshot_failure`
- `tests/test_desktop_env.py::TestDesktopSession::test_click_safety_bounds`
- `tests/test_desktop_env.py::TestDesktopSession::test_type_text`
- `tests/test_desktop_env.py::TestDesktopSession::test_type_text_skips_sync_wait_for_deterministic_text_apps`
- `tests/test_desktop_env.py::TestDesktopSession::test_type_text_runs_sync_wait_for_non_deterministic_apps`
- `tests/test_desktop_env.py::TestDesktopSession::test_press_key_single`
- `tests/test_desktop_env.py::TestDesktopSession::test_press_key_hotkey`

Root cause: environment-specific (no display).  These will continue to
fail in any headless CI runner; they should be guarded by a
`@pytest.mark.skipif(not _has_display())` marker post-refactor.

#### C. Auth middleware (1 failure)

- `tests/test_auth_middleware.py::test_api_route_is_blocked_without_credentials`
  — assertion `True is False`.  Likely a regression from a recent auth
  middleware change; not blocked by environment.  Real bug to triage.

#### D. Workflow / planner (1 failure)

- `tests/integration/test_target_workflow.py::test_target_workflow_planner_produces_clean_steps`
  — planner returned 1 phase (`['general']`) instead of the expected 4+.
  Likely depends on a real LLM provider; without one the planner falls
  back to a "general" plan.  Will need an offline fixture or a mocked
  planner during the refactor.

### 1.5 Other observations

- The pytest run logs `Task was destroyed but it is pending!` for several
  long-lived background tasks (`stabilizer_screenshot_reaper`, aiosqlite
  worker threads).  This is what causes the interpreter to hang past the
  pytest summary line.  The unified kernel's lifecycle ownership should
  make this strictly easier to clean up.
- A `DeprecationWarning` from `passlib` (`'crypt' is deprecated and slated
  for removal in Python 3.13`) appears once.  Cosmetic.

---

## 2. Go (supervisor) baseline

Reproducible command:

```
cd supervisor && go build ./...
cd supervisor && go test ./...
```

| Step | Result |
| --- | --- |
| `go build ./...` | **OK** (downloaded modules; built `supervisor` binary cleanly) |
| `go test ./...` | **OK** (no test files in any package; exit 0) |

```
?   github.com/AgentOS/supervisor                  [no test files]
?   github.com/AgentOS/supervisor/cmd/supervisor   [no test files]
?   github.com/AgentOS/supervisor/logger           [no test files]
?   github.com/AgentOS/supervisor/proto            [no test files]
?   github.com/AgentOS/supervisor/proto/checkpoint [no test files]
?   github.com/AgentOS/supervisor/proto/runtime    [no test files]
```

Finding: the Go supervisor has zero unit tests today.  The slimmed
`runtime-go/` introduced in Phase 4 should add test coverage for
lifecycle, update, and crypto packages.

---

## 3. Rust baseline

Per-workspace `cargo check` (no `--release`, no `cargo test`) on the
existing four-workspace layout.

| Workspace | Result | Notes |
| --- | --- | --- |
| `cli/` | **FAIL (compile error)** | `error[E0308]` in `src/commands/daemon.rs:123`: `if`/`else` arms have arrays of size 2 vs 1 (`&["-9", "supervisor"]` vs `&["supervisor"]`).  Real bug. |
| `tui/` | **OK** | `Finished `dev` profile [unoptimized + debuginfo] target(s) in 18.00s`. |
| `desktop/` | **FAIL (missing `protoc`)** | `desktop-protocol` build script needs `protoc`; not installed in this sandbox.  Environment-only.  Action: install `protobuf-compiler` in CI / dev images, or bundle a vendored `protoc` like `prost-build`. |
| `gui/src-tauri/` | **FAIL (missing `gdk-3.0`)** | `pkg-config` cannot find `gdk-3.0.pc`; the Tauri shell links against GTK on Linux.  Environment-only.  Action: install `libgtk-3-dev` (and friends) in Linux CI images. |

### 3.1 Failing crate detail

#### `cli/`

```
error[E0308]: `if` and `else` have incompatible types
   --> src/commands/daemon.rs:123:61
    |
123 |             .args(if force { &["-9", "supervisor"] } else { &["supervisor"] })
```

Real source bug; will be fixed when `cli/` moves under `ui/cli/` in
Phase 5 / 6 of the refactor.  Until then this crate cannot build.

#### `desktop/`

```
Error: Custom { kind: NotFound, error: "Could not find `protoc`. ..." }
```

The `desktop-protocol` build script depends on `protoc` being on
`PATH`.  This sandbox does not have `protoc` installed; the existing CI
job (`build-desktop-automation`) presumably pulls it in via the
`actions/setup-*` toolchain.  Phase 4/5 should switch to a vendored
`protoc` (e.g. via `prost-build`'s `protoc-bin-vendored` feature) so
contributor environments do not have to install system packages.

#### `gui/src-tauri/`

```
The system library `gdk-3.0` required by crate `gdk-sys` was not found.
```

Tauri requires GTK system libraries on Linux.  The sandbox is headless
and does not have `libgtk-3-dev`, `libgdk-pixbuf2.0-dev`, etc.
Environment-only.  Phase 6 / `ui/` reorganisation should document the
required apt packages explicitly.

---

## 4. Reproducing this report

```
# Python
python3.11 -m venv .venv
.venv/bin/pip install -U pip wheel
# `google-generativeai` conflicts with `protobuf>=6.31.1` in the existing
# requirements.txt; we filter it out for the baseline run.
grep -v '^google-generativeai' requirements.txt > /tmp/req.txt
.venv/bin/pip install -r /tmp/req.txt pytest-timeout pytest-mock

.venv/bin/python -m pytest tests/e2e/test_desktop_smoke.py -v

.venv/bin/python -m pytest tests/ \
    --ignore=tests/stress --ignore=tests/benchmarks \
    --maxfail=20 --tb=line --timeout=20 --timeout-method=thread \
    --no-header --asyncio-mode=auto -p no:cacheprovider

# Go
(cd supervisor && go build ./... && go test ./...)

# Rust
(cd cli && cargo check)
(cd tui && cargo check)
(cd desktop && cargo check)
(cd gui/src-tauri && cargo check)
```

---

## 5. Summary of regressions to watch in later phases

1. The new e2e smoke test must continue to pass (and the strict variant
   must `xpass` after Phase 3 fixes the `EXECUTING -> COMPLETED`
   transition bug).
2. The 67 currently-passing tests under the maxfail-20 window must stay
   green.
3. The 8 headless / desktop-automation failures and the 10
   missing-schema fixture failures are pre-existing; the refactor is
   not required to fix them but should not multiply them.
4. `cli/` already does not compile on `main`; Phase 5 / 6 must
   re-introduce it under `ui/cli/` in a buildable state.
5. `desktop/` and `gui/src-tauri/` build cleanly in environments with
   `protoc` and the GTK headers; CI images must continue to provision
   these.
6. The Go supervisor builds and "tests" cleanly because it has no
   tests; Phase 4 should add real coverage as it slims down.
