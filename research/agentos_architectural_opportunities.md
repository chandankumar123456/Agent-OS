# AgentOS Local-Native Agent Runtime: Research Synthesis
## Architectural Opportunities & Implementation Roadmap

**Based on research of:** Claude Code, Codex CLI, Computer Use, VSCode Extension Host, Temporal, Celery

---

## Quick Reference: Pattern-to-Feature Mapping

| External System | Key Pattern | AgentOS Application |
|----------------|-------------|---------------------|
| Claude Code | Session teleport | Session persistence & migration |
| Claude Code | CLAUDE.md | Project configuration system |
| Claude Code | Sub-agents | Agent Pool task decomposition |
| Codex CLI | Rust performance | Consider compiled components |
| Computer Use | Sandboxed execution | Tool isolation layer |
| VSCode ExtHost | Process isolation | Agent Worker architecture |
| Temporal | Durable execution | Session event sourcing |
| Celery | Task routing | Agent load balancing |

---

## Detailed Analysis by Dimension

### 1. Runtime Model: Session-Based Durable Execution

**Current AgentOS:**
- 8-layer stack with Action V1 (fast) and LangGraph (complex) paths
- State managed via AgentState TypedDict with reducers
- Desktop automation with observe-decide-act-verify-recover loop

**Opportunity: Temporal-Style Durable Sessions**

Add event-sourced session persistence:

```python
# New: Session persistence layer
class SessionEvent(BaseModel):
    event_id: str
    event_type: Literal["message", "tool_call", "tool_result", "state_change", "error"]
    timestamp: datetime
    payload: dict
    session_id: str
    
class DurableSession:
    """Session that survives process crashes"""
    
    async def execute_with_durability(
        self,
        workflow: AgentWorkflow,
        resume_from: Optional[str] = None
    ) -> SessionResult:
        """
        - If resume_from: Replay events to reconstruct state
        - Otherwise: Start new session with event logging
        - All mutations append events to log
        """
        pass
```

**Benefits:**
- Sessions survive crashes/restarts
- Complete audit trail for debugging
- Ability to replay sessions for testing
- Session migration between machines

**Implementation:**
- Add `SessionEventStore` interface
- PostgreSQL backend for production
- SQLite backend for local development
- Event replay mechanism in AgentRuntime

---

### 2. Interface Hierarchy: CLI-First with Progressive Enhancement

**Current AgentOS:**
- FastAPI backend with REST API
- Frontend (planned)
- No CLI interface yet

**Opportunity: Claude-Style Multi-Surface Design**

```
┌─────────────────────────────────────────┐
│           Surface Layer                 │
├─────────────┬─────────────┬────────────┤
│    CLI      │    API      │   Web UI   │
│  (Primary)  │  (Secondary)│  (Tertiary)│
└──────┬──────┴──────┬──────┴─────┬──────┘
       │             │            │
       └─────────────┴────────────┘
                    │
            ┌───────▼────────┐
            │  Core Runtime  │
            └────────────────┘
```

**CLI Design Principles (from Claude Code):**
1. Unix composable - pipe input/output
2. Natural language commands: `claude "fix the auth module"`
3. File path context: `claude -p "review these files" < changed.txt`
4. Session attachment: `claude --teleport <session-id>`

**Implementation:**
```python
# New: CLI module
import click
import asyncio

@click.group()
def agentos():
    """AgentOS - Local-native agent runtime"""
    pass

@agentos.command()
@click.argument('prompt')
@click.option('--session', '-s', help='Attach to existing session')
@click.option('--project', '-p', help='Project directory')
async def run(prompt: str, session: Optional[str], project: Optional[str]):
    """Execute agent task from command line"""
    runtime = await AgentRuntime.get_instance()
    
    if session:
        # Resume existing session
        result = await runtime.resume_session(session, prompt)
    else:
        # Start new session
        result = await runtime.execute_task(prompt, project_path=project)
    
    click.echo(result.output)

@agentos.command()
@click.argument('session_id')
async def teleport(session_id: str):
    """Attach to running session (local or remote)"""
    runtime = await AgentRuntime.get_instance()
    session = await runtime.get_session(session_id)
    await session.interactive_mode()
```

---

### 3. Execution Locality: Local-First with Cloud Bridge

**Current AgentOS:**
- Model calls go to configured API (OpenAI, etc.)
- Tools execute locally
- No local LLM support yet

**Opportunity: Claude-Style Local/Remote Flexibility**

```
Execution Modes:
├── FULL_LOCAL: Local LLM + local tools
├── LOCAL_TOOLS: Cloud model + local tools  ← Current
├── CLOUD_EXECUTION: Cloud model + cloud tools
└── HYBRID: Route per-task based on requirements
```

**Local LLM Integration (from Codex/Claude patterns):**

