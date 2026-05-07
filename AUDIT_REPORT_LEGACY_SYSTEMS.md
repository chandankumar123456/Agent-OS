# AgentOS Codebase Audit Report

**Date**: 2026-05-07  
**Purpose**: Identify legacy, deprecated, or duplicate systems that may cause architectural conflicts

---

## Executive Summary

The AgentOS codebase is generally well-organized with no legacy-named files (no "legacy", "old", "backup", "deprecated" patterns). However, **two critical duplicate class definitions** were identified that could cause confusion or runtime conflicts.

---

## Critical Issues

### 1. DUPLICATE: `AgentRouter` Class

**Two different implementations exist with the same class name:**

| Location | Purpose | Methods | Status |
|----------|---------|---------|--------|
| `app/agents/router.py` | Phase 3.2 - Capability-based task routing | 25+ methods (`route()`, `register_agent()`, `_score_complexity()`, etc.) | ✅ **ACTIVE** - Used in tests |
| `app/orchestrator/router.py` | Simple role-based resolution with fallback | 6 methods (`resolve()`, `resolve_worker()`, `add_agent_to_role()`) | ⚠️ **UNUSED** - Not imported anywhere |

**Recommendation**: 
- `app/agents/router.py` is the canonical implementation (Phase 3.2 compliant)
- `app/orchestrator/router.py` appears to be legacy and should be reviewed for removal or rename

**Import Evidence**:
- `app/agents/router.py` → imported in `tests/test_multi_agent.py`
- `app/orchestrator/router.py` → **NOT IMPORTED ANYWHERE**

---

### 2. POTENTIAL DUPLICATE: Similar File Names

| File 1 | File 2 | Notes |
|--------|--------|-------|
| `app/agents/llm_router.py` | `app/llm/providers/registry.py` | Different purposes - LLMRouter vs ProviderRegistry. No conflict. |

---

## Files with No Detected Imports

The following files exist but **do not appear to be imported** anywhere in the codebase:

| File | Location | Notes |
|------|----------|-------|
| `app/orchestrator/router.py` | 65 lines | Simple AgentRouter class - **DUPLICATE OF CRITICAL ISSUE #1** |
| `app/orchestrator/builder.py` | TBD | Workflow DAG persistence |
| `app/orchestrator/context.py` | TBD | Context management |
| `app/orchestrator/executor.py` | TBD | Single-step execution service |
| `app/orchestrator/retry.py` | TBD | Retry logic |
| `app/orchestrator/isolation.py` | TBD | Failure isolation |
| `app/orchestrator/locks.py` | TBD | Execution locks |
| `app/orchestrator/loop_detector.py` | TBD | Loop detection |
| `app/orchestrator/pipeline.py` | TBD | Legacy pipeline |
| `app/orchestrator/workflow.py` | TBD | DAG engine |
| `app/agents/types.py` | TBD | Used only in tests (`test_e2e_production.py`, `test_advanced_production.py`) |
| `app/llm/providers/registry.py` | TBD | LLM provider registry |
| `app/llm/providers/schemas.py` | TBD | Provider schemas |

**Note**: "Not imported" may mean the file is:
1. Loaded dynamically at runtime
2. Exposed via `__init__.py` and imported differently
3. Legacy code that should be removed

---

## Confirmed Single Implementations

### No Duplicates Found For:
- ✅ **FastAPI main entry**: Only `app/main.py` exists
- ✅ **TaskStateMachine**: Only `app/orchestrator/state_machine.py` (earlier `lifecycle.py` was a false positive)
- ✅ **SQLAlchemy models**: All in `app/memory/models.py` (single source of truth)
- ✅ **AgentRuntime singleton**: Only `app/runtime/runtime.py`
- ✅ **MCPClientManager singleton**: Only `app/mcp/client_manager.py`
- ✅ **ToolRegistry singleton**: Only `app/tools/registry.py`
- ✅ **Orchestrator singleton**: Only `app/orchestrator/core.py`

