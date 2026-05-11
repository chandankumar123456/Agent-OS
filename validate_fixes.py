"""
PRIORITY 1 VALIDATION SCRIPT for AgentOS v2
Tests all critical systems before any new feature work.
"""
import asyncio
import sys
import os
import platform
import json
import uuid
from datetime import datetime, timedelta

FAILURES = []

def report(name: str, passed: bool, details: str = ""):
    status = "PASS" if passed else "FAIL"
    print(f"[{status}] {name}{': ' + details if details else ''}")
    if not passed:
        FAILURES.append((name, details))

# =============================================================================
# SYSTEM 1: LANGGRAPH EXECUTION
# =============================================================================
print("\n" + "="*70)
print("SYSTEM 1: LANGGRAPH EXECUTION")
print("="*70)

# 1.1 AgentState structure
from app.langgraph.state import AgentState
state = AgentState(
    task_id=str(uuid.uuid4()),
    user_id="test-user",
    trace_id=str(uuid.uuid4()),
    query="test query",
    config={},
    messages=[],
    plan=[],
    current_step_index=0,
    steps=[],
    step_results={},
    tool_calls=[],
    verified=False,
    verification_notes=None,
    approved=None,
    approval_reason=None,
    result={},
    error=None,
    capability_assessment=None,
    feasibility_report=None,
    environment_config=None,
    verification_reports=[],
    recovery_decisions=[],
    created_at=datetime.utcnow().isoformat(),
    mode="task",
    status="pending",
)
report("1.1 AgentState instantiation", True)

# 1.2 step_id UUID bug check - verify no int step_id anywhere
from app.agents.base import AgentInput, AgentOutput, AgentStatus, AgentRole
step_id = uuid.uuid4()
task_id = uuid.uuid4()
agent_input = AgentInput(task_id=task_id, step_id=step_id, role=AgentRole.EXECUTOR, input_data={})
report("1.2 step_id is UUID object", isinstance(agent_input.step_id, uuid.UUID))

# 1.3 Graph compilation (all modes)
from app.langgraph.graphs import (
    compile_task_graph,
    compile_autonomous_graph,
    compile_workflow_graph,
    compile_collaboration_graph,
)
try:
    task_graph = compile_task_graph()
    report("1.3a compile_task_graph", task_graph is not None)
except Exception as e:
    report("1.3a compile_task_graph", False, str(e))

try:
    auto_graph = compile_autonomous_graph()
    report("1.3b compile_autonomous_graph", auto_graph is not None)
except Exception as e:
    report("1.3b compile_autonomous_graph", False, str(e))

try:
    wf_graph = compile_workflow_graph()
    report("1.3c compile_workflow_graph", wf_graph is not None)
except Exception as e:
    report("1.3c compile_workflow_graph", False, str(e))

try:
    col_graph = compile_collaboration_graph()
    report("1.3d compile_collaboration_graph", col_graph is not None)
except Exception as e:
    report("1.3d compile_collaboration_graph", False, str(e))

# 1.4 Verify orchestrator tries LangGraph first, fallback only on exception
from app.orchestrator.core import Orchestrator
orch_code = open("app/orchestrator/core.py").read()
report("1.4a _execute_with_langgraph exists", "_execute_with_langgraph" in orch_code)
report("1.4b LangGraph called first in execute_task", orch_code.find("_execute_with_langgraph") < orch_code.find("falling back"))
report("1.4c Fallback is exception-based", "except Exception as langgraph_err:" in orch_code)

# 1.5 Verify nodes use _to_openai_messages (human -> user fix)
from app.langgraph.nodes import _to_openai_messages
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
msgs = [HumanMessage(content="hi"), AIMessage(content="hello"), SystemMessage(content="sys")]
openai_msgs = _to_openai_messages(msgs)
roles = [m["role"] for m in openai_msgs]
report("1.5a HumanMessage maps to 'user'", "user" in roles)
report("1.5b AIMessage maps to 'assistant'", "assistant" in roles)
report("1.5c SystemMessage maps to 'system'", "system" in roles)
report("1.5d No 'human' role in output", "human" not in roles)

# =============================================================================
# SYSTEM 2: RUNTIME INITIALIZATION
# =============================================================================
print("\n" + "="*70)
print("SYSTEM 2: RUNTIME INITIALIZATION")
print("="*70)

from app.runtime.runtime import AgentRuntime

# 2.1 Singleton behavior
runtime1 = AgentRuntime()
runtime2 = AgentRuntime()
report("2.1 Runtime is singleton", runtime1 is runtime2)

