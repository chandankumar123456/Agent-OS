# AgentOS v2 — Deep Redesign Specification
## 2026-04-24

---

## 1. Agent Builder v2 — From Form to Composition Studio

### Problem
Current Agent Builder is a flat form (name, prompt, model, temperature, tools). It lacks the depth of modern agent frameworks (CrewAI, AutoGen, LangGraph). Users cannot express agent personality, goals, reasoning strategies, or tool binding parameters.

### Industry Patterns
- **CrewAI**: Role / Goal / Backstory pattern; YAML-based declarative config; Visual Agent Builder with real-time testing
- **AutoGen**: Conversable agents with code execution; group chat patterns; nested chat
- **OpenAI GPT Builder**: Conversation-based tuning; knowledge file upload; action (tool) binding with auth

### Proposed Design

#### Agent Schema v2 (Backend)
```python
class AgentConfigV2(BaseModel):
    agent_id: str
    name: str
    role: str           # e.g., "Senior Research Analyst"
    goal: str           # e.g., "Find and summarize information about X"
    backstory: str      # Personality + context
    
    # LLM Configuration
    model: str
    temperature: float
    max_tokens: int
    reasoning: bool = False
    max_reasoning_attempts: int = 3
    
    # Tool Binding
    tools: List[AgentToolBinding]
    allow_delegation: bool = False
    
    # Memory
    memory_enabled: bool = True
    knowledge_sources: List[str] = []  # IDs of uploaded docs
    
    # Execution Control
    max_iter: int = 20
    max_execution_time: int = 300
    max_retry_limit: int = 2
    
    # Templates
    system_template: Optional[str] = None
    prompt_template: Optional[str] = None
    response_template: Optional[str] = None

class AgentToolBinding(BaseModel):
    tool_name: str
    # Parameter mapping: agent can pre-fill or transform tool params
    param_bindings: Dict[str, str] = {}  # e.g., {"query": "{{task.input}}"}
    required: bool = False
    fallback_tool: Optional[str] = None
```

#### Frontend: Agent Composition Studio
- **Left Panel**: Template library (Researcher, Coder, Analyst, Creative, Custom)
- **Center Canvas**: Tabbed editor
  - *Identity*: Role, Goal, Backstory (rich text with examples)
  - *Brain*: Model, temperature, reasoning toggles
  - *Tools*: Visual drag-drop tool binding with param mapping
  - *Memory*: Knowledge source upload (txt, pdf, md)
  - *Advanced*: Templates, iteration limits, delegation
- **Right Panel**: Live Test Chat — conversation history with the agent, editable system prompt, regenerate buttons
- **Bottom Bar**: Save, Version, Export (YAML/JSON), Deploy

### API Additions
- `POST /agents/v2` — create agent with v2 schema
- `GET /agents/v2/templates` — list built-in templates with full config
- `POST /agents/v2/{id}/test` — test agent with a message, returns streaming response
- `POST /agents/v2/{id}/knowledge` — upload knowledge source
- `GET /agents/v2/{id}/versions` — version history

---

## 2. Workflow Orchestrator v2 — Event-Driven State Machine

### Problem
Current orchestrator compiles static graphs and falls back to legacy pipeline on error. It lacks: dynamic task spawning, event-driven triggers, compensation patterns, real-time status streaming, and robust failure recovery.

### Industry Patterns
- **Prefect**: Pythonic flows with `@flow`/`@task` decorators; state tracking; dynamic runtime; event-driven automations; resume from failure
- **Temporal**: Durable execution; state machines; sagas; human signals
- **LangGraph**: Checkpoint-based state persistence; conditional edges; interrupt for human-in-the-loop; parallel execution via `Send`

### Proposed Design

#### Execution Engine
Replace the static graph compilation with a **hybrid engine**:
1. **LangGraph** for agent reasoning loops (plan → execute → verify) with PostgreSQL checkpoints
2. **Prefect-like task runner** for tool execution and side effects
3. **Event bus** (Redis pub/sub) for cross-agent communication and status streaming

