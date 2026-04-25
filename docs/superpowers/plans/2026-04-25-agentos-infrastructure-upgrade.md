# AgentOS v2.1 — Infrastructure-Grade Agent Operating System

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform AgentOS from a working demo into a true AI Agent OS with reliable event delivery, full observability, smart routing, resilient recovery, layered memory, safety gates, and stress testing.

**Architecture:** Event-driven, modular architecture with strict separation of concerns. Redis Pub/Sub uses dedicated connection pools. Observability uses a structured event bus that feeds logs, DB, and websockets. Capability routing uses keyword heuristics + LLM fallback. Recovery is checkpoint-based with persisted retry state. Memory is tiered (task/session/workflow/user). Safety gates intercept irreversible actions before execution.

**Tech Stack:** FastAPI, SQLAlchemy async, PostgreSQL, Redis (asyncio), Celery, LangGraph, MCP, pytest.

---

## Phase 1: Fix Redis Pub/Sub Timeout & Reliable Event Bus

**Root Cause:** `RedisEventBus.subscribe()` uses the shared `redis_client` connection pool (`max_connections=50`). Each WebSocket creates a blocking pubsub subscription that holds a connection indefinitely. Under load, the pool exhausts, causing `Timeout reading from localhost:6379` for all Redis operations.

**Fix Strategy:**
1. Create a dedicated `RedisPubSubClient` with its own connection pool (unlimited or very high max_connections) separate from the operational Redis client.
2. Add connection health check, automatic reconnection, and graceful timeout handling in the subscription loop.
3. Update WebSocket handler to retry subscription on transient failures instead of dying silently.
4. Ensure Celery worker publishes events using the same reliable event bus.

---

### Task 1.1: Create Dedicated Redis PubSub Client

**Files:**
- Create: `app/memory/redis_pubsub.py`
- Modify: `app/memory/short_term.py` (reference only, ensure compatibility)

- [ ] **Step 1: Write the dedicated pubsub client**

```python
"""Dedicated Redis client for Pub/Sub operations to avoid connection pool exhaustion."""
import asyncio
import redis.asyncio as redis
from typing import Optional, AsyncIterator
from ..config.settings import settings
from ..logs.logger import logger

REDIS_URL = settings.REDIS_URL

class RedisPubSubClient:
    """Redis client exclusively for pub/sub. Uses its own connection pool."""

    def __init__(self):
        self._client: Optional[redis.Redis] = None
        self._lock = asyncio.Lock()

    async def connect(self):
        async with self._lock:
            if self._client is not None:
                try:
                    await self._client.ping()
                    return
                except Exception:
                    logger.warning("PubSub Redis connection dead, reconnecting")
                    await self._client.close()
                    self._client = None
            if not REDIS_URL:
                raise RuntimeError("REDIS_URL is not configured")
            # Dedicated pool: high max_connections, no socket_timeout on listen
            self._client = redis.from_url(
                REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
                max_connections=200,
                socket_connect_timeout=10,
                socket_keepalive=True,
                health_check_interval=30,
            )
            await self._client.ping()
            logger.info("Redis PubSub client connected (dedicated pool)")

    async def disconnect(self):
        async with self._lock:
            if self._client:
                await self._client.close()
                self._client = None
                logger.info("Redis PubSub client disconnected")

    def get_client(self) -> redis.Redis:
        if not self._client:
            raise RuntimeError("PubSub client is not connected")
        return self._client

    async def publish(self, channel: str, message: str):
        client = self.get_client()
        await client.publish(channel, message)

    async def subscribe(self, channel: str) -> AsyncIterator[str]:
        """Yield messages from a Redis channel with auto-reconnect."""
        client = self.get_client()
        pubsub = None
        try:
            pubsub = client.pubsub()
            await pubsub.subscribe(channel)
            logger.info(f"Subscribed to Redis channel: {channel}")
            async for message in pubsub.listen():
                if message["type"] == "message":
                    yield message["data"]
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"PubSub listen error on {channel}: {e}")
            raise
        finally:
            if pubsub is not None:
                try:
                    await pubsub.unsubscribe(channel)
                except Exception:
                    pass
                try:
                    await pubsub.close()
                except Exception:
                    pass

redis_pubsub_client = RedisPubSubClient()
```

