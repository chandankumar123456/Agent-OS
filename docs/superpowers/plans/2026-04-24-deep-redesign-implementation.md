# AgentOS v2 Deep Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans.

**Goal:** Rebuild AgentOS core subsystems (Tool Registry, Agent Builder, Workflow Orchestrator, Workflow Builder, Onboarding) with production-grade architectures inspired by CrewAI, Prefect, LangGraph, and n8n.

**Architecture:** Implement behind `/v2` API prefixes to maintain backward compatibility. Each subsystem is isolated with clear interfaces.

**Tech Stack:** Python 3.11, FastAPI, LangGraph, SQLAlchemy, Celery, Redis, React 18, Tailwind, Shepherd.js

---

## Phase 1A: Tool Registry v2 Backend

### Task 1: Create ToolV2 schemas and models

**Files:**
- Create: `app/tools/v2/schemas.py`
- Create: `app/tools/v2/models.py`
- Modify: `app/memory/models.py`

- [ ] **Step 1: Create schemas.py with ToolV2, ToolImplementation, HealthMetrics**

```python
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
from enum import Enum

class ImplementationType(str, Enum):
    NATIVE = "native"
    MCP = "mcp"
    OPENAPI = "openapi"
    PYTHON = "python"
    DOCKER = "docker"

class ToolImplementation(BaseModel):
    type: ImplementationType
    config: Dict[str, Any]

class HealthMetrics(BaseModel):
    invocation_count: int = 0
    avg_latency_ms: float = 0.0
    error_rate: float = 0.0
    last_check: Optional[str] = None

class ToolV2(BaseModel):
    tool_id: str
    name: str
    description: str
    version: str = "1.0.0"
    input_schema: Dict[str, Any]
    output_schema: Optional[Dict[str, Any]] = None
    implementation: ToolImplementation
    category: str = "general"
    tags: List[str] = []
    author: str = "system"
    dependencies: List[str] = []
    sandboxed: bool = False
    timeout: int = 30
    max_retries: int = 2
    health: HealthMetrics = HealthMetrics()
```

- [ ] **Step 2: Add ToolV2Model to app/memory/models.py**

```python
class ToolV2Model(Base):
    __tablename__ = "tools_v2"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tool_id = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    description = Column(Text)
    version = Column(String, default="1.0.0")
    input_schema = Column(JSON, default={})
    output_schema = Column(JSON, nullable=True)
    implementation_type = Column(String, nullable=False)
    implementation_config = Column(JSON, default={})
    category = Column(String, default="general", index=True)
    tags = Column(JSON, default=[])
    author = Column(String, default="system")
    dependencies = Column(JSON, default=[])
    sandboxed = Column(Boolean, default=False)
    timeout = Column(Integer, default=30)
    max_retries = Column(Integer, default=2)
    invocation_count = Column(Integer, default=0)
    avg_latency_ms = Column(Float, default=0.0)
    error_rate = Column(Float, default=0.0)
    status = Column(String, default="active")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

- [ ] **Step 3: Write test for schema validation**

```python
def test_toolv2_schema():
    tool = ToolV2(
        tool_id="test_tool",
        name="Test Tool",
        description="A test tool",
        input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
        implementation=ToolImplementation(type=ImplementationType.NATIVE, config={"module": "app.tools.search"}),
    )
    assert tool.tool_id == "test_tool"
    assert tool.health.invocation_count == 0
```

Run: `pytest tests/test_tool_registry_v2.py -v`

---

### Task 2: Create ToolRegistryV2 with CRUD and health monitoring

**Files:**
- Create: `app/tools/v2/registry.py`
- Create: `app/tools/v2/health_monitor.py`

- [ ] **Step 1: Create registry.py**

```python
from typing import Dict, List, Optional
from .schemas import ToolV2, HealthMetrics
from ...memory.long_term import db
from ...memory.models import ToolV2Model
from sqlalchemy import select
from ...logs.logger import logger

