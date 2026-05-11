# AgentOS: Eliminate All Mock/Stub Data & Fix Remaining Issues

**Goal:** Replace every mock, stub, and placeholder with real implementations. Complete removal of fake data.

**Phases (MUST complete each before moving to next):**

---

## Phase 1: GUI — Replace All Mock Data With Real API Calls
**Files:** `gui/src/pages/AgentBuilder.tsx`, `gui/src/pages/Tools.tsx`, `gui/src/pages/Chat.tsx`
- [ ] AgentBuilder page: Replace hardcoded `AGENTS` array → call `supervisorApi` / `/api/v1/agents` endpoints
- [ ] Tools page: Replace hardcoded `TOOLS` array → fetch from Supervisor or backend
- [ ] Chat page: Show real streaming/progress instead of just task ID

## Phase 2: Supervisor — Add Missing Desktop REST Endpoints
**Files:** `supervisor/server.go`, `supervisor/desktop_handlers.go` (new)
- [ ] Add `/api/v1/desktop/screenshot` route
- [ ] Add `/api/v1/desktop/click` route
- [ ] Add `/api/v1/desktop/type` route
- [ ] Add `/api/v1/desktop/focus` route
- [ ] Add `/api/v1/desktop/windows` route
- [ ] Add `/api/v1/desktop/find` route

## Phase 3: Backend — Fix All Python Stubs/Mocks
**Files:** `app/workers/executor_server.py`, `supervisor/updater.go`
- [ ] Replace all mock returns in executor_server with real LangGraph task execution
- [ ] Implement SHA-256 checksum verification in updater

## Phase 4: Security — Wire TLS Into gRPC & Fix Redis Race
**Files:** `supervisor/server.go`, `app/desktop/grpc_server.py`, `app/config/settings.py`
- [ ] Wire `crypto.go` mTLS into checkpoint gRPC server
- [ ] Add TLS to Python gRPC server
- [ ] Fix Redis validation race at module import time

## Phase 5: Rust — Replace Capture/OCR Stubs With Real Implementations
**Files:** `desktop/desktop-automation/src/capture/mod.rs`, `desktop/desktop-automation/src/ocr/windows.rs`
- [ ] Implement real DXGI screen capture (or delegate to Python gRPC)
- [ ] Implement real OCR (WinRT or delegate to Python gRPC)

---

## Validation
- Every page loads real data (no hardcoded arrays)
- CLI desktop commands return real results (no 404)
- All tests pass
- No `TODO`, `FUTURE`, `MOCK`, `STUB`, `placeholder` in critical paths
