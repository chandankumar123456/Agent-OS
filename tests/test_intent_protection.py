"""Comprehensive regression tests for intent classification and grounding protections.

These tests verify that:
1. ALL major intents have fast-path classification (not just desktop)
2. NO specialized intent silently falls back to generic tools
3. The grounding layer fails loudly when tools are missing for a specialized intent
"""
import pytest

from app.tools.grounding import tool_grounding_layer


@pytest.fixture
def runtime_tools_mock():
    """Mixed tool list containing desktop, browser, shell, file, and generic tools."""
    return [
        # Desktop
        {"name": "desktop_env__click"},
        {"name": "desktop_env__type_text"},
        {"name": "desktop__desktop__click"},
        # Browser
        {"name": "browser_env__launch"},
        {"name": "browser_env__navigate"},
        {"name": "browser_env__click"},
        # Shell
        {"name": "shell__execute_command"},
        {"name": "shell__run_script"},
        # File
        {"name": "filesystem__read_file"},
        {"name": "filesystem__write_file"},
        {"name": "filesystem__search_files"},
        # Web search
        {"name": "web_search"},
        {"name": "cloud_api__search_web"},
        # Code
        {"name": "code_executor__run_python"},
        # Generic
        {"name": "calculator"},
        {"name": "text_processor"},
    ]


class TestIntentFastPathClassification:
    """Verify fast-path indicators correctly classify natural language for ALL intents."""

    def test_browser_intent_fast_path(self, runtime_tools_mock):
        grounded = tool_grounding_layer.filter_tools_for_step(
            "Visit google.com in the browser and search for AgentOS", runtime_tools_mock
        )
        names = {t["name"] for t in grounded}
        assert "browser_env__navigate" in names, f"Browser navigate not grounded. Got: {names}"
        assert "browser_env__click" in names, f"Browser click not grounded. Got: {names}"
        assert "web_search" not in names, "Browser intent fell back to generic tools."

    def test_shell_intent_fast_path(self, runtime_tools_mock):
        grounded = tool_grounding_layer.filter_tools_for_step(
            "Run a powershell command to list all processes", runtime_tools_mock
        )
        names = {t["name"] for t in grounded}
        assert "shell__execute_command" in names, f"Shell command not grounded. Got: {names}"
        assert "calculator" not in names, "Shell intent fell back to generic tools."

    def test_file_search_intent_fast_path(self, runtime_tools_mock):
        grounded = tool_grounding_layer.filter_tools_for_step(
            "Look for file named report.pdf on the Desktop", runtime_tools_mock
        )
        names = {t["name"] for t in grounded}
        assert "filesystem__search_files" in names, f"File search not grounded. Got: {names}"
        assert "text_processor" not in names, "File search intent fell back to generic tools."

    def test_file_read_intent_fast_path(self, runtime_tools_mock):
        grounded = tool_grounding_layer.filter_tools_for_step(
            "Read the contents of C:\\Users\\test.txt", runtime_tools_mock
        )
        names = {t["name"] for t in grounded}
        assert "filesystem__read_file" in names, f"File read not grounded. Got: {names}"

    def test_file_write_intent_fast_path(self, runtime_tools_mock):
        grounded = tool_grounding_layer.filter_tools_for_step(
            "Write a hello world message to output.txt", runtime_tools_mock
        )
        names = {t["name"] for t in grounded}
        assert "filesystem__write_file" in names, f"File write not grounded. Got: {names}"

    def test_web_search_intent_fast_path(self, runtime_tools_mock):
        grounded = tool_grounding_layer.filter_tools_for_step(
            "Google the latest news about artificial intelligence", runtime_tools_mock
        )
        names = {t["name"] for t in grounded}
        assert "cloud_api__search_web" in names, f"Web search not grounded. Got: {names}"
        assert "web_search" in names, f"Built-in web_search not grounded. Got: {names}"

    def test_code_execution_intent_fast_path(self, runtime_tools_mock):
        grounded = tool_grounding_layer.filter_tools_for_step(
            "Run a python script to calculate fibonacci numbers", runtime_tools_mock
        )
        names = {t["name"] for t in grounded}
        assert "code_executor__run_python" in names, f"Code execution not grounded. Got: {names}"
        assert "calculator" not in names, "Code intent fell back to generic tools."

    def test_document_processing_intent_fast_path(self, runtime_tools_mock):
        grounded = tool_grounding_layer.filter_tools_for_step(
            "Parse the PDF and extract the text content", runtime_tools_mock
        )
        names = {t["name"] for t in grounded}
        assert "filesystem__read_file" in names, f"Document processing not grounded. Got: {names}"

    def test_calculation_intent_fast_path(self, runtime_tools_mock):
        grounded = tool_grounding_layer.filter_tools_for_step(
            "Calculate the average of 10, 20, and 30", runtime_tools_mock
        )
        names = {t["name"] for t in grounded}
        assert "calculator" in names, f"Calculator not grounded. Got: {names}"

    def test_browser_open_intent_fast_path(self, runtime_tools_mock):
        grounded = tool_grounding_layer.filter_tools_for_step(
            "Open result.html in Chrome to view it", runtime_tools_mock
        )
        names = {t["name"] for t in grounded}
        assert "browser_env__launch" in names, f"Browser open not grounded. Got: {names}"

    def test_communication_intent_fast_path(self):
        tools = [
            {"name": "cloud_api__send_email"},
            {"name": "cloud_api__send_message"},
            {"name": "slack__send_message"},
            {"name": "text_processor"},
            {"name": "calculator"},
        ]
        grounded = tool_grounding_layer.filter_tools_for_step(
            "Send an email to the team about the deployment", tools
        )
        names = {t["name"] for t in grounded}
        assert "cloud_api__send_email" in names, f"Email not grounded. Got: {names}"
        assert "text_processor" not in names, "Communication intent fell back to generic tools."


