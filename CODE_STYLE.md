# AgentOS — Code Style Guide

This document defines the coding conventions for the AgentOS codebase. All contributions must follow these standards.

## Python Style

### General Formatting
- **Line length**: 100 characters maximum
- **Indentation**: 4 spaces (no tabs)
- **Quotes**: Single quotes (`'`) for strings unless the string contains a single quote
- **Trailing commas**: Required in multi-line collection literals
- **No semicolons**: One statement per line

### Imports
- Use **absolute imports** within packages (e.g., `from .config.settings import settings`)
- Group imports in this order:
  1. Standard library (`os`, `sys`, `typing`, `asyncio`)
  2. Third-party (`fastapi`, `pydantic`, `langgraph`)
  3. Internal/app modules
- Separate groups with a blank line
- Avoid wildcard imports (`from module import *`)

### Naming Conventions

| Construct | Convention | Example |
|-----------|-----------|---------|
| Classes | PascalCase | `AgentRuntime`, `ToolRegistry` |
| Functions / methods | snake_case | `execute_task`, `get_by_email` |
| Variables | snake_case | `task_id`, `current_step_index` |
| Constants / enum members | UPPER_SNAKE_CASE | `MAX_STEPS_DEFAULT`, `AUTH_UNAUTHORIZED` |
| Private methods / attrs | Leading underscore | `_check_dependencies`, `_initialized` |
| Type variables | PascalCase, descriptive | `AgentState`, `ExecutionState` |
| Modules | snake_case | `client_manager.py`, `settings.py` |

### Type Hints
- All function parameters and return types must be annotated
- Use `typing` generics (`List`, `Dict`, `Optional`, `Union`) for Python < 3.9 compatibility where needed
- Prefer `| None` over `Optional` in Python 3.10+
- Use `TypedDict` for flat state dictionaries (e.g., `AgentState`)
- Use `enum.Enum` or `enum.StrEnum` for enumerated values

### Error Handling
- Raise custom `AgentOSError` for domain errors
- Include structured context: `error_type`, `recoverable`, `code`, `context`, `http_status`
- Use `try/except` with specific exception types; avoid bare `except:`
- Log exceptions with structured JSON logging before re-raising where appropriate

### Async Patterns
- All I/O-bound operations must use `async`/`await`
- Use `asynccontextmanager` for resource lifecycle management (e.g., FastAPI lifespan)
- Prefer `asyncio.Lock` over threading locks
- Use `AsyncMock` and `MagicMock` in tests for async dependencies

### Pydantic Models
- All request/response schemas inherit from `pydantic.BaseModel`
- Settings use `pydantic.BaseSettings` (or `pydantic_settings.BaseSettings` in v2)
- Use `@field_validator` and `@model_validator` for complex validation
- Use `ConfigDict` for model configuration
- Environment variable names are UPPER_CASE in settings classes

### Classes & OOP
- Prefer composition over inheritance
- Use dataclasses or Pydantic models for data containers
- Keep methods focused and short (aim for < 40 lines)
- Document public methods with docstrings (Google style)

---

## TypeScript / React Style

### General Formatting
- **Line length**: 100 characters maximum
- **Indentation**: 2 spaces
- **Semicolons**: Optional but consistent (project uses no trailing semicolons)
- **Quotes**: Single quotes for strings, backticks for template literals

### Naming Conventions

| Construct | Convention | Example |
|-----------|-----------|---------|
| Components | PascalCase | `Dashboard`, `AuthContext` |
| Hooks | camelCase, prefix `use` | `useWebSocket`, `useAuth` |
| Interfaces / Types | PascalCase | `Task`, `ApiClient` |
| Variables / functions | camelCase | `accessToken`, `fetchTasks` |
| Constants | UPPER_SNAKE_CASE | `MAX_RETRY_COUNT` |
| Files | PascalCase for components, camelCase for utilities | `client.ts`, `AuthContext.tsx` |

### TypeScript Patterns
- Use `interface` for object shapes (e.g., `export interface Task { ... }`)
- Mark optional fields with `?`: `query?: string`
- Use union types for nullable values: `string | null`
- Avoid `any` where possible; use `unknown` if the type is truly dynamic
- Export interfaces from API client modules for frontend/backend contract alignment

### React Patterns
- Functional components with hooks (no class components)
- Use `React Context` for global state (auth, theme)
- Custom hooks encapsulate reusable async logic (e.g., `useWebSocket`)
- Protect routes with localStorage token checks
- Prefix unused destructured state variables with `_`

---

## Testing Conventions

### Python Tests
- Framework: **pytest**
- Async tests use `@pytest.mark.asyncio`
- Mock external dependencies with `unittest.mock.patch` + `AsyncMock` / `MagicMock`
- Fixtures should return instantiated objects, not classes
- Test file naming: `test_<module>.py`
- Aim for unit tests per module; integration tests in `tests/integration/`
- One pre-existing failure in `test_executor_node_invokes_tool_when_llm_requests_it` is a known registry mock issue

### Frontend Tests
- Framework: **Vitest** (unit), **Playwright** (E2E)
- E2E tests use unique user emails per run to avoid DB conflicts
- E2E config auto-starts backend via `webServer` in `playwright.config.ts`

---

## Tool Naming Convention

All tools follow the `{server_name}__{tool_name}` format:
- `filesystem__read_file`
- `shell__execute_command`
- `browser_env__launch`
- `desktop_env__open_application`

**Dual-prefix support**: Some tools register aliases for backward compatibility (e.g., `desktop__*` aliases for `desktop_env__*`).

---

## Error Handling Standards

### Error Codes (ErrorCode Enum)
Use SCREAMING_SNAKE_CASE string enum values:
- `AUTH_UNAUTHORIZED`
- `EXECUTION_ERROR`
- `TOOL_NOT_FOUND`
- `VALIDATION_ERROR`

### HTTP Status Mapping
- `AUTH_UNAUTHORIZED` → 401
- `VALIDATION_ERROR` → 422
- `TOOL_NOT_FOUND` → 404
- `EXECUTION_ERROR` → 500 (or 502 for downstream failures)

---

## Documentation Standards

- **README.md**: High-level overview, architecture, setup, and guarantees
- **ARCHITECTURE.md**: Detailed 8-layer stack, data flow diagrams, tech stack table
- **CODE_STYLE.md**: This file — conventions for Python, TypeScript, testing, and naming
- **Inline docstrings**: Google style for public APIs
- **Type annotations**: Serve as living documentation; always present

---

## Configuration & Environment

- All runtime configuration lives in `app/config/settings.py`
- Environment variables are documented in `.env.example`
- Defaults for common settings:
  - `MAX_STEPS_DEFAULT=10`
  - `TIMEOUT_DEFAULT=300`
  - `MAX_RETRIES=3`
  - `OPENAI_MODEL=gpt-4o`
  - `ACCESS_TOKEN_EXPIRE_MINUTES=30`
- Never commit secrets (`.env`, credentials) to version control

---

## Singleton & Lifecycle Patterns

- Module-level singletons are the standard for core services
- Initialization must be idempotent (check `_initialized` flag)
- Use Redis mutex (`SET ... NX EX`) for cross-process singleton initialization
- Clean up resources in exception-safe `close()` methods

---

## Path Handling

- Windows is the primary target OS
- Planner generates OS-aware absolute paths
- Executor normalizes cross-OS hallucinated paths:
  - Unix paths on Windows → remap to current home/desktop
  - Windows paths on Unix → strip drive letter
  - Expand `~` to user home
  - Preserve file extensions during remapping

---

*Last updated: 2026-05-04*