- [ ] **Step 2: Write test for pubsub client**

Run: `pytest tests/test_redis_pubsub.py -v`

```python
import pytest
from app.memory.redis_pubsub import RedisPubSubClient

@pytest.mark.asyncio
async def test_pubsub_connect_publish_subscribe():
    client = RedisPubSubClient()
    await client.connect()
    channel = "agentos:test:pubsub"
    received = []

    async def listener():
        async for msg in client.subscribe(channel):
            received.append(msg)
            if len(received) >= 1:
                break

    task = asyncio.create_task(listener())
    await asyncio.sleep(0.1)
    await client.publish(channel, "hello")
    await asyncio.wait_for(task, timeout=5)
    await client.disconnect()
    assert received == ["hello"]
```

- [ ] **Step 3: Commit**

```bash
git add app/memory/redis_pubsub.py tests/test_redis_pubsub.py
git commit -m "feat(memory): add dedicated Redis PubSub client with isolated pool"
```

---

### Task 1.2: Refactor Event Bus to Use Dedicated PubSub Client

**Files:**
- Modify: `app/orchestrator/v2/event_bus.py`
- Modify: `app/api/ws.py`

- [ ] **Step 1: Update event_bus.py to use RedisPubSubClient**

```python
import asyncio
import json
from typing import AsyncIterator, Dict, Any
from ...memory.redis_pubsub import redis_pubsub_client
from ...logs.logger import logger

class Event:
    def __init__(self, event_type: str, payload: Dict[str, Any], source: str = "", timestamp: Optional[str] = None):
        self.event_type = event_type
        self.payload = payload
        self.source = source
        self.timestamp = timestamp or datetime.utcnow().isoformat()

    def json(self) -> str:
        return json.dumps({
            "type": self.event_type,
            "payload": self.payload,
            "source": self.source,
            "timestamp": self.timestamp,
        })

    @classmethod
    def parse(cls, raw: str) -> "Event":
        data = json.loads(raw)
        return cls(data["type"], data.get("payload", {}), data.get("source", ""), data.get("timestamp"))

class RedisEventBus:
    async def publish(self, channel: str, event: Event):
        try:
            await redis_pubsub_client.publish(f"agentos:{channel}", event.json())
        except Exception as e:
            logger.error(f"Event publish failed: {e}")

    async def subscribe(self, channel: str) -> AsyncIterator[Event]:
        try:
            async for raw in redis_pubsub_client.subscribe(f"agentos:{channel}"):
                try:
                    yield Event.parse(raw)
                except Exception as e:
                    logger.warning(f"Failed to parse event: {e}")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Event subscribe failed: {e}")

event_bus = RedisEventBus()
```

- [ ] **Step 2: Update ws.py to handle subscription retry and health**

In `app/api/ws.py`, update the `_subscribe` function:

```python
    async def _subscribe() -> None:
        backoff = 1.0
        max_backoff = 30.0
        while True:
            try:
                async for event in event_bus.subscribe(f"task:{task_id}"):
                    await manager.broadcast(task_id, event.json())
                    backoff = 1.0  # Reset backoff on success
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"WebSocket subscription error for task {task_id}: {e}")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, max_backoff)
```

- [ ] **Step 3: Ensure RedisPubSubClient is connected at startup**

Modify `app/main.py` lifespan to connect `redis_pubsub_client`:

```python
    try:
        from .memory.redis_pubsub import redis_pubsub_client
        await redis_pubsub_client.connect()
        logger.info("Redis PubSub client connected")
        initialized.append("redis_pubsub")
    except Exception as e:
        logger.error(f"Redis PubSub client connection failed: {e}")
```

And in shutdown:
```python
    if "redis_pubsub" in initialized:
        try:
            from .memory.redis_pubsub import redis_pubsub_client
            await redis_pubsub_client.disconnect()
        except Exception as e:
            logger.error(f"Redis PubSub client disconnect failed: {e}")
```

