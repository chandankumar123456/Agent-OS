# AgentOS Python Runtime - Technical Specification

**Version**: 0.2.0 (Local-Native Runtime)  
**Date**: 2026-05-09  
**Status**: gRPC Integration Complete

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Entry Points](#2-entry-points)
3. [Runtime Components](#3-runtime-components)
4. [LangGraph Integration](#4-langgraph-integration)
5. [Agent System](#5-agent-system)
6. [MCP Layer](#6-mcp-layer)
7. [Orchestrator](#7-orchestrator)
8. [Configuration & Environment](#8-configuration--environment)
9. [Async/Threading Patterns](#9-asyncthreading-patterns)
10. [Mode-Specific Behavior](#10-mode-specific-behavior)

---

## 1. Architecture Overview

### 1.1 Dual-Mode Architecture

AgentOS Python runtime supports two distinct execution modes:

```
┌─────────────────────────────────────────────────────────────┐
│                    ENTRY POINTS                              │
├─────────────────────┬───────────────────────────────────────┤
│  HTTP Mode          │  Desktop-Native Mode                  │
│  app/main.py        │  app/desktop_entry.py                 │
│  (FastAPI + Web)    │  (No FastAPI)                         │
└──────────┬──────────┴──────────────┬────────────────────────┘
           │                         │
           └──────────┬──────────────┘
                      │
           ┌──────────▼──────────┐
           │  app/bootstrap.py   │
           │  Shared Init        │
           │  - Database         │
           │  - Redis (HTTP)     │
           │  - Runtime          │
           │  - MCP/Tools        │
           │  - gRPC Client      │
           └─────────────────────┘
```

### 1.2 Core Principles

| Principle | Description |
|-----------|-------------|
| **Single Entry Point** | Runtime is the ONLY execution entry point - no module may instantiate agents directly |
| **Idempotent Initialization** | All components can be initialized multiple times safely |
| **Mode-Aware** | Components detect HTTP vs gRPC mode and adapt behavior |
| **Singleton Pattern** | Key components are singletons with lifecycle management |
| **Async First** | gRPC mode uses asyncio; FastAPI wraps async calls |

---

## 2. Entry Points

### 2.1 app/main.py - FastAPI HTTP Entry

**Purpose**: Web-based API entry point with FastAPI

**Key Features**:
- FastAPI application with lifespan management
- CORS middleware configuration
- JWT authentication via `get_current_user()` dependency
- Mode-aware initialization (HTTP vs gRPC)
- WebSocket support for real-time updates

**Initialization Flow**:
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Bootstrap shared components
    ctx = bootstrap()
    
    # 2. HTTP mode: Initialize Redis (gRPC mode: Supervisor handles Redis)
    if is_http_mode():
        await ctx.redis.ping()
    
    # 3. Yield control to FastAPI
    yield
    
    # 4. Cleanup on shutdown
    await ctx.runtime.shutdown()
```

**Usage**:
```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 2.2 app/desktop_entry.py - Desktop-Native Entry

**Purpose**: Pure desktop-native entry point without FastAPI dependencies

**Key Features**:
- No FastAPI imports (completely isolated from web stack)
- `DesktopRuntime` class for lifecycle management
- gRPC mode enforcement (always gRPC in desktop mode)
- Signal handling for graceful shutdown (SIGINT, SIGTERM)
- Runs as async main loop

**Architecture**:
```python
class DesktopRuntime:
    """Desktop-native runtime without FastAPI dependencies"""
    
    def __init__(self):
        self.ctx: Optional[BootstrapContext] = None
        self.running = False
    
    async def start(self):
        """Initialize and start the runtime"""
        os.environ["AGENTOS_RUNTIME_MODE"] = "grpc"
        self.ctx = bootstrap()
        self.running = True
        
        # Start gRPC server
        await self._start_grpc_server()
    
    async def _start_grpc_server(self):
        """Start the gRPC server for supervisor communication"""
        server = grpc.aio.server()
        # Add services...
        await server.start()
```

**Usage**:
```bash
# Set environment
$env:AGENTOS_RUNTIME_MODE="grpc"

# Run desktop entry
python -m app.desktop_entry
```

### 2.3 app/bootstrap.py - Shared Initialization

**Purpose**: Contains all shared initialization logic used by both entry points

**Key Features**:
- No FastAPI dependencies in core bootstrapping
- Supports both HTTP and gRPC modes via `BootstrapContext`
- Idempotent initialization with `BootstrapContext`
- Graceful shutdown with signal handlers
- Components: database, Redis (HTTP only), runtime, MCP, gRPC client

**BootstrapContext**:
```python
@dataclass
class BootstrapContext:
    """Context object holding all initialized components"""
    database: DatabaseManager  # PostgreSQL/SQLite
    redis: Optional[Redis]       # None in gRPC mode
    runtime: AgentRuntime      # Core runtime singleton
    mcp_manager: MCPClientManager
    grpc_client: Optional[GRPCClient]  # None in HTTP mode
    mode: RuntimeMode
```

**Bootstrap Function**:
```python
def bootstrap() -> BootstrapContext:
    """Initialize all shared components. Idempotent - safe to call multiple times."""
    
    # 1. Detect runtime mode
    mode = get_runtime_mode()
    
    # 2. Initialize database (both modes)
    database = DatabaseManager()
    
    # 3. Initialize Redis (HTTP mode only)
    redis = Redis() if is_http_mode() else None
    
    # 4. Initialize MCP manager (both modes)
    mcp_manager = MCPClientManager()
    
    # 5. Initialize gRPC client (gRPC mode only)
    grpc_client = GRPCClient() if is_grpc_mode() else None
    
    # 6. Initialize runtime (both modes)
    runtime = AgentRuntime(
        database=database,
        redis=redis,
        mcp_manager=mcp_manager,
        grpc_client=grpc_client
    )
    
    return BootstrapContext(...)
```

---

## 3. Runtime Components

### 3.1 AgentRuntime (app/runtime/runtime.py)

**Purpose**: Central runtime coordinator - singleton pattern

**Location**: Line 42 in `app/runtime/runtime.py`

**Key Features**:
- Singleton pattern with `AgentRuntime._instance`
- Redis mutex initialization for idempotent registration
- gRPC client lifecycle management (gRPC mode)
- Worker registry for agent instances
- Task execution via gRPC or direct mode

**Class Definition**:
```python
class AgentRuntime:
    """Central runtime coordinator with singleton pattern"""
    
    _instance: Optional["AgentRuntime"] = None
    _initialized = False
    _lock = asyncio.Lock()
    
    def __init__(
        self,
        database: DatabaseManager,
        redis: Optional[Redis],
        mcp_manager: MCPClientManager,
        grpc_client: Optional[GRPCClient] = None
    ):
        self.database = database
        self.redis = redis
        self.mcp_manager = mcp_manager
        self.grpc_client = grpc_client
        self._workers: Dict[str, AgentWorker] = {}
        self._mode = get_runtime_mode()
    
    async def initialize(self):
        """Idempotent initialization with Redis mutex"""
        if self._initialized:
            return
            
        async with self._lock:
            if self._initialized:
                return
                
            # Initialize MCP connections
            await self.mcp_manager.connect_all()
            
            # Initialize gRPC client (gRPC mode)
            if self.grpc_client and is_grpc_mode():
                await self.grpc_client.connect()
            
            self._initialized = True
    
    async def execute_task(self, task: Task) -> TaskResult:
        """Execute task - mode-aware routing"""
        if is_grpc_mode() and self.grpc_client:
            return await self.execute_task_via_grpc(task)
        else:
            return await self._execute_local(task)
    
    async def execute_task_via_grpc(self, task: Task) -> TaskResult:
        """Execute task via gRPC to supervisor"""
        request = ExecuteTaskRequest(
            task_id=task.id,
            query=task.query,
            config=task.config
        )
        response = await self.grpc_client.worker.execute_task(request)
        return TaskResult.from_proto(response)
```

**Mode-Specific Methods**:

| Method | HTTP Mode | gRPC Mode |
|--------|-----------|-----------|
| `initialize()` | Init Redis + MCP | Init gRPC client + MCP |
| `execute_task()` | Direct local execution | gRPC to supervisor |
| `get_status()` | Local query | gRPC to supervisor |

### 3.2 Runtime Mode Detection (app/runtime/mode.py)

**Purpose**: Unified runtime mode detection and configuration

**Key Components**:

```python
class RuntimeMode(str, Enum):
    """Runtime execution mode enumeration"""
    HTTP = "http"
    GRPC = "grpc"

def get_runtime_mode() -> RuntimeMode:
    """Get current runtime mode from environment"""
    mode = os.getenv("AGENTOS_RUNTIME_MODE", "http")
    return RuntimeMode(mode)

def is_grpc_mode() -> bool:
    """Check if running in gRPC mode"""
    return get_runtime_mode() == RuntimeMode.GRPC

def is_http_mode() -> bool:
    """Check if running in HTTP mode"""
    return get_runtime_mode() == RuntimeMode.HTTP

def get_supervisor_address() -> str:
    """Get supervisor gRPC address (gRPC mode only)"""
    if is_grpc_mode():
        return os.getenv("SUPERVISOR_ADDRESS", "localhost:50051")
    return ""
```

**Configuration**:

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `AGENTOS_RUNTIME_MODE` | `http` | Runtime mode: `http` or `grpc` |
| `SUPERVISOR_ADDRESS` | `localhost:50051` | gRPC supervisor address |
| `GRPC_CHECKPOINT_PORT` | `50052` | Checkpoint service port |
| `GRPC_WORKER_PORT` | `50053` | Worker service port |

### 3.3 gRPC Server Wrapper (app/runtime/grpc_server.py)

**Purpose**: gRPC server implementation for supervisor communication

**Services Implemented**:

#### RuntimeService (Port 50051)
```python
class RuntimeServiceImpl:
    """Runtime management service"""
    
    async def CreateTask(self, request, context):
        """Create a new task"""
        task = await self.runtime.create_task(
            query=request.query,
            config=request.config
        )
        return CreateTaskResponse(task_id=task.id)
    
    async def GetTask(self, request, context):
        """Get task status and results"""
        task = await self.runtime.get_task(request.task_id)
        return GetTaskResponse(
            task_id=task.id,
            status=task.status,
            result=task.result
        )
    
    async def CancelTask(self, request, context):
        """Cancel a running task"""
        success = await self.runtime.cancel_task(request.task_id)
        return CancelTaskResponse(success=success)
    
    async def ListTasks(self, request, context):
        """List all tasks"""
        tasks = await self.runtime.list_tasks(
            limit=request.limit,
            offset=request.offset
        )
        return ListTasksResponse(tasks=[...])
    
    async def GetRuntimeStatus(self, request, context):
        """Get runtime status and metrics"""
        return GetRuntimeStatusResponse(
            mode=self.runtime._mode,
            active_tasks=len(self.runtime._workers),
            memory_usage=get_memory_usage()
        )
    
    async def HealthCheck(self, request, context):
        """Health check endpoint"""
        return HealthCheckResponse(
            status="healthy",
            timestamp=time.time()
        )
```

#### CheckpointService (Port 50052)
```python
class CheckpointServiceImpl:
    """Checkpoint persistence service"""
    
    def __init__(self, checkpointer: SQLiteCheckpointer):
        self.checkpointer = checkpointer
    
    async def SaveCheckpoint(self, request, context):
        """Save checkpoint to SQLite"""
        await self.checkpointer.save(
            thread_id=request.thread_id,
            checkpoint=deserialize(request.checkpoint),
            metadata=deserialize(request.metadata)
        )
        return SaveCheckpointResponse(success=True)
    
    async def GetCheckpoint(self, request, context):
        """Retrieve checkpoint by thread_id"""
        checkpoint = await self.checkpointer.get(request.thread_id)
        return GetCheckpointResponse(
            checkpoint=serialize(checkpoint)
        )
    
    async def ListCheckpoints(self, request, context):
        """List all checkpoints for thread"""
        checkpoints = await self.checkpointer.list(
            thread_id=request.thread_id,
            limit=request.limit
        )
        return ListCheckpointsResponse(checkpoints=[...])
```

#### WorkerService (Port 50053)
```python
class WorkerServiceImpl:
    """Task execution worker service"""
    
    async def ExecuteTask(self, request, context):
        """Execute a task and return result"""
        result = await self.runtime.execute_task(
            Task(
                id=request.task_id,
                query=request.query,
                config=request.config
            )
        )
        return ExecuteTaskResponse(
            task_id=result.task_id,
            status=result.status,
            output=result.output
        )
    
    async def HealthCheck(self, request, context):
        """Worker health check"""
        return WorkerHealthResponse(
            status="healthy",
            active_workers=len(self.runtime._workers)
        )
```

---

## 4. LangGraph Integration

### 4.1 SQLite Checkpointer (app/langgraph/sqlite_checkpointer.py)

**Purpose**: LangGraph-compatible checkpoint persistence using SQLite

**Key Features**:
- Thread-safe SQLite with WAL mode
- Implements LangGraph `CheckpointWriter` and `CheckpointReader` interfaces
- Checkpoint persistence for resume across restarts
- Pending writes support for interrupt/resume

**Implementation**:

```python
class SQLiteCheckpointer:
    """SQLite-based checkpoint saver for LangGraph"""
    
    def __init__(self, db_path: str = "checkpoints.sqlite"):
        self.db_path = db_path
        self._pool = ConnectionPool(max_connections=10)
        self._init_db()
    
    def _init_db(self):
        """Initialize checkpoint tables"""
        with self._pool.get() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS checkpoints (
                    thread_id TEXT NOT NULL,
                    checkpoint_ns TEXT NOT NULL,
                    parent_checkpoint_id TEXT,
                    checkpoint_id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    checkpoint BLOB NOT NULL,
                    metadata BLOB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS pending_writes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    thread_id TEXT NOT NULL,
                    checkpoint_ns TEXT NOT NULL,
                    checkpoint_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    type TEXT NOT NULL,
                    value BLOB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
    
    async def save(
        self,
        thread_id: str,
        checkpoint: Checkpoint,
        metadata: Optional[CheckpointMetadata] = None
    ) -> str:
        """Save checkpoint to SQLite"""
        checkpoint_id = str(uuid.uuid4())
        
        with self._pool.get() as conn:
            conn.execute(
                """
                INSERT INTO checkpoints 
                (thread_id, checkpoint_ns, checkpoint_id, type, checkpoint, metadata)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    thread_id,
                    checkpoint.checkpoint_ns,
                    checkpoint_id,
                    checkpoint.type,
                    pickle.dumps(checkpoint),
                    pickle.dumps(metadata) if metadata else None
                )
            )
            conn.commit()
        
        return checkpoint_id
    
    async def get(self, thread_id: str) -> Optional[Checkpoint]:
        """Get latest checkpoint for thread"""
        with self._pool.get() as conn:
            row = conn.execute(
                """
                SELECT checkpoint FROM checkpoints
                WHERE thread_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (thread_id,)
            ).fetchone()
            
            if row:
                return pickle.loads(row[0])
            return None
    
    async def list(
        self,
        thread_id: str,
        limit: int = 100
    ) -> List[Checkpoint]:
        """List checkpoints for thread"""
        with self._pool.get() as conn:
            rows = conn.execute(
                """
                SELECT checkpoint FROM checkpoints
                WHERE thread_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (thread_id, limit)
            ).fetchall()
            
            return [pickle.loads(row[0]) for row in rows]
```

### 4.2 Checkpoint Schema

**Checkpoints Table**:
```sql
CREATE TABLE checkpoints (
    thread_id TEXT NOT NULL,           -- LangGraph thread identifier
    checkpoint_ns TEXT NOT NULL,       -- Namespace for checkpoint
    parent_checkpoint_id TEXT,         -- Parent checkpoint for DAG
    checkpoint_id TEXT PRIMARY KEY,    -- Unique checkpoint ID
    type TEXT NOT NULL,                -- Checkpoint type
    checkpoint BLOB NOT NULL,          -- Serialized checkpoint data
    metadata BLOB,                     -- Serialized metadata
    created_at TIMESTAMP               -- Creation timestamp
);
```

**Pending Writes Table**:
```sql
CREATE TABLE pending_writes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id TEXT NOT NULL,           -- Thread identifier
    checkpoint_ns TEXT NOT NULL,       -- Checkpoint namespace
    checkpoint_id TEXT NOT NULL,       -- Checkpoint reference
    task_id TEXT NOT NULL,             -- Task ID
    channel TEXT NOT NULL,             -- Channel name
    type TEXT NOT NULL,                -- Write type
    value BLOB,                        -- Serialized value
    created_at TIMESTAMP               -- Creation timestamp
);
```

---

## 5. Agent System

### 5.1 Base Agent (app/agents/base.py)

**Purpose**: Abstract base class for all agent implementations

```python
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

class BaseAgent(ABC):
    """Abstract base class for AgentOS agents"""
    
    def __init__(
        self,
        agent_id: str,
        name: str,
        description: str = "",
        config: Optional[Dict[str, Any]] = None
    ):
        self.agent_id = agent_id
        self.name = name
        self.description = description
        self.config = config or {}
        self._initialized = False
    
    @abstractmethod
    async def run(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Execute the agent with the given query"""
        pass
    
    @abstractmethod
    async def arun(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Async version of run"""
        pass
    
    async def initialize(self):
        """Initialize the agent - idempotent"""
        if not self._initialized:
            await self._do_initialize()
            self._initialized = True
    
    @abstractmethod
    async def _do_initialize(self):
        """Subclass initialization logic"""
        pass
```

### 5.2 ReAct Agent (app/agents/react_agent.py)

**Purpose**: LangChain ReAct agent implementation

```python
from langchain.agents import AgentExecutor, create_react_agent
from langchain_core.prompts import PromptTemplate

class ReActAgent(BaseAgent):
    """ReAct (Reasoning + Acting) agent implementation"""
    
    def __init__(
        self,
        agent_id: str,
        name: str,
        llm: Any,  # LangChain LLM
        tools: List[Any],
        **kwargs
    ):
        super().__init__(agent_id, name, **kwargs)
        self.llm = llm
        self.tools = tools
        self.agent_executor: Optional[AgentExecutor] = None
    
    async def _do_initialize(self):
        """Initialize ReAct agent executor"""
        prompt = PromptTemplate.from_template(REACT_PROMPT)
        agent = create_react_agent(
            llm=self.llm,
            tools=self.tools,
            prompt=prompt
        )
        self.agent_executor = AgentExecutor(
            agent=agent,
            tools=self.tools,
            verbose=True,
            handle_parsing_errors=True
        )
    
    async def run(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Execute ReAct agent"""
        await self.initialize()
        
        result = await self.agent_executor.ainvoke(
            {"input": query},
            config=context or {}
        )
        
        return {
            "output": result.get("output"),
            "intermediate_steps": result.get("intermediate_steps", []),
            "thoughts": self._extract_thoughts(result)
        }
```

### 5.3 Agent Factory (app/agents/factory.py)

**Purpose**: Static factory for creating agent instances

```python
class AgentFactory:
    """Factory for creating agent instances"""
    
    _agent_types: Dict[str, Type[BaseAgent]] = {
        "react": ReActAgent,
        "planner": PlannerAgent,
        "executor": ExecutorAgent,
        "verifier": VerifierAgent,
        # ... more agent types
    }
    
    @classmethod
    def create_agent(
        cls,
        agent_type: str,
        agent_id: str,
        name: str,
        **kwargs
    ) -> BaseAgent:
        """Create an agent instance by type"""
        if agent_type not in cls._agent_types:
            raise ValueError(f"Unknown agent type: {agent_type}")
        
        agent_class = cls._agent_types[agent_type]
        return agent_class(agent_id=agent_id, name=name, **kwargs)
    
    @classmethod
    def register_agent_type(
        cls,
        agent_type: str,
        agent_class: Type[BaseAgent]
    ):
        """Register a new agent type"""
        cls._agent_types[agent_type] = agent_class
```

---

## 6. MCP Layer

### 6.1 MCP Client (app/mcp/client.py)

**Purpose**: Per-server MCP client with stdio transport

```python
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

class MCPClient:
    """MCP client for a single server"""
    
    def __init__(self, server_name: str, config: ServerConfig):
        self.server_name = server_name
        self.config = config
        self.session: Optional[ClientSession] = None
        self._tools: List[Tool] = []
        self._connected = False
    
    async def connect(self):
        """Connect to MCP server via stdio"""
        if self._connected:
            return
        
        server_params = StdioServerParameters(
            command=self.config.command,
            args=self.config.args,
            env=self.config.env
        )
        
        async with stdio_client(server_params) as (read, write):
            self.session = ClientSession(read, write)
            await self.session.initialize()
            
            # Discover tools
            tools_response = await self.session.list_tools()
            self._tools = [
                Tool.from_mcp_tool(tool, self.server_name)
                for tool in tools_response.tools
            ]
            
            self._connected = True
    
    async def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> ToolResult:
        """Call a tool on this MCP server"""
        if not self._connected:
            raise RuntimeError("MCP client not connected")
        
        # Strip server prefix if present
        if tool_name.startswith(f"{self.server_name}__"):
            tool_name = tool_name[len(self.server_name) + 2:]
        
        result = await self.session.call_tool(tool_name, arguments)
        return ToolResult.from_mcp_result(result)
    
    async def disconnect(self):
        """Disconnect from MCP server"""
        if self.session:
            await self.session.close()
            self._connected = False
```

### 6.2 MCP Client Manager (app/mcp/client_manager.py)

**Purpose**: Manages multiple MCP client connections - singleton

**Location**: Line 15 in `app/mcp/client_manager.py`

```python
class MCPClientManager:
    """Singleton manager for MCP client connections"""
    
    _instance: Optional["MCPClientManager"] = None
    _initialized = False
    _lock = asyncio.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        self._clients: Dict[str, MCPClient] = {}
        self._tool_registry: Optional[ToolRegistry] = None
    
    async def connect_all(self):
        """Connect to all configured MCP servers"""
        if self._initialized:
            return
        
        async with self._lock:
            if self._initialized:
                return
            
            # Get server configurations
            server_configs = await self._load_server_configs()
            
            # Connect to each server
            for name, config in server_configs.items():
                client = MCPClient(name, config)
                await client.connect()
                self._clients[name] = client
            
            # Register tools with ToolRegistry
            await self._register_tools()
            
            self._initialized = True
    
    async def get_client(self, server_name: str) -> MCPClient:
        """Get MCP client by server name"""
        if server_name not in self._clients:
            raise ValueError(f"MCP server not connected: {server_name}")
        return self._clients[server_name]
    
    async def call_tool(
        self,
        full_tool_name: str,  # Format: "server_name__tool_name"
        arguments: Dict[str, Any]
    ) -> ToolResult:
        """Call a tool by its full name"""
        parts = full_tool_name.split("__", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid tool name format: {full_tool_name}")
        
        server_name, tool_name = parts
        client = await self.get_client(server_name)
        return await client.call_tool(tool_name, arguments)
    
    async def disconnect_all(self):
        """Disconnect from all MCP servers"""
        for client in self._clients.values():
            await client.disconnect()
        self._clients.clear()
        self._initialized = False
```

### 6.3 MCP Server Manager (app/mcp/server_manager.py)

**Purpose**: MCP server lifecycle management (start/stop)

```python
class MCPServerManager:
    """Manages MCP server lifecycle"""
    
    def __init__(self):
        self._processes: Dict[str, subprocess.Popen] = {}
        self._server_configs: Dict[str, ServerConfig] = {}
    
    async def start_server(self, server_name: str):
        """Start an MCP server process"""
        if server_name in self._processes:
            return  # Already running
        
        config = self._server_configs.get(server_name)
        if not config:
            raise ValueError(f"Unknown MCP server: {server_name}")
        
        process = subprocess.Popen(
            [config.command] + config.args,
            env=config.env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        self._processes[server_name] = process
        
        # Wait for server to be ready
        await self._wait_for_ready(server_name)
    
    async def stop_server(self, server_name: str):
        """Stop an MCP server process"""
        if server_name not in self._processes:
            return
        
        process = self._processes[server_name]
        process.terminate()
        
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        
        del self._processes[server_name]
    
    async def stop_all(self):
        """Stop all MCP servers"""
        for server_name in list(self._processes.keys()):
            await self.stop_server(server_name)
```

---

## 7. Orchestrator

### 7.1 Orchestrator Core (app/orchestrator/core.py)

**Purpose**: LangGraph workflow coordinator with mode selection

```python
class Orchestrator:
    """LangGraph workflow coordinator - singleton"""
    
    _instance: Optional["Orchestrator"] = None
    
    def __init__(
        self,
        runtime: AgentRuntime,
        checkpointer: Optional[SQLiteCheckpointer] = None
    ):
        self.runtime = runtime
        self.checkpointer = checkpointer
        self._graphs: Dict[str, CompiledGraph] = {}
        self._graph_builder = GraphBuilder()
    
    async def execute_task(
        self,
        task: Task,
        mode: ExecutionMode = ExecutionMode.AUTO
    ) -> TaskResult:
        """Execute task with mode selection"""
        
        # Determine execution mode
        selected_mode = await self._select_mode(task, mode)
        
        # Get or compile graph for mode
        graph = await self._get_or_compile_graph(selected_mode)
        
        # Execute via LangGraph
        result = await self._execute_graph(graph, task)
        
        return TaskResult(
            task_id=task.id,
            status="completed",
            output=result
        )
    
    async def _select_mode(
        self,
        task: Task,
        preferred_mode: ExecutionMode
    ) -> ExecutionMode:
        """Select execution mode based on task characteristics"""
        if preferred_mode != ExecutionMode.AUTO:
            return preferred_mode
        
        # Use capability selector for auto mode
        from app.action_v1.selector import CapabilitySelector
        selector = CapabilitySelector()
        capability = selector.classify(task.query)
        
        if capability.is_deterministic:
            return ExecutionMode.ACTION_V1
        else:
            return ExecutionMode.LANGGRAPH
    
    async def _get_or_compile_graph(
        self,
        mode: ExecutionMode
    ) -> CompiledGraph:
        """Get cached graph or compile new one"""
        if mode not in self._graphs:
            self._graphs[mode] = self._graph_builder.build(mode)
        return self._graphs[mode]
```

### 7.2 Graph Builder (app/orchestrator/graph_builder.py)

**Purpose**: Compiles agent graphs with checkpointer integration

```python
class GraphBuilder:
    """Builds LangGraph StateGraph for different execution modes"""
    
    def build(self, mode: ExecutionMode) -> CompiledGraph:
        """Build graph for execution mode"""
        if mode == ExecutionMode.ACTION_V1:
            return self._build_action_v1_graph()
        elif mode == ExecutionMode.LANGGRAPH:
            return self._build_langgraph_full()
        elif mode == ExecutionMode.WORKFLOW:
            return self._build_workflow_graph()
        else:
            raise ValueError(f"Unknown execution mode: {mode}")
    
    def _build_langgraph_full(self) -> CompiledGraph:
        """Build full LangGraph with all nodes"""
        from app.langgraph.nodes import (
            planner_node,
            executor_node,
            verifier_node,
            approval_node,
            summarizer_node
        )
        
        # Create state graph
        workflow = StateGraph(AgentState)
        
        # Add nodes
        workflow.add_node("planner", planner_node)
        workflow.add_node("executor", executor_node)
        workflow.add_node("verifier", verifier_node)
        workflow.add_node("approval", approval_node)
        workflow.add_node("summarizer", summarizer_node)
        
        # Add edges
        workflow.add_edge(START, "planner")
        workflow.add_edge("planner", "executor")
        workflow.add_edge("executor", "verifier")
        
        # Conditional edges
        workflow.add_conditional_edges(
            "verifier",
            self._should_approve,
            {
                "needs_approval": "approval",
                "completed": "summarizer",
                "needs_replan": "planner"
            }
        )
        
        workflow.add_conditional_edges(
            "approval",
            self._check_approval,
            {
                "approved": "summarizer",
                "rejected": END
            }
        )
        
        workflow.add_edge("summarizer", END)
        
        # Compile with checkpointer
        return workflow.compile(
            checkpointer=self.checkpointer,
            interrupt_before=["approval"]  # Human-in-the-loop
        )
    
    def _build_action_v1_graph(self) -> CompiledGraph:
        """Build simplified graph for Action V1 fast path"""
        workflow = StateGraph(AgentState)
        
        workflow.add_node("selector", action_v1_selector_node)
        workflow.add_node("executor", action_v1_executor_node)
        workflow.add_node("verifier", action_v1_verifier_node)
        
        workflow.add_edge(START, "selector")
        workflow.add_edge("selector", "executor")
        workflow.add_edge("executor", "verifier")
        workflow.add_edge("verifier", END)
        
        return workflow.compile()
```

---

## 8. Configuration & Environment

### 8.1 Environment Variables

| Variable | Default | HTTP | gRPC | Description |
|----------|---------|------|------|-------------|
| `AGENTOS_RUNTIME_MODE` | `http` | ✅ | ✅ | Runtime mode: `http` or `grpc` |
| `SUPERVISOR_ADDRESS` | `localhost:50051` | ❌ | ✅ | gRPC supervisor address |
| `DATABASE_URL` | *required* | ✅ | ✅ | PostgreSQL connection string |
| `REDIS_URL` | `redis://localhost:6379/0` | ✅ | ❌ | Redis connection (HTTP only) |
| `GRPC_CHECKPOINT_PORT` | `50052` | ❌ | ✅ | Checkpoint service port |
| `GRPC_WORKER_PORT` | `50053` | ❌ | ✅ | Worker service port |
| `SQLITE_CHECKPOINT_PATH` | `checkpoints.sqlite` | ❌ | ✅ | SQLite checkpointer path |

### 8.2 Mode Detection

```python
# app/runtime/mode.py

class RuntimeMode(str, Enum):
    HTTP = "http"
    GRPC = "grpc"

def get_runtime_mode() -> RuntimeMode:
    """Get current runtime mode"""
    mode = os.getenv("AGENTOS_RUNTIME_MODE", "http")
    return RuntimeMode(mode)

def is_http_mode() -> bool:
    return get_runtime_mode() == RuntimeMode.HTTP

def is_grpc_mode() -> bool:
    return get_runtime_mode() == RuntimeMode.GRPC
```

---

## 9. Async/Threading Patterns

### 9.1 Async Pattern Summary

| Component | Pattern | Notes |
|-----------|---------|-------|
| **gRPC Server** | `grpc.aio.server()` | Pure asyncio |
| **LangGraph** | `AsyncSqliteSaver` | Thread pool via `run_in_executor()` |
| **FastAPI** | Sync endpoints | Wraps async runtime calls |
| **Desktop Entry** | `asyncio.run(main())` | Pure async main loop |
| **SQLite** | `aiosqlite` | Async wrapper around sqlite3 |
| **MCP** | Async stdio | `stdio_client()` context manager |

### 9.2 Thread Safety

| Component | Thread Safety | Mechanism |
|-----------|---------------|-----------|
| **AgentRuntime** | Thread-safe | `asyncio.Lock()` |
| **MCPClientManager** | Thread-safe | `asyncio.Lock()` |
| **SQLiteCheckpointer** | Thread-safe | Connection pooling |
| **ToolRegistry** | Thread-safe | Singleton with lock |

### 9.3 Initialization Sequence

```
1. bootstrap()
   ├── detect_runtime_mode()
   ├── DatabaseManager()          # Both modes
   ├── Redis() (HTTP only)        # Conditional
   ├── MCPClientManager()         # Both modes
   ├── GRPCClient() (gRPC only)   # Conditional
   └── AgentRuntime()             # Both modes

2. runtime.initialize()
   ├── Redis mutex lock
   ├── mcp_manager.connect_all()
   │   └── For each server:
   │       ├── MCPClient()
   │       └── client.connect()
   └── grpc_client.connect() (gRPC only)

3. orchestrator.execute_task()
   ├── _select_mode()
   ├── _get_or_compile_graph()
   │   └── graph_builder.build()
   └── graph.ainvoke()
```

---

## 10. Mode-Specific Behavior

### 10.1 Component Availability by Mode

| Component | HTTP Mode | gRPC Mode | Notes |
|-----------|-----------|-----------|-------|
| FastAPI | ✅ | ❌ | Web API framework |
| Redis | ✅ | ❌ | Caching/pubsub |
| gRPC Client | ❌ | ✅ | Supervisor communication |
| gRPC Server | ❌ | ✅ | Accepts supervisor requests |
| SQLite | ✅ | ✅ | Both modes use SQLite checkpointer |
| PostgreSQL | ✅ | ✅ | Primary database |
| MCP Tools | ✅ | ✅ | Available in both modes |

### 10.2 Execution Path Differences

**HTTP Mode**:
```
Client Request
    ↓
FastAPI Endpoint
    ↓
Orchestrator.execute_task()
    ↓
LangGraph Graph (direct)
    ↓
Agent Execution
    ↓
Response
```

**gRPC Mode**:
```
Supervisor gRPC Call
    ↓
gRPC Server (RuntimeService)
    ↓
Orchestrator.execute_task()
    ↓
LangGraph Graph
    ↓
Agent Execution
    ↓
gRPC Response
    ↓
Supervisor
```

### 10.3 Configuration Loading

**HTTP Mode**:
```python
# Loads from environment + .env file
from app.config import settings

# Redis required
redis = Redis.from_url(settings.REDIS_URL)
```

**gRPC Mode**:
```python
# Loads from environment
from app.runtime.mode import get_runtime_mode

# Redis skipped (handled by supervisor)
redis = None
```

---

## Appendix A: File Locations

| Component | File Path | Line Count |
|-----------|-----------|------------|
| FastAPI Entry | `app/main.py` | ~350 |
| Desktop Entry | `app/desktop_entry.py` | ~150 |
| Bootstrap | `app/bootstrap.py` | ~200 |
| AgentRuntime | `app/runtime/runtime.py` | ~420 |
| Runtime Mode | `app/runtime/mode.py` | ~100 |
| gRPC Server | `app/runtime/grpc_server.py` | ~385 |
| SQLite Checkpointer | `app/langgraph/sqlite_checkpointer.py` | ~300 |
| Base Agent | `app/agents/base.py` | ~80 |
| ReAct Agent | `app/agents/react_agent.py` | ~150 |
| Agent Factory | `app/agents/factory.py` | ~100 |
| MCP Client | `app/mcp/client.py` | ~200 |
| MCP Client Manager | `app/mcp/client_manager.py` | ~180 |
| MCP Server Manager | `app/mcp/server_manager.py` | ~150 |
| Orchestrator | `app/orchestrator/core.py` | ~400 |
| Graph Builder | `app/orchestrator/graph_builder.py` | ~250 |
| gRPC Client | `app/proto/grpc_client.py` | ~330 |

---

## Appendix B: Key Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `fastapi` | 0.121+ | Web framework (HTTP mode) |
| `grpcio` | 1.62+ | gRPC client/server |
| `langgraph` | 0.0.50+ | LangGraph orchestration |
| `langchain` | 0.1+ | LLM/agent framework |
| `mcp` | 1.0+ | Model Context Protocol |
| `sqlalchemy` | 2.0+ | Database ORM |
| `redis` | 5.0+ | Redis client (HTTP mode) |
| `aiosqlite` | 0.20+ | Async SQLite |
| `pydantic` | 2.12+ | Data validation |

---

## Appendix C: Testing

### Unit Tests
```bash
# Test runtime mode detection
pytest tests/unit/test_runtime_mode.py -v

# Test gRPC client
pytest tests/unit/test_grpc_client.py -v

# Test SQLite checkpointer
pytest tests/unit/test_sqlite_checkpointer.py -v
```

### Integration Tests
```bash
# Test end-to-end gRPC flow
pytest tests/integration/test_grpc_e2e.py -v

# Test mode switching
pytest tests/integration/test_mode_switching.py -v

# Test supervisor communication
pytest tests/integration/test_supervisor.py -v
```

### Benchmarks
```bash
# gRPC latency benchmarks
pytest tests/benchmarks/test_grpc_latency.py -v

# Full benchmark suite
pytest tests/benchmarks/ -v
```

---

*Document Version: 1.0*  
*Last Updated: 2026-05-09*  
*Status: Complete*
