# AgentOS Local-Native Runtime Gap Analysis Report

## Executive Summary

This report documents the architectural gaps between the current **cloud-centric Python runtime** (FastAPI + PostgreSQL + Redis) and the **target local-native architecture** (Go supervisor + gRPC + SQLite + Rust desktop automation) as specified in the design document.

**Overall Assessment**: The current system is a production-grade FastAPI application with LangGraph orchestration, but requires significant architectural changes to meet the local-native vision. **~70% of Python business logic can be preserved**, but **infrastructure and communication layers need complete replacement**.

---

## Architecture Comparison Matrix

| Component | Current State | Target State | Status | Migration Complexity |
|-----------|--------------|--------------|--------|---------------------|
| **Entry Point** | FastAPI HTTP server | Go supervisor binary | 🔴 Missing | High |
| **Persistence** | PostgreSQL + Redis | SQLite (single file) | 🔴 Mismatch | High |
| **LangGraph Checkpointer** | `PostgresSaver` | `SqliteSaver` | 🔴 Wrong Impl | Medium |
| **Long-term Memory** | `PostgresLongTermMemory` | SQLite-based | 🔴 Wrong Impl | Medium |
| **Short-term Memory** | Redis | SQLite/in-memory | 🟡 Partial | Low |
| **Persistent Memory** | Redis + PostgreSQL dual-tier | SQLite single-tier | 🔴 Wrong Impl | Medium |
| **Inter-Process Comm** | HTTP/REST API | gRPC | 🔴 Missing | High |
| **Desktop Automation** | Python (pyautogui/uiautomation) | Rust (<5ms latency) | 🔴 Wrong Tech | High |
| **MCP Transport** | HTTP/stdio | gRPC via Rust bridge | 🔴 Wrong Impl | High |
| **Agent Runtime** | FastAPI-integrated | gRPC service | 🟡 Adaptable | Medium |
| **Orchestration** | LangGraph nodes | LangGraph nodes (preserved) | 🟢 Compatible | Low |
| **Execution State** | Pure Python dataclasses | Preserved with gRPC proto | 🟢 Compatible | Low |
| **Pydantic Models** | Extensive models | Preserved, proto-mapped | 🟢 Compatible | Low |

---

## Critical Gaps

### Gap 1: No gRPC Interface

**Current**: FastAPI HTTP REST API only
- `app/main.py`: HTTP routes, lifespan management, PostgreSQL engine
- `app/api/routes/`: 17 HTTP route modules
- WebSocket for real-time updates

**Target**: gRPC service with proto definitions
- Design doc specifies supervisor communication via gRPC
- Go supervisor already exists (`supervisor/main.go`) with gRPC server
- **Python runtime needs gRPC service implementation**

**Impact**: HIGH - Blocking communication with Go supervisor

**Migration Path**:
```python
# Current (HTTP)
@router.post("/tasks")
async def create_task(...)

# Target (gRPC)
service AgentRuntimeService {
  rpc CreateTask(CreateTaskRequest) returns (CreateTaskResponse);
  rpc StreamTaskEvents(TaskId) returns (stream TaskEvent);
}
```

---

### Gap 2: PostgreSQL Dependency

**Current**: Full PostgreSQL + asyncpg stack
- `DATABASE_URL=postgresql+asyncpg://...`
- `create_async_engine` with connection pooling
- 27 SQLAlchemy models in `app/memory/models.py`
- Alembic migrations

**Target**: SQLite with local-first design
- Single `.db` file in user's home directory
- `aiosqlite` for async support
- Same 27 models, but SQLite-native

**Files to Migrate**:
- `app/config/settings.py` - Database URL configuration
- `app/langgraph/checkpointer.py` - Replace `PostgresSaver` with `SqliteSaver`
- `app/memory/long_term.py` - Replace PostgreSQL repositories
- `app/memory/models.py` - SQLite-compatible schema

**Impact**: HIGH - All persistence layer

---

### Gap 3: Redis Dependency

