# Build Plan

## Canonical Roadmap for AgentOS Local-Native Runtime

---

## Project Overview

**Goal:** Transform AgentOS from cloud-centric SaaS to local-native autonomous agent runtime platform  
**Timeline:** 12 months  
**Approach:** 5-phase migration  
**Constraint:** No big-bang rewrite, maintain functionality

---

## Project Phases

### Phase 1: Foundation (Months 1-3)
**Goal:** Establish core infrastructure and local-first architecture

**Key Deliverables:**
- Go supervisor process with Windows service support
- SQLite persistence layer
- CLI skeleton with basic commands
- gRPC IPC foundation
- Python runtime subprocess integration
- Basic session lifecycle management
- Configuration system
- Logging infrastructure

**Success Criteria:**
- [ ] Supervisor runs as Windows service
- [ ] SQLite database operational
- [ ] CLI can start/stop runtime
- [ ] Runtime subprocess launches successfully
- [ ] Basic session persistence works
- [ ] gRPC communication established
- [ ] Configuration system functional

**Dependencies:** None (foundation phase)

**Risk:** Low

---

### Phase 2: Desktop Native (Months 4-7)
**Goal:** Build high-performance local desktop automation engine

**Key Deliverables:**
- Rust desktop automation engine
- Native OS APIs (Windows primary)
- OCR integration (Tesseract)
- Screen capture pipeline
- Input simulation (mouse, keyboard)
- gRPC bridge between Python and Rust
- Action V1 deterministic execution
- Window management
- Desktop context capture

**Success Criteria:**
- [ ] Rust desktop engine runs as subprocess
- [ ] Screen capture <5ms latency
- [ ] Input simulation <10ms latency
- [ ] OCR functional
- [ ] gRPC bridge operational
- [ ] Action V1 migrated from Python
- [ ] DesktopGoalLoop pattern preserved
- [ ] Window detection working

**Dependencies:** Phase 1 complete

**Risk:** Medium (new Rust codebase)

---

### Phase 3: Interfaces (Months 8-10)
**Goal:** Build comprehensive user interfaces

**Key Deliverables:**
- Rust CLI with full feature set
- Rust TUI for operational work
- Tauri GUI with React frontend
- System tray integration
- Session browser
- Real-time log tailing
- Configuration UI
- Multiple UI attach/detach

**Success Criteria:**
- [ ] CLI has parity with GUI features
- [ ] TUI operational
- [ ] Tauri GUI functional
- [ ] System tray working
- [ ] UI can detach without stopping runtime
- [ ] Multiple UIs can connect
- [ ] Session browser working

**Dependencies:** Phase 2 complete

**Risk:** Medium (Tauri learning curve)

---

### Phase 4: Performance (Months 11-12)
**Goal:** Optimize for performance and reliability

**Key Deliverables:**
- Go worker pool for parallel tasks
- Native IPC optimization
- Connection pooling
- Caching layer
- Memory optimization
- Startup time optimization
- Benchmark suite
- Profiling infrastructure

**Success Criteria:**
- [ ] Worker pool operational
- [ ] Performance benchmarks defined
- [ ] Startup time <50ms (CLI)
- [ ] Memory usage bounded
- [ ] Benchmarks passing
- [ ] Profiling tools working

**Dependencies:** Phase 3 complete

**Risk:** Low (optimization only)

---

### Phase 5: Polish (Months 12-14)
**Goal:** Production-ready distribution

**Key Deliverables:**
- Windows installer (MSI)
- Auto-updater
- Documentation
- Tutorial videos
- Example workflows
- Error reporting
- Crash analytics
- Beta testing

**Success Criteria:**
- [ ] Installer working
- [ ] Auto-updater functional
- [ ] Documentation complete
- [ ] Examples working
- [ ] Beta testing complete
- [ ] Production release

**Dependencies:** Phase 4 complete

**Risk:** Low (polish only)

---

## Milestones

### Foundation Milestone
**Date:** End of Month 3  
**Criteria:**
- Supervisor operational
- SQLite working
- CLI functional
- Runtime launches
- Basic sessions work

### Desktop Native Milestone
**Date:** End of Month 7  
**Criteria:**
- Rust desktop operational
- <5ms automation latency
- Action V1 working
- DesktopGoalLoop functional

### Interfaces Milestone
**Date:** End of Month 10  
**Criteria:**
- All UIs functional
- UI detachment works
- Session browser working
- System tray integrated

### Performance Milestone
**Date:** End of Month 12  
**Criteria:**
- Benchmarks passing
- Performance targets met
- Worker pool operational
- Memory optimized

### Production Milestone
**Date:** End of Month 14  
**Criteria:**
- Installer working
- Documentation complete
- Beta tested
- Production release

---

## Migration Sequencing

### Sequence Overview
1. Foundation → Desktop Native → Interfaces → Performance → Polish

### Parallel Work Possible
- Phase 3 (Interfaces) can start before Phase 2 complete (CLI)
- Phase 4 (Performance) can begin as soon as Phase 2 (Desktop) has working automation
- Phase 5 (Polish) can start documentation during Phase 3

### Synchronization Points
- End of Phase 1: Runtime must be stable before Desktop work
- End of Phase 2: Automation must be reliable before UI polish
- End of Phase 3: All interfaces functional before optimization

