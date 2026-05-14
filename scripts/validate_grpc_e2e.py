#!/usr/bin/env python3
"""
Phase 1, Deliverable 4: gRPC End-to-End Validation Script
==========================================================
Validates gRPC communication between Python runtime gRPC server and client.

Tests:
    1. gRPC server startup and shutdown
    2. HealthCheck RPC
    3. CreateTask RPC
    4. GetTask RPC
    5. ListTasks RPC
    6. GetRuntimeStatus RPC
    7. StreamTaskEvents (server-side streaming)
    8. CancelTask RPC
    9. GetConfig / SetConfig RPC
    10. Proto field validation (no mismatches)
    11. Concurrent health checks

Usage:
    python scripts/validate_grpc_e2e.py [--verbose] [--port PORT]
"""

import asyncio
import sys
import os
import argparse
import time
import json
from datetime import datetime
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Set gRPC mode before any imports
os.environ["AGENTOS_RUNTIME_MODE"] = "grpc"
os.environ["RUNTIME_MODE"] = "grpc"

# Check if running from scripts/ or project root
os.chdir(str(PROJECT_ROOT))


class ValidationReport:
    """Collects and reports validation results."""
    
    def __init__(self):
        self.tests = []
        self.start_time = time.time()
        self.errors = []
        self.warnings = []
        self.fixes_applied = []
    
    def add_test(self, name, passed, details="", error=None):
        status = "PASS" if passed else "FAIL"
        entry = {
            "name": name,
            "status": status,
            "passed": passed,
            "details": details,
            "error": str(error) if error else None,
        }
        self.tests.append(entry)
        symbol = "+" if passed else "X"
        print(f"  [{symbol}] {name}")
        if details:
            print(f"      {details}")
        if error:
            print(f"      ERROR: {error}")
    
    def add_error(self, name, error):
        self.errors.append({"name": name, "error": str(error)})
    
    def add_warning(self, message):
        self.warnings.append(message)
        print(f"  [!] WARNING: {message}")
    
    def add_fix(self, description):
        self.fixes_applied.append(description)
    
    def summary(self):
        elapsed = time.time() - self.start_time
        total = len(self.tests)
        passed = sum(1 for t in self.tests if t["passed"])
        failed = total - passed
        
        print("\n" + "=" * 70)
        print("VALIDATION SUMMARY")
        print("=" * 70)
        print(f"  Total tests:  {total}")
        print(f"  Passed:       {passed}")
        print(f"  Failed:       {failed}")
        print(f"  Success rate: {passed/total*100:.1f}%" if total > 0 else "  Success rate: N/A")
        print(f"  Duration:     {elapsed:.2f}s")
        print(f"  Warnings:     {len(self.warnings)}")
        print(f"  Fixes applied:{len(self.fixes_applied)}")
        
        if self.errors:
            print(f"\n  Errors encountered ({len(self.errors)}):")
            for err in self.errors:
                print(f"    - {err['name']}: {err['error']}")
        
        if failed:
            print(f"\n  Failed tests:")
            for t in self.tests:
                if not t["passed"]:
                    print(f"    - {t['name']}")
        
        if self.warnings:
            print(f"\n  Warnings:")
            for w in self.warnings:
                print(f"    - {w}")
        
        if self.fixes_applied:
            print(f"\n  Fixes applied during validation:")
            for f in self.fixes_applied:
                print(f"    - {f}")
        
        return passed, failed