- [ ] **Step 4: Commit**

```bash
git add app/orchestrator/v2/event_bus.py app/api/ws.py app/main.py
git commit -m "fix(event-bus): isolate pubsub to dedicated redis pool with retry"
```

---

### Task 1.3: Integrate Event Publishing into Task Execution Pipeline

**Files:**
- Modify: `app/queue/tasks.py`
- Modify: `app/orchestrator/core.py`

- [ ] **Step 1: Publish task lifecycle events from Celery worker**

In `app/queue/tasks.py`, add event publishing inside the `run()` coroutine:

```python
from ..orchestrator.v2.event_bus import event_bus, Event

# Inside run():
await event_bus.publish(f"task:{task_id}", Event("task.received", {"task_id": task_id, "query": query, "user_id": user_id}, source="celery"))
# ... after status updates:
await event_bus.publish(f"task:{task_id}", Event("task.status_changed", {"task_id": task_id, "status": "running"}, source="celery"))
# ... on completion:
await event_bus.publish(f"task:{task_id}", Event("task.completed", {"task_id": task_id, "status": result.status.value}, source="celery"))
# ... on failure:
await event_bus.publish(f"task:{task_id}", Event("task.failed", {"task_id": task_id, "error": str(exc)}, source="celery"))
```

- [ ] **Step 2: Publish reasoning events from orchestrator**

In `app/orchestrator/core.py`, inside `_execute_with_langgraph`, publish key decisions:

```python
await event_bus.publish(f"task:{task_id}", Event("planner.reasoning", {"capability": assessment.primary_capability.value, "mode": mode}, source="orchestrator"))
await event_bus.publish(f"task:{task_id}", Event("environment.selected", {"environment": env_config.environment.value}, source="orchestrator"))
```

- [ ] **Step 3: Commit**

```bash
git add app/queue/tasks.py app/orchestrator/core.py
git commit -m "feat(events): publish task lifecycle and reasoning events to event bus"
```

---

## Phase 2: Build Execution Observability Layer

**Goal:** Every task must emit a structured reasoning trace that is queryable.

---

### Task 2.1: Create Observability Event Models and Bus

**Files:**
- Create: `app/observability/models.py`
- Create: `app/observability/bus.py`
- Create: `app/observability/__init__.py`

- [ ] **Step 1: Define observability event models**

```python
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
from datetime import datetime
from enum import Enum

class ObservabilityEventType(str, Enum):
    TASK_RECEIVED = "task.received"
    PLANNER_REASONING = "planner.reasoning"
    CAPABILITY_SELECTED = "capability.selected"
    ENVIRONMENT_SELECTED = "environment.selected"
    STEP_STARTED = "step.started"
    TOOL_INVOKED = "tool.invoked"
    TOOL_RESULT = "tool.result"
    RETRY_INITIATED = "retry.initiated"
    RECOVERY_ACTION = "recovery.action"
    VERIFICATION_COMPLETED = "verification.completed"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    SAFETY_CHECK = "safety.check"

class ObservabilityEvent(BaseModel):
    event_type: ObservabilityEventType
    task_id: str
    trace_id: Optional[str] = None
    step_id: Optional[str] = None
    payload: Dict[str, Any] = {}
    source: str = "agentos"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
```

- [ ] **Step 2: Create ObservabilityBus**

```python
from typing import Optional
from .models import ObservabilityEvent, ObservabilityEventType
from ..memory.long_term import trace_repo, span_repo
from ..memory.redis_pubsub import redis_pubsub_client
from ..logs.logger import logger

class ObservabilityBus:
    async def emit(self, event: ObservabilityEvent):
        # 1. Log to console
        logger.info(f"[{event.event_type}] task={event.task_id} source={event.source} payload={event.payload}")
        # 2. Publish to real-time event bus
        try:
            from ..orchestrator.v2.event_bus import event_bus
            await event_bus.publish(f"task:{event.task_id}", event)
        except Exception as e:
            logger.warning(f"Observability real-time publish failed: {e}")
        # 3. Persist to DB as span
        try:
            await span_repo.create(
                trace_id=event.trace_id or event.task_id,
                span_id=f"{event.event_type}:{event.timestamp.isoformat()}",
                operation=event.event_type.value,
                agent_name=event.source,
                metadata=event.payload,
            )
        except Exception as e:
            logger.warning(f"Observability DB persist failed: {e}")

observability_bus = ObservabilityBus()
```