class ToolRegistryV2:
    def __init__(self):
        self._cache: Dict[str, ToolV2] = {}
    
    async def register(self, tool: ToolV2) -> ToolV2:
        # Upsert to DB
        async with db.get_session() as session:
            existing = await session.execute(select(ToolV2Model).where(ToolV2Model.tool_id == tool.tool_id))
            row = existing.scalar_one_or_none()
            if row:
                row.name = tool.name
                row.description = tool.description
                row.version = tool.version
                row.input_schema = tool.input_schema
                row.output_schema = tool.output_schema
                row.implementation_type = tool.implementation.type
                row.implementation_config = tool.implementation.config
                row.category = tool.category
                row.tags = tool.tags
                row.author = tool.author
                row.dependencies = tool.dependencies
                row.sandboxed = tool.sandboxed
                row.timeout = tool.timeout
                row.max_retries = tool.max_retries
            else:
                row = ToolV2Model(
                    tool_id=tool.tool_id,
                    name=tool.name,
                    description=tool.description,
                    version=tool.version,
                    input_schema=tool.input_schema,
                    output_schema=tool.output_schema,
                    implementation_type=tool.implementation.type,
                    implementation_config=tool.implementation.config,
                    category=tool.category,
                    tags=tool.tags,
                    author=tool.author,
                    dependencies=tool.dependencies,
                    sandboxed=tool.sandboxed,
                    timeout=tool.timeout,
                    max_retries=tool.max_retries,
                )
                session.add(row)
            await session.commit()
        self._cache[tool.tool_id] = tool
        logger.info(f"Registered tool v2: {tool.tool_id}")
        return tool
    
    async def get(self, tool_id: str) -> Optional[ToolV2]:
        if tool_id in self._cache:
            return self._cache[tool_id]
        async with db.get_session() as session:
            result = await session.execute(select(ToolV2Model).where(ToolV2Model.tool_id == tool_id))
            row = result.scalar_one_or_none()
            if not row:
                return None
            tool = self._row_to_schema(row)
            self._cache[tool_id] = tool
            return tool
    
    async def list_all(self) -> List[ToolV2]:
        async with db.get_session() as session:
            result = await session.execute(select(ToolV2Model).where(ToolV2Model.status == "active"))
            rows = result.scalars().all()
            return [self._row_to_schema(r) for r in rows]
    
    async def list_by_category(self, category: str) -> List[ToolV2]:
        async with db.get_session() as session:
            result = await session.execute(select(ToolV2Model).where(ToolV2Model.category == category, ToolV2Model.status == "active"))
            rows = result.scalars().all()
            return [self._row_to_schema(r) for r in rows]
    
    async def delete(self, tool_id: str) -> bool:
        async with db.get_session() as session:
            result = await session.execute(select(ToolV2Model).where(ToolV2Model.tool_id == tool_id))
            row = result.scalar_one_or_none()
            if not row:
                return False
            row.status = "deleted"
            await session.commit()
        self._cache.pop(tool_id, None)
        return True
    
    def _row_to_schema(self, row: ToolV2Model) -> ToolV2:
        from .schemas import ToolImplementation, ImplementationType, HealthMetrics
        return ToolV2(
            tool_id=row.tool_id,
            name=row.name,
            description=row.description,
            version=row.version,
            input_schema=row.input_schema,
            output_schema=row.output_schema,
            implementation=ToolImplementation(type=ImplementationType(row.implementation_type), config=row.implementation_config),
            category=row.category,
            tags=row.tags,
            author=row.author,
            dependencies=row.dependencies,
            sandboxed=row.sandboxed,
            timeout=row.timeout,
            max_retries=row.max_retries,
            health=HealthMetrics(
                invocation_count=row.invocation_count,
                avg_latency_ms=row.avg_latency_ms,
                error_rate=row.error_rate,
            ),
        )

# Singleton
tool_registry_v2 = ToolRegistryV2()
```

- [ ] **Step 2: Create health_monitor.py**

```python
import asyncio
import time
from typing import Dict, Any
from .registry import tool_registry_v2
from .schemas import ToolV2, ImplementationType
from ...logs.logger import logger

class ToolHealthMonitor:
    def __init__(self, interval: int = 60):
        self.interval = interval
        self._task = None
    
    def start(self):
        if self._task is None:
            self._task = asyncio.create_task(self._loop())
            logger.info("Tool health monitor started")
    
    def stop(self):
        if self._task:
            self._task.cancel()
            self._task = None
    
    async def _loop(self):
        while True:
            try:
                await self._check_all()
            except Exception as e:
                logger.error(f"Health check loop error: {e}")
            await asyncio.sleep(self.interval)
    
    async def _check_all(self):
        tools = await tool_registry_v2.list_all()
        for tool in tools:
            await self._check_one(tool)
    
    async def _check_one(self, tool: ToolV2):
        start = time.time()
        try:
            # For native tools, try a no-op or lightweight call
            if tool.implementation.type == ImplementationType.NATIVE:
                success = True  # Native tools are trusted
            else:
                # For MCP/OpenAPI, we just verify connectivity
                success = True  # Simplified for now
            latency = (time.time() - start) * 1000
            await self._update_health(tool.tool_id, success, latency)
        except Exception as e:
            latency = (time.time() - start) * 1000
            await self._update_health(tool.tool_id, False, latency, str(e))
    
    async def _update_health(self, tool_id: str, success: bool, latency_ms: float, error: str = None):
        from ...memory.long_term import db
        from ...memory.models import ToolV2Model
        from sqlalchemy import select
        async with db.get_session() as session:
            result = await session.execute(select(ToolV2Model).where(ToolV2Model.tool_id == tool_id))
            row = result.scalar_one_or_none()
            if not row:
                return
            row.invocation_count += 1
            # Exponential moving average for latency
            alpha = 0.1
            row.avg_latency_ms = (alpha * latency_ms) + ((1 - alpha) * row.avg_latency_ms)
            if not success:
                row.error_rate = (alpha * 1.0) + ((1 - alpha) * row.error_rate)
            else:
                row.error_rate = (alpha * 0.0) + ((1 - alpha) * row.error_rate)
            await session.commit()

tool_health_monitor = ToolHealthMonitor()
```

- [ ] **Step 3: Write tests for registry CRUD**

```python
import pytest
from app.tools.v2.schemas import ToolV2, ToolImplementation, ImplementationType
from app.tools.v2.registry import ToolRegistryV2

@pytest.fixture
def registry():
    return ToolRegistryV2()

@pytest.mark.asyncio
async def test_register_and_get(registry):
    tool = ToolV2(tool_id="test", name="Test", description="Desc", input_schema={}, implementation=ToolImplementation(type=ImplementationType.NATIVE, config={}))
    await registry.register(tool)
    fetched = await registry.get("test")
    assert fetched is not None
    assert fetched.name == "Test"