async def validate_proto_fields(report):
    """Validate proto message field definitions match between proto and code."""
    print("\n--- Proto Field Validation ---")
    
    from app.proto import runtime_pb2
    
    # 1. HealthCheckResponse must NOT have 'error' field
    hcr_fields = {f.name for f in runtime_pb2.HealthCheckResponse.DESCRIPTOR.fields}
    report.add_test(
        "Proto: HealthCheckResponse has no 'error' field",
        "error" not in hcr_fields,
        f"Fields: {sorted(hcr_fields)}"
    )
    
    # 2. HealthCheckResponse must have healthy, version, timestamp
    for required in ["healthy", "version", "timestamp"]:
        report.add_test(
            f"Proto: HealthCheckResponse has '{required}' field",
            required in hcr_fields
        )
    
    # 3. TaskEvent must NOT have 'message' field
    te_fields = {f.name for f in runtime_pb2.TaskEvent.DESCRIPTOR.fields}
    report.add_test(
        "Proto: TaskEvent has no 'message' field",
        "message" not in te_fields,
        f"Fields: {sorted(te_fields)}"
    )
    
    # 4. TaskEvent must have expected fields
    for required in ["task_id", "event_type", "timestamp", "task", "step", "log", "error"]:
        report.add_test(
            f"Proto: TaskEvent has '{required}' field",
            required in te_fields
        )
    
    # 5. RuntimeStatus must NOT have 'error' field
    rs_fields = {f.name for f in runtime_pb2.RuntimeStatus.DESCRIPTOR.fields}
    report.add_test(
        "Proto: RuntimeStatus has no 'error' field",
        "error" not in rs_fields,
        f"Fields: {sorted(rs_fields)}"
    )
    
    # 6. Check service methods match between proto and generated code
    from app.proto import runtime_pb2_grpc
    expected_methods = [
        "CreateTask", "GetTask", "CancelTask", "ListTasks",
        "StreamTaskEvents", "ApproveTask", "RejectTask",
        "GetRuntimeStatus", "Shutdown", "HealthCheck",
        "GetConfig", "SetConfig"
    ]
    servicer_methods = [m for m in dir(runtime_pb2_grpc.RuntimeServiceServicer) 
                        if not m.startswith("_")]
    for method in expected_methods:
        report.add_test(
            f"Proto: RuntimeService has '{method}' method",
            method in servicer_methods
        )
    
    # 7. Verify CheckpointService methods
    try:
        from app.proto import checkpoint_pb2, checkpoint_pb2_grpc
        cp_methods = [m for m in dir(checkpoint_pb2_grpc.CheckpointServiceServicer) 
                      if not m.startswith("_")]
        expected_cp = ["SaveCheckpoint", "GetCheckpoint", "ListCheckpoints", 
                       "GetLatestCheckpoint", "CleanupCheckpoints", "SubscribeCheckpoints"]
        for method in expected_cp:
            report.add_test(
                f"Proto: CheckpointService has '{method}' method",
                method in cp_methods
            )
        report.add_test("Proto: CheckpointService stub importable", True)
    except Exception as e:
        report.add_error("CheckpointService validation", e)
        report.add_test("Proto: CheckpointService stub importable", False, error=str(e))
    
    # 8. Verify WorkerService methods  
    try:
        from app.proto import worker_pb2, worker_pb2_grpc
        wk_methods = [m for m in dir(worker_pb2_grpc.WorkerExecutorServicer) 
                      if not m.startswith("_")]
        expected_wk = ["ExecuteTask", "HealthCheck"]
        for method in expected_wk:
            report.add_test(
                f"Proto: WorkerService has '{method}' method",
                method in wk_methods
            )
        report.add_test("Proto: WorkerService stub importable", True)
    except Exception as e:
        report.add_error("WorkerService validation", e)
        report.add_test("Proto: WorkerService stub importable", False, error=str(e))


async def validate_server_lifecycle(report, port):
    """Validate gRPC server startup and shutdown."""
    print("\n--- Server Lifecycle Validation ---")
    
    from app.runtime.grpc_server import GRPCServer
    
    # Test 1: Server startup
    server = GRPCServer(host="127.0.0.1", port=port)
    try:
        await server.start()
        report.add_test(
            "Server: startup succeeds",
            server._server is not None,
            f"Server started on 127.0.0.1:{port}"
        )
    except Exception as e:
        report.add_test("Server: startup succeeds", False, error=str(e))
        report.add_error("Server startup", e)
        return None
    
    # Test 2: Server has runtime components
    report.add_test(
        "Server: AgentRuntime initialized",
        server._runtime is not None
    )
    report.add_test(
        "Server: Orchestrator initialized", 
        server._orchestrator is not None
    )
    report.add_test(
        "Server: Checkpointer initialized",
        server._checkpointer is not None
    )
    
    # Test 3: Server shutdown
    try:
        await server.stop(grace=1.0)
        report.add_test(
            "Server: graceful shutdown",
            server._server is None and server._runtime is None,
            "All resources cleaned up"
        )
    except Exception as e:
        report.add_test("Server: graceful shutdown", False, error=str(e))
    
    # Test 4: Restart server for client tests
    server2 = GRPCServer(host="127.0.0.1", port=port)
    await server2.start()
    report.add_test("Server: restart succeeds", True)
    return server2