- [ ] **Step 3: Commit**

```bash
git add app/observability/
git commit -m "feat(observability): create structured observability event bus"
```

---

### Task 2.2: Instrument LangGraph Nodes and Orchestrator

**Files:**
- Modify: `app/langgraph/nodes.py`
- Modify: `app/orchestrator/core.py`
- Modify: `app/orchestrator/executor.py`

- [ ] **Step 1: Instrument planner_node**

```python
from ...observability.bus import observability_bus, ObservabilityEvent, ObservabilityEventType

# Inside planner_node, after plan generation:
await observability_bus.emit(ObservabilityEvent(
    event_type=ObservabilityEventType.PLANNER_REASONING,
    task_id=task_id,
    trace_id=state.get("trace_id"),
    payload={"plan": plan, "capability_context": capability_context},
    source="planner_node",
))
```

- [ ] **Step 2: Instrument executor_node**

Inside `executor_node`, after each tool call:

```python
await observability_bus.emit(ObservabilityEvent(
    event_type=ObservabilityEventType.TOOL_INVOKED,
    task_id=task_id,
    trace_id=state.get("trace_id"),
    step_id=str(step_number),
    payload={"tool": tool_name, "params": tool_params},
    source="executor_node",
))
# ... after result:
await observability_bus.emit(ObservabilityEvent(
    event_type=ObservabilityEventType.TOOL_RESULT,
    task_id=task_id,
    trace_id=state.get("trace_id"),
    step_id=str(step_number),
    payload={"tool": tool_name, "result": tool_result},
    source="executor_node",
))
```

- [ ] **Step 3: Instrument verifier_node and summarizer_node**

Similar pattern for verification and summary events.

- [ ] **Step 4: Commit**

```bash
git add app/langgraph/nodes.py app/orchestrator/core.py app/orchestrator/executor.py
git commit -m "feat(observability): instrument all execution nodes with structured events"
```

---

## Phase 3: Upgrade Capability Router with Intent-Based Routing

---

### Task 3.1: Extend Capability Models and Router

**Files:**
- Modify: `app/capabilities/models.py`
- Modify: `app/capabilities/router.py`

- [ ] **Step 1: Add new capabilities to enum**

```python
class Capability(str, Enum):
    FILE = "file"
    CODE = "code"
    WEB = "web"
    SHELL = "shell"
    WORKFLOW = "workflow"
    DEPLOYMENT = "deployment"
    KNOWLEDGE = "knowledge"
    CHAT = "chat"
    RESEARCH = "research"
    COMMUNICATION = "communication"
    DATA_PROCESSING = "data_processing"
```

- [ ] **Step 2: Add patterns for new capabilities in router**

```python
Capability.RESEARCH: ["research", "investigate", "analyze data", "find papers", "literature review", "study", "survey"],
Capability.COMMUNICATION: ["email", "send message", "slack", "notify", "contact", "call", "message"],
Capability.DATA_PROCESSING: ["transform", "clean data", "etl", "parse", "aggregate", "filter", "sort", "csv processing"],
```

- [ ] **Step 3: Add intent-to-environment mapping**

Create `IntentRouter` inside `router.py`:

```python
class IntentRouter:
    """Maps capabilities to execution environments."""
    ENV_MAP = {
        Capability.FILE: ExecutionEnvironment.FILE,
        Capability.CODE: ExecutionEnvironment.SHELL,
        Capability.WEB: ExecutionEnvironment.BROWSER_UI,
        Capability.SHELL: ExecutionEnvironment.SHELL,
        Capability.RESEARCH: ExecutionEnvironment.CLOUD_API,
        Capability.COMMUNICATION: ExecutionEnvironment.CLOUD_API,
        Capability.DATA_PROCESSING: ExecutionEnvironment.LOCAL,
        Capability.DEPLOYMENT: ExecutionEnvironment.SHELL,
        Capability.KNOWLEDGE: ExecutionEnvironment.CLOUD_API,
        Capability.CHAT: ExecutionEnvironment.LOCAL,
        Capability.WORKFLOW: ExecutionEnvironment.LOCAL,
    }

    def select_environment(self, assessment: CapabilityAssessment) -> ExecutionEnvironment:
        return self.ENV_MAP.get(assessment.primary_capability, ExecutionEnvironment.LOCAL)
```