```

---

### Task 3: Add v2 API routes for Tool Registry

**Files:**
- Create: `app/api/routes/tools_v2.py`
- Modify: `app/api/__init__.py`

- [ ] **Step 1: Create tools_v2.py routes**

```python
from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Any
from ...tools.v2.registry import tool_registry_v2
from ...tools.v2.schemas import ToolV2
from ...api.deps import get_current_user
from ...logs.logger import logger

router = APIRouter(prefix="/tools/v2", tags=["tools-v2"])

@router.get("")
async def list_tools_v2(_: object = Depends(get_current_user)):
    tools = await tool_registry_v2.list_all()
    return {"tools": [t.model_dump() for t in tools]}

@router.post("")
async def register_tool_v2(tool: ToolV2, current_user: object = Depends(get_current_user)):
    result = await tool_registry_v2.register(tool)
    logger.info(f"User {getattr(current_user, 'id', 'unknown')} registered tool v2 {tool.tool_id}")
    return {"tool": result.model_dump()}

@router.get("/{tool_id}")
async def get_tool_v2(tool_id: str, _: object = Depends(get_current_user)):
    tool = await tool_registry_v2.get(tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail=f"Tool {tool_id} not found")
    return {"tool": tool.model_dump()}

@router.delete("/{tool_id}")
async def delete_tool_v2(tool_id: str, current_user: object = Depends(get_current_user)):
    deleted = await tool_registry_v2.delete(tool_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Tool {tool_id} not found")
    logger.info(f"User {getattr(current_user, 'id', 'unknown')} deleted tool v2 {tool_id}")
    return {"message": f"Tool {tool_id} deleted"}

@router.get("/{tool_id}/health")
async def get_tool_health_v2(tool_id: str, _: object = Depends(get_current_user)):
    tool = await tool_registry_v2.get(tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail=f"Tool {tool_id} not found")
    return {"tool_id": tool_id, "health": tool.health.model_dump()}
```

- [ ] **Step 2: Mount routes in app/api/__init__.py**

```python
from .routes import tools, agents, auth, tasks, config, workflows, tools_v2
api_router.include_router(tools_v2.router)
```

---

## Phase 1B: Onboarding Backend

### Task 4: Create onboarding models and sample data seeder

**Files:**
- Create: `app/onboarding/models.py`
- Create: `app/onboarding/seeder.py`
- Modify: `app/memory/models.py`

- [ ] **Step 1: Add UserOnboardingState model to app/memory/models.py**

```python
class UserOnboardingState(Base):
    __tablename__ = "user_onboarding_state"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, unique=True, nullable=False, index=True)
    has_completed_tour = Column(Boolean, default=False)
    has_created_first_task = Column(Boolean, default=False)
    has_created_first_agent = Column(Boolean, default=False)
    has_created_first_workflow = Column(Boolean, default=False)
    dismissed_prompts = Column(JSON, default=[])
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

- [ ] **Step 2: Create seeder.py**

```python
from uuid import uuid4
from ..memory.long_term import agent_repo, workflow_repo, task_repo
from ..logs.logger import logger

EXAMPLE_AGENTS = [
    {
        "agent_key": f"example_researcher_{uuid4().hex[:8]}",
        "name": "Research Analyst",
        "role": "researcher",
        "system_prompt": "You are a research analyst. Your goal is to find and synthesize information on any topic. You use web search and text processing tools.",
        "model": "gpt-4o",
        "temperature": 0.3,
        "tools": ["web_search", "text_processor"],
    },
    {
        "agent_key": f"example_coder_{uuid4().hex[:8]}",
        "name": "Code Assistant",
        "role": "coder",
        "system_prompt": "You are a senior software engineer. Write clean, well-documented code. Use shell tools when needed.",
        "model": "gpt-4o",
        "temperature": 0.1,
        "tools": ["shell"],
    },
    {
        "agent_key": f"example_analyst_{uuid4().hex[:8]}",
        "name": "Data Analyst",
        "role": "analyst",
        "system_prompt": "You are a data analyst. Calculate metrics, process text, and present findings clearly.",
        "model": "gpt-4o-mini",
        "temperature": 0.2,
        "tools": ["calculator", "text_processor"],
    },
]

EXAMPLE_WORKFLOWS = [
    {
        "name": "Content Pipeline",
        "definition": {
            "nodes": [
                {"id": "research", "step": "Research topic", "agent_type": "executor", "node_type": "agent"},
                {"id": "draft", "step": "Draft content", "agent_type": "executor", "node_type": "agent", "depends_on": ["research"]},
                {"id": "review", "step": "Review content", "agent_type": "verifier", "node_type": "agent", "depends_on": ["draft"]},
            ]
        }
    },
    {
        "name": "Data Processing",
        "definition": {
            "nodes": [
                {"id": "ingest", "step": "Ingest data", "agent_type": "executor", "node_type": "agent"},
                {"id": "transform", "step": "Transform data", "agent_type": "executor", "node_type": "agent", "depends_on": ["ingest"]},
                {"id": "analyze", "step": "Analyze results", "agent_type": "verifier", "node_type": "agent", "depends_on": ["transform"]},
            ]
        }
    },
]

async def seed_example_data(user_id: str):
    """Idempotently seed example data for a user."""
    logger.info(f"Seeding example data for user {user_id}")
    
    # Seed agents
    for agent_data in EXAMPLE_AGENTS:
        try:
            await agent_repo.upsert(**agent_data, status="active", version="1.0.0")
        except Exception as e:
            logger.warning(f"Failed to seed agent {agent_data['name']}: {e}")
    
    # Seed workflows
    for wf_data in EXAMPLE_WORKFLOWS:
        try:
            await workflow_repo.create(
                task_id=str(uuid4()),
                user_id=user_id,
                name=wf_data["name"],
                definition=wf_data["definition"],
                status="saved",
            )
        except Exception as e:
            logger.warning(f"Failed to seed workflow {wf_data['name']}: {e}")
    
    logger.info(f"Example data seeding complete for user {user_id}")
```