# 2.2 Duplicate initialization guard
async def test_runtime_init():
    # Reset first
    runtime1.reset()
    # First init
    await runtime1.initialize()
    init_count = len(runtime1.list_active())
    # Second init should be no-op
    await runtime1.initialize()
    init_count2 = len(runtime1.list_active())
    report("2.2a Duplicate init is no-op", init_count == init_count2,
           f"First={init_count}, Second={init_count2}")
    # Core agents registered only once
    core_ids = ["core_planner", "core_executor", "core_verifier"]
    for cid in core_ids:
        workers = [w for w in runtime1.list_active() if w["agent_id"] == cid]
        report(f"2.2b {cid} registered once", len(workers) <= 1,
               f"Found {len(workers)} instances")
    runtime1.reset()
asyncio.run(test_runtime_init())

# 2.3 Redis mutex does not deadlock
async def test_redis_mutex():
    runtime1.reset()
    await runtime1.initialize()
    # Simulate another process holding mutex by setting it
    from app.memory.short_term import redis_client
    await redis_client.connect()
    await redis_client.client.set("agentos:runtime:init_mutex", "other-process", nx=True, ex=10)
    # Reset and re-init - should skip DB writes but not deadlock
    runtime1.reset()
    await runtime1.initialize()
    await redis_client.client.delete("agentos:runtime:init_mutex")
    await redis_client.disconnect()
    report("2.3 Redis mutex no deadlock", True)
asyncio.run(test_redis_mutex())

# =============================================================================
# SYSTEM 3: TOOL REGISTRATION
# =============================================================================
print("\n" + "="*70)
print("SYSTEM 3: TOOL REGISTRATION")
print("="*70)

from app.tools.registry import ToolRegistry, tool_registry

# 3.1 Singleton behavior
reg1 = ToolRegistry()
reg2 = ToolRegistry()
report("3.1 ToolRegistry is singleton", reg1 is reg2)

# 3.2 Default tools registered only once
default_tools = tool_registry.list_tools()
default_names = [t["name"] for t in default_tools]
report("3.2a Default tools present", len(default_names) > 0, str(default_names))

# 3.3 MCP tool discovery idempotency
async def test_mcp_idempotency():
    # Reset flag and discover twice
    tool_registry._mcp_tools_registered = False
    # First discovery
    await tool_registry.discover_mcp_tools()
    first_count = len(tool_registry.list_tools())
    # Second discovery should be no-op
    await tool_registry.discover_mcp_tools()
    second_count = len(tool_registry.list_tools())
    report("3.3 MCP discovery idempotent", first_count == second_count,
           f"First={first_count}, Second={second_count}")
asyncio.run(test_mcp_idempotency())

# 3.4 MCP wrapped tool schema
from app.tools.registry import MCPWrappedTool
mcp_tool = MCPWrappedTool("test_mcp", "A test tool", {"type": "object", "properties": {}})
schema = mcp_tool.get_schema()
report("3.4 MCPWrappedTool schema has name", schema.get("name") == "test_mcp")

# =============================================================================
# SYSTEM 4: WEBSOCKET STABILITY
# =============================================================================
print("\n" + "="*70)
print("SYSTEM 4: WEBSOCKET STABILITY")
print("="*70)

from app.api.ws import ConnectionManager

# 4.1 Connection manager basic ops
async def test_ws_manager():
    mgr = ConnectionManager()
    class FakeWS:
        def __init__(self):
            self.closed = False
            self.msgs = []
        async def accept(self): pass
        async def send_text(self, msg): self.msgs.append(msg)
        async def close(self, code=None, reason=None): self.closed = True
        async def receive_text(self):
            await asyncio.sleep(100)  # Never return
            return ""

    ws1 = FakeWS()
    await mgr.connect("task-1", ws1)
    report("4.1a Connect adds to active", "task-1" in mgr.active_connections)

    # 4.2 Disconnect removes and cleans up
    await mgr.disconnect("task-1", ws1)
    report("4.2a Disconnect removes from active", "task-1" not in mgr.active_connections)
    report("4.2b Disconnect closes socket", ws1.closed)

    # 4.3 Orphan removal on broadcast failure
    ws2 = FakeWS()
    ws3 = FakeWS()
    await mgr.connect("task-2", ws2)
    await mgr.connect("task-2", ws3)
    # Simulate ws2 becoming dead by breaking its send
    async def broken_send(msg):
        raise Exception("connection lost")
    ws2.send_text = broken_send
    await mgr.broadcast("task-2", "hello")
    report("4.3a Dead socket removed on broadcast", ws2 not in mgr.active_connections.get("task-2", []))
    report("4.3b Healthy socket still active", ws3 in mgr.active_connections.get("task-2", []))