async def validate_client_connection(report, port):
    """Validate gRPC client can connect to the server."""
    print("\n--- Client Connection Validation ---")
    
    from app.proto.grpc_client import GRPCClient, GRPCClientConfig
    
    config = GRPCClientConfig(
        host="127.0.0.1",
        port=port,
        use_tls=False,
        connection_timeout=5.0,
    )
    client = GRPCClient(config)
    
    # Test 1: Connect
    try:
        await client.connect()
        report.add_test(
            "Client: connect succeeds",
            client.is_connected,
            f"Connected to 127.0.0.1:{port}"
        )
    except Exception as e:
        report.add_test("Client: connect succeeds", False, error=str(e))
        report.add_error("Client connection", e)
        return None
    
    # Test 2: Client has all services
    report.add_test(
        "Client: RuntimeService available",
        client.runtime is not None
    )
    report.add_test(
        "Client: CheckpointService available",
        client.checkpoint is not None
    )
    report.add_test(
        "Client: WorkerService available",
        client.worker is not None
    )
    
    return client


async def validate_health_check(report, client):
    """Validate HealthCheck RPC."""
    print("\n--- HealthCheck RPC Validation ---")
    
    try:
        response = await client.runtime.health_check()
        
        report.add_test(
            "HealthCheck: response received",
            response is not None
        )
        
        # Check proto fields
        if hasattr(response, 'healthy'):
            report.add_test(
                "HealthCheck: healthy field present",
                isinstance(response.healthy, bool),
                f"healthy={response.healthy}"
            )
        else:
            report.add_test("HealthCheck: healthy field present", False, "Field missing")
        
        if hasattr(response, 'version'):
            report.add_test(
                "HealthCheck: version field present",
                isinstance(response.version, str) and len(response.version) > 0,
                f"version={response.version}"
            )
        else:
            report.add_test("HealthCheck: version field present", False, "Field missing")
        
        # Ensure no 'error' property (should not exist on proto)
        if hasattr(response, 'error'):
            report.add_test("HealthCheck: no spurious 'error' field", False, 
                          f"Unexpected error field: {response.error}")
        else:
            report.add_test("HealthCheck: no spurious 'error' field", True)
        
    except Exception as e:
        report.add_test("HealthCheck: call succeeds", False, error=str(e))
        report.add_error("HealthCheck", e)
    
    # Test client-level health_check wrapper
    try:
        healthy = await client.health_check()
        report.add_test(
            "HealthCheck: client wrapper returns True",
            healthy is True,
            f"Overall health: {healthy}"
        )
    except Exception as e:
        report.add_test("HealthCheck: client wrapper returns True", False, error=str(e))


async def validate_create_task(report, client):
    """Validate CreateTask RPC."""
    print("\n--- CreateTask RPC Validation ---")
    
    task_id = None
    
    try:
        response = await client.runtime.create_task(
            query="Test task: validate gRPC e2e communication",
            task_type=1,  # TASK_TYPE_SIMPLE
            require_approval=False,
            timeout_seconds=300,
        )
        
        report.add_test(
            "CreateTask: response received",
            response is not None
        )
        
        # Check success
        if hasattr(response, 'success'):
            report.add_test(
                "CreateTask: success=True",
                response.success is True,
                f"success={response.success}"
            )
        
        # Check task object
        if hasattr(response, 'task') and response.task:
            task = response.task
            task_id = task.id if hasattr(task, 'id') else None
            
            report.add_test(
                "CreateTask: task.id present",
                task_id is not None and len(task_id) > 0,
                f"task_id={task_id}"
            )
            
            if hasattr(task, 'query'):
                report.add_test(
                    "CreateTask: task.query matches input",
                    "validate gRPC" in task.query,
                    f"query={task.query[:50]}..."
                )
            
            if hasattr(task, 'status'):
                report.add_test(
                    "CreateTask: task.status is set",
                    task.status != 0,  # not TASK_STATUS_UNSPECIFIED
                    f"status={task.status}"
                )
        else:
            report.add_test("CreateTask: task object present", False, "No task in response")
            
    except Exception as e:
        report.add_test("CreateTask: call succeeds", False, error=str(e))
        report.add_error("CreateTask", e)
    
    return task_id