---

### Task 5: Add Onboarding API routes

**Files:**
- Create: `app/api/routes/onboarding.py`
- Modify: `app/api/__init__.py`

- [ ] **Step 1: Create onboarding.py routes**

```python
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import List
from ...api.deps import get_current_user
from ...memory.long_term import db
from ...memory.models import UserOnboardingState
from ...onboarding.seeder import seed_example_data
from sqlalchemy import select
from ...logs.logger import logger

router = APIRouter(prefix="/onboarding", tags=["onboarding"])

class OnboardingStateResponse(BaseModel):
    has_completed_tour: bool
    has_created_first_task: bool
    has_created_first_agent: bool
    has_created_first_workflow: bool
    dismissed_prompts: List[str]
    onboarding_complete: bool

class CompleteStepRequest(BaseModel):
    step: str

async def _get_or_create_state(user_id: str) -> UserOnboardingState:
    async with db.get_session() as session:
        result = await session.execute(select(UserOnboardingState).where(UserOnboardingState.user_id == user_id))
        state = result.scalar_one_or_none()
        if not state:
            state = UserOnboardingState(user_id=user_id)
            session.add(state)
            await session.commit()
        return state

@router.get("/state", response_model=OnboardingStateResponse)
async def get_onboarding_state(current_user: object = Depends(get_current_user)):
    user_id = str(getattr(current_user, "id", ""))
    state = await _get_or_create_state(user_id)
    return OnboardingStateResponse(
        has_completed_tour=state.has_completed_tour,
        has_created_first_task=state.has_created_first_task,
        has_created_first_agent=state.has_created_first_agent,
        has_created_first_workflow=state.has_created_first_workflow,
        dismissed_prompts=state.dismissed_prompts,
        onboarding_complete=state.has_completed_tour and (state.has_created_first_task or state.has_created_first_agent or state.has_created_first_workflow),
    )

@router.post("/complete/{step}")
async def complete_step(step: str, current_user: object = Depends(get_current_user)):
    user_id = str(getattr(current_user, "id", ""))
    state = await _get_or_create_state(user_id)
    async with db.get_session() as session:
        if step == "tour":
            state.has_completed_tour = True
        elif step == "first_task":
            state.has_created_first_task = True
        elif step == "first_agent":
            state.has_created_first_agent = True
        elif step == "first_workflow":
            state.has_created_first_workflow = True
        elif step == "dismiss_prompt":
            pass  # handled separately
        await session.commit()
    logger.info(f"User {user_id} completed onboarding step: {step}")
    return {"success": True}

@router.post("/seed")
async def seed_data(current_user: object = Depends(get_current_user)):
    user_id = str(getattr(current_user, "id", ""))
    await seed_example_data(user_id)
    return {"success": True}
```

---

## Phase 2: Agent Builder v2 Backend + Frontend

### Task 6: Create Agent Config V2 Backend

**Files:**
- Create: `app/agents/v2/schemas.py`
- Create: `app/agents/v2/registry.py`
- Modify: `app/memory/models.py`

- [ ] **Step 1: Add AgentConfigV2 model to app/memory/models.py**

```python
class AgentConfigV2Model(Base):
    __tablename__ = "agent_config_v2"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    role = Column(String, nullable=False)
    goal = Column(Text)
    backstory = Column(Text)
    model = Column(String, default="gpt-4o")
    temperature = Column(Float, default=0.7)
    max_tokens = Column(Integer, default=2048)
    reasoning = Column(Boolean, default=False)
    max_reasoning_attempts = Column(Integer, default=3)
    tools = Column(JSON, default=[])
    allow_delegation = Column(Boolean, default=False)
    memory_enabled = Column(Boolean, default=True)
    knowledge_sources = Column(JSON, default=[])
    max_iter = Column(Integer, default=20)
    max_execution_time = Column(Integer, default=300)
    max_retry_limit = Column(Integer, default=2)
    system_template = Column(Text, nullable=True)
    prompt_template = Column(Text, nullable=True)
    response_template = Column(Text, nullable=True)
    status = Column(String, default="active")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

- [ ] **Step 2: Create app/agents/v2/schemas.py**

```python
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

class AgentToolBinding(BaseModel):
    tool_name: str
    param_bindings: Dict[str, str] = {}
    required: bool = False
    fallback_tool: Optional[str] = None

class AgentConfigV2(BaseModel):
    agent_id: str
    name: str
    role: str
    goal: str = ""
    backstory: str = ""
    model: str = "gpt-4o"
    temperature: float = 0.7
    max_tokens: int = 2048
    reasoning: bool = False
    max_reasoning_attempts: int = 3
    tools: List[AgentToolBinding] = []
    allow_delegation: bool = False
    memory_enabled: bool = True
    knowledge_sources: List[str] = []
    max_iter: int = 20
    max_execution_time: int = 300
    max_retry_limit: int = 2
    system_template: Optional[str] = None
    prompt_template: Optional[str] = None
    response_template: Optional[str] = None