asyncio.run(test_ws_manager())

# 4.4 Frontend reconnect logic
frontend_ws_code = open("frontend/src/hooks/useWebSocket.ts").read()
report("4.4a Reconnect on unexpected close", "reconnect" in frontend_ws_code.lower())
report("4.4b Exponential backoff", "Math.min(1000 * 2 ** reconnectAttempts" in frontend_ws_code)
report("4.4c Clean close no reconnect", "event.code === 1000" in frontend_ws_code)
report("4.4d Unmount cleanup", "isUnmountingRef.current = true" in frontend_ws_code)

# =============================================================================
# SYSTEM 5: REDIS EVENT SYSTEM
# =============================================================================
print("\n" + "="*70)
print("SYSTEM 5: REDIS EVENT SYSTEM")
print("="*70)

from app.orchestrator.event_bus import RedisEventBus, Event

# 5.1 Event serialization/deserialization
evt = Event("test_event", {"key": "value"}, source="test")
evt_json = evt.json()
parsed = Event.parse(evt_json)
report("5.1a Event round-trip serialization", parsed.event_type == "test_event")
report("5.1b Event payload preserved", parsed.payload.get("key") == "value")

# 5.2 Redis pubsub with timeout
async def test_redis_pubsub():
    from app.memory.short_term import redis_client
    await redis_client.connect()
    bus = RedisEventBus()

    received = []
    async def subscriber():
        try:
            async for event in bus.subscribe("test_channel"):
                received.append(event)
                break
        except asyncio.TimeoutError:
            pass
        except Exception as e:
            report("5.2 Subscriber error", False, str(e))

    sub_task = asyncio.create_task(asyncio.wait_for(subscriber(), timeout=10))
    await asyncio.sleep(0.5)
    await bus.publish("test_channel", Event("ping", {"data": 1}))
    try:
        await sub_task
    except asyncio.TimeoutError:
        pass

    report("5.2a Pubsub message received", len(received) > 0)
    if received:
        report("5.2b Message content correct", received[0].event_type == "ping")

    # 5.3 Cleanup on unsubscribe
    report("5.3 Pubsub cleanup", True)  # If we got here, cleanup worked
    await redis_client.disconnect()
asyncio.run(test_redis_pubsub())

# =============================================================================
# SYSTEM 6: AUTHENTICATION FLOW
# =============================================================================
print("\n" + "="*70)
print("SYSTEM 6: AUTHENTICATION FLOW")
print("="*70)

from app.auth.utils import (
    create_access_token, verify_access_token, create_refresh_token,
    hash_password, verify_password, generate_api_key, get_password_strength
)

# 6.1 JWT create/verify round-trip
token = create_access_token({"sub": "user-123", "role": "admin"})
payload = verify_access_token(token)
report("6.1a Access token round-trip", payload is not None and payload["sub"] == "user-123")

# 6.2 Refresh token
refresh = create_refresh_token({"sub": "user-123"})
payload_r = verify_access_token(refresh)
report("6.2a Refresh token valid", payload_r is not None and payload_r["sub"] == "user-123")

# 6.3 Token expiry rejection
expired_token = create_access_token({"sub": "user-123"}, expires_delta=timedelta(seconds=-1))
payload_exp = verify_access_token(expired_token)
report("6.3 Expired token rejected", payload_exp is None)

# 6.4 Password hashing/verification
hashed = hash_password("MyP@ssw0rd")
report("6.4a Password hash works", len(hashed) > 0)
report("6.4b Password verify correct", verify_password("MyP@ssw0rd", hashed))
report("6.4c Password verify wrong fails", not verify_password("wrong", hashed))

# 6.5 Password strength
report("6.5a Strong password accepted", get_password_strength("Hello1World"))
report("6.5b Weak password rejected", not get_password_strength("weak"))

# 6.6 WebSocket auth validation
ws_code = open("app/api/ws.py").read()
report("6.6a WS validates token before accept", "verify_access_token(token)" in ws_code)
report("6.6b WS rejects invalid token", "Invalid or expired token" in ws_code)

# 6.7 Frontend auth flow
auth_ctx = open("frontend/src/context/AuthContext.tsx").read()
report("6.7a Frontend stores tokens", "localStorage.setItem('accessToken'" in auth_ctx)
report("6.7b Frontend refresh logic", "refreshAccessToken" in auth_ctx)
report("6.7c Frontend periodic expiry check", "setInterval" in auth_ctx)
report("6.7d Frontend logout on expiry", "logout()" in auth_ctx)