- [ ] **Step 4: Commit**

```bash
git add app/capabilities/models.py app/capabilities/router.py
git commit -m "feat(router): extend capabilities with research, communication, data_processing and intent-to-env mapping"
```

---

## Phase 4: Build Failure Recovery System

---

### Task 4.1: Persist Retry State to Redis

**Files:**
- Modify: `app/capabilities/recovery.py`

- [ ] **Step 1: Replace in-memory retry counts with Redis-backed store**

```python
from ..memory.short_term import redis_client

class RecoveryEngine:
    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries
        # ... rest same but use redis_client for retry counts

    async def _get_retry_count(self, task_id: str, step_id: Optional[str]) -> int:
        key = f"agentos:retries:{task_id}:{step_id or 'task'}"
        data = await redis_client.get(key)
        return int(data["count"]) if data else 0

    async def _increment_retry(self, task_id: str, step_id: Optional[str]):
        key = f"agentos:retries:{task_id}:{step_id or 'task'}"
        count = await self._get_retry_count(task_id, step_id)
        await redis_client.set(key, {"count": count + 1}, expire=86400)

    async def decide(self, ...):
        current_retries = await self._get_retry_count(task_id, step_id)
        # ... logic same but await increment where needed
```

- [ ] **Step 2: Commit**

```bash
git add app/capabilities/recovery.py
git commit -m "feat(recovery): persist retry counts to redis for cross-process recovery"
```

---

### Task 4.2: Checkpoint Recovery Service

**Files:**
- Create: `app/recovery/checkpoint_service.py`
- Modify: `app/orchestrator/core.py`

- [ ] **Step 1: Create CheckpointRecoveryService**

```python
from ..langgraph.graphs import get_checkpointer
from ..logs.logger import logger

class CheckpointRecoveryService:
    async def resume_task(self, task_id: str, mode: str, state: dict):
        """Resume a task from its last LangGraph checkpoint."""
        checkpointer = get_checkpointer()
        # Logic to load checkpoint and re-invoke graph from that point
        logger.info(f"Resuming task {task_id} from checkpoint")
        # ... implementation using checkpointer.get()
```

- [ ] **Step 2: Integrate into orchestrator fallback**

In `execute_task`, before falling back to legacy mode, attempt checkpoint resume.

- [ ] **Step 3: Commit**

```bash
git add app/recovery/ app/orchestrator/core.py
git commit -m "feat(recovery): add checkpoint recovery service for task resumption"
```

---

## Phase 5: Refactor Memory Layer

---

### Task 5.1: Create Tiered Memory Classes

**Files:**
- Create: `app/memory/task_memory.py`
- Create: `app/memory/session_memory.py`
- Create: `app/memory/workflow_memory.py`
- Create: `app/memory/user_memory.py`

- [ ] **Step 1: Implement TaskMemory**

```python
from .short_term import redis_client
from typing import Dict, Any, Optional

class TaskMemory:
    prefix = "agentos:memory:task:"
    async def get(self, task_id: str) -> Optional[Dict[str, Any]]:
        return await redis_client.get(f"{self.prefix}{task_id}")
    async def set(self, task_id: str, data: Dict[str, Any], expire: int = 3600):
        await redis_client.set(f"{self.prefix}{task_id}", data, expire)
    async def update_progress(self, task_id: str, step_index: int, step_state: dict):
        data = await self.get(task_id) or {}
        data["current_step_index"] = step_index
        data["step_state"] = step_state
        await self.set(task_id, data)
```

- [ ] **Step 2: Implement SessionMemory**

