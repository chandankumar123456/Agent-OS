import pytest
from unittest.mock import patch, MagicMock
from app.tools.grounding import ToolGroundingLayer, CAPABILITY_TOOL_MAP


def test_grounding_warns_on_unregistered_tools():
    """FR4.3: Must log warning if capability maps to tools not in registry."""
    layer = ToolGroundingLayer()
    fake_registry = MagicMock()
    fake_registry.tools = {"real_tool": MagicMock()}

    with patch("app.tools.grounding.tool_registry", fake_registry):
        with patch("app.tools.grounding.logger") as mock_logger:
            result = layer.ground_tools(
                intent="desktop_automation",
                all_tools=[
                    {"name": "real_tool"},
                    {"name": "phantom_tool"},
                ],
            )
    mock_logger.warning.assert_called_once()
    # With mocked logger, %s is not interpolated; check the variadic args
    assert "phantom_tool" in str(mock_logger.warning.call_args)


def test_no_phantom_desktop_tools_in_capability_map():
    """All phantom desktop__desktop__* tools must be removed from CAPABILITY_TOOL_MAP."""
    desktop_patterns = CAPABILITY_TOOL_MAP.get("desktop_automation", [])
    phantom = [p for p in desktop_patterns if "desktop__desktop__" in p]
    assert phantom == [], (
        f"Phantom desktop__desktop__ tools found in CAPABILITY_TOOL_MAP['desktop_automation']: {phantom}"
    )


def test_get_allowed_tools_uses_exact_match():
    """Allowed tools must use exact match for MCP-style tool names — no prefix leakage."""
    layer = ToolGroundingLayer()
    # Mock registry so cloud_api__* tools pass the FR4.3 validation
    fake_registry = MagicMock()
    fake_registry.tools = {
        "cloud_api__search_web": MagicMock(),
        "cloud_api__send_email": MagicMock(),
        "cloud_api__http_request": MagicMock(),
    }

    # Simulate allowed patterns for web_search intent:
    # cloud_api__search_web should NOT also allow cloud_api__send_email
    all_tools = [
        {"name": "cloud_api__search_web"},
        {"name": "cloud_api__send_email"},
        {"name": "cloud_api__http_request"},
    ]

    with patch("app.tools.grounding.tool_registry", fake_registry):
        allowed = layer.get_allowed_tools("web_search", all_tools)
    allowed_names = {t["name"] for t in allowed}

    assert "cloud_api__search_web" in allowed_names, "Expected tool must be allowed"
    assert "cloud_api__send_email" not in allowed_names, (
        "cloud_api__send_email leaked through prefix-matching — exact match required"
    )


def test_forbidden_prefixes_applied_to_specialized_intents():
    """Forbidden prefixes must apply to all intents, not just when allowed is empty."""
    layer = ToolGroundingLayer()
    # Mock registry so tools pass the FR4.3 validation
    fake_registry = MagicMock()
    fake_registry.tools = {
        "browser_env__launch": MagicMock(),
        "browser_env__navigate": MagicMock(),
        "shell__execute_command": MagicMock(),
    }

    # browser_navigation intent has shell__execute_command in its forbidden set
    all_tools = [
        {"name": "browser_env__launch"},
        {"name": "browser_env__navigate"},
        {"name": "shell__execute_command"},
    ]

    with patch("app.tools.grounding.tool_registry", fake_registry):
        allowed = layer.get_allowed_tools("browser_navigation", all_tools)
    allowed_names = {t["name"] for t in allowed}

    assert "browser_env__launch" in allowed_names
    assert "browser_env__navigate" in allowed_names
    assert "shell__execute_command" not in allowed_names, (
        "shell__execute_command should be blocked by forbidden-prefix for browser_navigation intent"
    )


def test_unregistered_tools_warned_in_allowed_tools():
    """Unregistered tools must trigger a warning in get_allowed_tools (FR4.3 reachability)."""
    layer = ToolGroundingLayer()
    fake_registry = MagicMock()
    # Only cloud_api__search_web is registered; cloud_api__send_email is NOT
    fake_registry.tools = {"cloud_api__search_web": MagicMock()}

    all_tools = [
        {"name": "cloud_api__search_web"},
        {"name": "cloud_api__send_email"},
    ]

    with patch("app.tools.grounding.tool_registry", fake_registry):
        with patch("app.tools.grounding.logger") as mock_logger:
            allowed = layer.get_allowed_tools("web_search", all_tools)
            allowed_names = {t["name"] for t in allowed}

    # cloud_api__search_web should be allowed (it's in CAPABILITY_TOOL_MAP)
    assert "cloud_api__search_web" in allowed_names
    # Warning should have been logged for the unregistered tool
    mock_logger.warning.assert_called_once()
    assert "cloud_api__send_email" in str(mock_logger.warning.call_args)