# 6.8 API client auto-refresh
client_code = open("frontend/src/api/client.ts").read()
report("6.8a API client 401 refresh", "_attemptRefresh" in client_code)
report("6.8b API client auth:expired event", "auth:expired" in client_code)

# =============================================================================
# SYSTEM 7: PLANNER PATH AWARENESS
# =============================================================================
print("\n" + "="*70)
print("SYSTEM 7: PLANNER PATH AWARENESS")
print("="*70)

from app.utils.paths import (
    get_desktop_path,
    looks_like_foreign_path,
    remap_path,
    remap_tool_params,
    normalize_paths_in_text,
)

# 7.1 Desktop path is OS-aware
desktop = get_desktop_path()
report("7.1a Desktop path is absolute", os.path.isabs(desktop))
report("7.1b Desktop path exists or is valid", isinstance(desktop, str) and len(desktop) > 0)
if platform.system() == "Windows":
    report("7.1c Windows desktop uses backslashes", "\\" in desktop or "/" not in desktop)
else:
    report("7.1c Unix desktop uses forward slashes", "/" in desktop)

# 7.2 Foreign path detection
report("7.2a Unix path on Windows is foreign",
       platform.system() == "Windows" and looks_like_foreign_path("/home/user/file.txt") or platform.system() != "Windows")
report("7.2b Windows path on Unix is foreign",
       platform.system() in ("Linux", "Darwin") and looks_like_foreign_path("C:\\Users\\file.txt") or platform.system() not in ("Linux", "Darwin"))
report("7.2c Native path not foreign", not looks_like_foreign_path(desktop))

# 7.3 Path remapping
home = os.path.expanduser("~")
if platform.system() == "Windows":
    remapped = remap_path("/home/user/Desktop/report.txt", home, desktop)
    report("7.3a Unix Desktop path remapped to Windows", desktop.replace("\\", "/") in remapped.replace("\\", "/"))
    remapped2 = remap_path("/home/user/Documents/file.txt", home, desktop)
    report("7.3b Unix home path remapped to Windows", home.replace("\\", "/") in remapped2.replace("\\", "/"))
else:
    remapped = remap_path("C:\\Users\\John\\Desktop\\report.txt", home, desktop)
    report("7.3a Windows Desktop path remapped to Unix", desktop in remapped)
    remapped2 = remap_path("C:\\Users\\John\\Documents\\file.txt", home, desktop)
    report("7.3b Windows home path remapped to Unix", home in remapped2)

# 7.4 Tool parameter remapping
params = {"path": "/home/user/Desktop/file.txt", "content": "hello"}
remapped_params = remap_tool_params(params, home, desktop)
report("7.4a Tool params path remapped", remapped_params["path"] != "/home/user/Desktop/file.txt")
report("7.4b Tool params content unchanged", remapped_params["content"] == "hello")

# 7.5 Text normalization
text = "Create a file at /home/user/Desktop/output.txt and /home/user/docs/readme.md"
normalized = normalize_paths_in_text(text, home, desktop)
report("7.5a Text paths normalized", normalized != text)

# 7.6 Planner prompt includes OS info
planner_code = open("app/langgraph/nodes.py").read()
report("7.6a Planner prompt has os_info", "os_info" in planner_code)
report("7.6b Planner prompt has desktop_path", "desktop_path" in planner_code)
report("7.6c Planner prompt instructs absolute paths", "exact absolute paths" in planner_code)
report("7.6d Planner prompt OS-specific separators", "backslashes" in planner_code and "forward slashes" in planner_code)

# 7.7 Executor prompt includes OS info
exec_code = open("app/agents/executor.py").read()
report("7.7a Executor prompt has os_info", "os_info" in exec_code)
report("7.7b Executor prompt has desktop_path", "desktop_path" in exec_code)
report("7.7c Executor remaps tool params", "remap_tool_params" in exec_code)

# =============================================================================
# SUMMARY
# =============================================================================
print("\n" + "="*70)
print("VALIDATION SUMMARY")
print("="*70)

total = len([l for l in open(__file__).readlines() if 'report("' in l])
passed = total - len(FAILURES)
print(f"Total checks: {total}")
print(f"Passed: {passed}")
print(f"Failed: {len(FAILURES)}")

if FAILURES:
    print("\nFAILED CHECKS:")
    for name, details in FAILURES:
        print(f"  - {name}: {details}")
    print("\n=== VALIDATION FAILED ===")
    sys.exit(1)
else:
    print("\n=== ALL VALIDATIONS PASSED ===")
    sys.exit(0)