```python
class SessionMemory:
    prefix = "agentos:memory:session:"
    async def get_browser_session(self, task_id: str) -> Optional[Dict[str, Any]]:
        return await redis_client.get(f"{self.prefix}browser:{task_id}")
    async def set_browser_session(self, task_id: str, session_data: Dict[str, Any], expire: int = 7200):
        await redis_client.set(f"{self.prefix}browser:{task_id}", session_data, expire)
```

- [ ] **Step 3: Implement WorkflowMemory (DB-backed)**

```python
from .long_term import workflow_repo
class WorkflowMemory:
    async def get_state(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        wf = await workflow_repo.get_by_id(workflow_id)
        return wf.definition if wf else None
    async def save_state(self, workflow_id: str, state: Dict[str, Any]):
        await workflow_repo.update(workflow_id, definition=state)
```

- [ ] **Step 4: Implement UserMemory (DB-backed)**

```python
from .long_term import config_repo
class UserMemory:
    async def get_preferences(self, user_id: str) -> Dict[str, Any]:
        return await config_repo.get_all()  # Scoped by user_id in real impl
```

- [ ] **Step 5: Commit**

```bash
git add app/memory/task_memory.py app/memory/session_memory.py app/memory/workflow_memory.py app/memory/user_memory.py
git commit -m "feat(memory): create tiered memory layers (task, session, workflow, user)"
```

---

## Phase 6: Build Safety Layer

---

### Task 6.1: Create Safety Gate

**Files:**
- Create: `app/safety/gate.py`
- Create: `app/safety/models.py`
- Modify: `app/langgraph/nodes.py`

- [ ] **Step 1: Define safety models and gate**

```python
from enum import Enum
from typing import List, Dict, Any

class ActionSeverity(str, Enum):
    SAFE = "safe"
    WARNING = "warning"
    IRREVERSIBLE = "irreversible"

IRREVERSIBLE_TOOLS = {
    "filesystem__delete_file", "filesystem__delete_directory",
    "shell__execute_command",  # Only if matches dangerous patterns
    "email__send", "slack__send_message",
    "browser_env__submit_form",  # If payment-related
}

DANGEROUS_PATTERNS = ["rm -rf", "drop", "delete", "payment", "purchase", "buy", "transfer"]

class SafetyGate:
    def check_tool_call(self, tool_name: str, params: Dict[str, Any], query: str) -> ActionSeverity:
        if tool_name in IRREVERSIBLE_TOOLS:
            return ActionSeverity.IRREVERSIBLE
        for pattern in DANGEROUS_PATTERNS:
            if pattern in str(params).lower() or pattern in query.lower():
                return ActionSeverity.WARNING
        return ActionSeverity.SAFE
```

- [ ] **Step 2: Integrate into executor_node**

Before executing a tool in `executor_node`:

```python
from ...safety.gate import SafetyGate, ActionSeverity
from ...observability.bus import observability_bus, ObservabilityEvent, ObservabilityEventType

severity = SafetyGate().check_tool_call(tool_name, tool_params, state.get("query", ""))
if severity == ActionSeverity.IRREVERSIBLE:
    await observability_bus.emit(ObservabilityEvent(
        event_type=ObservabilityEventType.SAFETY_CHECK,
        task_id=task_id,
        payload={"tool": tool_name, "severity": "irreversible", "params": tool_params},
        source="safety_gate",
    ))
    # Trigger interrupt for approval
    # ... integration with approval_node or raise special exception
```

- [ ] **Step 3: Commit**

```bash
git add app/safety/ app/langgraph/nodes.py
git commit -m "feat(safety): add safety gate for irreversible actions with observability integration"
```

---

## Phase 7: Build Stress Test Framework

---

### Task 7.1: Create Stress Test Runner and Scenarios

**Files:**
- Create: `tests/stress/runner.py`
- Create: `tests/stress/test_scenarios.py`
- Create: `tests/stress/conftest.py`

- [ ] **Step 1: Create StressTestRunner**

