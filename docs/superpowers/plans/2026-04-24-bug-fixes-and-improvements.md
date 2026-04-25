# AgentOS v2 — Bug Fixes & System Improvements Plan

**Goal:** Fix all critical production bugs, redesign Tool Registry, improve Workflow Orchestrator/Builder, enhance Agent Builder, and implement User Onboarding.

**Tech Stack:** Python 3.11, FastAPI, LangGraph, Celery, React 18, Tailwind CSS, PostgreSQL, Redis

---

## Stream 1: Critical Bug Fixes (Backend)

### Bug 1: Fix 'human' role in LangGraph nodes
**File:** `app/langgraph/nodes.py`  
HumanMessage.type returns 'human', but OpenAI expects 'user'. Add `_to_openai_messages()` mapper and replace all `[{"role": m.type, ...}]` conversions.

### Bug 2: Fix max_tokens null in LLM client
**File:** `app/agents/llm_client.py`  
When `max_tokens=None`, omit it entirely from kwargs. For newer models (gpt-5.x, o1, o3), use `max_completion_tokens` instead of `max_tokens`.

### Bug 3: Fix bytes JSON serialization in checkpointer
**File:** `app/langgraph/checkpointer.py`  
Add custom JSONEncoder/Decoder that handles `bytes` (base64), `datetime`, and `set`. Update `_encode()` and `_decode()` to use them.

### Bug 4: Fix MCP servers 404 (route ordering)
**File:** `app/api/routes/tools.py`  
Move all `/mcp-servers` routes BEFORE `/{tool_name}` so FastAPI doesn't match `tool_name="mcp-servers"` first.

### Bug 5: Fix executor "Extra data" JSON parsing
**File:** `app/agents/llm_client.py` + `app/agents/executor.py`  
Add `_extract_json()` helper that strips markdown fences and extracts first JSON object/array by brace counting. Use it in `complete_json()`. Also add a user message in `ExecutorAgent.execute()`.

---

## Stream 2: Tool Registry Redesign

### Backend
**File:** `app/tools/registry.py`  
- Enhance `RegisteredTool` with `category`, `version`, `health_status`, `use_count`, `tags`, `author`
- Add `list_by_category()`, `get_categories()`, `health_check()`, `run_discovery()`

**File:** `app/api/routes/tools.py`  
- Add `GET /tools/categories`
- Add `GET /tools/health` and `GET /tools/{tool_name}/health`

### Frontend
**File:** `frontend/src/pages/Tools.tsx`  
- Add category filter chips and search bar
- Show health status badges (green/red/gray)
- Add tool detail modal with parameter schema viewer
- Add MCP server connection wizard form

---

## Stream 3: Workflow Orchestrator & Builder

### Backend
**File:** `app/orchestrator/workflow.py`  
- Add `WORKFLOW_TEMPLATES` dict with `sequential_review`, `parallel_research`, `error_recovery`
- Add `list_templates()`, `load_template()`
- Add event callbacks (`on_event`, `_emit`) in `WorkflowEngine`

**File:** `app/orchestrator/builder.py`  
- Add `validate_definition()` that checks missing node refs and cycles

**File:** `app/api/routes/workflows.py`  
- Add `GET /workflows/templates` endpoint

### Frontend
**File:** `frontend/src/pages/WorkflowBuilder.tsx`  
- Add template selector sidebar (3 built-in templates)
- Add `validateWorkflow()` with cycle detection before save/execute
- Fix `executeWorkflow()` to save then create task with `mode: 'workflow'`
- Add tool multi-select to agent node properties panel
- Fetch available tools from API to populate selects

---

## Stream 4: Agent Builder Enhancement

### Frontend
**File:** `frontend/src/pages/AgentBuilder.tsx`  
- Add agent template presets sidebar (Researcher, Coder, Reviewer, Creative)
- Add "Test Agent" panel with prompt input + result output
- Group tools by category in assignment panel
- Show tool descriptions on hover

### Backend
**File:** `app/api/routes/agents.py`  
- No major changes needed; existing CRUD supports all fields

---

## Stream 5: User Onboarding Experience

### Frontend
**File:** `frontend/src/pages/Dashboard.tsx`  
- Add `QuickStartPanel` with 5 preset tasks:
  1. "Research the latest AI news"
  2. "Calculate complex formulas"
  3. "Review and summarize a document"
  4. "Build a simple workflow"
  5. "Create a custom agent"
- Show onboarding tooltip/guide on first visit (check localStorage flag `hasCompletedOnboarding`)
- Replace empty state "No tasks yet" with friendly welcome + quick-start cards

**File:** `frontend/src/pages/Landing.tsx`  
- Add "See Demo" button that shows a short animated walkthrough
- Add 2 example agent cards below feature grid

**New Files:**
- `frontend/src/components/OnboardingModal.tsx` — step-by-step modal (4 steps: Welcome → Dashboard Tour → Create First Task → Explore Builders)
- `frontend/src/components/QuickStartPanel.tsx` — preset task cards

---

## Verification

After all streams complete:
1. Run `pytest tests/` — ensure existing tests still pass
2. Run backend: `uvicorn app.main:app --reload`
3. Run Celery: `celery -A app.queue.tasks worker --pool=solo --loglevel=info`
4. Submit a test task through Dashboard — verify no 400 errors
5. Open Tool Registry — verify MCP servers load (200)
6. Open Workflow Builder — verify templates populate canvas
7. Open Agent Builder — verify templates work and test agent responds
8. Clear localStorage and reload Dashboard — verify onboarding appears