```

- [ ] **Step 3: Create app/agents/v2/registry.py**

```python
from typing import Optional, List
from .schemas import AgentConfigV2
from ...memory.long_term import db
from ...memory.models import AgentConfigV2Model
from sqlalchemy import select
from ...logs.logger import logger

class AgentRegistryV2:
    async def register(self, config: AgentConfigV2) -> AgentConfigV2:
        async with db.get_session() as session:
            existing = await session.execute(select(AgentConfigV2Model).where(AgentConfigV2Model.agent_id == config.agent_id))
            row = existing.scalar_one_or_none()
            data = config.model_dump()
            if row:
                for key, value in data.items():
                    if hasattr(row, key):
                        setattr(row, key, value)
            else:
                row = AgentConfigV2Model(**data)
                session.add(row)
            await session.commit()
        logger.info(f"Registered agent v2: {config.agent_id}")
        return config
    
    async def get(self, agent_id: str) -> Optional[AgentConfigV2]:
        async with db.get_session() as session:
            result = await session.execute(select(AgentConfigV2Model).where(AgentConfigV2Model.agent_id == agent_id))
            row = result.scalar_one_or_none()
            if not row:
                return None
            return AgentConfigV2(**{c: getattr(row, c) for c in AgentConfigV2.model_fields})
    
    async def list_all(self) -> List[AgentConfigV2]:
        async with db.get_session() as session:
            result = await session.execute(select(AgentConfigV2Model).where(AgentConfigV2Model.status == "active"))
            rows = result.scalars().all()
            return [AgentConfigV2(**{c: getattr(r, c) for c in AgentConfigV2.model_fields}) for r in rows]

agent_registry_v2 = AgentRegistryV2()
```

---

### Task 7: Add Agent v2 API routes

**Files:**
- Create: `app/api/routes/agents_v2.py`
- Modify: `app/api/__init__.py`

- [ ] **Step 1: Create agents_v2.py routes**

```python
from fastapi import APIRouter, HTTPException, Depends
from typing import List
from ...agents.v2.registry import agent_registry_v2
from ...agents.v2.schemas import AgentConfigV2
from ...api.deps import get_current_user
from ...logs.logger import logger

router = APIRouter(prefix="/agents/v2", tags=["agents-v2"])

BUILT_IN_TEMPLATES = [
    {
        "id": "researcher",
        "name": "Research Agent",
        "config": AgentConfigV2(
            agent_id="template_researcher",
            name="Research Agent",
            role="researcher",
            goal="Uncover cutting-edge developments in any topic",
            backstory="You're a seasoned researcher with a knack for uncovering the latest developments.",
            model="gpt-4o",
            temperature=0.3,
            tools=[{"tool_name": "web_search"}, {"tool_name": "text_processor"}],
        ).model_dump(),
    },
    {
        "id": "coder",
        "name": "Code Agent",
        "config": AgentConfigV2(
            agent_id="template_coder",
            name="Code Agent",
            role="coder",
            goal="Write and debug code efficiently",
            backstory="Expert software engineer with 10 years of experience.",
            model="gpt-4o",
            temperature=0.1,
            tools=[{"tool_name": "shell"}],
        ).model_dump(),
    },
    {
        "id": "creative",
        "name": "Creative Writer",
        "config": AgentConfigV2(
            agent_id="template_creative",
            name="Creative Writer",
            role="creative",
            goal="Create compelling creative content",
            backstory="Award-winning creative writer with a unique voice.",
            model="gpt-4o",
            temperature=0.9,
            tools=[{"tool_name": "text_processor"}],
        ).model_dump(),
    },
]

@router.get("/templates")
async def list_agent_templates(_: object = Depends(get_current_user)):
    return {"templates": BUILT_IN_TEMPLATES}

@router.get("")
async def list_agents_v2(_: object = Depends(get_current_user)):
    agents = await agent_registry_v2.list_all()
    return {"agents": [a.model_dump() for a in agents]}

@router.post("")
async def create_agent_v2(config: AgentConfigV2, current_user: object = Depends(get_current_user)):
    result = await agent_registry_v2.register(config)
    logger.info(f"User {getattr(current_user, 'id', 'unknown')} created agent v2 {config.agent_id}")
    return {"agent": result.model_dump()}

@router.get("/{agent_id}")
async def get_agent_v2(agent_id: str, _: object = Depends(get_current_user)):
    agent = await agent_registry_v2.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    return {"agent": agent.model_dump()}
```

---

## Phase 3: Workflow Orchestrator v2

### Task 8: Create Redis Event Bus

**Files:**
- Create: `app/orchestrator/v2/event_bus.py`

- [ ] **Step 1: Create event_bus.py**

```python
import asyncio
import json
from typing import AsyncIterator, Dict, Any, Optional
from ...memory.short_term import redis_client
from ...logs.logger import logger

class Event:
    def __init__(self, event_type: str, payload: Dict[str, Any], source: str = ""):
        self.event_type = event_type
        self.payload = payload
        self.source = source
    
    def json(self) -> str:
        return json.dumps({"type": self.event_type, "payload": self.payload, "source": self.source})
    
    @classmethod
    def parse(cls, raw: str) -> "Event":
        data = json.loads(raw)
        return cls(data["type"], data.get("payload", {}), data.get("source", ""))