```python
import asyncio
import time
from typing import List, Dict, Any
from dataclasses import dataclass

@dataclass
class StressResult:
    scenario: str
    total_tasks: int
    success: int
    failed: int
    avg_latency_ms: float
    p95_latency_ms: float
    errors: List[str]

class StressTestRunner:
    def __init__(self, client):
        self.client = client

    async def run_scenario(self, name: str, queries: List[str], concurrent: int = 5) -> StressResult:
        semaphore = asyncio.Semaphore(concurrent)
        latencies = []
        errors = []

        async def run_one(query: str):
            async with semaphore:
                start = time.time()
                try:
                    resp = await self.client.post("/api/v1/tasks", json={"query": query})
                    resp.raise_for_status()
                    return time.time() - start, None
                except Exception as e:
                    return time.time() - start, str(e)

        results = await asyncio.gather(*[run_one(q) for q in queries])
        for latency, error in results:
            latencies.append(latency * 1000)
            if error:
                errors.append(error)

        latencies.sort()
        p95 = latencies[int(len(latencies) * 0.95)] if latencies else 0
        avg = sum(latencies) / len(latencies) if latencies else 0
        return StressResult(
            scenario=name,
            total_tasks=len(queries),
            success=len(queries) - len(errors),
            failed=len(errors),
            avg_latency_ms=avg,
            p95_latency_ms=p95,
            errors=errors[:10],
        )
```

- [ ] **Step 2: Write scenario tests**

```python
import pytest
from .runner import StressTestRunner

@pytest.mark.asyncio
async def test_simple_tasks(client):
    runner = StressTestRunner(client)
    queries = ["What is 2+2?" for _ in range(10)]
    result = await runner.run_scenario("simple", queries, concurrent=5)
    assert result.failed == 0

@pytest.mark.asyncio
async def test_multi_step_tasks(client):
    runner = StressTestRunner(client)
    queries = ["Create a file on desktop, then read it back" for _ in range(5)]
    result = await runner.run_scenario("multi_step", queries, concurrent=2)
    assert result.success > 0
```

- [ ] **Step 3: Commit**

```bash
git add tests/stress/
git commit -m "feat(tests): add stress test framework with runner and scenarios"
```

---

## Phase 8: Enforce Modular Infrastructure

---

### Task 8.1: Refactor Orchestrator Core Responsibilities

**Files:**
- Create: `app/orchestrator/task_runner.py`
- Modify: `app/orchestrator/core.py`

- [ ] **Step 1: Extract LangGraph execution into TaskRunner**

Move `_execute_with_langgraph` and helper methods from `core.py` into `TaskRunner` class.

- [ ] **Step 2: Update core.py to delegate**

```python
from .task_runner import TaskRunner

class Orchestrator:
    def __init__(self):
        # ... existing init ...
        self.task_runner = TaskRunner(self.runtime, self.router)

    async def _execute_with_langgraph(self, query, config, task_id, user_id, mode):
        return await self.task_runner.run(query, config, task_id, user_id, mode)
```

- [ ] **Step 3: Commit**

```bash
git add app/orchestrator/task_runner.py app/orchestrator/core.py
git commit -m "refactor(orchestrator): extract TaskRunner to enforce modular boundaries"
```

---

## Summary of Changes

1. **Redis Pub/Sub:** Dedicated pool, retry logic, health checks.
2. **Observability:** Structured events emitted from every node, persisted to DB and websockets.
3. **Capability Router:** New capabilities (research, communication, data_processing) with intent-to-environment mapping.
4. **Recovery:** Redis-backed retry counts, checkpoint recovery service.
5. **Memory:** Four distinct layers with clear responsibilities.
6. **Safety:** Gate intercepts irreversible tool calls before execution.
7. **Stress Tests:** Formal framework with latency and error tracking.
8. **Modularity:** TaskRunner extracted from Orchestrator core.

---

## Verification Commands

```bash
# Run unit tests
pytest tests/ -v --ignore=tests/stress

# Run stress tests
pytest tests/stress/ -v

# Run Redis pubsub tests
pytest tests/test_redis_pubsub.py -v

# Start application and verify no startup errors
python -m app.main
```
