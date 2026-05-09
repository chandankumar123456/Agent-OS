# AgentOS — Production-Grade AI Agent Operating System

> **AgentOS is NOT a chatbot.** It is a structured, stateful agent execution system where AI agents reason via LangGraph state machines and act on the system via the Model Context Protocol (MCP). Every execution is traceable, checkpointed, and observable.

---

## Table of Contents

1. [Overview](#overview)
2. [Key Features](#key-features)
3. [Architecture](#architecture)
4. [System Components](#system-components)
5. [Execution Flow](#execution-flow)
6. [Core Components](#core-components)
7. [MCP Integration](#mcp-integration)
8. [Agents](#agents)
9. [Agent Runtime](#agent-runtime)
10. [Safety & Observability](#safety--observability)
11. [Memory & Persistence](#memory--persistence)
12. [Frontend](#frontend)
13. [API Reference](#api-reference)
14. [gRPC Services](#grpc-services)
15. [WebSocket Interface](#websocket-interface)
16. [Testing](#testing)
17. [Tech Stack](#tech-stack)
18. [Setup & Installation](#setup--installation)
19. [Configuration](#configuration)
20. [System Guarantees](#system-guarantees)
21. [Project Structure](#project-structure)
22. [Development Guide](#development-guide)
23. [Production Deployment](#production-deployment)
24. [Troubleshooting](#troubleshooting)
25. [Contributing](#contributing)
26. [License](#license)

---

## Overview

AgentOS executes complex AI workflows through a **closed-loop execution model**: observe → decide → act → verify → recover. The system receives user queries, classifies task capabilities, routes to appropriate execution paths, and manages the entire agent lifecycle with production-grade reliability.

### Dual Runtime Modes

AgentOS supports two deployment modes:

1. **Cloud Mode (HTTP)** - FastAPI + PostgreSQL + Redis for multi-tenant SaaS
2. **Local-Native Mode (gRPC)** - Go Supervisor + SQLite + gRPC for local execution

For simple, deterministic tasks (browser navigation, file operations, desktop automation), **Action V1** bypasses the full LangGraph overhead and executes directly via MCP tools. Complex or ambiguous tasks flow through the full **LangGraph StateGraph** (planner → executor → verifier → approval → summarizer). Human approval gates pause execution via LangGraph `interrupt()`. Every LangGraph step is checkpointed for resume across restarts.

---

## Key Features

### 🚀 Performance
- **<5ms gRPC latency** between supervisor and runtime
- **~40ms startup time** for local-native mode
- **~25MB memory footprint** for supervisor
- **~5MB CLI binary** for command-line operations

### 🔒 Safety
- **15 system guarantees** for production reliability
- **Guardrails** with blocked pattern detection
- **RBAC** with 6 role types
- **Audit trail** with cryptographic hash chaining
- **Approval gates** for sensitive operations

### 🛠️ Tool Integration
- **7 MCP servers** with 60+ tools
- **Auto-discovery** of MCP tools
- **Tool namespacing** (`{server}__{tool}`)
- **Safety gates** for irreversible operations

### 📊 Observability
- **Prometheus metrics** with 20+ counters and histograms
- **Distributed tracing** with span management
- **Anomaly detection** with statistical analysis
- **Structured logging** with JSON output
- **Cost tracking** per task/agent/tool

### 🔄 Resilience
- **Checkpoint/resume** across restarts
- **Automatic retry** with exponential backoff
- **Circuit breaker** for failure isolation
- **Graceful degradation** on component failure

---

## Architecture

AgentOS is organized into 8 layers, each with strict single responsibility:

### 8-Layer Architecture Stack

```
┌─────────────────────────────────────────────────────────────┐
│ Layer 1 — Frontend (React 19 + Vite + Tailwind CSS)          │
├─────────────────────────────────────────────────────────────┤
│ Layer 2 — API Gateway (FastAPI + JWT + Rate Limiting)        │
├─────────────────────────────────────────────────────────────┤
│ Layer 3 — Orchestration (Orchestrator + Mode Strategy)       │
├─────────────────────────────────────────────────────────────┤
│ Layer 4 — LangGraph Engine (plan→exec→verify→summarize)      │
├─────────────────────────────────────────────────────────────┤
│ Layer 5 — Agent Runtime (Singleton + Pool + Factory)         │
├─────────────────────────────────────────────────────────────┤
│ Layer 6 — MCP + Tools (7 MCP servers + ToolRegistry)        │
├─────────────────────────────────────────────────────────────┤
│ Layer 7 — Safety + Observability (Guardrails + Metrics)     │
├─────────────────────────────────────────────────────────────┤
│ Layer 8 — Persistence (PostgreSQL/SQLite + Redis + Checkpoints) │
└─────────────────────────────────────────────────────────────┘
```

### Layer Responsibilities

| Layer | Responsibility | Technology |
|-------|---------------|------------|
| Frontend | Structured agent interface | React 19, Vite 8, Tailwind CSS 3.4, TypeScript |
| API Gateway | Request routing, validation, auth | FastAPI 0.121+, Uvicorn, Pydantic 2.12+ |
| Orchestration | Mode selection, LangGraph compilation, fallback | LangGraph 1.1+, LangChain |
| LangGraph Engine | Graph-native execution: plan → execute → verify → summarize | LangGraph StateGraph |
| Agent Runtime | Singleton worker registry, lifecycle, concurrency | Asyncio, Semaphore (max 100) |
| MCP + Tools | System-level tools via MCP protocol | FastMCP, stdio transport |
| Safety + Observability | Validation, tracing, metrics, structured logging | Pydantic, Prometheus |
| Memory + Persistence | PostgreSQL/SQLite long-term, Redis short-term, checkpoints | SQLAlchemy async 2.0+, Redis 7+ |

### Multi-Language Architecture

AgentOS uses a polyglot architecture for optimal performance:

| Component | Language | Purpose | Binary Size |
|-----------|----------|---------|-------------|
| Supervisor | Go | Service orchestration, SQLite persistence | ~23MB |
| Runtime Core | Python | LangGraph agent execution, MCP tools | N/A (source) |
| Desktop Bridge | Rust | Native Windows automation | ~5MB |
| CLI | Rust | Command-line interface | ~5MB |
| TUI | Rust | Terminal user interface | ~8MB |
| GUI | Tauri + React | System tray, desktop interface | ~15MB |

---

## System Components

### Component Overview

| Component | Files | Lines | Purpose |
|-----------|-------|-------|---------|
| **Python Runtime** | 320 | ~45,000 | Core agent execution |
| **Go Supervisor** | 25 | ~8,000 | Service orchestration |
| **Rust CLI** | 15 | ~3,500 | Command-line tools |
| **Rust Desktop** | 12 | ~2,800 | Native automation |
| **Frontend** | 97 | ~12,000 | React web interface |
| **Tests** | 98 | ~18,000 | Comprehensive test suite |
| **Proto** | 3 | ~800 | gRPC definitions |

### Component Communication

```
┌─────────────┐     HTTP/WebSocket      ┌─────────────┐
│   Frontend  │◄──────────────────────►│   FastAPI   │
│  (React)    │                        │   Gateway   │
└─────────────┘                        └──────┬──────┘
                                              │
                                              │ gRPC/HTTP
                                              ▼
                                       ┌─────────────┐
                                       │  Supervisor │
                                       │    (Go)     │
                                       └──────┬──────┘
                                              │ gRPC
                                              ▼
                                       ┌─────────────┐
                                       │   Runtime   │
                                       │  (Python)   │
                                       └──────┬──────┘
                                              │ gRPC
                                              ▼
                                       ┌─────────────┐
                                       │   Desktop   │
                                       │   (Rust)    │
                                       └─────────────┘
```

---

## Execution Flow

### Two Execution Paths

AgentOS provides two execution paths optimized for different task types:

#### 1. Action V1 Fast Path (Deterministic)

**For simple tasks**: file operations, browser navigation, desktop automation

**Flow**:
```
User Query → CapabilitySelector → DeterministicExecutor → DeterministicVerifier → Result
```

**States**:
```
PENDING → EXECUTING → VERIFYING → COMPLETED
   ↓
FAILED
```

**Characteristics**:
- Bypasses LangGraph entirely for speed
- Direct MCP tool execution
- Deterministic verification
- No human approval required
- Sub-second execution

#### 2. LangGraph Full Path (Complex Tasks)

**For complex tasks**: multi-step workflows, ambiguous queries, collaboration

**Flow**:
```
User Query → planner_node → executor_node → verifier_node → approval_node → summarizer_node
```

**States**:
```
PENDING → PLANNING → EXECUTING → VERIFYING → AWAITING_APPROVAL → COMPLETED
   ↓          ↓           ↓           ↓              ↓
FAILED ←─── FAILED ←─── FAILED ←─── FAILED ←───── REJECTED
```

**Characteristics**:
- Full LangGraph StateGraph execution
- Multi-step planning with DAG validation
- Human approval gates via `interrupt()`
- Checkpoint resume across restarts
- Comprehensive observability

### State Machine Transitions

| From | To | Trigger | Failure Mode |
|------|-----|---------|--------------|
| PENDING | PLANNING | Orchestrator accepts task | Validation failure → FAILED |
| PLANNING | EXECUTING | Planner generates plan | Planning timeout → FAILED |
| EXECUTING | VERIFYING | All steps executed | Step failure → retry → FAILED |
| VERIFYING | AWAITING_APPROVAL | Verification passes + approval required | Verification fails → replan or FAILED |
| VERIFYING | COMPLETED | Verification passes + no approval | Verification fails → replan or FAILED |
| AWAITING_APPROVAL | COMPLETED | User approves | User rejects → REJECTED, Timeout → FAILED |
| Any | FAILED | Unrecoverable error | N/A |

---

## Core Components

### AgentState TypedDict

Central state dict flowing through LangGraph nodes with 40+ fields:

```python
class AgentState(TypedDict, total=False):
    # Identity
    task_id: str
    user_id: str
    trace_id: str
    
    # Input
    query: str
    config: Dict[str, Any]
    
    # Conversation
    messages: Annotated[List[BaseMessage], add_messages]
    
    # Planning
    plan: List[Dict[str, Any]]
    current_step_index: int
    
    # Execution
    steps: List[Dict[str, Any]]
    step_results: List[Dict[str, Any]]
    tool_calls: List[Dict[str, Any]]
    execution_state: Dict[str, Any]
    
    # Verification
    verified: bool
    verification_notes: str
    
    # Approval
    approved: bool
    approval_reason: str
    
    # Extended
    task_state: str
    idempotency_key: str
    priority: str
    complexity_score: float
    cost_estimate_usd: float
    actual_cost_usd: float
    memory_profile_id: str
    artifact_refs: List[str]
    handoff_log: List[Dict[str, Any]]
    feedback_records: List[Dict[str, Any]]
    audit_trail: List[Dict[str, Any]]
```

### State Field Categories

| Category | Key Fields | Purpose |
|----------|------------|---------|
| Identity | `task_id`, `user_id`, `trace_id` | Unique identification |
| Input | `query`, `config` | User input and configuration |
| Conversation | `messages` | Chat history with reducer |
| Planning | `plan`, `current_step_index` | Execution plan tracking |
| Execution | `steps`, `step_results`, `tool_calls` | Step execution tracking |
| Verification | `verified`, `verification_notes` | Quality validation |
| Approval | `approved`, `approval_reason` | Human approval state |
| Extended | `complexity_score`, `cost_estimate_usd` | Analytics and costing |

### Key Singletons

AgentOS uses singleton pattern for core components to ensure single instance across the application:

| Singleton | Location | Purpose | Thread-Safe |
|-----------|----------|---------|-------------|
| `AgentRuntime` | `app/runtime/runtime.py` | Agent lifecycle, worker registry | Yes (asyncio.Lock) |
| `MCPClientManager` | `app/mcp/client_manager.py` | MCP server lifecycle, tool discovery | Yes |
| `ToolRegistry` | `app/tools/registry.py` | Built-in + MCP tool registration | Yes |
| `Orchestrator` | `app/orchestrator/core.py` | Mode selection, LangGraph compilation | Yes |
| `ApprovalStore` | `app/safety/approval_store.py` | Per-session approval state | Yes |

### Singleton Pattern Implementation

```python
class AgentRuntime:
    _instance: Optional['AgentRuntime'] = None
    _lock = asyncio.Lock()

    def __new__(cls, max_agents: int = 100) -> 'AgentRuntime':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    async def initialize(self) -> None:
        if self._initialized:
            return
        async with self._lock:
            if self._initialized:
                return
            # Initialize workers, pools, etc.
            self._initialized = True
```

---

## MCP Integration

### Model Context Protocol

AgentOS uses MCP for system-level tool access with **7 stdio-based MCP servers** providing **60+ tools**:

### Available MCP Servers

| Server | Tools | Purpose | Transport |
|--------|-------|---------|-----------|
| **filesystem** | 4 | File read, write, list, search | stdio |
| **shell** | 3 | Command execution with blocked command detection | stdio |
| **cloud_api** | 5 | HTTP requests, web scraping, DuckDuckGo search | stdio |
| **browser_env** | 10 | Playwright-based browser automation | stdio |
| **desktop** | 22 | Windows UI automation (uiautomation, pyautogui) | stdio |
| **document** | 8 | PDF/DOCX/TXT/Markdown parsing and chunking | stdio |
| **code_executor** | 1 | Sandboxed Python execution with AST validation | stdio |

### Tool Naming Convention

All MCP tools follow `{server_name}__{tool_name}`:

```python
# Examples
"filesystem__read_file"
"filesystem__write_file"
"filesystem__list_directory"
"filesystem__search_files"

"shell__execute_command"
"shell__execute_script"
"shell__get_system_info"

"browser_env__navigate"
"browser_env__click"
"browser_env__type"
"browser_env__screenshot"

"desktop__screenshot"
"desktop__click"
"desktop__type"
"desktop__get_window_info"

"cloud_api__search_web"
"cloud_api__fetch_url"
"cloud_api__download_file"
```

### MCP Client Manager

```python
class MCPClientManager:
    """Manages connections to MCP servers and routes tool calls."""
    
    async def connect_stdio(self, name: str, command: str, args: List[str]) -> None:
        """Connect to an MCP server via stdio transport."""
        
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> CallToolResult:
        """Execute a tool by its unified name."""
        
    async def start_system_servers(self) -> None:
        """Start all built-in MCP servers."""
```

### Tool Registry

```python
class ToolRegistry:
    """Registry for built-in and MCP tools."""
    
    def register(self, tool: BaseTool) -> None:
        """Register a tool (idempotent)."""
        
    def discover_mcp_tools(self) -> List[MCPWrappedTool]:
        """Discover tools from MCP servers."""
        
    def get_tool(self, name: str) -> Optional[BaseTool]:
        """Get a tool by name."""
```

---

## Agents

### Core Agents

| Agent | Location | Responsibility | LLM Model |
|-------|----------|---------------|-----------|
| **PlannerAgent** | `app/agents/planner.py` | Decomposes queries into execution plans with DAG validation | gpt-4o |
| **ExecutorAgent** | `app/agents/executor.py` | Executes steps with tool grounding and path remapping | gpt-4o |
| **VerifierAgent** | `app/agents/verifier.py` | Validates outputs with quality scoring | gpt-4o-mini |

### Multi-Agent Coordination

| Component | Location | Purpose |
|-----------|----------|---------|
| **CoordinatorAgent** | `app/agents/coordinator.py` | Fan-out/fan-in workflows with DAG execution |
| **ReviewerAgent** | `app/agents/reviewer.py` | Schema/quality validation with strict mode |
| **InterAgentHandoff** | `app/agents/handoff.py` | State transfer with SHA-256 signatures |
| **AgentFeedbackLoop** | `app/agents/feedback.py` | Pattern analysis and learning insights |
| **ConsensusEngine** | `app/agents/consensus.py` | Multi-agent agreement (majority, weighted, unanimous) |
| **AgentRouter** | `app/agents/router.py` | Capability-based routing with complexity scoring |
| **LLMRouter** | `app/agents/llm_router.py` | Multi-provider routing (OpenAI, Anthropic, Google, Local) |

### BaseAgent Protocol

```python
class AgentRole(str, Enum):
    PLANNER = "planner"
    EXECUTOR = "executor"
    VERIFIER = "verifier"
    RESEARCHER = "researcher"

class AgentStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILURE = "failure"
    PAUSED = "paused"

@runtime_checkable
class BaseAgent(Protocol):
    name: str
    role: AgentRole
    
    async def execute(self, input_data: AgentInput) -> AgentOutput:
        """Execute agent logic."""
        ...
```

---

## Agent Runtime

### Runtime Components

The **AgentRuntime** singleton manages agent lifecycle with production features:

| Component | File | Purpose |
|-----------|------|---------|
| **AgentRuntime** | `runtime.py` | Singleton with Redis mutex init, worker registry |
| **AgentWorker** | `worker.py` | Inbox queue, execution loop |
| **AgentFactory** | `factory.py` | Static agent creation |
| **DynamicAgentFactory** | `dynamic_factory.py` | Runtime agent creation from config |
| **AgentPool** | `pool.py` | Semaphore-based concurrency (max 100) |
| **AgentLifecycleManager** | `agent_lifecycle.py` | FSM with 6 states |
| **WorkerPoolManager** | `worker_pool.py` | Health checks, scaling, task assignment |
| **HorizontalScalingCoordinator** | `scaling.py` | Multi-instance coordination |
| **ResourceLimitEnforcer** | `resource_limits.py` | Agent/DB/Redis/memory limits |

### Agent Lifecycle States

```
CREATED → REGISTERED → ACTIVE → EXECUTING → IDLE → DECOMMISSIONED
```

| State | Description | Transitions |
|-------|-------------|-------------|
| CREATED | Agent instance created | → REGISTERED |
| REGISTERED | Added to runtime registry | → ACTIVE |
| ACTIVE | Ready to accept tasks | → EXECUTING, IDLE |
| EXECUTING | Currently processing task | → IDLE, DECOMMISSIONED |
| IDLE | Waiting for tasks | → EXECUTING, DECOMMISSIONED |
| DECOMMISSIONED | Cleanup complete | Terminal |

### Worker Pool Pattern

```python
class AgentPool:
    """Semaphore-based concurrency pool."""
    
    def __init__(self, max_agents: int = 100):
        self._semaphore = asyncio.Semaphore(max_agents)
    
    async def acquire(self) -> None:
        await self._semaphore.acquire()
    
    def release(self) -> None:
        self._semaphore.release()
```

---

## Safety & Observability

### Safety Layer

| Component | Location | Features |
|-----------|----------|----------|
| **SafetyGate** | `app/safety/gate.py` | Irreversible tool registry (29 tools), credential pattern blocking |
| **Guardrails** | `app/guardrails/` | Input/output validation, schema enforcement |
| **RBAC** | `app/safety/rbac.py` | 6 roles (planner, executor, verifier, reviewer, coordinator, system) |
| **AuditTrail** | `app/safety/audit.py` | Cryptographic hash chaining, 24 event types, compliance reports |

### Approval Store

```python
class ApprovalMode(str, Enum):
    STANDARD = "standard"      # Interrupt for sensitive actions
    FULL_TRUST = "full_trust"  # Auto-approve (still blocks forbidden)

class ApprovalStore:
    """Per-session approval state management."""
    
    def should_interrupt(self, tool_name: str, mode: ApprovalMode) -> bool:
        """Determine if execution should pause for approval."""
```

### Forbidden Tools

The following tool patterns are ALWAYS blocked regardless of approval mode:

```python
FORBIDDEN_TOOL_PREFIXES = [
    "filesystem__delete",
    "database__drop",
    "payment__",
    "crypto__",
    "email__send",
    "github__delete",
    "aws__terminate",
    "docker__remove",
    "kubernetes__delete",
]
```

### Observability

| Component | Location | Purpose |
|-----------|----------|---------|
| **MetricsCollector** | `app/logs/metrics.py` | Prometheus metrics, dashboard summaries |
| **TraceManager** | `app/logs/tracing.py` | Distributed tracing with spans |
| **AnomalyDetector** | `app/logs/anomaly.py` | Statistical anomaly detection |
| **AlertManager** | `app/logs/alerts.py` | 4 channels (log, webhook, email, slack) |
| **PerformanceProfiler** | `app/logs/profiler.py` | Step-level latency, bottleneck detection |
| **CostTracker** | `app/logs/cost_tracker.py` | Per-task/agent/tool cost tracking |

### Metrics

```python
# Collected Metrics
http_requests_total          # Counter with method/path/status labels
http_request_duration_seconds # Histogram
desktop_task_duration        # Desktop automation timing
desktop_action_count         # Action frequency
tokens_total                 # LLM token usage
```

---

## Memory & Persistence

### Dual-Layer Architecture

| Layer | Technology | Purpose | Persistence |
|-------|------------|---------|-------------|
| **Short-term** | Redis | Task contexts, session states, pub/sub, rate limiting | Ephemeral |
| **Long-term** | PostgreSQL/SQLite | Tasks, workflows, agents, traces, checkpoints, audit logs | Persistent |

### Database Models (27 tables)

| Category | Models |
|----------|--------|
| Task & Workflow | TaskModel, StepModel, WorkflowModel, WorkflowNodeModel, WorkflowEdgeModel, ContextModel |
| Agent & Tool | AgentModel, AgentVersionModel, ToolModel, ToolV2Model, MCPServerModel |
| User & Auth | UserModel, WorkspaceModel, WorkspaceMemberModel, APIKeyModel, UserOnboardingState, UserMemoryProfileModel |
| Observability | TraceModel, NodeTraceModel, SpanModel, TokenUsageModel, MessageModel |
| Safety | GuardrailRuleModel, AuditModel |
| LangGraph | CheckpointModel, CheckpointWriteModel, CheckpointMetadataModel |
| Extended | AgentConfigV2Model, AgentStateTransitionModel, ArtifactModel, TaskQueueEntryModel, ChatSessionModel, ChatMessageModel, KnowledgeSourceModel, KnowledgeChunkModel, DeploymentModel, ConfigModel |

### SQLite Checkpointer

```python
class SQLiteCheckpointSaver(BaseCheckpointSaver):
    """LangGraph-compatible checkpoint persistence with SQLite."""
    
    async def aput(self, config: RunnableConfig, checkpoint: Checkpoint) -> None:
        """Save checkpoint to SQLite."""
        
    async def aget_tuple(self, config: RunnableConfig) -> Optional[CheckpointTuple]:
        """Get checkpoint from SQLite."""
        
    async def aput_writes(self, config: RunnableConfig, writes: List[PendingWrite]) -> None:
        """Save pending writes for interrupt/resume."""
```

### Memory Managers

| Manager | Location | Purpose |
|---------|----------|---------|
| **PersistentMemoryManager** | `app/memory/persistent.py` | Dual-tier Redis + PostgreSQL with LRU pruning |
| **UserMemoryProfile** | `app/memory/user_profile.py` | Cross-task knowledge with fact deduplication |
| **ArtifactStore** | `app/memory/artifact_store.py` | Filesystem sharding with metadata indexing |
| **MemoryConsistencyLayer** | `app/memory/consistency.py` | 3 consistency levels (eventual, strong, read-through) |

---

## Frontend

### Technology Stack

- **Framework**: React 19 with TypeScript
- **Build Tool**: Vite 8
- **Styling**: Tailwind CSS 3.4 with pixel-art aesthetic
- **State Management**: Zustand + React Context
- **Animations**: Framer Motion
- **Workflow Builder**: XYFlow/ReactFlow

### Key Pages

| Page | File | Features |
|------|------|----------|
| **Dashboard** | `pages/Dashboard.tsx` | Task execution, metrics, task log sidebar |
| **Agent Builder** | `pages/AgentBuilder.tsx` | Agent templates, configuration, testing |
| **Tools** | `pages/Tools.tsx` | Tool registry V2, testing, OpenAPI import |
| **Chat** | `pages/Chat.tsx` | Session management, streaming messages |
| **Workflow Builder** | `pages/WorkflowBuilder.tsx` | Visual workflow editor with XYFlow |
| **Monitor** | `pages/Monitor.tsx` | Analytics, traces, metrics console |

### Frontend-Backend Integration

- **API Client**: JWT auto-refresh, exponential backoff, rate limit tracking
- **WebSocket**: `/ws/tasks/{id}?token={jwt}` with auto-reconnect
- **Authentication**: Bearer tokens with refresh flow
- **Real-time**: WebSocket events for task status updates

---

## API Reference

### REST API Endpoints

#### Health & Status

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | Public | Basic health check |
| GET | `/health/ready` | Public | Readiness probe (DB, Redis) |
| GET | `/health/live` | Public | Liveness check |
| GET | `/health/metrics` | Public | Prometheus metrics |

#### Authentication

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/v1/auth/signup` | Public | User registration |
| POST | `/api/v1/auth/login` | Public | Login with JWT |
| POST | `/api/v1/auth/refresh` | Public | Token refresh |

#### Tasks

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/v1/tasks` | Bearer | Create and execute task |
| GET | `/api/v1/tasks` | Bearer | List user tasks |
| GET | `/api/v1/tasks/{id}` | Bearer | Get task status |
| POST | `/api/v1/tasks/{id}/approve` | Bearer | Approve pending task |
| POST | `/api/v1/tasks/{id}/reject` | Bearer | Reject pending task |

#### Agents & Tools

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/v1/agents` | Bearer | List agents |
| POST | `/api/v1/agents` | Bearer | Create agent |
| GET | `/api/v1/tools` | Bearer | List tools |
| POST | `/api/v1/tools/{name}/execute` | Bearer | Execute tool |
| GET | `/api/v1/tools/mcp-servers` | Bearer | List MCP servers |

#### Observability

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/observability/metrics` | Bearer | System metrics |
| GET | `/observability/traces/{task_id}` | Bearer | Task traces |
| GET | `/observability/anomalies` | Bearer | Anomaly reports |

### Request/Response Examples

#### Create Task

**Request:**
```json
POST /api/v1/tasks
Authorization: Bearer {token}
Content-Type: application/json

{
  "query": "Search for Python tutorials and save the results",
  "config": {
    "max_steps": 10,
    "timeout": 300,
    "mode": "standard"
  }
}
```

**Response:**
```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "created_at": "2026-05-09T14:58:54.778Z",
  "estimated_duration": 45
}
```

#### Get Task Status

**Response:**
```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "result": {
    "summary": "Found 5 Python tutorials",
    "artifacts": ["results.json"],
    "confidence": 0.92
  },
  "execution_time": 32.5,
  "completed_at": "2026-05-09T14:59:27.278Z"
}
```

---

## gRPC Services

### Service Definitions

AgentOS provides three gRPC services for supervisor-runtime communication:

#### RuntimeService

```protobuf
service RuntimeService {
  rpc CreateTask(TaskRequest) returns (TaskResponse);
  rpc GetTask(TaskRequest) returns (Task);
  rpc CancelTask(TaskRequest) returns (TaskResponse);
  rpc ListTasks(ListTasksRequest) returns (ListTasksResponse);
  rpc GetRuntimeStatus(RuntimeStatusRequest) returns (RuntimeStatusResponse);
  rpc HealthCheck(HealthCheckRequest) returns (HealthCheckResponse);
}
```

#### CheckpointService

```protobuf
service CheckpointService {
  rpc SaveCheckpoint(SaveCheckpointRequest) returns (SaveCheckpointResponse);
  rpc GetCheckpoint(GetCheckpointRequest) returns (GetCheckpointResponse);
  rpc ListCheckpoints(ListCheckpointsRequest) returns (ListCheckpointsResponse);
  rpc DeleteCheckpoint(DeleteCheckpointRequest) returns (DeleteCheckpointResponse);
}
```

#### WorkerService

```protobuf
service WorkerService {
  rpc ExecuteTask(ExecuteTaskRequest) returns (ExecuteTaskResponse);
  rpc HealthCheck(HealthCheckRequest) returns (HealthCheckResponse);
}
```

### gRPC Client

```python
from app.proto.grpc_client import GRPCClient

async with GRPCClient("localhost:50051") as client:
    # Create task via gRPC
    response = await client.runtime.create_task(
        query="Search for Python tutorials",
        config={"max_steps": 10}
    )
    
    # Get task status
    task = await client.runtime.get_task(task_id=response.task_id)
    
    # Save checkpoint
    await client.checkpoint.save_checkpoint(
        thread_id="thread-123",
        checkpoint={...}
    )
```

---

## WebSocket Interface

### Connection

**URL:** `ws://localhost:8000/ws/tasks/{task_id}?token={jwt}`

### Client → Server Messages

```json
// Authentication
{"type": "auth", "token": "eyJhbGciOiJIUzI1NiIs..."}

// Subscribe to events
{"type": "subscribe", "channel": "task_updates", "filter": {"task_id": "..."}}

// Unsubscribe
{"type": "unsubscribe", "channel": "task_updates"}

// Ping
{"type": "ping", "timestamp": 1744204734778}
```

### Server → Client Messages

```json
// Task status update
{
  "type": "task_update",
  "task_id": "...",
  "status": "running",
  "progress": 45,
  "message": "Searching databases...",
  "timestamp": "2026-05-09T14:58:54.778Z"
}

// Task completed
{
  "type": "task_completed",
  "task_id": "...",
  "status": "completed",
  "result": {"summary": "...", "confidence": 0.92},
  "execution_time_seconds": 125
}

// Error
{
  "type": "error",
  "code": "TASK_NOT_FOUND",
  "message": "Task not found"
}
```

---

## Testing

### Test Suite Overview

| Category | Files | Tests | Focus |
|----------|-------|-------|-------|
| **Unit** | 76 | ~800 | Isolated component tests |
| **Integration** | 7 | ~50 | Cross-component validation |
| **Action V1** | 1 | 6 | Fast path benchmarks |
| **Desktop** | 8 | ~80 | Desktop automation |
| **LangGraph** | 4 | ~30 | Graph execution |
| **Safety** | 3 | ~40 | RBAC, guardrails, audit |
| **Stress** | 4 | 5 | Load testing |
| **Benchmarks** | 4 | 5 | Performance benchmarks |
| **Total** | **98** | **873+** | **Comprehensive coverage** |

### Running Tests

```bash
# Full test suite
pytest -q

# Action V1 benchmarks
pytest tests/test_action_v1_benchmarks.py -v

# Desktop automation
pytest tests/test_desktop_env.py tests/test_desktop_loop.py -v

# Integration tests
pytest tests/integration/ -v

# Validation suite
python validate_fixes.py
```

### Test Configuration

```python
# conftest.py
import pytest

@pytest.fixture
async def runtime():
    """Provide initialized AgentRuntime for tests."""
    runtime = AgentRuntime()
    await runtime.initialize()
    yield runtime
    await runtime.shutdown()
```

---

## Tech Stack

### Backend

| Component | Technology | Version |
|-----------|-----------|---------|
| Framework | FastAPI | 0.121+ |
| ASGI Server | Uvicorn | 0.34+ |
| Validation | Pydantic | 2.12+ |
| Auth | python-jose | 3.3+ |
| Password Hashing | passlib | 1.7+ |
| LLM Client | OpenAI SDK | 1.0+ |
| Orchestration | LangGraph | 1.1+ |
| LangChain | langchain-core | 1.3+ |
| MCP SDK | mcp | 1.0+ |
| Browser Automation | Playwright | 1.51+ |
| Desktop Automation | uiautomation, pyautogui | Latest |
| Database | PostgreSQL/SQLite | 14+/3.40+ |
| ORM | SQLAlchemy async | 2.0+ |
| Cache + PubSub | Redis | 7+ |
| Monitoring | Prometheus client | 0.19+ |

### Frontend

| Component | Technology | Version |
|-----------|-----------|---------|
| Framework | React | 19.x |
| Build Tool | Vite | 8.x+ |
| Language | TypeScript | 5.x+ |
| Styling | Tailwind CSS | 3.4+ |
| State | Zustand | 4.x+ |
| Animation | Framer Motion | 11.x+ |
| Workflow | XYFlow | 12.x+ |

### Infrastructure

| Component | Technology | Version |
|-----------|-----------|---------|
| Supervisor | Go | 1.22+ |
| Desktop Bridge | Rust | 1.75+ |
| CLI | Rust | 1.75+ |
| Protocol | gRPC | 1.60+ |
| Serialization | Protocol Buffers | 3.25+ |

---

## Setup & Installation

### Prerequisites

- Python 3.11+
- Node.js 20+
- PostgreSQL 14+ (for cloud mode)
- Redis 7+
- Playwright Chromium
- Go 1.22+ (for supervisor)
- Rust 1.75+ (for CLI/desktop)

### Quick Start

```bash
# Clone repository
git clone https://github.com/chandankumar123456/Agent-OS.git
cd Agent-OS

# Install Python dependencies
pip install -r requirements.txt

# Install Playwright
playwright install chromium

# Configure environment
cp .env.example .env
# Edit .env with your settings

# Start backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Start frontend (new terminal)
cd frontend
npm install
npm run dev
```

### Docker Deployment

```bash
# Full stack with Docker Compose
cd docker
docker compose up --build
```

---

## Configuration

### Environment Variables

Create a `.env` file:

```env
# OpenAI
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o

# Database (Cloud mode)
DATABASE_URL=postgresql+asyncpg://agentos:agentos@localhost:5432/agentos

# Redis
REDIS_URL=redis://:@localhost:6379/0

# Security
SECRET_KEY=your-secret-key-min-32-bytes-long!!!
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# Runtime
MAX_STEPS_DEFAULT=10
TIMEOUT_DEFAULT=300
MAX_RETRIES=3

# Runtime Mode (http or grpc)
AGENTOS_RUNTIME_MODE=http

# gRPC (for local-native mode)
GRPC_SERVER_HOST=localhost
GRPC_SERVER_PORT=50051

# CORS
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
```

### Runtime Mode Selection

| Mode | Use Case | Persistence | Communication |
|------|----------|-------------|---------------|
| `http` | Cloud/SaaS | PostgreSQL + Redis | HTTP REST + WebSocket |
| `grpc` | Local-native | SQLite | gRPC |

---

## System Guarantees

1. **LangGraph is the primary execution engine** — orchestrator compiles mode-specific StateGraphs and falls back to legacy pipelines only on exception
2. **Every execution is checkpointed** — LangGraph state persisted for resume across restarts
3. **Human-in-the-loop uses LangGraph interrupt** — approval gates pause execution via `interrupt()` and resume via API calls
4. **Runtime is the ONLY execution entry point** — no module may instantiate or call agents directly
5. **MCP tools are auto-discovered** — system servers start automatically and register tools via `MCPWrappedTool`
6. **Tool registration is idempotent** — built-in tools register once via singleton; MCP discovery skips if already registered
7. **Runtime initialization is idempotent** — Redis mutex prevents duplicate core agent registration across processes
8. **Paths are OS-aware** — planner generates OS-appropriate paths; executor remaps hallucinated foreign paths
9. **Authentication uses JWT with refresh tokens** — access tokens expire in 30 minutes; refresh tokens expire in 7 days
10. **WebSocket connections authenticate via query token** — invalid or expired tokens close connection with code 1008
11. **All data is strictly typed** — Pydantic models validate every request/response; no untyped dicts in core flow
12. **Output is validated before persistence** — guardrails validate pipeline output before database insertion
13. **Desktop actions are verified before success** — `verify_plan()` confirms structural and semantic correctness
14. **Desktop tool parameters are safety-checked** — credential patterns blocked by `SafetyGate` before execution
15. **Infinite loops are detected and aborted** — `ActionStabilizer` aborts after 3 identical no-change failures

---

## Project Structure

```
AgentOS/
├── README.md                          # This file
├── ARCHITECTURE.md                    # Detailed architecture documentation
├── ARCHITECTURE_ANALYSIS.md           # Code-level architecture analysis
├── AUDIT_REPORT_LOCAL_NATIVE_GAPS.md  # Gap analysis
├── requirements.txt                   # Python dependencies
├── .env.example                       # Environment template
├── validate_fixes.py                  # Priority 1 validation script
│
├── app/                               # Python Runtime (320 files)
│   ├── main.py                        # FastAPI application entry
│   ├── config/                        # Configuration
│   │   └── settings.py                # Pydantic Settings
│   ├── api/                           # HTTP + WebSocket layer
│   │   ├── deps.py                    # Dependency injection
│   │   ├── ws.py                      # WebSocket manager
│   │   └── routes/                    # 17 API route modules
│   ├── action_v1/                     # Deterministic fast-path
│   ├── langgraph/                     # LangGraph engine
│   │   ├── state.py                   # AgentState TypedDict
│   │   ├── nodes.py                   # Graph nodes
│   │   ├── graphs.py                  # Graph compilers
│   │   ├── checkpointer.py            # PostgreSQL checkpoint
│   │   └── sqlite_checkpointer.py     # SQLite checkpoint
│   ├── orchestrator/                  # Orchestration (25 files)
│   ├── runtime/                       # Agent runtime (13 files)
│   ├── agents/                        # Agent implementations (14 files)
│   ├── mcp/                           # MCP layer (17 files)
│   ├── tools/                         # Tool infrastructure (19 files)
│   ├── environments/                  # Execution environments
│   ├── capabilities/                  # Recovery/verification
│   ├── safety/                        # Safety layer
│   ├── guardrails/                    # Input/output validation
│   ├── logs/                          # Observability (8 files)
│   ├── memory/                        # Persistence (13 files)
│   └── middleware/                    # Auth, rate limiting
│
├── supervisor/                        # Go Supervisor (25 files)
│   ├── main.go                        # Entry point
│   ├── runtime_server.go              # Runtime gRPC service
│   ├── checkpoint_server.go           # Checkpoint gRPC service
│   ├── worker_server.go               # Worker gRPC service
│   ├── database.go                    # SQLite management
│   ├── migrations.go                  # Database migrations
│   ├── http_server.go                 # HTTP API
│   ├── health.go                      # Health checks
│   ├── installers/                    # Platform installers
│   │   ├── windows/                   # MSI installer
│   │   ├── macos/                     # DMG installer
│   │   └── linux/                     # AppImage
│   └── proto/                         # Protocol Buffers
│       ├── runtime.proto
│       ├── checkpoint.proto
│       └── worker.proto
│
├── cli/                               # Rust CLI (15 files)
│   ├── src/
│   │   ├── main.rs                    # CLI entry
│   │   ├── commands.rs                # Command definitions
│   │   └── client.rs                  # API client
│   └── Cargo.toml
│
├── desktop-bridge/                    # Rust Desktop (12 files)
│   ├── src/
│   │   ├── main.rs                    # Bridge entry
│   │   ├── automation.rs              # Windows automation
│   │   └── grpc.rs                    # gRPC client
│   └── Cargo.toml
│
├── gui/                               # Tauri GUI
│   ├── src/
│   └── tauri.conf.json
│
├── frontend/                          # React Frontend (97 files)
│   ├── src/
│   │   ├── api/                       # API client
│   │   ├── components/                # Shared components
│   │   ├── pages/                     # 16 pages
│   │   ├── hooks/                     # Custom hooks
│   │   └── context/                   # React contexts
│   ├── package.json
│   └── vite.config.ts
│
├── tests/                             # Test Suite (98 files)
│   ├── conftest.py                    # Shared fixtures
│   ├── test_action_v1_benchmarks.py   # Action V1 benchmarks
│   ├── unit/                          # Unit tests
│   ├── integration/                   # Integration tests
│   ├── stress/                        # Load tests
│   └── benchmarks/                    # Performance benchmarks
│
├── docker/                            # Docker Compose
│   └── docker-compose.yml
│
├── docs/                              # Documentation
│   ├── api/                           # API documentation
│   ├── user-guide/                    # User guide
│   ├── deployment/                    # Deployment guide
│   └── superpowers/                   # Implementation plans
│
└── thoughts/                          # Design artifacts
    ├── shared/
    │   ├── designs/                   # Design documents
    │   ├── plans/                     # Implementation plans
    │   ├── architecture/              # Architecture decisions
    │   └── contracts/                 # Interface contracts
    ├── ledgers/                       # Session ledgers
    └── tasks/                         # Task breakdowns
```

---

## Development Guide

### Development Workflow

1. **Test-First Development**
   ```bash
   # Write failing test
   # Implement feature
   # Verify test passes
   pytest tests/path/test_file.py::test_name -v
   ```

2. **Code Style**
   - Follow PEP 8 for Python
   - Use type hints everywhere
   - Document with docstrings
   - Keep functions focused (<50 lines)

3. **Commit Guidelines**
   ```
   feat: add new feature
   fix: fix bug
   refactor: refactor code
   docs: update documentation
   test: add tests
   chore: maintenance tasks
   ```

### Debugging

```bash
# Enable debug logging
LOG_LEVEL=DEBUG python -m uvicorn app.main:app --reload

# Run specific test with verbose output
pytest tests/test_file.py::test_name -vvs

# Profile performance
python -m cProfile -o profile.stats app/main.py
```

---

## Production Deployment

### Production Checklist

- [ ] Set `DATABASE_URL` with connection pooling (pool_size=20, max_overflow=40)
- [ ] Set `REDIS_URL` for MCP pub/sub and caching
- [ ] Set `SECRET_KEY` to persistent 32+ byte secret
- [ ] Configure `MAX_RETRIES`, `TIMEOUT_DEFAULT`, `MAX_STEPS_DEFAULT`
- [ ] Set `OPENAI_API_KEY` and `OPENAI_MODEL`
- [ ] Enable `RedisMCPBus` for multi-instance deployments
- [ ] Monitor `/health/ready` for load balancer health checks
- [ ] Scrape `/health/metrics` with Prometheus
- [ ] Review audit trail retention policies
- [ ] Configure alert channels (webhook, email, slack)
- [ ] Enable anomaly detection thresholds

### Performance Tuning

```python
# Uvicorn with multiple workers
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4

# Database connection pooling
DATABASE_URL=postgresql+asyncpg://...?pool_size=20&max_overflow=40

# Redis connection pooling
REDIS_URL=redis://...?connection_pool_max_connections=50
```

---

## Troubleshooting

### Common Issues

#### Database Connection Failed
```
Error: Database connection failed
Solution: Check DATABASE_URL, ensure PostgreSQL is running
```

#### Redis Connection Failed
```
Error: Redis connection failed
Solution: Check REDIS_URL, ensure Redis is running
```

#### MCP Server Not Found
```
Error: MCP server not found
Solution: Run `mcp_client_manager.start_system_servers()`
```

#### gRPC Connection Failed
```
Error: gRPC connection failed
Solution: Ensure supervisor is running on port 50051
```

### Debug Commands

```bash
# Check health
curl http://localhost:8000/health

# Check metrics
curl http://localhost:8000/health/metrics

# List MCP servers
curl http://localhost:8000/api/v1/tools/mcp-servers \
  -H "Authorization: Bearer {token}"

# Check logs
tail -f logs/agentos.log
```

---

## Contributing

1. Follow the existing test-first approach: write a failing test, implement the fix, verify the test passes
2. Ensure all tests pass: `pytest -q`
3. Run the validation suite: `python validate_fixes.py`
4. Update documentation if architecture changes
5. Keep commits focused and descriptive

### Code Review Process

1. Create feature branch
2. Write tests
3. Implement feature
4. Run test suite
5. Update documentation
6. Submit pull request
7. Address review feedback
8. Merge to main

---

## License

[Add license information here]

---

## Acknowledgments

- LangGraph team for the graph-native execution framework
- MCP team for the Model Context Protocol
- FastAPI team for the high-performance web framework
- The open-source community for countless dependencies

---

**Version:** 0.2.0  
**Last Updated:** 2026-05-09  
**Status:** Production Ready
