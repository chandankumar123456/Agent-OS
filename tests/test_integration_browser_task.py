import pytest
from app.capabilities.environment_selector import environment_selector
from app.capabilities.models import CapabilityAssessment, CapabilityRequirement, ExecutionEnvironment


def test_browser_ui_task_routing():
    assessment = CapabilityAssessment(
        task_id="t1",
        query="open chrome and search for what is agentic ai",
        required_capabilities=[CapabilityRequirement(capability="web")],
        primary_capability="web",
    )
    env = environment_selector.select(assessment.query, assessment)
    assert env == ExecutionEnvironment.BROWSER_UI


def test_cloud_api_task_routing():
    assessment = CapabilityAssessment(
        task_id="t2",
        query="search latest AI news",
        required_capabilities=[CapabilityRequirement(capability="web")],
        primary_capability="web",
    )
    env = environment_selector.select(assessment.query, assessment)
    assert env == ExecutionEnvironment.CLOUD_API


def test_login_task_routing():
    assessment = CapabilityAssessment(
        task_id="t3",
        query="login to linkedin",
        required_capabilities=[CapabilityRequirement(capability="web")],
        primary_capability="web",
    )
    env = environment_selector.select(assessment.query, assessment)
    assert env == ExecutionEnvironment.BROWSER_UI