```python
# New: Model router
class ModelRouter:
    """Routes requests to local or cloud models based on configuration"""
    
    def __init__(self):
        self.local_client = None  # Ollama, llama.cpp
        self.cloud_client = None  # OpenAI, Anthropic
        
    async def route_request(
        self,
        prompt: str,
        requirements: ModelRequirements
    ) -> ModelResponse:
        """
        Decision logic:
        - If local available and sufficient: use local
        - If local insufficient: use cloud
        - If both available: parallel request, return fastest
        """
        pass

# Integration with existing AgentRuntime
class AgentRuntime:
    async def get_model_client(self, task: Task) -> ModelClient:
        if self.config.local_llm.enabled:
            return await self.model_router.get_local_client()
        return await self.model_router.get_cloud_client()
```

---

### 4. Process Model: VSCode-Style Extension Host

**Current AgentOS:**
- Module-level singletons (AgentRuntime, MCPClientManager, ToolRegistry)
- Single process with async execution
- Tools run as separate processes via stdio (MCP)

**Opportunity: Multi-Process Agent Workers**

**VSCode Architecture Applied:**

```
┌────────────────────────────────────────────────────┐
│                Main Process                         │
│  ┌─────────────┐  ┌─────────────┐  ┌────────────┐ │
│  │   API       │  │Orchestrator │  │  Sessions  │ │
│  │   Server    │  │             │  │   Manager  │ │
│  └─────────────┘  └──────┬──────┘  └────────────┘ │
└──────────────────────────┼───────────────────────┘
                           │ Message Queue (Redis)
┌──────────────────────────▼───────────────────────┐
│              Agent Worker Pool                    │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐       │
│  │ Worker 1 │  │ Worker 2 │  │ Worker N │       │
│  │(Isolated)│  │(Isolated)│  │(Isolated)│       │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘       │
└───────┼─────────────┼─────────────┼───────────────┘
        │             │             │
        └─────────────┴─────────────┘
                      │
        ┌─────────────▼─────────────┐
        │      Tool Runtime         │
        │  (MCP Servers, Shell)     │
        └───────────────────────────┘
```

**Benefits:**
- Worker crashes don't affect main process
- Resource isolation (memory, CPU per worker)
- Independent scaling
- Clear error boundaries

**Implementation Approach:**
```python
# New: Agent Worker architecture
class AgentWorker:
    """Isolated process for agent execution"""
    
    def __init__(self, worker_id: str):
        self.worker_id = worker_id
        self.runtime = AgentRuntime()  # Fresh instance
        
    async def execute_task(self, task: Task) -> TaskResult:
        """Execute task in isolated context"""
        try:
            return await self.runtime.execute(task)
        except Exception as e:
            # Worker-level error handling
            return TaskResult.error(e)
            
    async def health_check(self) -> HealthStatus:
        """Report worker health"""
        return HealthStatus(
            worker_id=self.worker_id,
            memory_usage=self.get_memory(),
            cpu_usage=self.get_cpu(),
            active_tasks=len(self.runtime.active_tasks)
        )

class WorkerPool:
    """Manages pool of agent workers"""
    
    def __init__(self, max_workers: int = 10):
        self.max_workers = max_workers
        self.workers: Dict[str, AgentWorker] = {}
        self.semaphore = asyncio.Semaphore(max_workers)
        
    async def acquire_worker(self) -> AgentWorker:
        """Get available worker or spawn new one"""
        async with self.semaphore:
            # Find healthy worker or spawn new
            pass
```

---

### 5. State Management: Hybrid Persistence Strategy

**Current AgentOS:**
- AgentState TypedDict in memory
- Redis for some persistence
- No structured event logging

**Opportunity: Multi-Layer Persistence**

| Data Type | Pattern | Implementation |
|-----------|---------|----------------|
| Session History | Event-sourced | Append-only event log |
| Agent Memory | Vector store | Chroma/pgvector |
| Tool Results | Ephemeral | TTL cache |
| Configuration | File-based | `.agentos/config.yml` |
| Workflow State | Database | PostgreSQL |

**CLAUDE.md Equivalent for AgentOS:**

```markdown
# .agentos/AGENTOS.md

## Project Context

### Tech Stack
- Python 3.11+ with FastAPI
- PostgreSQL for persistence
- Redis for caching
- React frontend

### Architecture
- 8-layer stack
- Action V1 fast path for simple tasks
- LangGraph path for complex workflows

### Tool Access
- Filesystem: read-write allowed in project root
- Shell: allowed commands listed below
- Web: allowed domains for research

### Testing
Run: `pytest -q`
Validate: `python validate_fixes.py`

### MCP Servers
```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "."]
    }
  }
}
```
```