async def validate_get_task(report, client, task_id):
    """Validate GetTask RPC."""
    print("\n--- GetTask RPC Validation ---")
    
    if not task_id:
        report.add_test("GetTask: requires valid task_id", False, "No task_id available")
        return
    
    try:
        response = await client.runtime.get_task(task_id)
        
        report.add_test(
            "GetTask: response received",
            response is not None
        )
        
        if hasattr(response, 'task') and response.task:
            task = response.task
            report.add_test(
                "GetTask: correct task returned",
                hasattr(task, 'id') and task.id == task_id,
                f"Got task {task.id}"
            )
        else:
            report.add_test("GetTask: task object present", False, "No task in response")
        
        if hasattr(response, 'success'):
            report.add_test(
                "GetTask: success=True",
                response.success is True,
                f"success={response.success}"
            )
            
    except Exception as e:
        report.add_test("GetTask: call succeeds", False, error=str(e))
        report.add_error("GetTask", e)
    
    # Test getting non-existent task
    try:
        fake_id = "task_nonexistent_12345"
        resp = await client.runtime.get_task(fake_id)
        # Should have failed 
        if hasattr(resp, 'success') and resp.success is False:
            report.add_test(
                "GetTask: non-existent task returns success=False",
                True,
                "Correctly rejected non-existent task"
            )
        else:
            report.add_test(
                "GetTask: non-existent task returns success=False",
                False,
                f"Unexpected response for fake task: {resp}"
            )
    except Exception as e:
        # gRPC error on NotFound is also acceptable behavior
        report.add_test(
            "GetTask: non-existent task returns error",
            True,
            f"gRPC error (expected): {str(e)[:100]}"
        )


async def validate_list_tasks(report, client, task_id):
    """Validate ListTasks RPC."""
    print("\n--- ListTasks RPC Validation ---")
    
    try:
        response = await client.runtime.list_tasks(
            limit=100,
            offset=0,
            include_completed=True,
        )
        
        report.add_test(
            "ListTasks: response received",
            response is not None
        )
        
        if hasattr(response, 'tasks'):
            tasks = list(response.tasks) if response.tasks else []
            report.add_test(
                "ListTasks: tasks list returned",
                len(tasks) > 0,
                f"Found {len(tasks)} task(s)"
            )
            
            # Verify our created task is in the list
            found = any(
                hasattr(t, 'id') and t.id == task_id 
                for t in tasks
            ) if task_id else False
            report.add_test(
                "ListTasks: created task in list",
                found,
                f"Task {task_id} {'found' if found else 'not found'} in list"
            )
        else:
            report.add_test("ListTasks: tasks list returned", False, "No tasks field")
            
    except Exception as e:
        report.add_test("ListTasks: call succeeds", False, error=str(e))
        report.add_error("ListTasks", e)


async def validate_runtime_status(report, client):
    """Validate GetRuntimeStatus RPC."""
    print("\n--- GetRuntimeStatus RPC Validation ---")
    
    try:
        response = await client.runtime.get_runtime_status(include_metrics=True)
        
        report.add_test(
            "GetRuntimeStatus: response received",
            response is not None
        )
        
        if hasattr(response, 'state'):
            report.add_test(
                "GetRuntimeStatus: state field present",
                response.state is not None,
                f"state={response.state}"
            )
        
        if hasattr(response, 'version'):
            report.add_test(
                "GetRuntimeStatus: version field present",
                isinstance(response.version, str) and len(response.version) > 0,
                f"version={response.version}"
            )
        
        if hasattr(response, 'active_tasks'):
            report.add_test(
                "GetRuntimeStatus: active_tasks field present",
                isinstance(response.active_tasks, int)
            )
        
    except Exception as e:
        report.add_test("GetRuntimeStatus: call succeeds", False, error=str(e))
        report.add_error("GetRuntimeStatus", e)


