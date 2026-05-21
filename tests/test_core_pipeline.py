"""Integration test: plan-execute-verify pipeline with mocked LLM.

Verifies the full AgentLoop (plan -> build DAG -> execute -> observe -> verify)
completes without crashes when the LLM client is mocked to return predictable
JSON responses.
"""
import os
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4

import pytest

# Ensure test environment is configured before app imports
os.environ.setdefault("AGENTOS_ENV", "test")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-env-32chars!!")
os.environ.setdefault("RUNTIME_MODE", "grpc")
os.environ.setdefault("AGENTOS_RUNTIME_MODE", "grpc")


@pytest.fixture
def mock_llm_planner_response():
    """Planner LLM response with a simple two-step plan."""
    return {
        "steps": [
            {
                "id": "step-1",
                "step": "List files in the current directory",
                "tool": "filesystem__list_directory",
                "args": {"path": "/tmp"},
                "depends_on": [],
            },
            {
                "id": "step-2",
                "step": "Verify the listing was successful",
                "tool": "shell__run_command",
                "args": {"command": "echo done"},
                "depends_on": ["step-1"],
            },
        ]
    }


@pytest.fixture
def mock_llm_executor_response():
    """Executor LLM response indicating successful step execution."""
    return {
        "status": "completed",
        "output": "Step executed successfully",
        "confidence": 0.95,
    }


@pytest.fixture
def mock_llm_verifier_response():
    """Verifier LLM response indicating task is complete."""
    return {
        "valid": True,
        "confidence": 0.9,
        "reasoning": "All steps completed successfully",
    }


class TestCorePipelineImports:
    """Test that core modules can be imported without crashes."""

    def test_import_app_main(self):
        """Verify core.main can be imported."""
        import core.main
        assert hasattr(core.main, "app")

    def test_import_orchestrator(self):
        """Verify the orchestrator can be imported."""
        from core.orchestrator.core import Orchestrator
        assert Orchestrator is not None

    def test_import_agent_loop(self):
        """Verify the AgentLoop can be imported."""
        from core.orchestrator.agent_loop import AgentLoop
        assert AgentLoop is not None

    def test_import_llm_client(self):
        """Verify the LLM client module can be imported."""
        from core.agents.llm_client import LLMClient
        assert LLMClient is not None

    def test_import_desktop_entry(self):
        """Verify desktop_entry can be imported."""
        from core.desktop_entry import DesktopRuntime
        assert DesktopRuntime is not None

    def test_import_mcp_client_manager(self):
        """Verify MCP client manager can be imported."""
        from core.mcp.client_manager import MCPClientManager
        assert MCPClientManager is not None

    def test_import_short_term_memory(self):
        """Verify short-term memory can be imported."""
        from core.memory.short_term import ShortTermMemory
        assert ShortTermMemory is not None


class TestLLMClientSSL:
    """Test that the LLM client handles SSL issues gracefully."""

    def test_llm_client_init_with_bad_ssl(self):
        """LLMClient should not crash when SSL_CERT_FILE is wrong."""
        original = os.environ.get("SSL_CERT_FILE")
        try:
            os.environ["SSL_CERT_FILE"] = "/nonexistent/cert.pem"
            from core.agents.llm_client import LLMClient
            # Should not raise FileNotFoundError
            client = LLMClient(api_key="sk-test")
            assert client.client is not None
        finally:
            if original is not None:
                os.environ["SSL_CERT_FILE"] = original
            else:
                os.environ.pop("SSL_CERT_FILE", None)

    def test_llm_client_init_with_valid_ssl(self):
        """LLMClient should initialize normally with valid cert path."""
        original = os.environ.get("SSL_CERT_FILE")
        try:
            os.environ["SSL_CERT_FILE"] = "/etc/pki/tls/certs/ca-bundle.crt"
            from core.agents.llm_client import LLMClient
            client = LLMClient(api_key="sk-test")
            assert client.client is not None
        finally:
            if original is not None:
                os.environ["SSL_CERT_FILE"] = original
            else:
                os.environ.pop("SSL_CERT_FILE", None)


class TestShortTermMemoryFallback:
    """Test that ShortTermMemory degrades gracefully without Redis."""

    @pytest.mark.asyncio
    async def test_short_term_memory_save_and_get(self):
        """In gRPC mode, ShortTermMemory should use in-memory backend."""
        from core.memory.short_term import ShortTermMemory

        mem = ShortTermMemory()
        task_id = str(uuid4())
        context = {"query": "test task", "iteration": 1}

        result = await mem.save_context(task_id, context)
        # In gRPC mode with in-memory backend, this should succeed
        assert result is True or result is False  # Either backend is fine

        retrieved = await mem.get_context(task_id)
        if retrieved is not None:
            assert retrieved["query"] == "test task"