**Implementation:**
```python
# New: Project configuration
class ProjectConfig(BaseModel):
    """Per-project agent configuration"""
    
    tech_stack: List[str] = []
    architecture_notes: str = ""
    allowed_tools: List[str] = ["*"]  # Default allow all
    blocked_tools: List[str] = []
    mcp_servers: Dict[str, MCPServerConfig] = {}
    test_commands: Dict[str, str] = {}
    
    @classmethod
    def load_from_project(cls, project_path: Path) -> "ProjectConfig":
        config_path = project_path / ".agentos" / "AGENTOS.md"
        if config_path.exists():
            return cls._parse_markdown(config_path)
        return cls()  # Default config
```

---

### 6. Tool System: Enhanced MCP with Safety

**Current AgentOS:**
- MCP tools via stdio transport
- Namespace: `{server}__{tool}`
- ToolRegistry as module-level singleton

**Opportunity: Computer-Use Style Sandboxing**

```
Tool Execution Security Layers:
├── Container isolation (Docker)
├── Permission-based access (read/write/execute)
├── Timeout enforcement
├── Resource limits (CPU, memory, network)
└── Audit logging
```

**Implementation:**
```python
# New: Sandboxed tool execution
class SandboxedToolExecutor:
    """Execute tools in isolated environment"""
    
    def __init__(self, sandbox_config: SandboxConfig):
        self.config = sandbox_config
        
    async def execute(
        self,
        tool: Tool,
        arguments: Dict[str, Any]
    ) -> ToolResult:
        """
        Execution flow:
        1. Validate arguments against schema
        2. Check permissions
        3. Spawn container/namespace
        4. Execute with timeout
        5. Capture output
        6. Clean up
        """
        if not self._has_permission(tool, arguments):
            return ToolResult.error("Permission denied")
            
        container = await self._spawn_container()
        try:
            result = await asyncio.wait_for(
                container.execute(tool, arguments),
                timeout=self.config.timeout_seconds
            )
            return result
        except asyncio.TimeoutError:
            return ToolResult.error("Tool execution timeout")
        finally:
            await container.cleanup()
```

---

### 7. IPC Patterns: Multi-Transport Support

**Current AgentOS:**
- Stdio for MCP tools
- HTTP for API
- Async/await within process

**Opportunity: Celery-Style Task Routing**

```python
# New: Task routing system
class TaskRouter:
    """Routes tasks to appropriate workers based on requirements"""
    
    def route_task(self, task: Task) -> WorkerSelection:
        """
        Routing logic:
        - Tool requirements → worker with tool access
        - GPU requirements → worker with GPU
        - Priority → dedicated high-priority queue
        - Session affinity → same worker for context
        """
        if task.requires_gpu:
            return self.gpu_worker_pool.acquire()
        elif task.session_id:
            return self.get_affinity_worker(task.session_id)
        else:
            return self.default_pool.acquire()
```

---

## Implementation Roadmap

### Phase 1: Session Persistence (Q1)
- [ ] Design SessionEvent schema
- [ ] Implement SessionEventStore (SQLite/PostgreSQL)
- [ ] Add event logging to AgentRuntime
- [ ] Create session replay mechanism
- [ ] Add `agentos resume <session-id>` CLI command

### Phase 2: Local-First Execution (Q1-Q2)
- [ ] Integrate Ollama/llama.cpp for local LLM
- [ ] ModelRouter for local/cloud routing
- [ ] Offline mode detection
- [ ] Project configuration system (AGENTOS.md)

### Phase 3: Worker Architecture (Q2)
- [ ] AgentWorker process model
- [ ] WorkerPool with semaphore management
- [ ] Health checks and auto-restart
- [ ] Inter-process communication (Redis queues)

### Phase 4: Tool Safety (Q2-Q3)
- [ ] Sandboxed tool execution
- [ ] Permission system for tools
- [ ] Resource limits and timeouts
- [ ] Audit logging for all tool calls

### Phase 5: Distribution (Q3)
- [ ] Desktop app (Tauri/Electron)
- [ ] VSCode extension
- [ ] Session teleport between devices
- [ ] Cloud bridge for model access

---

## Risk Assessment

| Feature | Risk | Mitigation |
|---------|------|------------|
| Event sourcing | Performance overhead | Async batching, selective persistence |
| Multi-process | Complexity increase | Clear interfaces, thorough testing |
| Local LLM | Quality vs cloud | Hybrid routing, user choice |
| Sandboxing | Tool compatibility | Graceful fallback, whitelist mode |

---

## Success Metrics

1. **Session Persistence**: 99.9% of sessions recoverable after crash
2. **Local Execution**: Sub-200ms latency for local model responses
3. **Tool Safety**: Zero escape from sandbox in testing
4. **Multi-surface**: Sessions migrate between CLI/Web in <5 seconds

---

## Next Actions

1. **Review** this document with team for feedback
2. **Prioritize** Phase 1 features for next sprint
3. **Prototype** SessionEventStore with SQLite backend
4. **Design** AGENTOS.md schema and parsing
5. **Research** local LLM options for Python integration
