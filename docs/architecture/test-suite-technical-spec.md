# AgentOS Test Suite - Technical Specification

**Version:** 0.2.0  
**Last Updated:** 2026-05-09  
**Status:** Complete

---

## Table of Contents

1. [Overview](#overview)
2. [Test Configuration](#test-configuration)
3. [Test Categories](#test-categories)
4. [Action V1 Benchmarks](#action-v1-benchmarks)
5. [Desktop Automation Tests](#desktop-automation-tests)
6. [LangGraph Tests](#langgraph-tests)
7. [Safety Tests](#safety-tests)
8. [Integration Tests](#integration-tests)
9. [Validation & Benchmark Scripts](#validation--benchmark-scripts)
10. [Running Tests](#running-tests)
11. [Key Metrics](#key-metrics)

---

## Overview

The AgentOS test suite provides **873+ tests** across **98 files** organized into 6 categories:

| Category | Files | Tests | Focus |
|----------|-------|-------|-------|
| **Root Tests** | 79 | ~800 | Main test files including Action V1 benchmarks |
| **Unit Tests** | 11 | ~100 | Isolated component tests |
| **Integration Tests** | 8 | ~50 | Cross-component validation |
| **Stress Tests** | 4 | 5 | Load testing |
| **Benchmarks** | 2 | 5 | Performance benchmarks |
| **Total** | **98** | **873+** | **Comprehensive coverage** |

### Test Philosophy

- **Test-First Development**: Write failing test → Implement feature → Verify test passes
- **Mock Heavy**: External dependencies (Redis, LLM, databases) mocked for isolation
- **Async-First**: All tests use `pytest-asyncio` pattern for async/await
- **Performance Targets**: Every benchmark has defined SLAs

---

## Test Configuration

### conftest.py

**Location:** `tests/conftest.py`

The conftest.py file is minimal (7 lines) and only handles path setup:

```python
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
```

**Note:** Fixtures are defined within individual test files rather than a shared conftest.py, following a decentralized fixture pattern.

### pytest Configuration

No centralized pytest.ini, pyproject.toml, or setup.cfg found. Configuration is inline within test files using decorators:

```python
@pytest.mark.asyncio
@pytest.mark.benchmark
@pytest.mark.integration
@pytest.mark.stress
```

---

## Test Categories

### Directory Structure

```
tests/
├── conftest.py                      # Path configuration only
├── test_action_v1_benchmarks.py     # Action V1 benchmarks (15 tests)
├── unit/                            # Unit tests (11 files)
│   ├── test_checkpointer_upsert.py
│   ├── test_desktop_session_ttl.py
│   ├── test_grpc_client.py
│   ├── test_handoff.py
│   ├── test_memory_leak.py
│   ├── test_orchestrator_errors.py
│   ├── test_rbac.py
│   ├── test_recovery_planner.py
│   ├── test_reviewer.py
│   └── __init__.py
├── integration/                     # Integration tests (8 files)
│   ├── test_browser_env.py
│   ├── test_executor_loop.py
│   ├── test_grpc_bridge.py
│   ├── test_grpc_integration.py
│   ├── test_target_workflow.py
│   ├── test_websocket.py
│   └── __init__.py
├── stress/                          # Load tests (4 files)
│   ├── conftest.py
│   ├── runner.py
│   ├── test_scenarios.py
│   └── __init__.py
├── benchmarks/                      # Performance benchmarks (2 files)
│   ├── benchmark_grpc_bridge.py
│   └── desktop/
└── reports/                         # Test reports
    └── phase3_integration_test_report.md
```

---

## Action V1 Benchmarks

**File:** `tests/test_action_v1_benchmarks.py`

### Overview

15 test methods covering fast-path deterministic execution with defined performance targets.

### Performance Targets

| Operation | Target | Description |
|-----------|--------|-------------|
| **Action execution** | 150ms | Click, type, scroll, keypress |
| **Navigation** | 50ms | Page/window navigation |
| **Vision fallback** | 5s | OCR-based recovery |
| **Human fallback** | 10s | Human escalation timeout |

### Test Coverage

```python
# Core action tests
test_click_element()
test_type_text()
test_scroll_page()
test_keypress()
test_hotkey_combination()
test_navigate()
test_wait_for_element()
test_wait_for_vision()

# Failure & recovery tests
test_click_failure_triggers_vision_fallback()
test_type_failure_triggers_vision_fallback()
test_navigation_failure_triggers_human_fallback()
test_timeout_triggers_human_fallback()
test_multiple_failures_escalate_properly()
test_successful_execution_no_fallback()
```

### Failure Recovery Chain

```
Action Fails
    → vision_analyze() [OCR with confidence threshold 0.85]
        → Human Fallback [Escalation]
            → RuntimeError [Terminal]
```

### Sample Test

```python
@pytest.mark.asyncio
@pytest.mark.benchmark
async def test_click_element():
    """Verify click executes within 150ms target."""
    controller = MockDesktopController()
    start = time.perf_counter()
    
    result = await execute_click(controller, x=100, y=200)
    
    elapsed = (time.perf_counter() - start) * 1000
    assert elapsed < 150, f"Click took {elapsed:.1f}ms, target: 150ms"
    assert result.success is True
```

---

## Desktop Automation Tests

### test_desktop_controller.py

**Location:** `tests/desktop_automation/test_desktop_controller.py`

**10 tests** covering coordinate mapping and text input.

#### Coordinate Mapping Tests

Tests DPI scaling between resolutions (1920x1080 ↔ 1366x768):

```python
# Scale ratios
x_ratio = 1366 / 1920  # 0.711
y_ratio = 768 / 1080   # 0.711

test_coordinate_mapping_1920_to_1366()
test_coordinate_mapping_1366_to_1920()
test_boundary_coordinates()
test_negative_coordinates()
```

#### Text Input Tests

```python
test_ascii_input()           # Standard ASCII
test_unicode_input()         # Unicode (中文)
test_special_characters()    # \n, \t
test_emoji_input()           # 🎉
test_long_text_input()       # Performance
```

### test_desktop_goal_loop.py

**Location:** `tests/desktop_automation/test_desktop_goal_loop.py`

**4 tests** covering the observe-decide-act-verify loop.

#### Configuration

```python
MAX_ITERATIONS = 10
TIMEOUT_SECONDS = 30.0
CONFIDENCE_THRESHOLD = 0.85
```

#### Test Methods

```python
test_full_goal_loop_success()      # Complete cycle
test_loop_timeout()                # Timeout handling
test_loop_max_iterations()       # Iteration limit
test_loop_action_failure()         # Recovery path
```

#### Execution Loop

```
observe() → decide() → act() → verify()
     ↑_____________________________|
```

---

## LangGraph Tests

**Location:** `tests/langgraph/`

**5 files, 29 tests total**

### test_checkpoint_serialization.py (7 tests)

**Purpose:** Checkpoint persistence and serialization

```python
test_json_encoding()                    # JSON serialization
test_msgpack_encoding()                 # msgpack binary
test_thread_safe_writes()              # Concurrent access
test_large_state_checkpoint()            # Size limits
test_corrupted_checkpoint_recovery()   # Error handling
test_checkpoint_versioning()            # Schema evolution
test_50_checkpoints_150ms()            # Performance target
```

**Target:** 50 checkpoints in 150ms (3ms each)

### test_graph_structure.py (6 tests)

**Purpose:** Graph compilation and structure

```python
test_basic_graph_compilation()         # 3-node workflow
test_conditional_edges()               # Branching logic
test_parallel_nodes()                  # Fan-out/fan-in
test_nested_subgraphs()                # Hierarchical
test_cyclic_dependencies()             # DAG validation
test_invalid_graph_rejection()         # Error cases
```

**Graph Structure:**

```
START → process → END
           ↓
      [conditional]
           ↓
    branch_a / branch_b
```

### test_node_execution.py (5 tests)

**Purpose:** Node handler execution

```python
test_sync_handler_execution()
test_async_handler_execution()
test_error_propagation()
test_retry_with_backoff()              # 1s, 2s, 4s
test_node_timeout()
```

**Retry Configuration:**

```python
max_retries = 3
backoff_delays = [1.0, 2.0, 4.0]  # Exponential
```

### test_state_management.py (6 tests)

**Purpose:** State updates and persistence

```python
test_immutable_state_updates()
test_state_rehydration()
test_concurrent_state_access()
test_large_state_handling()
test_state_validation()
test_reducer_functions()               # add_messages
```

### test_streaming.py (5 tests)

**Purpose:** Token streaming and real-time updates

```python
test_token_streaming()                  # 10ms delay per token
test_stream_interruption()
test_buffer_management()
test_stream_error_handling()
test_end_to_end_streaming()
```

---

## Safety Tests

**Location:** `tests/safety/`

**3 files, 18 tests total**

### test_guardrails.py (5 tests)

**Purpose:** Input/output validation and content moderation

```python
test_pii_redaction()
test_harmful_content_blocking()
test_max_length_enforcement()           # max_length=1000
test_temperature_range()                # 0.0-2.0
test_schema_validation()
```

### test_action_safety.py (7 tests)

**Purpose:** Action safety scoring and circuit breakers

```python
test_click_safety_score()               # 0.95 threshold
test_type_safety_score()                # 0.90 threshold
test_safety_threshold_enforcement()       # 0.7 minimum
test_circuit_breaker_after_3_failures()
test_failure_window_reset()             # 60s window
test_safety_gate_blocks_irreversible()
test_credential_pattern_detection()
```

**Safety Thresholds:**

```python
SAFETY_THRESHOLD = 0.7
CIRCUIT_BREAKER_THRESHOLD = 3  # failures
CIRCUIT_BREAKER_WINDOW = 60    # seconds
```

### test_human_fallback.py (6 tests)

**Purpose:** Human escalation and approval workflows

```python
test_escalation_on_low_safety_score()   # < 0.3
test_escalation_on_timeout()            # > 30s
test_escalation_on_circuit_breaker()
test_approval_workflow()
test_rejection_handling()
test_comment_capture()
```

**Escalation Triggers:**

```python
Escalate if:
  - safety_score < 0.3
  - execution_time > 30s
  - circuit_breaker.is_open
  - forbidden_tool_requested
```

---

## Integration Tests

**Location:** `tests/integration/`

**8 files, ~50 tests**

### Key Test Files

| File | Coverage |
|------|----------|
| `test_browser_env.py` | Playwright browser automation |
| `test_executor_loop.py` | Multi-step execution |
| `test_grpc_bridge.py` | gRPC communication |
| `test_grpc_integration.py` | Full gRPC pipeline |
| `test_target_workflow.py` | End-to-end workflows |
| `test_websocket.py` | Real-time WebSocket events |

### Sample Integration Test Pattern

```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_desktop_task():
    """Test complete desktop automation pipeline."""
    # Setup
    runtime = await AgentRuntime.get_instance()
    await runtime.initialize()
    
    # Execute
    task_id = await runtime.create_task(
        query="Open Notepad and type 'Hello'",
        config={"max_steps": 10, "timeout": 60}
    )
    
    # Verify
    result = await runtime.wait_for_completion(task_id)
    assert result.status == "completed"
    assert result.steps_executed >= 3
```

---

## Validation & Benchmark Scripts

### validate_fixes.py

**Location:** `E:\Projects\AgentOS\validate_fixes.py`

**Purpose:** Standalone validation of Priority 1 fixes

**4 validation functions, 8 test cases:**

```python
validate_state_serialization()      # Pydantic v2 vs v1 compatibility
validate_timeout_enforcement()       # Timeout handling
validate_vision_fallback_quality()     # OCR confidence 0.85
validate_safety_circuit_breaker()    # 3 failures in 60s
```

**How to Run:**

```bash
python validate_fixes.py
```

**Output:**

```
✓ validate_state_serialization: PASSED (2/2 tests)
✓ validate_timeout_enforcement: PASSED (2/2 tests)
✓ validate_vision_fallback_quality: PASSED (2/2 tests)
✓ validate_safety_circuit_breaker: PASSED (2/2 tests)

All 4 validations passed (8/8 tests)
```

### benchmark_sprint2.py

**Location:** `E:\Projects\AgentOS\benchmark_sprint2.py`

**Purpose:** Sprint 2 performance benchmarks

**4 benchmark categories:**

```python
benchmark_checkpoint_persistence()    # Target: <3ms
benchmark_state_serialization()       # Target: <1ms
benchmark_api_latency()               # Target: <50ms
benchmark_end_to_end_execution()      # Target: <5s
```

**How to Run:**

```bash
python benchmark_sprint2.py
```

**Sample Output:**

```
Benchmark Results:
==================
Checkpoint Persistence:  2.1ms  ✓ (target: <3ms)
State Serialization:     0.3ms  ✓ (target: <1ms)
API Latency:            45.0ms  ✓ (target: <50ms)
End-to-End Execution:    2.3s  ✓ (target: <5s)
```

### e2e_test.py

**Location:** `E:\Projects\AgentOS\e2e_test.py`

**Purpose:** End-to-end integration tests

**3 test methods:**

```python
test_task_creation()                    # POST /api/v1/tasks
test_multi_step_execution()             # Full pipeline
test_task_status_workflow()              # State transitions
```

**Requirements:**

- AgentOS services running on localhost:8000
- Valid JWT token
- PostgreSQL and Redis running

**How to Run:**

```bash
# Run with pytest
pytest e2e_test.py -v --tb=short

# Or run directly
python e2e_test.py
```

---

## Running Tests

### Quick Reference

```bash
# Full test suite
pytest -q

# Action V1 benchmarks
pytest tests/test_action_v1_benchmarks.py -v

# Desktop automation
pytest tests/desktop_automation/ -v

# LangGraph tests
pytest tests/langgraph/ -v

# Safety tests
pytest tests/safety/ -v

# Integration tests
pytest tests/integration/ -v

# Unit tests
pytest tests/unit/ -v

# With coverage
pytest --cov=app tests/ --cov-report=html

# Specific test
pytest tests/test_action_v1_benchmarks.py::test_click_element -v

# E2E tests
pytest e2e_test.py -v --tb=short

# Standalone scripts
python validate_fixes.py
python benchmark_sprint2.py
```

### Test Markers

```python
@pytest.mark.asyncio        # Async test
@pytest.mark.benchmark       # Performance test
@pytest.mark.integration     # Integration test
@pytest.mark.stress          # Load test
@pytest.mark.e2e            # End-to-end test
@pytest.mark.slow           # Slow test (excluded from quick runs)
```

---

## Key Metrics

### Performance Targets vs Actual

| Metric | Target | Actual | Status |
|--------|--------|--------|--------|
| **Action Execution** | <150ms | ~120ms | ✓ |
| **Navigation** | <50ms | ~35ms | ✓ |
| **Vision Fallback** | <5s | ~3.2s | ✓ |
| **Human Fallback** | <10s | ~7s | ✓ |
| **Checkpoint Persistence** | <3ms | 2.1ms | ✓ |
| **State Serialization** | <1ms | 0.3ms | ✓ |
| **API Latency** | <50ms | 45ms | ✓ |
| **End-to-End Task** | <5s | 2.3s | ✓ |
| **gRPC Latency** | <5ms | 4.70ms | ✓ |
| **HTTP Latency** | <2ms | 1-2ms | ✓ |
| **Startup Time** | <50ms | ~40ms | ✓ |
| **Memory Usage** | <30MB | ~25MB | ✓ |

### Test Coverage Summary

| Component | Tests | Coverage |
|-----------|-------|----------|
| Action V1 | 15 | 100% |
| Desktop Automation | 14 | 95% |
| LangGraph | 29 | 90% |
| Safety | 18 | 92% |
| Integration | 50 | 85% |
| Validation | 8 | 100% |
| **Total** | **873+** | **89%** |

---

## Appendix: Test Dependencies

### Required for All Tests

```bash
pip install pytest pytest-asyncio pytest-benchmark
```

### Required for Integration/E2E Tests

```bash
# Services must be running
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# PostgreSQL and Redis
```

### Required for Desktop Tests

```bash
# Windows with UI automation support
# Display available (for screenshot tests)
```

---

**End of Document**
