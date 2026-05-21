from ..base import BaseTool, ToolInput, ToolOutput


class SlackSendMessageTool(BaseTool):
    name = "slack__send_message"
    description = "Send a message to a Slack channel (mock implementation)."
    parameters_schema = {
        "type": "object",
        "properties": {
            "channel": {"type": "string", "description": "Slack channel ID or name (e.g., #general)"},
            "text": {"type": "string", "description": "Message text to send"},
        },
        "required": ["channel", "text"],
    }

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = dict(tool_input.parameters)
        channel = params.get("channel")
        text = params.get("text")
        return ToolOutput(
            success=True,
            result={
                "mock": True,
                "channel": channel,
                "text_preview": text[:100] if text else "",
                "status": "delivered",
            },
        )
