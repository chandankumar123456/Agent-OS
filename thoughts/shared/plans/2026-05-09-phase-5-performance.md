# Phase 5: Performance Optimization - Implementation Plan

## Overview
**Phase:** 5 of 5 (Final implementation phase before Polish)
**Timeline:** 2-3 months
**Goal:** Optimize the entire AgentOS system for production use with <100MB memory, <1s startup, and <5ms IPC latency.

## Current State
- Phases 1-4 completed successfully
- CLI (~5MB) and TUI (~4MB) binaries built and tested
- GUI structure complete (Tauri + React)
- All integration tests passing (5/5)
- Desktop automation latency: 4.70ms (target achieved)

## Target Metrics

| Metric | Current | Target | Priority |
|--------|---------|--------|----------|
| Memory Footprint | ~300-500MB | <100MB | P0 |
| Cold Start Latency | ~3-5s | <1s | P0 |
| IPC Latency | ~10-20ms (Redis) | <1ms (Native) | P0 |
| Worker Parallelism | Asyncio (GIL limited) | Goroutines | P0 |
| Binary Size | ~5MB (CLI) | <50MB total | P1 |
| Connection Pool | Basic | Optimized | P1 |

## Workstreams

### Workstream 1: Go Workers (P0) - Month 1-2
**Goal:** Replace Python asyncio workers with Go goroutines for true parallelism

**Tasks:**
1. [ ] Design Go worker architecture
   - Worker pool with goroutines
   - Task queue with channels
   - Python bridge via gRPC/Unix sockets
   - Health monitoring and auto-restart

2. [ ] Implement worker pool
   - `supervisor/workers/pool.go`
   - Dynamic worker scaling (min: 2, max: 100)
   - Task assignment with load balancing
   - Worker lifecycle management

3. [ ] Create Python task executor
   - `app/workers/executor.py`
   - gRPC server for receiving tasks from Go
   - Result streaming back to Go
   - Error handling and recovery

4. [ ] Integration with supervisor
   - Start/stop worker pool with supervisor lifecycle
   - Health checks and metrics
   - Resource limits enforcement

**Deliverables:**
- Go worker pool running
- Task execution via Go workers
- Performance benchmarks showing <1ms task dispatch

### Workstream 2: Native IPC (P0) - Month 1-2
**Goal:** Replace Redis with high-performance native IPC

**Tasks:**
1. [ ] Design IPC architecture
   - Named pipes (Windows) / Unix domain sockets
   - Protocol: gRPC or custom binary
   - Message types: pub/sub, request/response
   - Zero-copy where possible

2. [ ] Implement IPC server
   - `supervisor/ipc/server.go`
   - Channel-based pub/sub
   - Connection pooling
   - Message routing

3. [ ] Create Python IPC client
   - `app/ipc/client.py`
   - Async client with connection pooling
   - Pub/sub subscriptions
   - Automatic reconnection

4. [ ] Replace Redis usage
   - Task queue: IPC channels
   - Session state: Shared memory/SQLite
   - Pub/sub: IPC pub/sub
   - Rate limiting: In-memory with sync

5. [ ] Migration path
   - Feature flag for IPC vs Redis
   - Gradual migration by component
   - Rollback capability

**Deliverables:**
- Native IPC working
- Redis dependency removed
- Latency benchmarks: <1ms local, <5ms cross-process

### Workstream 3: Memory Optimization (P1) - Month 2
**Goal:** Reduce Python runtime memory to <100MB

**Tasks:**
1. [ ] Memory profiling
   - Heap profiling with `tracemalloc`
   - Identify largest allocations
   - Memory leak detection
   - Report: `reports/memory-profile.md`

2. [ ] Optimize data structures
   - Replace dicts with `__slots__` classes
   - Use `pydantic.v1` vs v2 (smaller footprint)
   - Lazy loading for heavy modules
   - String interning for repeated values

3. [ ] Resource cleanup
   - Proper cleanup of MCP connections
   - Close idle database connections
   - Clear LRU caches periodically
   - Dispose of LangGraph checkpoints

4. [ ] Module optimization
   - Optional imports for heavy libraries
   - JIT loading for tools
   - Skip unnecessary initializations
   - Preload only essential modules

**Deliverables:**
- Memory usage <100MB
- Memory profiling report
- Optimization guidelines document

### Workstream 4: Startup Time (P1) - Month 2
**Goal:** Reduce cold start to <1s