```python
class WorkflowOrchestratorV2:
    def __init__(self):
        self.checkpointer = PostgresCheckpointSaver()
        self.event_bus = RedisEventBus()
        self.task_runner = CeleryTaskRunner()
    
    async def execute(self, workflow_def: WorkflowDefinition, trigger: Trigger):
        # 1. Compile to LangGraph state graph
        graph = self.compiler.compile(workflow_def)
        
        # 2. Subscribe to events for real-time updates
        async with self.event_bus.subscribe(workflow_def.id) as events:
            # 3. Run graph with checkpointing
            result = await graph.ainvoke(
                state,
                config={"configurable": {"thread_id": workflow_def.id}},
            )
            # 4. Emit completion event
            await self.event_bus.publish("workflow.completed", result)
```

#### Workflow Definition v2
```python
class WorkflowDefinition(BaseModel):
    workflow_id: str
    name: str
    version: str
    
    triggers: List[Trigger]  # schedule, webhook, event, manual
    
    nodes: List[WorkflowNodeV2]
    edges: List[WorkflowEdgeV2]
    
    # Failure handling
    on_failure: FailurePolicy  # retry, fallback, compensate, pause
    max_retries: int = 3
    retry_delay: int = 5
    
    # Human-in-the-loop
    approval_gates: List[ApprovalGate]

class WorkflowNodeV2(BaseModel):
    node_id: str
    name: str
    type: NodeType  # agent, tool, decision, wait, subflow, map
    config: Dict[str, Any]
    
    # Execution
    agent_id: Optional[str]  # reference to AgentConfigV2
    tool_bindings: List[ToolBinding]
    
    # Dynamic spawning
    map_over: Optional[str]  # iterate over a list output
    condition: Optional[str]  # python expression for decision nodes
    
    # Timeout & retry
    timeout: int = 300
    retry_policy: RetryPolicy

class Trigger(BaseModel):
    type: TriggerType  # cron, webhook, event, manual
    config: Dict[str, Any]  # e.g., {"cron": "0 9 * * *"}
```

#### Event Bus (Redis Pub/Sub)
```python
class RedisEventBus:
    async def publish(self, channel: str, event: Event):
        await redis.publish(f"agentos:{channel}", event.json())
    
    async def subscribe(self, channel: str) -> AsyncIterator[Event]:
        pubsub = redis.pubsub()
        await pubsub.subscribe(f"agentos:{channel}")
        async for message in pubsub.listen():
            yield Event.parse(message)
```

#### WebSocket Streaming
Add a WebSocket endpoint `/ws/workflows/{workflow_id}` that streams node status changes in real-time.

### API Additions
- `POST /workflows/v2` — create workflow v2
- `GET /workflows/v2/{id}/events` — SSE stream of workflow events
- `POST /workflows/v2/{id}/trigger` — manual trigger
- `POST /workflows/v2/{id}/pause` — pause execution
- `POST /workflows/v2/{id}/resume` — resume from checkpoint
- `POST /workflows/v2/{id}/approve` — approve a gate

---

## 3. Workflow Builder v2 — Visual Studio with Live Execution

### Problem
Current Workflow Builder is a drag-drop canvas with basic node types. It lacks: execution simulation, real-time status on nodes, parameter binding UI, validation feedback, and connection to actual agent/tool definitions.

### Industry Patterns
- **n8n**: Node-based workflow builder; each node is a configurable action; live execution with status indicators; error handling per node
- **Retool Workflows**: Visual builder with SQL/API nodes; parameter passing between nodes; branching logic
- **LangChain Studio**: LangGraph visualization; node state inspection; checkpoint browsing

### Proposed Design

#### Canvas Enhancements
- **Node Types**:
  - *Agent Node*: Select from saved agents; show agent icon, role badge
  - *Tool Node*: Select from tool registry; configure param bindings visually
  - *Decision Node*: Branching with visual yes/no paths; condition editor with autocomplete
  - *Map Node*: Fan-out over a list; visual representation of iteration
  - *Wait Node*: Human approval gate; shows who's assigned
  - *Subflow Node*: Embed another workflow; expandable inline
- **Edge Types**: Success (green), Error (red), Conditional (amber dashed)
- **Live Status**: Nodes pulse when running, turn green on success, red on error; tooltip shows last output
- **Mini-Log**: Bottom panel shows execution log per node

