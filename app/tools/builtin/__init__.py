from typing import List
from ..base import BaseTool
from .github import GitHubSearchReposTool, GitHubGetRepoTool
from .slack import SlackSendMessageTool
from .notion import NotionSearchPagesTool
from .web_scraper import WebScraperExtractTextTool


BUILTIN_TOOLS: List[BaseTool] = [
    GitHubSearchReposTool(),
    GitHubGetRepoTool(),
    SlackSendMessageTool(),
    NotionSearchPagesTool(),
    WebScraperExtractTextTool(),
    # CodeExecutorRunPythonTool is now provided by the code_executor MCP server.
]


def register_builtin_tools(registry) -> None:
    """Register all built-in tools with the provided registry."""
    for tool in BUILTIN_TOOLS:
        registry.register(tool)