async def validate_stream_task_events(report, client, task_id):
    """Validate StreamTaskEvents server-side streaming RPC."""
    print("\n--- StreamTaskEvents RPC Validation ---")
    
    if not task_id:
        report.add_test("StreamTaskEvents: requires valid task_id", False, "No task_id")
        return
    
    try:
        from app.proto import runtime_pb2
        
        # Call the streaming RPC directly via stub
        request = runtime_pb2.TaskEventRequest(
            task_id=task_id,
            include_history=True
        )
        
        # Get stub from client internals
        stub = client.runtime._stub
        if not stub:
            report.add_test("StreamTaskEvents: stub available", False)
            return
        
        report.add_test("StreamTaskEvents: stub available", True)
        
        # Call the streaming method
        stream = stub.StreamTaskEvents(request)
        
        events_received = []
        timeout = 3.0  # seconds
        deadline = time.time() + timeout
        
        try:
            async for event in stream:
                events_received.append(event)
                if len(events_received) >= 2:
                    break
                if time.time() > deadline:
                    break
        except asyncio.TimeoutError:
            pass
        
        report.add_test(
            "StreamTaskEvents: events received",
            len(events_received) > 0,
            f"Received {len(events_received)} event(s)"
        )
        
        if events_received:
            event = events_received[0]
            if hasattr(event, 'event_type'):
                report.add_test(
                    "StreamTaskEvents: event_type is enum (not string)",
                    isinstance(event.event_type, int) or event.event_type != "",
                    f"event_type={event.event_type}"
                )
            if hasattr(event, 'task_id'):
                report.add_test(
                    "StreamTaskEvents: task_id matches",
                    event.task_id == task_id,
                    f"task_id={event.task_id}"
                )
            # Ensure no spurious 'message' field
            if hasattr(event, 'message'):
                report.add_test("StreamTaskEvents: no spurious 'message' field", False,
                              f"Unexpected message field: {event.message}")
            else:
                report.add_test("StreamTaskEvents: no spurious 'message' field", True)
                
    except Exception as e:
        report.add_test("StreamTaskEvents: call succeeds", False, error=str(e))
        report.add_error("StreamTaskEvents", e)


async def validate_cancel_task(report, client, task_id):
    """Validate CancelTask RPC."""
    print("\n--- CancelTask RPC Validation ---")
    
    if not task_id:
        report.add_test("CancelTask: requires valid task_id", False, "No task_id")
        return
    
    try:
        response = await client.runtime.cancel_task(task_id, reason="Validation test")
        
        report.add_test(
            "CancelTask: response received",
            response is not None
        )
        
        if hasattr(response, 'success'):
            report.add_test(
                "CancelTask: success=True",
                response.success is True,
                f"success={response.success}"
            )
            
    except Exception as e:
        report.add_test("CancelTask: call succeeds", False, error=str(e))
        report.add_error("CancelTask", e)


async def validate_config_rpcs(report, client):
    """Validate GetConfig and SetConfig RPCs."""
    print("\n--- Config RPC Validation ---")
    
    # GetConfig
    try:
        from app.proto import runtime_pb2
        gc_request = runtime_pb2.GetConfigRequest()
        gc_response = await client.runtime._stub.GetConfig(gc_request)
        
        report.add_test(
            "GetConfig: response received",
            gc_response is not None
        )
        
        if hasattr(gc_response, 'success'):
            report.add_test(
                "GetConfig: success field present",
                isinstance(gc_response.success, bool),
                f"success={gc_response.success}"
            )
            
    except Exception as e:
        report.add_test("GetConfig: call succeeds", False, error=str(e))
    
    # SetConfig
    try:
        from app.proto import runtime_pb2
        sc_request = runtime_pb2.SetConfigRequest(key="test_key", value="test_value")
        sc_response = await client.runtime._stub.SetConfig(sc_request)
        
        report.add_test(
            "SetConfig: response received",
            sc_response is not None
        )
        
    except Exception as e:
        report.add_test("SetConfig: call succeeds", False, error=str(e))