#### Parameter Binding UI
When connecting two nodes, a binding editor appears:
```
Source: Agent Node "Planner" → Output: "plan.steps"
Target: Agent Node "Executor" → Input: "steps"
Transform: (optional) "{{plan.steps | first}}"
```

#### Validation Engine
Real-time validation as user builds:
- Missing required params → red outline on node
- Type mismatch between connected nodes → red edge with tooltip
- Cycle detection → toast notification
- Unreachable nodes → grayed out with warning

#### Simulation Mode
"Dry Run" button that executes workflow with mock data:
- Shows data flowing through edges
- Highlights path taken through decision nodes
- Shows estimated token usage and cost

### API Additions
- `POST /workflows/v2/validate` — validate workflow definition without saving
- `POST /workflows/v2/simulate` — dry run with mock data
- `GET /workflows/v2/{id}/status` — current execution status of all nodes

---

## 4. Tool Registry v2 — Universal Tool Platform

### Problem
Current registry is a simple dict of tools. No schema validation, no sandboxing, no versioning, no dependency tracking, no OpenAPI ingestion. MCP tools are wrapped but not deeply integrated.

### Industry Patterns
- **LangChain Tools**: Unified interface with `invoke()`; structured input/output schemas; async support
- **OpenAI Functions**: JSONSchema-based function definitions; strict mode validation
- **MCP (Model Context Protocol)**: Stdio/SSE transport; tool discovery; capability negotiation
- **E2B Sandbox**: Secure code execution in cloud sandboxes

### Proposed Design

#### Tool Interface v2
```python
class ToolV2(BaseModel):
    tool_id: str
    name: str
    description: str
    version: str
    
    # Schema
    input_schema: JsonSchema
    output_schema: Optional[JsonSchema]
    
    # Implementation
    implementation: ToolImplementation
    
    # Metadata
    category: str
    tags: List[str]
    author: str
    dependencies: List[str]  # other tool IDs
    
    # Execution config
    sandboxed: bool = False
    timeout: int = 30
    max_retries: int = 2
    
    # Telemetry
    invocation_count: int = 0
    avg_latency_ms: float = 0.0
    error_rate: float = 0.0

class ToolImplementation(BaseModel):
    type: ImplementationType  # native, mcp, openapi, python, docker
    config: Dict[str, Any]
    # native: {module: "app.tools.search", class: "SearchTool"}
    # mcp: {server_name: "filesystem"}
    # openapi: {spec_url: "...", operation_id: "..."}
    # python: {code: "..."}
    # docker: {image: "...", command: "..."}
```

#### Plugin Architecture
```
app/tools/plugins/
  __init__.py
  loader.py          # Dynamic import and hot-reload
  sandbox.py         # Docker/E2B sandbox execution
  openapi_ingestor.py # Convert OpenAPI specs to ToolV2
```

#### OpenAPI Ingestion
Users can paste an OpenAPI spec URL. The system:
1. Fetches and validates the spec
2. Creates one ToolV2 per operation
3. Auto-generates input/output schemas
4. Creates an HTTP client wrapper
5. Registers all tools under a category

#### Tool Sandbox
For untrusted tools (user-submitted Python, Docker):
- Execute in E2B sandbox or local Docker container
- Time and memory limits enforced
- Network access controlled (allowlist)
- Output sanitized before returning

#### Health Monitoring
Continuous background health checks:
- Ping each tool with a no-op invocation every 60s
- Track latency percentiles (p50, p95, p99)
- Alert when error rate > 5% or latency > 10s
- Auto-disable unhealthy tools with graceful degradation

#### Dependency Graph
Tools can declare dependencies on other tools:
- Visualize dependency graph in UI
- Detect circular dependencies at registration time
- Install/update dependencies atomically

### API Additions
- `POST /tools/v2` — register tool v2
- `POST /tools/v2/ingest-openapi` — ingest from OpenAPI spec
- `POST /tools/v2/{id}/sandbox` — run in sandbox
- `GET /tools/v2/{id}/health` — detailed health metrics
- `GET /tools/v2/{id}/telemetry` — invocation stats
- `GET /tools/v2/dependency-graph` — full dependency graph

---

## 5. User Onboarding v2 — Progressive Discovery System

### Problem
Current onboarding is a 4-step modal. It lacks: progressive feature disclosure, interactive tutorials, contextual help, sample data, and personalized guidance based on user actions.

