"""Regression tests for desktop grounding bug.

When a user asks for desktop operations (e.g. "open notepad"), the grounding
layer must return desktop tools, not generic tools like text_processor or
web_search. These tests prove the current broken state.
"""
import pytest

from app.tools.grounding import tool_grounding_layer


@pytest.fixture
def runtime_tools_mock():
    """Return a mixed tool list containing desktop and generic tools."""
    return [
        # Registered desktop_env tools
        {"name": "desktop_env__click"},
        {"name": "desktop_env__type_text"},
        {"name": "desktop_env__press_key"},
        {"name": "desktop_env__focus_window"},
        {"name": "desktop_env__get_window_list"},
        # MCP desktop tools (desktop__*)
        {"name": "desktop__get_ui_tree"},
        {"name": "desktop__click_element"},
        {"name": "desktop__type_element"},
        {"name": "desktop__focus_and_interact"},
        # MCP desktop tools (desktop__desktop__*)
        {"name": "desktop__desktop__click"},
        {"name": "desktop__desktop__type_text"},
        {"name": "desktop__desktop__press_key"},
        {"name": "desktop__desktop__focus_window"},
        # Generic tools that must NOT be returned for desktop intents
        {"name": "web_search"},
        {"name": "calculator"},
        {"name": "text_processor"},
    ]


class TestDesktopGroundingRegression:
    """Tests that simulate the exact failure mode of the desktop grounding bug."""

    def test_open_notepad_intent_classified_as_desktop(self, runtime_tools_mock):
        """Explicit desktop automation intent must ground desktop tools."""
        step = "Use desktop automation to open Notepad and type a quick note."
        grounded = tool_grounding_layer.filter_tools_for_step(step, runtime_tools_mock)
        grounded_names = {t["name"] for t in grounded}

        # Must contain desktop tools
        assert "desktop_env__click" in grounded_names
        assert "desktop_env__type_text" in grounded_names
        assert "desktop__desktop__click" in grounded_names

        # Must NOT contain generic tools
        assert "web_search" not in grounded_names
        assert "calculator" not in grounded_names
        assert "text_processor" not in grounded_names

    def test_type_in_notepad_intent_classified_as_desktop(self, runtime_tools_mock):
        """Typing in Notepad must ground typing-related desktop tools."""
        step = "Type a short comparison note in Notepad."
        grounded = tool_grounding_layer.filter_tools_for_step(step, runtime_tools_mock)
        grounded_names = {t["name"] for t in grounded}

        # Must contain typing tools
        assert "desktop_env__type_text" in grounded_names
        assert "desktop__desktop__type_text" in grounded_names

        # Must NOT contain generic tools
        assert "web_search" not in grounded_names
        assert "calculator" not in grounded_names
        assert "text_processor" not in grounded_names

    def test_open_notepad_natural_language(self):
        """Natural language phrase 'open notepad' must classify as desktop."""
        intent = tool_grounding_layer.classify_intent("open notepad")
        assert intent == "desktop_automation", f"Expected desktop_automation, got {intent}"

    def test_desktop_automation_never_gets_generic_tools(self):
        """If no desktop tools are available, generic tools must NOT be returned."""
        tools_without_desktop = [
            {"name": "web_search"},
            {"name": "calculator"},
            {"name": "text_processor"},
        ]
        grounded = tool_grounding_layer.get_allowed_tools(
            "desktop_automation", tools_without_desktop
        )
        grounded_names = {t["name"] for t in grounded}

        assert "web_search" not in grounded_names
        assert "calculator" not in grounded_names
        assert "text_processor" not in grounded_names
        assert grounded_names == set()