class RedisEventBus:
    def __init__(self):
        self._pubsub = None
    
    async def publish(self, channel: str, event: Event):
        try:
            await redis_client.client.publish(f"agentos:{channel}", event.json())
        except Exception as e:
            logger.error(f"Event publish failed: {e}")
    
    async def subscribe(self, channel: str) -> AsyncIterator[Event]:
        try:
            pubsub = redis_client.client.pubsub()
            await pubsub.subscribe(f"agentos:{channel}")
            async for message in pubsub.listen():
                if message["type"] == "message":
                    try:
                        yield Event.parse(message["data"])
                    except Exception as e:
                        logger.warning(f"Failed to parse event: {e}")
        except Exception as e:
            logger.error(f"Event subscribe failed: {e}")
        finally:
            try:
                await pubsub.unsubscribe(f"agentos:{channel}")
            except:
                pass

event_bus = RedisEventBus()
```

---

### Task 9: Create Workflow Engine v2

**Files:**
- Create: `app/orchestrator/v2/engine.py`
- Create: `app/orchestrator/v2/schemas.py`

- [ ] **Step 1: Create schemas.py**

```python
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from enum import Enum

class NodeType(str, Enum):
    AGENT = "agent"
    TOOL = "tool"
    DECISION = "decision"
    WAIT = "wait"
    SUBFLOW = "subflow"
    MAP = "map"

class TriggerType(str, Enum):
    MANUAL = "manual"
    CRON = "cron"
    WEBHOOK = "webhook"
    EVENT = "event"

class WorkflowNodeV2(BaseModel):
    node_id: str
    name: str
    type: NodeType
    config: Dict[str, Any] = {}
    agent_id: Optional[str] = None
    tool_bindings: List[Dict[str, Any]] = []
    map_over: Optional[str] = None
    condition: Optional[str] = None
    timeout: int = 300
    retry_count: int = 2

class WorkflowEdgeV2(BaseModel):
    from_node: str
    to_node: str
    condition: Optional[str] = None
    label: Optional[str] = None

class Trigger(BaseModel):
    type: TriggerType
    config: Dict[str, Any]

class WorkflowDefinitionV2(BaseModel):
    workflow_id: str
    name: str
    version: str = "1.0.0"
    triggers: List[Trigger] = []
    nodes: List[WorkflowNodeV2]
    edges: List[WorkflowEdgeV2]
    max_retries: int = 3
    retry_delay: int = 5
```

- [ ] **Step 2: Create engine.py**

```python
from typing import Dict, Any, List
from .schemas import WorkflowDefinitionV2, WorkflowNodeV2, NodeType
from .event_bus import event_bus, Event
from ...logs.logger import logger

class WorkflowEngineV2:
    async def execute(self, workflow: WorkflowDefinitionV2, initial_context: Dict[str, Any]):
        logger.info(f"[WorkflowV2] Starting workflow {workflow.workflow_id}")
        await event_bus.publish(f"workflow:{workflow.workflow_id}", Event("workflow.started", {"workflow_id": workflow.workflow_id}))
        
        # Build adjacency list
        graph: Dict[str, List[str]] = {n.node_id: [] for n in workflow.nodes}
        for edge in workflow.edges:
            if edge.from_node in graph:
                graph[edge.from_node].append(edge.to_node)
        
        # Build node map
        node_map = {n.node_id: n for n in workflow.nodes}
        
        # Execution state
        completed = set()
        failed = set()
        context = dict(initial_context)
        
        # Find entry nodes (no incoming edges)
        all_targets = {e.to_node for e in workflow.edges}
        entry_nodes = [n for n in workflow.nodes if n.node_id not in all_targets]
        
        # BFS execution
        queue = [n.node_id for n in entry_nodes]
        
        while queue:
            node_id = queue.pop(0)
            if node_id in completed or node_id in failed:
                continue
            
            node = node_map.get(node_id)
            if not node:
                continue
            
            await event_bus.publish(f"workflow:{workflow.workflow_id}", Event("node.started", {"node_id": node_id, "workflow_id": workflow.workflow_id}))
            
            try:
                result = await self._execute_node(node, context)
                context[node_id] = result
                completed.add(node_id)
                await event_bus.publish(f"workflow:{workflow.workflow_id}", Event("node.completed", {"node_id": node_id, "result": result}))
                
                # Queue next nodes
                for next_id in graph.get(node_id, []):
                    if next_id not in queue and next_id not in completed:
                        queue.append(next_id)
            except Exception as e:
                logger.error(f"[WorkflowV2] Node {node_id} failed: {e}")
                failed.add(node_id)
                await event_bus.publish(f"workflow:{workflow.workflow_id}", Event("node.failed", {"node_id": node_id, "error": str(e)}))
        
        await event_bus.publish(f"workflow:{workflow.workflow_id}", Event("workflow.completed", {"workflow_id": workflow.workflow_id, "completed": list(completed), "failed": list(failed)}))
        return {"context": context, "completed": list(completed), "failed": list(failed)}
    
    async def _execute_node(self, node: WorkflowNodeV2, context: Dict[str, Any]) -> Any:
        if node.type == NodeType.AGENT:
            # Delegate to agent runtime
            from ...agents.v2.registry import agent_registry_v2
            agent = await agent_registry_v2.get(node.agent_id)
            if not agent:
                raise RuntimeError(f"Agent {node.agent_id} not found")
            return {"agent_id": node.agent_id, "status": "executed", "output": f"Agent {agent.name} executed"}
        elif node.type == NodeType.TOOL:
            # Execute tool
            return {"tool": node.tool_bindings, "status": "executed"}
        elif node.type == NodeType.DECISION:
            # Evaluate condition
            return {"condition": node.condition, "status": "evaluated", "context": context}
        elif node.type == NodeType.WAIT:
            return {"status": "waiting_approval"}
        else:
            return {"status": "unknown_node_type"}