**Tasks:**
1. [ ] Startup profiling
   - Profile import times with `python -X importtime`
   - Identify slow imports
   - Measure initialization phases
   - Report: `reports/startup-profile.md`

2. [ ] Lazy loading
   - Defer MCP server startup
   - Lazy load heavy ML models
   - On-demand tool registry
   - JIT agent initialization

3. [ ] Pre-compilation
   - Use `sys.dont_write_bytecode = False`
   - Pre-compile critical modules
   - Consider `mypyc` for hot paths
   - Bundle compiled modules

4. [ ] Caching
   - Tool discovery cache
   - Compiled LangGraph graphs
   - Warm-start with saved state
   - Fast-path for common operations

**Deliverables:**
- Startup time <1s
- Startup profiling report
- Lazy loading architecture

### Workstream 5: Connection Pooling (P2) - Month 2-3
**Goal:** Optimize SQLite and connection usage

**Tasks:**
1. [ ] SQLite optimization
   - Enable WAL mode
   - Connection pooling with `sqlalchemy.pool`
   - Prepared statement caching
   - Batch operations

2. [ ] Connection lifecycle
   - Connection health checks
   - Automatic reconnection
   - Connection timeout tuning
   - Graceful shutdown

3. [ ] Performance tuning
   - SQLite pragmas (cache_size, synchronous)
   - Index optimization
   - Query optimization
   - Vacuum and analyze

**Deliverables:**
- Optimized SQLite with pooling
- Connection management improved
- Query performance benchmarks

## Implementation Order

```
Month 1:
  Week 1-2: Go Workers (architecture + basic pool)
  Week 3-4: Native IPC (architecture + basic implementation)

Month 2:
  Week 1-2: Go Workers (integration + Python bridge)
  Week 3: Native IPC (Redis replacement + migration)
  Week 4: Memory profiling + optimizations

Month 3:
  Week 1: Startup time optimization
  Week 2: Connection pooling + SQLite optimization
  Week 3-4: Testing, benchmarking, and refinement
```

## Success Criteria

### Must Have (P0)
- [ ] Go workers dispatch tasks in <1ms
- [ ] Native IPC latency <1ms (local), <5ms (cross-process)
- [ ] Memory usage <100MB (Python runtime)
- [ ] All existing tests pass

### Should Have (P1)
- [ ] Startup time <1s
- [ ] SQLite with WAL mode and pooling
- [ ] Performance benchmarks document
- [ ] Memory profiling report

### Nice to Have (P2)
- [ ] Connection health monitoring
- [ ] Auto-scaling workers based on load
- [ ] Performance regression tests
- [ ] Startup time profiling report

## Risks and Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| Go/Python bridge complexity | High | Start with simple gRPC, iterate |
| IPC performance not meeting targets | High | Benchmark early, fallback to Redis possible |
| Memory leaks in Python | Medium | Profiling, regular testing |
| Breaking changes | High | Feature flags, gradual migration |
| Time constraints | Medium | Prioritize P0, defer P2 if needed |

## Dependencies

### Technical
- Go 1.21+ (already have)
- Python 3.11+ (already have)
- gRPC for Go and Python
- SQLite with WAL support

### From Previous Phases
- Phase 1: Go supervisor with SQLite
- Phase 2: Rust desktop automation
- Phase 4: CLI/TUI/GUI interfaces

## Testing Strategy

### Unit Tests
- Go worker pool tests
- IPC client/server tests
- Memory tracking tests

### Integration Tests
- End-to-end with Go workers
- IPC with all components
- Performance benchmarks

### Load Tests
- Worker pool stress test
- IPC throughput test
- Memory leak detection

## Documentation

### Required
- Architecture document for Go workers
- IPC protocol specification
- Migration guide (Redis → IPC)
- Performance tuning guide

### Generated
- Memory profiling reports
- Startup time analysis
- Performance benchmarks

## Rollback Plan

If performance improvements fail:
1. Feature flags to disable Go workers (fallback to Python)
2. Redis can be re-enabled for IPC
3. SQLite optimizations are backward compatible
4. Keep Python worker code as fallback

## Next Phase: Phase 6 (Polish)

After Phase 5 completion:
- Installers (WiX for Windows)
- Auto-updater
- Documentation
- Migration guides
- Final benchmarks
- Release candidate

---

**Plan Created:** 2026-05-09
**Last Updated:** 2026-05-09
**Status:** Ready for implementation
