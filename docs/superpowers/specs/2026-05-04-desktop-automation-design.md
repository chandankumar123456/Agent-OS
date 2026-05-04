# AgentOS Desktop Automation Production Hardening — Design Spec

> **Date:** 2026-05-04
> **Based on:** DESKTOP_AUTOMATION_PRD_SRS_PLAN.md, DESKTOP_AUTOMATION_RESEARCH.md, hybrid-perception-research-report.md, production-automation-failure-report.md
> **Status:** Approved

---

## Goal

Close the integration gaps preventing AgentOS desktop automation from reaching production-grade reliability (≥90% success rate). Fix checkpointer redundancy, plug memory leaks (session TTL + screenshot cleanup), add positive desktop recovery strategies, repair tool grounding, and establish a runnable desktop regression benchmark suite.

---

## Architecture

**Hotfix-first, then parallel.** Phase 1 (stabilization) is a single focused PR. Phases 2-5 run as independent streams once stabilization merges. The existing `DesktopGoalLoop`, verifier integration, vision fallback, and infinite-loop detection are preserved unchanged — we only fix what's broken around them.

**Core principle:** Every subsystem gets a single source of truth. The checkpointer uses one upsert path. The session manager owns one reaper task. The recovery engine owns one desktop planner. No redundant fallback layers.

---

## Tech Stack

- **Python 3.12**, FastAPI, LangGraph, SQLAlchemy + asyncpg, Redis, Celery
- **Desktop:** `uiautomation`, `pyautogui`, `pyperclip`, `mss`, `opencv-python-headless`, `pywin32`
- **Vision:** `easyocr`, `transformers`, `ultralytics`, `timm`, `einops`, `supervision`
- **New additions:** `psutil`, `asyncio-throttle`, `pytesseract`, `comtypes`
- **Testing:** pytest, pytest-asyncio, Playwright (for benchmark orchestration)

---

## Component Responsibilities

| Component | File | Responsibility |
|-----------|------|----------------|
| `PostgresCheckpointSaver` | `app/langgraph/checkpointer.py` | Single-path idempotent checkpoint writes via `ON CONFLICT DO NOTHING` |
| `Orchestrator` | `app/orchestrator/core.py` | Delegates to checkpointer; no fragile substring matching |
| `DesktopSessionManager` | `app/environments/desktop_env.py` | TTL enforcement (30min), background `asyncio` reaper task, session timestamps |
| `ActionStabilizer` | `app/environments/execution_stabilizer.py` | Periodic orphaned screenshot cleanup (5min interval via background task) |
| `DesktopRecoveryPlanner` | `app/capabilities/recovery.py` | Positive desktop recovery: REFOCUS, REBUILD_TREE, VISION_ESCALATE, DISMISS_POPUP |
| `ToolGroundingLayer` | `app/tools/grounding.py` | Validated capability-to-tool map; no phantom tools; all mapped tools exist in registry |
| `DesktopBenchmarkSuite` | `tests/benchmarks/desktop/` | pytest plugin + 5 regression tasks (Win32/WPF/Electron/canvas) |

---

## Data Flow

```
Task Submit
    │
    ▼
┌─────────────────┐
│ Orchestrator    │──► Checkpointer (upsert only)
│ (no substring   │
│  matching)      │
└────────┬────────┘
         │
         ▼
┌──────────────────────────────────────────────┐
│ Desktop Automation Subsystem                 │
│                                               │
│  DesktopSessionManager                        │
│   ├── get_or_create_session(task_id)          │
│   ├── _start_cleanup_task()  ◄── asyncio loop │
│   └── close_expired_sessions()                │
│                                               │
│  DesktopGoalLoop (existing, unchanged)        │
│   ├── observe → decide → execute → verify     │
│   └── delegates to ActionStabilizer           │
│                                               │
│  ActionStabilizer                             │
│   ├── execute_with_retry()                    │
│   ├── detect_infinite_loop()                  │
│   └── _start_cleanup_task()  ◄── asyncio loop │
│                                               │
│  RecoveryEngine                               │
│   ├── decide()  ──► DesktopRecoveryPlanner    │
│   │                  ├── REFOCUS              │
│   │                  ├── REBUILD_TREE         │
│   │                  ├── VISION_ESCALATE      │
│   │                  └── DISMISS_POPUP        │
│   └── execute()  ──► enforces DESKTOP gate   │
│                                               │
└──────────────────────────────────────────────┘
```

---

## Error Handling

1. **Checkpointer:** `ON CONFLICT DO NOTHING` silently drops duplicates. No exceptions. No session poisoning.
2. **Session reaper:** Catches and logs all exceptions per-session; never crashes the worker loop.
3. **Recovery planner:** If all strategies exhaust, returns `ESCALATE` with a descriptive reason. Never falls back to browser/shell.
4. **Benchmark suite:** Each task runs in an isolated subprocess. Failure of one task does not abort the suite.

---

## Testing Strategy

- **Unit tests** for every new function/method (`DesktopSessionManager` TTL, `cleanup_temp_screenshots` scheduler, `DesktopRecoveryPlanner` strategies).
- **Integration tests** for checkpointer upsert idempotency and recovery engine desktop gate.
- **Regression benchmarks** (5 tasks) run against real applications: Notepad (Win32), Calculator (UWP/WPF), VS Code (Electron), Paint (canvas-like).
- **Memory profiling** test: run 50 desktop tasks, assert <2MB growth per task.

---

## Security Considerations

- Screenshots retained for debugging have a configurable TTL (default 24h) and live in the system temp directory.
- Recovery planner never escalates to shell/browser for desktop tasks.
- Session reaper does not expose internal session data in logs (logs task_id only, not UI element maps).

---

## Spec Self-Review

1. **Placeholder scan:** No TBDs. All sections complete.
2. **Internal consistency:** Architecture matches the component responsibilities table. Data flow diagram aligns with file changes.
3. **Scope check:** Focused on integration/lifecycle gaps. Does not rewrite `DesktopGoalLoop`, verifier, or vision fallback (they already work).
4. **Ambiguity check:** TTL values (30min session, 5min screenshot, 60s reaper interval) are explicit. Recovery strategies are enumerated.

---

*End of design spec.*
