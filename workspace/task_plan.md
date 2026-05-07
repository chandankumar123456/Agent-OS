# AgentOS Backend Architecture Audit & Consolidation Plan

## Goal
Identify and resolve multiple backend implementations in the AgentOS repository to ensure only ONE canonical backend exists, correctly connected to the frontend.

## Status: 🔄 IN PROGRESS - Phase 1: Brainstorming & Architecture Audit

---

## Phase 1: Brainstorming & Architecture Audit

### Objectives
- Read `workspace/build_plan.md` completely ✅
- Read `workspace/status.md` completely ✅
- Understand Section 2 structure in build_plan.md (5 phases completed)
- Understand 12-section structure of build_plan.md
- Audit repository structure carefully
- Identify all backend implementations
- Identify all API layers, runtimes, services, orchestration systems, routers, execution flows, and agent pipelines
- Identify frontend/backend mappings
- Detect duplicate systems and overlapping functionality
- Determine which backend is actually canonical/current
- Identify dead/stale/partial backend migrations
- Analyze risks before modifying anything

### Current Understanding
From status.md:
- Phases 1-5 COMPLETE (36 components built, 289 tests passing)
- 8-layer architecture: Frontend → API Gateway → Orchestration → LangGraph → Agent Runtime → MCP+Tools → Safety+Observability → Memory+Persistence
- Two execution paths: Action V1 (fast path) and LangGraph (full path)
- Single backend at `app/` directory
- Frontend at `frontend/` directory

### Questions to Answer
1. Are there multiple backend implementations in `app/`?
2. Are there legacy/stale backend directories?
3. Are there duplicate API route definitions?
4. Are there multiple orchestration systems?
5. Are there conflicting execution flows?
6. Is the frontend correctly connected to the canonical backend?

---

## Phase 2: Deep Analysis with Subagents

### Subagent Tasks

#### Task A: Repository Structure Audit
**Scope:** Audit the entire repository structure to identify:
- All Python backend directories
- All API layer definitions
- All orchestration systems
- All execution entry points
- Duplicate or conflicting implementations

**Files to analyze:**
- `app/` directory structure
- `api/` directory structure  
- All `__init__.py` files
- All router definitions
- All main entry points

**Deliverable:** Map of all backend implementations with classification (canonical/stale/duplicate)

#### Task B: API Layer Analysis
**Scope:** Identify all API layers:
- FastAPI app definitions
- Route registrations
- Middleware definitions
- API version conflicts

**Files to analyze:**
- `app/main.py`
- `app/api/routes/*.py`
- `app/api/deps.py`
- `app/api/ws.py`
- All API initialization files

**Deliverable:** Complete API layer map with version conflicts and duplicate routes

#### Task C: Execution Flow Analysis
**Scope:** Identify all execution flows:
- Orchestrator implementations
- LangGraph paths
- Action V1 paths
- Legacy pipeline paths
- Runtime initialization

**Files to analyze:**
- `app/orchestrator/core.py`
- `app/orchestrator/task_runner.py`
- `app/action_v1/runner.py`
- `app/langgraph/nodes.py`
- `app/langgraph/graphs.py`
- `app/runtime/runtime.py`

**Deliverable:** Execution flow diagram with duplicate/conflicting paths identified

#### Task D: Frontend-Backend Mapping Analysis
**Scope:** Verify frontend connects correctly to backend:
- API client configuration
- Endpoint mappings
- WebSocket connections
- Environment variable alignment

**Files to analyze:**
- `frontend/src/api/client.ts`
- `frontend/.env`
- `frontend/src/hooks/useWebSocket.ts`
- `frontend/package.json` proxy settings
- `.env` and `.env.example`

**Deliverable:** Frontend-backend connection map with misalignments identified

#### Task E: Risk Assessment
**Scope:** Based on findings from Tasks A-D:
- Identify critical architectural risks
- Assess impact of duplicate systems
- Determine safest consolidation approach
- Identify what can be safely removed vs. what must be preserved

**Deliverable:** Risk assessment report with consolidation strategy

---

## Phase 3: Consolidation Planning

### Deliverables
1. Detailed cleanup/migration strategy
2. Backend consolidation plan
3. Frontend remapping plan
4. Dependency cleanup plan
5. Testing/validation plan
6. Rollback/risk mitigation plan

---

## Phase 4: Implementation (NOT STARTED)

### Entry Criteria
- All subagent analyses complete
- Consolidation plan approved
- Risk mitigation strategies in place
- Backup/rollback procedures defined

### Exit Criteria
- Only ONE backend implementation exists
- Frontend correctly connects to canonical backend
- All tests pass
- Documentation updated
- No duplicate/conflicting code remains

---

## Next Steps
1. Launch subagents for Tasks A-E
2. Collect and synthesize findings
3. Create Phase 3 consolidation plan
4. Present plan for review
5. Proceed with Phase 4 implementation

---

## Findings Log

### Finding 1: Build Plan Structure
- Section 1: System Breakdown (8 subsystems)
- Section 2: Build Phases (5 phases - COMPLETED per status.md)
- Section 3: Component-Level Tasks (37 tasks - some incomplete)
- Section 4: Execution Flow Design
- Section 5: Data & State Design
- Section 6: Agent System Design
- Section 7: Tool System Design

**Status:** Status.md tracks phases 1-5 of Section 2, but Section 3 tasks may not all be complete.

### Finding 2: Current Architecture
From README and CLAUDE.md:
- Single backend in `app/` directory
- 8-layer stack with clear responsibilities
- LangGraph is primary execution engine
- Action V1 as fast path
- Runtime is ONLY execution entry point
- Frontend in `frontend/` uses Vite + React

**Suspicion:** May be dead/stale code from partial implementations OR multiple similar implementations.

---

## Risks Identified So Far

### Risk 1: Phase 3 Tasks Incomplete
Some Section 3 component-level tasks may not be fully implemented despite status.md showing phases complete.

### Risk 2: Partial Legacy Code
Old implementations may exist that weren't fully removed during migrations.

### Risk 3: Duplicate File Names
Similar files in different directories may cause confusion.

---

## Session Notes
- Started: 2026-05-07
- Planning phase active
- Subagent execution pending
