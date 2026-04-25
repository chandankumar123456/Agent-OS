from ..base import BaseTool, ToolInput, ToolOutput


class NotionSearchPagesTool(BaseTool):
    name = "notion__search_pages"
    description = "Search Notion pages by query (mock implementation)."
    parameters_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query string"},
        },
        "required": ["query"],
    }

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = dict(tool_input.parameters)
        query = params.get("query", "")
        return ToolOutput(
            success=True,
            result={
                "mock": True,
                "query": query,
                "results": [
                    {"title": f"Mock page matching '{query}'", "id": "mock-page-1", "url": "https://notion.so/mock-1"},
                ],
            },
        )