### Industry Patterns
- **Linear**: Minimalist onboarding with contextual tooltips; progress tracking; keyboard shortcuts guide
- **Notion**: Blank slate templates; inline video tutorials; command palette discovery
- **Vercel**: Project scaffolding from templates; deploy button; real-time feedback

### Proposed Design

#### Onboarding Flow
1. **Welcome Screen** (modal)
   - Value proposition: "Build AI agents in minutes"
   - Quick-start options: "I want to..." (Run a task / Build an agent / Create a workflow)
   - Skip option: "I'll explore on my own"

2. **Contextual Product Tour** (Shepherd.js / Intro.js)
   - Triggered automatically on first visit to each page
   - Highlights key UI elements with step-by-step tooltips
   - User can dismiss or mark as complete
   - Progress persisted in localStorage

3. **Sample Data Seeding** (Backend)
   - On first signup, automatically create:
     - 3 example agents (Researcher, Coder, Data Analyst)
     - 2 example workflows (Content Pipeline, Data Processing)
     - 1 completed task with full trace for demonstration
   - Marked with `is_example: true` so users can delete them

4. **Guided First Run**
   - If user selects "Run a task":
     - Pre-fill query: "Summarize the key benefits of multi-agent systems"
     - Highlight Execute button with pulsing animation
     - After completion, explain the result panel and trace
   - If user selects "Build an agent":
     - Navigate to Agent Builder with Researcher template pre-selected
     - Guide through identity → tools → test flow
   - If user selects "Create a workflow":
     - Navigate to Workflow Builder with Sequential Review template
     - Guide through adding nodes, connecting edges, executing

5. **Help System**
   - Floating help button (bottom-right) on every page
   - Contextual: shows help relevant to current page
   - Searchable knowledge base with common tasks
   - "What's New" changelog for returning users

#### Backend: Onboarding State API
```python
class UserOnboardingState(BaseModel):
    user_id: str
    has_completed_tour: bool = False
    has_created_first_task: bool = False
    has_created_first_agent: bool = False
    has_created_first_workflow: bool = False
    dismissed_prompts: List[str] = []
    
    @property
    def onboarding_complete(self) -> bool:
        return self.has_completed_tour and (
            self.has_created_first_task or 
            self.has_created_first_agent or 
            self.has_created_first_workflow
        )
```

- `GET /onboarding/state` — get current onboarding state
- `POST /onboarding/complete/{step}` — mark step complete
- `POST /onboarding/seed` — create example data (idempotent)

#### Frontend Components
- `OnboardingModal.tsx` — welcome + intent selection
- `ContextualTour.tsx` — Shepherd.js wrapper with step definitions per route
- `HelpWidget.tsx` — floating help button + searchable docs
- `EmptyState.tsx` — contextual empty states with CTA (not just "No items")

---

## Implementation Order

Given dependencies, the recommended order is:

1. **Tool Registry v2** — Other systems depend on tools
2. **Agent Builder v2** — Depends on tool registry for binding
3. **Workflow Orchestrator v2** — Depends on agents and tools
4. **Workflow Builder v2** — Depends on orchestrator v2 APIs
5. **Onboarding v2** — Depends on all features being ready to demonstrate

---

## Files to Create/Modify

### Backend
- `app/tools/v2/` — new tool registry, plugin loader, sandbox, openapi ingestor
- `app/agents/v2/` — new agent config schema, agent test endpoint
- `app/orchestrator/v2/` — event bus, workflow engine v2, checkpoint manager
- `app/api/routes/v2/` — new API routes (or extend existing with v2 prefix)
- `app/onboarding/` — onboarding state, sample data seeder

### Frontend
- `frontend/src/pages/AgentBuilderV2.tsx`
- `frontend/src/pages/WorkflowBuilderV2.tsx`
- `frontend/src/components/ToolRegistryV2.tsx`
- `frontend/src/components/Onboarding/` — tour, help widget, empty states
- `frontend/src/context/OnboardingContext.tsx`

### Database Migrations
- Add `agent_config_v2` table
- Add `workflow_definition_v2` table
- Add `tool_v2` table
- Add `user_onboarding_state` table
- Add `knowledge_sources` table