**Current**: Redis for multiple purposes
- `app/memory/short_term.py`: `RedisClient` singleton
- `app/memory/session_memory.py`: Session state in Redis
- `app/memory/persistent.py`: Dual-tier Redis + PostgreSQL
- Rate limiting, pub/sub, caching

**Target**: SQLite or in-memory for local-native
- SQLite for persistent caching
- In-memory structures for ephemeral data
- Optional: Keep Redis only for multi-instance scenarios

**Files to Migrate**:
- `app/memory/short_term.py` - Replace with SQLite cache
- `app/memory/session_memory.py` - SQLite-backed sessions
- `app/memory/persistent.py` - Single SQLite tier

**Impact**: MEDIUM - Can coexist during transition

---

### Gap 4: No Rust Desktop Bridge Integration

**Current**: Python desktop automation
- `app/environments/desktop_env.py`: `DesktopSession` with UIA
- `app/action_v1/`: Python-based desktop automation
- pyautogui, uiautomation libraries

**Target**: Rust gRPC bridge (<5ms latency)
- Rust desktop automation with native OS APIs
- Protocol Buffers for communication
- Python runtime acts as gRPC client to Rust bridge

**Impact**: HIGH - Performance-critical desktop automation

**Migration Path**:
```python
# Current (Python direct)
desktop_session = DesktopSession()
await desktop_session.click(x, y)

# Target (gRPC to Rust)
stub = DesktopBridgeStub(channel)
await stub.Click(ClickRequest(x=x, y=y))
```

---

### Gap 5: MCP Transport Mismatch

**Current**: HTTP/stdio transports
- `app/mcp/client_manager.py`: `MCPClientManager` with stdio
- Servers in `app/mcp/servers/`
- Direct Python integration

**Target**: gRPC via Rust bridge
- MCP servers run as separate processes
- Communication via gRPC to Rust bridge
- Design doc specifies Rust desktop bridge handles MCP

**Impact**: MEDIUM - Functional but not local-native architecture

---

## Reusable Components (Preserve)

### ✅ LangGraph Engine (90% reusable)
- `app/langgraph/nodes.py` - Node definitions preserved
- `app/langgraph/graphs.py` - Graph compilers preserved
- `app/langgraph/state.py` - AgentState TypedDict preserved
- **Only change**: Checkpointer backend

### ✅ Agent Implementations (95% reusable)
- `app/agents/planner.py` - PlannerAgent logic
- `app/agents/executor.py` - ExecutorAgent with tool grounding
- `app/agents/verifier.py` - VerifierAgent logic
- All multi-agent coordination (coordinator, router, etc.)

### ✅ Tool Registry (80% reusable)
- `app/tools/registry.py` - ToolRegistry singleton
- `app/tools/base.py` - Tool base classes
- `app/tools/validation.py` - Validation pipeline
- **Adaptation needed**: gRPC service wrapper

### ✅ Pydantic Models (100% reusable)
- All request/response models
- Can map directly to Protocol Buffers
- `app/execution_state.py` - Execution state dataclasses

### ✅ Safety & Observability (90% reusable)
- `app/safety/gate.py` - SafetyGate
- `app/safety/audit.py` - Audit trail
- `app/logs/logger.py` - Structured logging
- `app/logs/metrics.py` - Prometheus metrics

### ✅ Execution Logic (95% reusable)
- `app/orchestrator/core.py` - Orchestrator logic
- `app/orchestrator/task_runner.py` - Task runner
- `app/action_v1/` - Action V1 fast path
- **Adaptation**: Remove FastAPI dependencies, add gRPC service wrapper

---

## Components Requiring Replacement

### 🔴 Database Layer (Complete Rewrite)

| File | Current | Replacement |
|------|---------|-------------|
| `app/config/settings.py` | PostgreSQL URLs | SQLite path config |
| `app/memory/models.py` | PostgreSQL-optimized | SQLite-compatible |
| `app/memory/long_term.py` | PostgreSQL repos | SQLite repos |
| `app/langgraph/checkpointer.py` | `PostgresSaver` | `SqliteSaver` |
| `app/memory/persistent.py` | Redis+PG dual-tier | SQLite single-tier |
| `app/memory/session_memory.py` | Redis-backed | SQLite-backed |

