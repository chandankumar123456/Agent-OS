# AgentOS

A desktop-native, local-first autonomous agent runtime. No Redis, no Postgres, no Celery, no FastAPI required by default. One process, one SQLite database, one event loop.

AgentOS executes complex multi-step tasks across desktop GUI, web browser, filesystem, shell, and cloud APIs from a single local runtime. It integrates LangGraph for structured LLM orchestration, an MCP tool server mesh, local-first task scheduling with SQLite persistence, and multi-agent coordination.

**Languages:** Python (asyncio kernel), Go (supervisor), Rust (CLI, TUI, desktop automation, Tauri shell), TypeScript + React (GUI frontend)

**IPC:** gRPC over Unix domain sockets (UDS). No HTTP required for local operation.

---

## Architecture

```
+-------------------+       gRPC-over-UDS        +---------------------+
|   UI Clients      | <========================> |   core/ (Python)    |
|                   |   ~/.agentos/ipc.sock      |                     |
|  - cli (Rust)     |                            |  AgentKernel        |
|  - tui (Rust)     |                            |  - Scheduler        |
|  - Tauri GUI      |                            |  - State Machine    |
|  - React frontend |                            |  - SQLite Store     |
+-------------------+                            |  - LangGraph        |
                                                 |  - MCP Tools        |
+-------------------+                            |  - Event Bus        |
|  runtime-go/      |                            +---------------------+
|  (Go supervisor)  |                                     |
|  - Process lifecycle                                    |
|  - Auto-update    |                            +---------------------+
|  - Crypto/signing |                            |  native/ (Rust)     |
+-------------------+                            |  - desktop-automation
                                                 |  - ipc-protocol     |
                                                 |  - sandbox          |
                                                 +---------------------+
```

The **kernel** (`core/`) is the single source of truth. All UI clients connect via gRPC over a Unix domain socket. The Go supervisor manages process lifecycle, auto-updates, and binary signing but contains zero business logic. The Rust `native/` workspace provides performance-critical desktop automation and the IPC protocol definitions.

---

## Folder Layout

```
core/               Python unified runtime (kernel, scheduler, state machine, adapters)
runtime-go/         Go process supervisor (lifecycle, update, crypto)
native/             Rust workspace: desktop-automation, ipc-protocol, sandbox
ui/                 Unified UI workspace: cli, tui, src-tauri, ipc-client, React frontend
proto/              Canonical .proto files (runtime.proto, checkpoint.proto, worker.proto)
tests/              pytest test suites (unit, integration, e2e, smoke, stress, benchmarks)
docs/               Documentation and migration history
scripts/            Utility scripts (migrations, validation)
migrations/         SQL migration files
docker/             Dockerfile and docker-compose for optional containerized deployment
pyproject.toml      Python package definition with optional extras
```

---

## Quickstart

### Prerequisites

- Python 3.11+
- Go 1.22+ (for supervisor)
- Rust 1.83+ (for native crates and UI binaries)
- Node 18+ with pnpm (for React frontend)

### Install and Run

```bash
# Clone
git clone https://github.com/Chandankumar123456/agentos.git
cd agentos

# Install Python runtime (editable mode with dev dependencies)
pip install -e '.[dev]'

# Start the kernel
python -m core
```

The kernel starts and listens on `~/.agentos/ipc.sock` (or `$XDG_RUNTIME_DIR/agentos.sock`).

In another terminal, run the CLI, TUI, or GUI:

```bash
# Rust CLI (from ui/ workspace)
cd ui && cargo run --bin agentos-cli

# Or start the Tauri desktop app
cd ui && cargo tauri dev
```

### Custom socket path

```bash
python -m core --socket-path /tmp/my-agent.sock
```

### With HTTP adapter (optional)

```bash
pip install -e '.[http]'
python -m core --http --http-port 8000
```

---

## Optional Adapters

The default runtime uses only SQLite and gRPC. External infrastructure is available via pip extras:

