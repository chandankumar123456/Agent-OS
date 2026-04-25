import pytest
from app.capabilities.environment_selector import ExecutionEnvironmentSelector
from app.capabilities.models import Capability, CapabilityAssessment, CapabilityRequirement, ExecutionEnvironment

selector = ExecutionEnvironmentSelector()


def make_assessment(primary: Capability):
    return CapabilityAssessment(
        task_id="t1",
        query="test",
        required_capabilities=[CapabilityRequirement(capability=primary)],
        primary_capability=primary,
    )


def test_browser_ui_open_chrome():
    assessment = make_assessment(Capability.WEB)
    result = selector.select("open chrome and search for AI", assessment)
    assert result == ExecutionEnvironment.BROWSER_UI


def test_browser_ui_login():
    assessment = make_assessment(Capability.WEB)
    result = selector.select("login to linkedin", assessment)
    assert result == ExecutionEnvironment.BROWSER_UI


def test_cloud_api_fallback():
    assessment = make_assessment(Capability.WEB)
    result = selector.select("search latest AI news", assessment)
    assert result == ExecutionEnvironment.CLOUD_API


def test_shell_env():
    assessment = make_assessment(Capability.SHELL)
    result = selector.select("run git status", assessment)
    assert result == ExecutionEnvironment.SHELL


def test_file_env():
    assessment = make_assessment(Capability.FILE)
    result = selector.select("read file config.txt", assessment)
    assert result == ExecutionEnvironment.FILE


def test_sandbox_for_code():
    assessment = make_assessment(Capability.CODE)
    result = selector.select("write a python script", assessment)
    assert result == ExecutionEnvironment.SANDBOX