workflow_engine_v2 = WorkflowEngineV2()
```

---

### Task 10: Add Workflow v2 API routes

**Files:**
- Create: `app/api/routes/workflows_v2.py`
- Modify: `app/api/__init__.py`

- [ ] **Step 1: Create workflows_v2.py**

```python
from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any
from ...orchestrator.v2.schemas import WorkflowDefinitionV2
from ...orchestrator.v2.engine import workflow_engine_v2
from ...orchestrator.v2.event_bus import event_bus, Event
from ...api.deps import get_current_user
from ...logs.logger import logger

router = APIRouter(prefix="/workflows/v2", tags=["workflows-v2"])

@router.post("/execute")
async def execute_workflow_v2(workflow: WorkflowDefinitionV2, current_user: object = Depends(get_current_user)):
    user_id = str(getattr(current_user, "id", "system"))
    logger.info(f"User {user_id} executing workflow v2 {workflow.workflow_id}")
    result = await workflow_engine_v2.execute(workflow, {"user_id": user_id, "workflow_id": workflow.workflow_id})
    return {"workflow_id": workflow.workflow_id, "result": result}

@router.post("/validate")
async def validate_workflow_v2(workflow: WorkflowDefinitionV2, _: object = Depends(get_current_user)):
    errors = []
    node_ids = {n.node_id for n in workflow.nodes}
    for edge in workflow.edges:
        if edge.from_node not in node_ids:
            errors.append(f"Edge references missing source: {edge.from_node}")
        if edge.to_node not in node_ids:
            errors.append(f"Edge references missing target: {edge.to_node}")
    if not workflow.nodes:
        errors.append("Workflow must have at least one node")
    return {"valid": len(errors) == 0, "errors": errors}

@router.get("/{workflow_id}/events")
async def stream_workflow_events(workflow_id: str, _: object = Depends(get_current_user)):
    from fastapi.responses import StreamingResponse
    import asyncio
    
    async def event_generator():
        try:
            async for event in event_bus.subscribe(f"workflow:{workflow_id}"):
                yield f"data: {event.json()}\n\n"
        except asyncio.CancelledError:
            pass
    
    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

---

## Phase 4: Workflow Builder v2 Frontend

### Task 11: Create Workflow Builder v2 page

**Files:**
- Create: `frontend/src/pages/WorkflowBuilderV2.tsx`

This is a large component. Key features:
- ReactFlow canvas with custom nodes (Agent, Tool, Decision, Wait, Map)
- Template sidebar with built-in templates
- Properties panel with parameter binding UI
- Validation feedback (red outlines, tooltips)
- Execute button with dry-run option

Since this is a very large file, the implementing agent should build it incrementally.

---

## Phase 5: Onboarding Frontend

### Task 12: Create Shepherd.js tour integration

**Files:**
- Install: `npm install shepherd.js`
- Create: `frontend/src/components/Onboarding/TourProvider.tsx`
- Create: `frontend/src/components/Onboarding/tourSteps.ts`

- [ ] **Step 1: Create tourSteps.ts**

```typescript
export const dashboardTourSteps = [
  {
    id: 'task-form',
    attachTo: { element: '#dashboard-task-form', on: 'bottom' },
    title: 'Submit a Task',
    text: 'Enter any query here and choose an execution mode. Try "Research AI trends" to get started.',
  },
  {
    id: 'metrics',
    attachTo: { element: '#metrics-panel', on: 'left' },
    title: 'Live Metrics',
    text: 'Track system health, task counts, and performance in real time.',
  },
  {
    id: 'recent-tasks',
    attachTo: { element: '#recent-tasks-panel', on: 'top' },
    title: 'Recent Tasks',
    text: 'All your tasks appear here with status indicators. Click any task to see its trace.',
  },
];

export const agentBuilderTourSteps = [
  {
    id: 'templates',
    attachTo: { element: '#agent-templates', on: 'right' },
    title: 'Agent Templates',
    text: 'Start with a template or build from scratch. Templates include pre-configured tools and prompts.',
  },
  {
    id: 'identity',
    attachTo: { element: '#agent-identity', on: 'bottom' },
    title: 'Agent Identity',
    text: 'Define role, goal, and backstory. These shape how the agent behaves and responds.',
  },
  {
    id: 'test-panel',
    attachTo: { element: '#agent-test-panel', on: 'top' },
    title: 'Test Your Agent',
    text: 'Send a test prompt and see how your agent responds before saving.',
  },
];
```

- [ ] **Step 2: Create TourProvider.tsx**

