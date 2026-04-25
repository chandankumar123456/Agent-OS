"""Tests for the CapabilityRouter and IntentRouter."""
import pytest

from app.capabilities.models import Capability, CapabilityAssessment, ExecutionEnvironment
from app.capabilities.router import CapabilityRouter, IntentRouter


class TestCapabilityRouterClassify:
    """Tests for CapabilityRouter.classify()."""

    def test_detect_research(self):
        router = CapabilityRouter()
        assessment = router.classify("Research the latest papers on quantum computing", task_id="t1")
        assert Capability.RESEARCH in {r.capability for r in assessment.required_capabilities}

    def test_detect_communication(self):
        router = CapabilityRouter()
        assessment = router.classify("Send an email to the team about the meeting", task_id="t2")
        assert Capability.COMMUNICATION in {r.capability for r in assessment.required_capabilities}

    def test_detect_data_processing(self):
        router = CapabilityRouter()
        assessment = router.classify("Clean and process the CSV dataset", task_id="t3")
        assert Capability.DATA_PROCESSING in {r.capability for r in assessment.required_capabilities}

    def test_research_primary_capability(self):
        router = CapabilityRouter()
        assessment = router.classify("Investigate academic sources for climate change data", task_id="t4")
        assert assessment.primary_capability == Capability.RESEARCH

    def test_communication_primary_capability(self):
        router = CapabilityRouter()
        assessment = router.classify("Notify the team via Slack about the deployment", task_id="t5")
        assert assessment.primary_capability == Capability.COMMUNICATION

    def test_data_processing_primary_capability(self):
        router = CapabilityRouter()
        assessment = router.classify("Transform and aggregate the dataset", task_id="t6")
        assert assessment.primary_capability == Capability.DATA_PROCESSING


class TestIntentRouterSelectEnvironment:
    """Tests for IntentRouter.select_environment()."""

    def test_file_maps_to_file(self):
        router = IntentRouter()
        assessment = CapabilityAssessment(
            task_id="t1",
            query="read file",
            required_capabilities=[],
            primary_capability=Capability.FILE,
        )
        assert router.select_environment(assessment) == ExecutionEnvironment.FILE

    def test_code_maps_to_shell(self):
        router = IntentRouter()
        assessment = CapabilityAssessment(
            task_id="t2",
            query="run python script",
            required_capabilities=[],
            primary_capability=Capability.CODE,
        )
        assert router.select_environment(assessment) == ExecutionEnvironment.SHELL

    def test_web_maps_to_browser_ui(self):
        router = IntentRouter()
        assessment = CapabilityAssessment(
            task_id="t3",
            query="scrape website",
            required_capabilities=[],
            primary_capability=Capability.WEB,
        )
        assert router.select_environment(assessment) == ExecutionEnvironment.BROWSER_UI

    def test_shell_maps_to_shell(self):
        router = IntentRouter()
        assessment = CapabilityAssessment(
            task_id="t4",
            query="run shell command",
            required_capabilities=[],
            primary_capability=Capability.SHELL,
        )
        assert router.select_environment(assessment) == ExecutionEnvironment.SHELL

    def test_research_maps_to_cloud_api(self):
        router = IntentRouter()
        assessment = CapabilityAssessment(
            task_id="t5",
            query="research topic",
            required_capabilities=[],
            primary_capability=Capability.RESEARCH,
        )
        assert router.select_environment(assessment) == ExecutionEnvironment.CLOUD_API

    def test_communication_maps_to_cloud_api(self):
        router = IntentRouter()
        assessment = CapabilityAssessment(
            task_id="t6",
            query="send email",
            required_capabilities=[],
            primary_capability=Capability.COMMUNICATION,
        )
        assert router.select_environment(assessment) == ExecutionEnvironment.CLOUD_API

    def test_data_processing_maps_to_local(self):
        router = IntentRouter()
        assessment = CapabilityAssessment(
            task_id="t7",
            query="process data",
            required_capabilities=[],
            primary_capability=Capability.DATA_PROCESSING,
        )
        assert router.select_environment(assessment) == ExecutionEnvironment.LOCAL

    def test_deployment_maps_to_shell(self):
        router = IntentRouter()
        assessment = CapabilityAssessment(
            task_id="t8",
            query="deploy app",
            required_capabilities=[],
            primary_capability=Capability.DEPLOYMENT,
        )
        assert router.select_environment(assessment) == ExecutionEnvironment.SHELL

    def test_knowledge_maps_to_cloud_api(self):
        router = IntentRouter()
        assessment = CapabilityAssessment(
            task_id="t9",
            query="search documents",
            required_capabilities=[],
            primary_capability=Capability.KNOWLEDGE,
        )
        assert router.select_environment(assessment) == ExecutionEnvironment.CLOUD_API

    def test_chat_maps_to_local(self):
        router = IntentRouter()
        assessment = CapabilityAssessment(
            task_id="t10",
            query="chat with me",
            required_capabilities=[],
            primary_capability=Capability.CHAT,
        )
        assert router.select_environment(assessment) == ExecutionEnvironment.LOCAL

    def test_workflow_maps_to_local(self):
        router = IntentRouter()
        assessment = CapabilityAssessment(
            task_id="t11",
            query="run workflow",
            required_capabilities=[],
            primary_capability=Capability.WORKFLOW,
        )
        assert router.select_environment(assessment) == ExecutionEnvironment.LOCAL

    def test_unknown_capability_defaults_to_local(self):
        router = IntentRouter()
        # Create an assessment with a capability not in the map
        # Since all current capabilities are mapped, we simulate by clearing the map
        router.ENVIRONMENT_MAP = {}
        assessment = CapabilityAssessment(
            task_id="t12",
            query="unknown task",
            required_capabilities=[],
            primary_capability=Capability.CHAT,
        )
        assert router.select_environment(assessment) == ExecutionEnvironment.LOCAL