---

## Subsystem Dependencies

```
┌─────────────────────────────────────────────────────────────┐
│                    DEPENDENCY GRAPH                        │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Supervisor (Go)                                             │
│       │                                                      │
│       ├── SQLite (embedded)                                 │
│       │                                                      │
│       ├── Python Runtime (subprocess)                       │
│       │       │                                              │
│       │       └── LangGraph                                 │
│       │              │                                       │
│       │              └── MCP                                 │
│       │                                                      │
│       └── Rust Desktop (subprocess)                         │
│               │                                              │
│               └── Tesseract OCR                             │
│                                                              │
│  CLI (Rust)                                                  │
│       │                                                      │
│       └── Supervisor gRPC                                   │
│                                                              │
│  TUI (Rust)                                                  │
│       │                                                      │
│       └── Supervisor gRPC                                   │
│                                                              │
│  GUI (Tauri)                                                 │
│       │                                                      │
│       ├── Supervisor gRPC                                   │
│       └── Rust Sidecar                                       │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**Critical Path:**
Supervisor → Python Runtime → Rust Desktop → CLI → TUI → GUI

---

## Implementation Order

### Priority 1: Foundation (Weeks 1-4)
1. Project structure and build system
2. SQLite schema design
3. Go supervisor skeleton
4. gRPC .proto definitions
5. Python runtime subprocess integration
6. Basic CLI commands

### Priority 2: Persistence (Weeks 5-8)
1. Configuration system
2. Session persistence
3. State checkpointing
4. Migration framework
5. Logging infrastructure

### Priority 3: Integration (Weeks 9-12)
1. End-to-end session lifecycle
2. Error handling
3. Recovery mechanisms
4. Testing framework

### Priority 4: Desktop Engine (Months 4-7)
1. Rust project setup
2. Windows API bindings
3. Screen capture
4. Input simulation
5. gRPC integration
6. Action V1 migration
7. OCR integration

### Priority 5: Interfaces (Months 8-10)
1. CLI feature complete
2. TUI development
3. Tauri project setup
4. React UI port
5. System tray

### Priority 6: Performance (Months 11-12)
1. Worker pool
2. Caching
3. Benchmarks
4. Profiling

### Priority 7: Polish (Months 12-14)
1. Installer
2. Documentation
3. Examples
4. Beta testing

---

## Success Criteria (Overall)

### Functional
- [ ] All current AgentOS features work locally
- [ ] Desktop automation <5ms latency
- [ ] Runtime survives UI closure
- [ ] CLI is fully functional
- [ ] GUI is optional
- [ ] Works offline

### Performance
- [ ] CLI startup <50ms
- [ ] Memory usage <500MB idle
- [ ] Session startup <2s
- [ ] Automation success rate >90%

### Quality
- [ ] Zero critical bugs
- [ ] Comprehensive test coverage
- [ ] Documentation complete
- [ ] Examples working

### Distribution
- [ ] Windows installer
- [ ] Auto-updater
- [ ] Beta tested
- [ ] Production ready

---

## Architectural Constraints

**Must Preserve:**
- DesktopGoalLoop pattern
- Action V1 fast path
- MCP ecosystem
- LangGraph orchestration
- Tool registry

**Must Implement:**
- Runtime survives UI closure
- Local-first execution
- CLI primary interface
- SQLite persistence
- gRPC IPC

**Must Not:**
- Require cloud for core automation
- Break existing workflows
- Lose data
- Increase latency
- Add complexity for users

---

## Validation Checkpoints

### Checkpoint 1: Foundation Complete
**When:** End of Month 3  
**Validation:**
- Automated tests pass
- Manual testing complete
- Performance baseline established
- Code review complete
- Documentation started

### Checkpoint 2: Desktop Native Complete
**When:** End of Month 7  
**Validation:**
- Desktop automation works
- Latency benchmarks pass
- Action V1 functional
- Integration tests pass
- Code review complete

### Checkpoint 3: Interfaces Complete
**When:** End of Month 10  
**Validation:**
- All UIs functional
- UI detach works
- Feature parity verified
- User testing complete
- Documentation complete

### Checkpoint 4: Performance Complete
**When:** End of Month 12  
**Validation:**
- Benchmarks pass
- Profiling complete
- Optimizations verified
- No regressions
- Performance report

### Checkpoint 5: Production Ready
**When:** End of Month 14  
**Validation:**
- Installer works
- Beta feedback addressed
- Documentation complete
- Examples working
- Release approved

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Rust learning curve | Training, pair programming, external review |
| Phase delays | Buffer in timeline, parallel work |
| Feature regression | Comprehensive testing, feature parity matrix |
| Performance issues | Benchmarks from day 1, profiling infrastructure |
| User adoption | Beta program, migration guide, documentation |

---

## Resource Requirements

### Development
- 2-3 developers full-time
- 1 Rust specialist (consultant acceptable)
- 1 Go developer
- Existing Python team

### Infrastructure
- Windows development machines
- CI/CD pipeline
- Test automation
- Benchmarking hardware

### External
- Tesseract OCR integration
- gRPC tooling
- Windows code signing certificate
- Installer tooling

---

## Last Updated

**Date:** 2026-05-09  
**By:** Agent  
**Version:** 1.0.0