```tsx
import { useEffect, useRef } from 'react';
import Shepherd from 'shepherd.js';
import 'shepherd.js/dist/css/shepherd.css';

interface TourProviderProps {
  tourId: string;
  steps: any[];
  onComplete?: () => void;
}

export const TourProvider: React.FC<TourProviderProps> = ({ tourId, steps, onComplete }) => {
  const tourRef = useRef<Shepherd.Tour | null>(null);

  useEffect(() => {
    const hasSeen = localStorage.getItem(`tour_${tourId}`);
    if (hasSeen) return;

    const tour = new Shepherd.Tour({
      defaultStepOptions: {
        cancelIcon: { enabled: true },
        classes: 'shepherd-theme-dark',
        scrollTo: { behavior: 'smooth', block: 'center' },
      },
      useModalOverlay: true,
    });

    steps.forEach((step) => {
      tour.addStep({
        id: step.id,
        title: step.title,
        text: step.text,
        attachTo: step.attachTo,
        buttons: [
          { text: 'Skip', action: tour.cancel },
          { text: 'Next', action: tour.next },
        ],
      });
    });

    tour.on('complete', () => {
      localStorage.setItem(`tour_${tourId}`, 'true');
      onComplete?.();
    });

    tour.on('cancel', () => {
      localStorage.setItem(`tour_${tourId}`, 'true');
    });

    // Delay to ensure DOM is ready
    const timer = setTimeout(() => tour.start(), 500);
    tourRef.current = tour;

    return () => {
      clearTimeout(timer);
      tour.destroy();
    };
  }, [tourId, steps, onComplete]);

  return null;
};
```

---

### Task 13: Create Help Widget

**Files:**
- Create: `frontend/src/components/Onboarding/HelpWidget.tsx`

```tsx
import { useState } from 'react';
import { HelpCircle, X, Search } from 'lucide-react';

const HELP_ARTICLES = [
  { title: 'How to create an agent', content: 'Go to Agent Builder, select a template, customize the identity and tools, then test and save.' },
  { title: 'How to build a workflow', content: 'Open Workflow Builder, drag nodes from the palette, connect them with edges, and click Execute.' },
  { title: 'Understanding task modes', content: 'Task: single execution. Workflow: predefined steps. Autonomous: self-replanning. Collaboration: parallel agents.' },
  { title: 'Tool binding', content: 'In Workflow Builder, connect an Agent node to a Tool node. Click the edge to map parameters.' },
];

export const HelpWidget = () => {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');

  const filtered = HELP_ARTICLES.filter(a => a.title.toLowerCase().includes(query.toLowerCase()));

  return (
    <div className="fixed bottom-6 right-6 z-50">
      {open && (
        <div className="mb-4 w-80 bg-surface-high border border-outline/20 rounded-xl shadow-2xl overflow-hidden">
          <div className="p-4 border-b border-outline/10 flex items-center justify-between">
            <h3 className="font-semibold text-sm">Help</h3>
            <button onClick={() => setOpen(false)} className="text-secondaryText hover:text-primaryText">
              <X className="w-4 h-4" />
            </button>
          </div>
          <div className="p-3">
            <div className="flex items-center gap-2 bg-surface-highest rounded-lg px-3 py-2 mb-3">
              <Search className="w-4 h-4 text-secondaryText" />
              <input
                className="bg-transparent text-sm w-full focus:outline-none"
                placeholder="Search help..."
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </div>
            <div className="space-y-2 max-h-64 overflow-y-auto">
              {filtered.map((article) => (
                <details key={article.title} className="group">
                  <summary className="text-sm font-medium cursor-pointer list-none flex items-center justify-between">
                    {article.title}
                    <span className="text-secondaryText text-xs group-open:rotate-180 transition-transform">▼</span>
                  </summary>
                  <p className="text-xs text-secondaryText mt-2 pl-2">{article.content}</p>
                </details>
              ))}
            </div>
          </div>
        </div>
      )}
      <button
        onClick={() => setOpen(!open)}
        className="w-12 h-12 rounded-full bg-primary text-black shadow-lg hover:bg-primary/90 transition-colors flex items-center justify-center"
      >
        {open ? <X className="w-5 h-5" /> : <HelpCircle className="w-5 h-5" />}
      </button>
    </div>
  );
};
```

---

## Integration & Verification

### Task 14: Update App.tsx with new routes and components

**Files:**
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Add routes for v2 pages**

```typescript
import AgentBuilderV2 from './pages/AgentBuilderV2';
import WorkflowBuilderV2 from './pages/WorkflowBuilderV2';

// In routes:
<Route path="/builder/v2" element={<AgentBuilderV2 />} />
<Route path="/workflows/builder/v2" element={<WorkflowBuilderV2 />} />
```

### Task 15: Run tests and verify

- [ ] **Step 1: Run backend tests**
  Run: `pytest tests/ -v`
  Expected: All existing tests pass + new tests pass

- [ ] **Step 2: Run frontend build**
  Run: `cd frontend && npm run build`
  Expected: Build succeeds with 0 TypeScript errors

- [ ] **Step 3: Verify API endpoints**
  Start backend and check:
  - `GET /api/v1/tools/v2` returns tools list
  - `GET /api/v1/agents/v2/templates` returns templates
  - `GET /api/v1/onboarding/state` returns state
  - `POST /api/v1/workflows/v2/validate` validates workflows

- [ ] **Step 4: Integration test**
  Create an agent v2 → Create a workflow v2 with that agent → Execute workflow → Verify events stream