### 🔴 Communication Layer (Complete Rewrite)

| File | Current | Replacement |
|------|---------|-------------|
| `app/main.py` | FastAPI app | gRPC service |
| `app/api/routes/` | HTTP routes | gRPC handlers |
| `app/api/ws.py` | WebSocket | gRPC streaming |

### 🔴 Desktop Automation (Complete Rewrite)

| File | Current | Replacement |
|------|---------|-------------|
| `app/environments/desktop_env.py` | Python UIA | gRPC client to Rust |
| `app/action_v1/executor.py` | Python direct | gRPC calls |

---

## Migration Strategy Recommendations

### Phase 1: SQLite Migration (2-3 weeks)

1. **Create SQLite schema** based on existing PostgreSQL models
2. **Replace checkpointer**: `PostgresSaver` → `SqliteSaver`
3. **Replace long-term memory**: PostgreSQL → SQLite
4. **Test**: Ensure all 413 tests pass with SQLite

**Files to modify**:
```
app/config/settings.py        # Add SQLite path
app/langgraph/checkpointer.py # Replace saver
app/memory/long_term.py       # Replace repos
app/memory/models.py          # SQLite-compatible types
```

### Phase 2: gRPC Service (3-4 weeks)

1. **Define proto files** for AgentRuntime API
2. **Create gRPC service** wrapping AgentRuntime
3. **Add streaming support** for task events
4. **Remove HTTP routes** (or keep as legacy)

**New files**:
```
protos/runtime.proto       # Service definition
app/grpc/server.py         # gRPC service implementation
app/grpc/mappers.py        # Proto ↔ Pydantic mapping
```

### Phase 3: Rust Bridge Integration (3-4 weeks)

1. **Create gRPC client** for Rust desktop bridge
2. **Replace Python desktop automation** with gRPC calls
3. **Update MCP transport** to use Rust bridge
4. **Benchmark**: Ensure <5ms latency target

**Files to modify**:
```
app/environments/desktop_env.py   # gRPC client calls
app/mcp/client_manager.py         # Bridge integration
```

### Phase 4: Supervisor Integration (2-3 weeks)

1. **Lifecycle management**: Respond to supervisor signals
2. **Health checks**: gRPC health protocol
3. **Graceful shutdown**: Checkpoint + cleanup

---

## Detailed File-by-File Analysis

### 🔴 Critical Files (Must Replace)

#### `app/main.py` (415 lines)
- **Current**: FastAPI app with lifespan, PostgreSQL engine
- **Target**: gRPC service with supervisor lifecycle hooks
- **Lines to change**: ~80% (lifecycle, database init, HTTP routes)
- **Reusable**: LangGraph initialization logic

#### `app/langgraph/checkpointer.py` (70 lines)
- **Current**: `PostgresSaver` with asyncpg
- **Target**: `SqliteSaver` from langgraph-checkpoint-sqlite
- **Lines to change**: 100%
- **Effort**: Low (LangGraph provides SqliteSaver)

#### `app/memory/long_term.py` (280+ lines)
- **Current**: `PostgresLongTermMemory` with SQLAlchemy async
- **Target**: SQLite repository with aiosqlite
- **Lines to change**: ~70%
- **Reusable**: Repository pattern, query logic

#### `app/memory/persistent.py` (414 lines)
- **Current**: Dual-tier Redis + PostgreSQL
- **Target**: Single SQLite tier
- **Lines to change**: ~60%
- **Reusable**: Memory management logic, LRU pruning

#### `app/config/settings.py` (60 lines)
- **Current**: PostgreSQL, Redis, cloud-centric
- **Target**: SQLite path, local-first
- **Lines to change**: ~40%
- **Note**: Must preserve backward compatibility during transition

### 🟡 Adaptable Files (Partial Changes)