class TestNoSpecializedIntentGetsGenericFallback:
    """Verify that missing specialized tools NEVER silently degrade to generic tools."""

    def test_browser_intent_no_generic_fallback(self):
        """If no browser tools exist, browser intent must return empty list."""
        empty_tools = [
            {"name": "web_search"},
            {"name": "calculator"},
            {"name": "text_processor"},
        ]
        grounded = tool_grounding_layer.get_allowed_tools("browser_navigation", empty_tools)
        names = {t["name"] for t in grounded}
        assert names == set(), f"Browser intent fell back to generic tools: {names}"

    def test_shell_intent_no_generic_fallback(self):
        """If no shell tools exist, shell intent must return empty list."""
        empty_tools = [
            {"name": "web_search"},
            {"name": "calculator"},
            {"name": "text_processor"},
        ]
        grounded = tool_grounding_layer.get_allowed_tools("shell_execution", empty_tools)
        names = {t["name"] for t in grounded}
        assert names == set(), f"Shell intent fell back to generic tools: {names}"

    def test_file_search_intent_no_generic_fallback(self):
        """If no file tools exist, file_search intent must return empty list."""
        empty_tools = [
            {"name": "web_search"},
            {"name": "calculator"},
            {"name": "text_processor"},
        ]
        grounded = tool_grounding_layer.get_allowed_tools("file_search", empty_tools)
        names = {t["name"] for t in grounded}
        assert names == set(), f"File search intent fell back to generic tools: {names}"

    def test_code_execution_intent_no_generic_fallback(self):
        """If no code tools exist, code_execution intent must return empty list."""
        empty_tools = [
            {"name": "web_search"},
            {"name": "calculator"},
            {"name": "text_processor"},
        ]
        grounded = tool_grounding_layer.get_allowed_tools("code_execution", empty_tools)
        names = {t["name"] for t in grounded}
        assert names == set(), f"Code intent fell back to generic tools: {names}"

    def test_web_search_intent_no_generic_fallback(self):
        """If no web search tools exist, web_search intent must return empty list."""
        empty_tools = [
            {"name": "calculator"},
            {"name": "text_processor"},
        ]
        grounded = tool_grounding_layer.get_allowed_tools("web_search", empty_tools)
        names = {t["name"] for t in grounded}
        assert "calculator" not in names, "Web search intent fell back to calculator."
        assert "text_processor" not in names, "Web search intent fell back to text_processor."

    def test_document_processing_intent_no_generic_fallback(self):
        """If no document tools exist, document_processing intent must NOT fall back to unrelated tools.

        Note: text_processor IS explicitly listed in CAPABILITY_TOOL_MAP['document_processing']
        as a valid helper tool, so it is expected to be included.
        """
        empty_tools = [
            {"name": "web_search"},
            {"name": "calculator"},
            {"name": "text_processor"},
        ]
        grounded = tool_grounding_layer.get_allowed_tools("document_processing", empty_tools)
        names = {t["name"] for t in grounded}
        # text_processor is explicitly allowed; calculator and web_search are NOT
        assert "calculator" not in names, "Document intent fell back to calculator."
        assert "web_search" not in names, "Document intent fell back to web_search."

    def test_general_intent_still_gets_fallback(self):
        """General intent SHOULD still get generic tools when nothing else matches."""
        tools = [
            {"name": "web_search"},
            {"name": "calculator"},
            {"name": "text_processor"},
        ]
        grounded = tool_grounding_layer.get_allowed_tools("general", tools)
        names = {t["name"] for t in grounded}
        assert "web_search" in names, "General intent lost web_search fallback."
        assert "calculator" in names, "General intent lost calculator fallback."
        assert "text_processor" in names, "General intent lost text_processor fallback."


class TestIntentClassificationEdgeCases:
    """Verify edge cases in intent classification."""

    def test_mixed_description_prefers_desktop(self):
        """If description contains both desktop and generic words, desktop wins."""
        intent = tool_grounding_layer.classify_intent(
            "Open notepad and search for something"
        )
        assert intent == "desktop_automation", f"Expected desktop, got {intent}"

    def test_mixed_description_prefers_browser(self):
        """If description contains both browser and generic words, browser wins."""
        intent = tool_grounding_layer.classify_intent(
            "Open chrome and calculate the sum"
        )
        assert intent == "browser_navigation", f"Expected browser, got {intent}"

    def test_empty_description_defaults_to_general(self):
        intent = tool_grounding_layer.classify_intent("")
        assert intent == "general", f"Expected general for empty string, got {intent}"

    def test_completely_unknown_description_defaults_to_general(self):
        intent = tool_grounding_layer.classify_intent("do something completely vague")
        assert intent == "general", f"Expected general for vague description, got {intent}"