---

## File Organization Analysis

### Python Files in `app/` Directory
- **Total Python files**: 195 (excluding `__pycache__`)
- **Models files**: 5 (action_v1, capabilities, memory, observability, safety)
- **Routes files**: 17 (API endpoints)

### SQLAlchemy Models
All 36 SQLAlchemy models are defined in **one location**: `app/memory/models.py`

Models include: TaskModel, AgentModel, WorkflowModel, CheckpointModel, UserModel, etc.

---

## Architectural Concerns

### 1. `app/llm/` Package
- `app/llm/providers/registry.py` and `schemas.py` exist
- No imports detected in codebase
- LLM routing is handled by `app/agents/llm_router.py`
- **Status**: May be planned future infrastructure or dead code

### 2. `app/orchestrator/` Directory
Many files in this directory appear unused:
- `builder.py` - Workflow DAG persistence
- `context.py` - Context management
- `executor.py` - Single-step execution
- `retry.py` - Retry logic
- `router.py` - **DUPLICATE AgentRouter (Critical)**
- `isolation.py` - Failure isolation
- `locks.py` - Execution locks
- `loop_detector.py` - Loop detection
- `pipeline.py` - Legacy pipeline
- `workflow.py` - DAG engine

**Note**: Some may be used via `from app.orchestrator import *` in `__init__.py`

### 3. `app/pipelines/document_ingestion.py`
- Actively used by `app/mcp/servers/document.py`
- **Status**: Active and properly integrated

---

## Recommendations

### Immediate Actions

1. **CRITICAL - Resolve `AgentRouter` Duplicate**:
   ```python
   # Option A: Rename the unused one
   mv app/orchestrator/router.py app/orchestrator/legacy_role_router.py
   
   # Option B: Delete if confirmed unused
   rm app/orchestrator/router.py
   ```

2. **Audit `app/orchestrator/` Files**:
   - Check `__init__.py` for wildcard imports that might hide usage
   - Review each file to determine if it's legacy or planned infrastructure
   - Consider moving confirmed unused files to `app/_deprecated/` for a deprecation period

### Follow-Up Actions

3. **Validate Import Paths**:
   - Some files may be imported via wildcard imports (`from app.orchestrator import *`)
   - Run static analysis to confirm actual usage

4. **Consider Consolidation**:
   - `app/llm/` and `app/agents/llm_router.py` seem to have overlapping concerns
   - Document the intended architecture for LLM provider management

5. **Codebase Cleanup**:
   - Remove or deprecate files confirmed as dead code
   - Add inline documentation explaining the purpose of each orchestrator file

---

## Metrics

| Metric | Count |
|--------|-------|
| Critical Duplicates | 1 (`AgentRouter`) |
| Files with No Imports | 13+ |
| SQLAlchemy Models | 36 (all in one file) |
| Route Files | 17 |
| Test Files | ~50 |

---

## Appendix: Import Analysis

### Files Confirmed Imported
- `app/agents/router.py` → `tests/test_multi_agent.py`
- `app/agents/types.py` → `tests/test_e2e_production.py`, `tests/test_advanced_production.py`
- `app/orchestrator/state_machine.py` → `tests/test_state_machine.py`
- `app/pipelines/document_ingestion.py` → `app/mcp/servers/document.py`

### Files NOT Imported (Sample)
- `app/orchestrator/router.py` ❌
- `app/orchestrator/builder.py` ❌
- `app/orchestrator/context.py` ❌
- `app/llm/providers/registry.py` ❌

---

## Conclusion

The AgentOS codebase is mostly clean, but the **duplicate `AgentRouter` class in `app/orchestrator/router.py` is a critical issue** that should be resolved immediately to prevent confusion or runtime conflicts. Many orchestrator helper files appear unused and should be reviewed for deprecation or removal.