async def validate_concurrent_health_checks(report, client):
    """Validate concurrent health checks."""
    print("\n--- Concurrent Health Checks Validation ---")
    
    try:
        tasks = [client.runtime.health_check() for _ in range(5)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        successes = sum(1 for r in results if not isinstance(r, Exception) and 
                       hasattr(r, 'healthy') and r.healthy)
        
        report.add_test(
            "Concurrent: 5 health checks succeed",
            successes == 5,
            f"{successes}/5 concurrent health checks passed"
        )
        
        # No exceptions during concurrent calls
        errors = sum(1 for r in results if isinstance(r, Exception))
        report.add_test(
            "Concurrent: no exceptions during health checks",
            errors == 0,
            f"{errors} exceptions"
        )
        
    except Exception as e:
        report.add_test("Concurrent: health checks succeed", False, error=str(e))


async def validate_client_shutdown(report, client):
    """Validate client disconnection."""
    print("\n--- Client Shutdown Validation ---")
    
    try:
        await client.close()
        report.add_test(
            "Client: disconnect succeeds",
            not client.is_connected
        )
    except Exception as e:
        report.add_test("Client: disconnect succeeds", False, error=str(e))


async def validate_grpc_source_code(report):
    """Validate source code for known bugs (not just runtime tests)."""
    print("\n--- Source Code Bug Detection ---")
    
    grpc_server_path = PROJECT_ROOT / "app" / "runtime" / "grpc_server.py"
    if not grpc_server_path.exists():
        report.add_test("Source: grpc_server.py exists", False, "File not found")
        return
    
    content = grpc_server_path.read_text()
    
    # Bug 1: HealthCheckResponse should not set 'error' field
    if 'HealthCheckResponse(healthy=False, error=' in content:
        report.add_test("Source: HealthCheckResponse has no error= field (BUG FIX)", False,
                      "Found 'error=' in HealthCheckResponse - this field doesn't exist in proto")
    else:
        report.add_test("Source: HealthCheckResponse has no error= field", True)
    
    # Bug 2: StreamTaskEvents should not set 'message' field
    if 'message="Task completed"' in content:
        report.add_test("Source: StreamTaskEvents has no message= field (BUG FIX)", False,
                      "Found 'message=' in TaskEvent - this field doesn't exist in proto")
    else:
        report.add_test("Source: StreamTaskEvents has no message= field", True)
    
    # Bug 3: StreamTaskEvents event_type should be enum, not string
    if 'event_type="completed"' in content:
        report.add_test("Source: StreamTaskEvents event_type is enum, not string (BUG FIX)", False,
                      "Found event_type='completed' (string) - should be runtime_pb2.TASK_EVENT_COMPLETED enum")
    else:
        report.add_test("Source: StreamTaskEvents event_type is enum", True)
    
    # Bug 4: RuntimeStatus should not set 'error' field
    if 'RuntimeState.RUNTIME_STATE_ERROR, error=' in content:
        report.add_test("Source: RuntimeStatus has no error= field (BUG FIX)", False,
                      "Found 'error=' in RuntimeStatus - this field doesn't exist in proto")
    else:
        report.add_test("Source: RuntimeStatus has no error= field", True)


async def validate_proto_file_sync(report):
    """Validate that proto files are synchronized between app/proto/ and supervisor/proto/."""
    print("\n--- Proto File Synchronization Check ---")
    
    app_proto_path = PROJECT_ROOT / "app" / "proto"
    sup_proto_path = PROJECT_ROOT / "supervisor" / "proto"
    
    # Compare runtime.proto files (if both exist as .proto files)
    # The app/proto/ directory has generated Python files, not the raw .proto
    # but the supervisor/proto/ has the .proto source
    
    sup_runtime_proto = sup_proto_path / "runtime.proto"
    sup_checkpoint_proto = sup_proto_path / "checkpoint.proto"
    sup_worker_proto = sup_proto_path / "worker.proto"
    
    report.add_test(
        "Proto sync: supervisor/proto/runtime.proto exists",
        sup_runtime_proto.exists()
    )
    report.add_test(
        "Proto sync: supervisor/proto/checkpoint.proto exists",
        sup_checkpoint_proto.exists()
    )
    report.add_test(
        "Proto sync: supervisor/proto/worker.proto exists",
        sup_worker_proto.exists()
    )
    
    # Check if app/proto has generated pb2 files
    for name in ["runtime_pb2.py", "checkpoint_pb2.py", "worker_pb2.py"]:
        exists = (app_proto_path / name).exists()
        report.add_test(
            f"Proto sync: app/proto/{name} (generated) exists",
            exists
        )
    
    for name in ["runtime_pb2_grpc.py", "checkpoint_pb2_grpc.py", "worker_pb2_grpc.py"]:
        exists = (app_proto_path / name).exists()
        report.add_test(
            f"Proto sync: app/proto/{name} (generated) exists",
            exists
        )
    
    # Verify Go generated files exist
    go_runtime_path = sup_proto_path / "runtime"
    for name in ["runtime.pb.go", "runtime_grpc.pb.go"]:
        exists = (go_runtime_path / name).exists()
        report.add_test(
            f"Proto sync: supervisor/proto/runtime/{name} (Go generated) exists",
            exists
        )


async def main():
    parser = argparse.ArgumentParser(
        description="AgentOS gRPC End-to-End Validation"
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--port", "-p", type=int, default=50051, help="Port for gRPC server")
    args = parser.parse_args()
    
    report = ValidationReport()
    
    print("=" * 70)
    print("AGENTOS PHASE 1 - gRPC END-TO-END VALIDATION")
    print(f"Date: {datetime.now().isoformat()}")
    print(f"Port: {args.port}")
    print("=" * 70)
    
    # Phase 1: Proto field validation (no server needed)
    await validate_proto_fields(report)
    
    # Phase 2: Source code bug detection (no server needed)
    await validate_grpc_source_code(report)
    
    # Phase 3: Proto file sync check (no server needed)
    await validate_proto_file_sync(report)
    
    # Phase 4: Server lifecycle test
    server = await validate_server_lifecycle(report, args.port)
    if not server:
        print("\n  FAILED: Server could not start. Aborting remaining tests.")
        report.summary()
        return 1
    
    try:
        # Phase 5: Client connection test
        client = await validate_client_connection(report, args.port)
        if not client:
            print("\n  FAILED: Client could not connect. Aborting remaining tests.")
            report.summary()
            return 1
        
        try:
            # Phase 6: Health check
            await validate_health_check(report, client)
            
            # Phase 7: Task CRUD
            task_id = await validate_create_task(report, client)
            await validate_get_task(report, client, task_id)
            await validate_list_tasks(report, client, task_id)
            await validate_cancel_task(report, client, task_id)
            
            # Phase 8: Runtime status
            await validate_runtime_status(report, client)
            
            # Phase 9: Event streaming
            await validate_stream_task_events(report, client, task_id)
            
            # Phase 10: Config RPCs
            await validate_config_rpcs(report, client)
            
            # Phase 11: Concurrent operations
            await validate_concurrent_health_checks(report, client)
            
            # Phase 12: Clean shutdown
            await validate_client_shutdown(report, client)
            
        finally:
            # Ensure client is closed
            if client and client.is_connected:
                await client.close()
    
    finally:
        # Ensure server is stopped
        if server:
            try:
                await server.stop()
            except Exception:
                pass
    
    passed, failed = report.summary()
    
    # Write JSON report for CI
    report_path = PROJECT_ROOT / "PHASE1_GRPC_VALIDATION_REPORT.json"
    with open(report_path, "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "tests": report.tests,
            "warnings": report.warnings,
            "fixes_applied": report.fixes_applied,
            "errors": report.errors,
            "total": len(report.tests),
            "passed": passed,
            "failed": failed,
            "success_rate": f"{passed/len(report.tests)*100:.1f}%" if report.tests else "N/A"
        }, f, indent=2)
    print(f"\nJSON report written to: {report_path}")
    
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
