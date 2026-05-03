import pytest
from unittest.mock import patch, MagicMock
from app.tools.grounding import ToolGroundingLayer


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