| Extra        | Install command              | Use case                                                  |
|--------------|------------------------------|-----------------------------------------------------------|
| `[http]`     | `pip install -e '.[http]'`   | FastAPI HTTP/WebSocket adapter for browser-based clients   |
| `[redis]`    | `pip install -e '.[redis]'`  | Shared pub/sub and caching across multiple kernel instances|
| `[postgres]` | `pip install -e '.[postgres]'` | Durable task/checkpoint storage for production clusters |
| `[celery]`   | `pip install -e '.[celery]'` | Distributed task execution across worker nodes            |
| `[desktop]`  | `pip install -e '.[desktop]'` | Desktop GUI automation (Playwright, pyautogui)           |
| `[vision]`   | `pip install -e '.[vision]'` | Vision models for screen understanding                   |

These are additive. The core runtime never imports them unless explicitly enabled.

---

## IPC Contract

All components communicate via gRPC defined in `proto/`:

| File               | Services                                                    |
|--------------------|-------------------------------------------------------------|
| `runtime.proto`    | RuntimeService: CreateTask, GetTask, ListTasks, CancelTask, StreamTaskEvents, HealthCheck |
| `checkpoint.proto` | CheckpointService: SaveCheckpoint, GetCheckpoint, ListCheckpoints |
| `worker.proto`     | WorkerExecutor: ExecuteTask, HealthCheck                    |
| `desktop.proto`    | DesktopService: desktop automation RPCs                     |

**Transport:** gRPC over Unix domain sockets (UDS).

**Default socket:** `~/.agentos/ipc.sock`

**Windows:** Named pipe at `\\.\pipe\agentos-ipc`

**TCP fallback:** `localhost:50051` (set via `--socket-path localhost:50051`)

### Regenerating stubs

```bash
# Python
python -m grpc_tools.protoc -I proto \
  --python_out=core/proto --grpc_python_out=core/proto \
  proto/*.proto

# Go
protoc -I proto --go_out=runtime-go/internal/proto \
  --go-grpc_out=runtime-go/internal/proto proto/*.proto

# Rust (handled by build.rs in native/ipc-protocol)
cd native && cargo build
```

---

## Building from Source

### Python (core/)

```bash
pip install -e '.[dev]'
python -m core --help
```

### Go (runtime-go/)

```bash
cd runtime-go
go build ./...
```

### Rust - Native crates (native/)

```bash
cd native
cargo build --workspace
```

### Rust - UI binaries (ui/)

```bash
cd ui
cargo build --workspace
```

### React frontend (ui/)

```bash
cd ui
pnpm install
pnpm build
```

### Tauri desktop app

```bash
cd ui
cargo tauri build
```

---

## Running Tests

### Python

```bash
# Full suite
pytest tests/ --ignore=tests/stress --ignore=tests/benchmarks \
  --maxfail=20 --timeout=20 --asyncio-mode=auto

# E2E only
pytest tests/e2e/ -v

# Smoke test
pytest tests/e2e/test_desktop_smoke.py -v
```

### Go

```bash
cd runtime-go
go test ./...
```

### Rust

```bash
# Native crates
cd native && cargo test --workspace

# UI binaries
cd ui && cargo test --workspace
```

### Linting

```bash
# Python
ruff check core/ tests/
mypy core/ --ignore-missing-imports

# Go
cd runtime-go && go vet ./...

# Rust
cd native && cargo clippy --workspace -- -D warnings
cd ui && cargo clippy --workspace --exclude agentos-tauri -- -D warnings
```

---

## Contributing

1. Fork and create a feature branch
2. Make changes following existing code style
3. Run the full test suite and linters
4. Submit a pull request

Key rules:
- No FastAPI imports outside `core/adapters/http.py`
- No Redis/Celery/Postgres in default code paths (adapters only)
- Single asyncio loop in the kernel
- Single SQLite writer task
- Zero business logic in `ui/`
- Canonical proto source of truth is `proto/`

---

## License

MIT License. See [LICENSE](./LICENSE) for details.