#### `app/runtime/runtime.py` (240 lines)
- **Current**: FastAPI dependency injection
- **Target**: gRPC service with runtime management
- **Lines to change**: ~30%
- **Reusable**: Core agent logic, worker management

#### `app/orchestrator/core.py` (600+ lines)
- **Current**: HTTP-integrated orchestrator
- **Target**: gRPC-integrated orchestrator
- **Lines to change**: ~25%
- **Reusable**: All LangGraph compilation logic

#### `app/mcp/client_manager.py` (380 lines)
- **Current**: Direct stdio/HTTP transport
- **Target**: gRPC via Rust bridge
- **Lines to change**: ~40%
- **Reusable**: Server lifecycle, tool discovery

### 🟢 Preserved Files (Minimal Changes)

#### `app/agents/*.py` (14 files, ~4,500 lines)
- All agent implementations remain unchanged
- Only dependency injection changes
- **Reusability**: 95%+

#### `app/langgraph/nodes.py` (500+ lines)
- LangGraph nodes preserved
- Only checkpointer reference changes
- **Reusability**: 95%+

#### `app/execution_state.py` (198 lines)
- Execution state dataclasses
- Map to proto, preserve logic
- **Reusability**: 100%

#### `app/tools/registry.py` (200+ lines)
- ToolRegistry singleton
- Add gRPC service wrapper
- **Reusability**: 90%

#### `app/safety/*.py` (8 files, ~1,500 lines)
- Safety layer preserved
- **Reusability**: 95%+

#### `app/guardrails/*.py`
- Validation preserved
- **Reusability**: 95%+

---

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| SQLite performance vs PostgreSQL | Medium | High | Benchmark early, consider connection pooling |
| gRPC complexity vs HTTP | Medium | Medium | Keep HTTP as fallback during transition |
| Rust bridge reliability | Medium | High | Graceful fallback to Python automation |
| Migration timeline | High | Medium | Phased approach, preserve existing tests |
| Data loss during migration | Low | Critical | Full backup, incremental migration |

---

## Test Strategy

### Phase 1 Tests (SQLite Migration)
- All 413 existing tests must pass with SQLite
- Add SQLite-specific stress tests
- Benchmark checkpoint save/load times

### Phase 2 Tests (gRPC)
- Proto round-trip tests
- gRPC service integration tests
- Streaming event tests

### Phase 3 Tests (Rust Bridge)
- Desktop automation latency tests
- End-to-end integration tests with Rust bridge
- Load tests for gRPC channels

---

## Estimated Effort

| Phase | Duration | Files Changed | Lines Changed | Complexity |
|-------|----------|---------------|---------------|------------|
| 1. SQLite Migration | 2-3 weeks | 15 files | ~2,000 lines | Medium |
| 2. gRPC Service | 3-4 weeks | 25 files | ~3,500 lines | High |
| 3. Rust Bridge | 3-4 weeks | 10 files | ~1,500 lines | High |
| 4. Integration | 2-3 weeks | 5 files | ~500 lines | Medium |
| **Total** | **10-14 weeks** | **~55 files** | **~7,500 lines** | **High** |

---

## Conclusion

The current Python runtime is well-architected and **~70% of business logic can be preserved** during migration to local-native. The critical gaps are:

1. **Infrastructure layer**: PostgreSQL → SQLite, HTTP → gRPC
2. **Desktop automation**: Python → Rust bridge via gRPC
3. **Communication pattern**: FastAPI monolith → gRPC service

**Recommendation**: Proceed with phased migration starting with SQLite (Phase 1) to de-risk the persistence layer, then gRPC service (Phase 2) to enable supervisor communication, and finally Rust bridge integration (Phase 3) for desktop automation.

The existing LangGraph orchestration, agent logic, safety systems, and tool registry are all compatible with the target architecture and require only adaptation layers, not rewrites.

---

*Report generated: 2026-05-09*
*Based on: design document `2026-05-09-agentos-local-native-redesign.md`*
*Python runtime audit of 87+ files, ~413 tests*
