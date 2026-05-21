import json
from typing import Dict, Any, Optional
from ..logs.logger import logger


class ToolCallParser:
    """Parses agent output to detect tool invocations."""

    @staticmethod
    def parse(output_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Extract tool_call from agent JSON output."""
        if not isinstance(output_data, dict):
            return None

        tool_call = output_data.get("tool_call")
        if not tool_call:
            return None

        if isinstance(tool_call, dict):
            return {
                "name": tool_call.get("name"),
                "params": tool_call.get("params", {}),
            }

        # Try parsing if tool_call is a string
        if isinstance(tool_call, str):
            try:
                parsed = json.loads(tool_call)
                return {
                    "name": parsed.get("name"),
                    "params": parsed.get("params", {}),
                }
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse tool_call string: {tool_call}")
                return None

        return None

    @staticmethod
    def has_tool_call(output_data: Dict[str, Any]) -> bool:
        return ToolCallParser.parse(output_data) is not None