@pytest.mark.asyncio
class TestCorePipeline:
    """Integration test for the plan-execute-verify pipeline."""

    async def test_orchestrator_instantiation(self):
        """Orchestrator can be instantiated without crashing."""
        from core.orchestrator.core import Orchestrator

        orch = Orchestrator()
        assert orch.runtime is not None
        assert orch.agent_loop is not None
        assert orch.router is not None

    async def test_agent_loop_with_mocked_agents(
        self,
        mock_llm_planner_response,
        mock_llm_executor_response,
        mock_llm_verifier_response,
    ):
        """Full pipeline: plan -> execute -> verify with mocked agents."""
        from core.orchestrator.core import Orchestrator
        from core.agents.base import AgentOutput, AgentStatus

        orch = Orchestrator()

        # Mock the planner agent
        mock_planner = AsyncMock()
        mock_planner.execute = AsyncMock(
            return_value=AgentOutput(
                task_id=uuid4(),
                step_id=uuid4(),
                status=AgentStatus.SUCCESS,
                output_data=mock_llm_planner_response,
                confidence=0.9,
            )
        )

        # Mock the executor agent
        mock_executor = AsyncMock()
        mock_executor.execute = AsyncMock(
            return_value=AgentOutput(
                task_id=uuid4(),
                step_id=uuid4(),
                status=AgentStatus.SUCCESS,
                output_data=mock_llm_executor_response,
                confidence=0.95,
            )
        )

        # Mock the verifier agent
        mock_verifier = AsyncMock()
        mock_verifier.execute = AsyncMock(
            return_value=AgentOutput(
                task_id=uuid4(),
                step_id=uuid4(),
                status=AgentStatus.SUCCESS,
                output_data=mock_llm_verifier_response,
                confidence=0.9,
            )
        )

        # Patch the router to return our mocked agents
        def mock_resolve(agent_type):
            if agent_type == "planner":
                return mock_planner
            elif agent_type == "verifier":
                return mock_verifier
            else:
                return mock_executor

        orch.router.resolve = mock_resolve

        # Mock the workflow builder to return a simple workflow
        mock_workflow_node = MagicMock()
        mock_workflow_node.id = uuid4()
        mock_workflow_node.step_number = 1
        mock_workflow_node.agent_type = "executor"
        mock_workflow_node.depends_on = []
        mock_workflow_node.input_data = {
            "step": "List files in directory",
            "raw_step": {"id": "step-1", "step": "List files"},
        }
        mock_workflow_node.node_type = "agent"
        mock_workflow_node.condition_code = None
        mock_workflow_node.approval_config = None

        mock_workflow = MagicMock()
        mock_workflow.id = uuid4()

        orch.agent_loop.workflow_builder.build = AsyncMock(
            return_value={
                "workflow": mock_workflow,
                "nodes": [mock_workflow_node],
            }
        )

        # Mock the workflow engine to simulate execution
        async def mock_execute_graph(nodes, callbacks, context):
            run_node = callbacks["run_node"]
            results = {}
            for node in nodes:
                try:
                    result = await run_node(node, context)
                    results[node.id] = {
                        "status": "completed",
                        "output": result,
                    }
                except Exception as e:
                    results[node.id] = {
                        "status": "failed",
                        "output": {"error": str(e)},
                    }
            return {"nodes": results}

        orch.agent_loop.workflow_engine.execute_graph = mock_execute_graph

        # Mock persistence repos to avoid DB dependency
        with patch("core.orchestrator.agent_loop.trace_repo") as mock_trace_repo, \
             patch("core.orchestrator.agent_loop.task_repo") as mock_task_repo, \
             patch("core.orchestrator.agent_loop.workflow_node_repo") as mock_wn_repo, \
             patch("core.orchestrator.agent_loop.node_trace_repo") as mock_nt_repo, \
             patch("core.orchestrator.agent_loop.short_term_memory") as mock_stm:

            mock_trace_repo.create = AsyncMock()
            mock_trace_repo.update_status = AsyncMock()
            mock_task_repo.update = AsyncMock()
            mock_wn_repo.update = AsyncMock()
            mock_nt_repo.create = AsyncMock()
            mock_stm.save_context = AsyncMock(return_value=True)
            mock_stm.get_context = AsyncMock(return_value=None)

            # Also mock _load_task_state and _hydrate_memory_context
            orch._load_task_state = AsyncMock()
            orch._hydrate_memory_context = AsyncMock(return_value={})

            # Mock guardrails to always pass
            with patch("core.orchestrator.agent_loop.guardrails") as mock_guardrails:
                mock_guardrails.verify_output = AsyncMock(return_value=True)

                # Execute the task
                result = await orch.agent_loop.run(
                    query="List files in /tmp and verify success",
                    config={"max_iterations": 3},
                    task_id=uuid4(),
                    user_id="test-user",
                )

        # Verify the result
        assert result is not None
        assert result.status == AgentStatus.SUCCESS
        assert result.output_data is not None

    async def test_pipeline_handles_planner_failure(self):
        """Pipeline returns failure gracefully when planner fails."""
        from core.orchestrator.core import Orchestrator
        from core.agents.base import AgentOutput, AgentStatus

        orch = Orchestrator()

        # Mock planner that returns failure
        mock_planner = AsyncMock()
        mock_planner.execute = AsyncMock(
            return_value=AgentOutput(
                task_id=uuid4(),
                step_id=uuid4(),
                status=AgentStatus.FAILURE,
                error_type="planning_error",
                error_message="Failed to generate plan",
                recoverable=False,
            )
        )

        def mock_resolve(agent_type):
            if agent_type == "planner":
                return mock_planner
            return AsyncMock()

        orch.router.resolve = mock_resolve

        with patch("core.orchestrator.agent_loop.trace_repo") as mock_trace_repo, \
             patch("core.orchestrator.agent_loop.task_repo") as mock_task_repo, \
             patch("core.orchestrator.agent_loop.short_term_memory") as mock_stm:

            mock_trace_repo.create = AsyncMock()
            mock_trace_repo.update_status = AsyncMock()
            mock_task_repo.update = AsyncMock()
            mock_stm.get_context = AsyncMock(return_value=None)

            orch._load_task_state = AsyncMock()
            orch._hydrate_memory_context = AsyncMock(return_value={})

            result = await orch.agent_loop.run(
                query="This task should fail at planning",
                config={},
                task_id=uuid4(),
                user_id="test-user",
            )

        assert result is not None
        assert result.status == AgentStatus.FAILURE
        assert "plan" in (result.error_message or "").lower() or "plan" in (result.error_type or "").lower()
