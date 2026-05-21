from typing import Dict, Any
from ..base import BaseTool, ToolInput, ToolOutput


class GitHubSearchReposTool(BaseTool):
    name = "github__search_repos"
    description = "Search GitHub repositories by query with optional language and sort filters."
    parameters_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query string"},
            "language": {"type": "string", "description": "Filter by programming language (e.g., python, javascript)"},
            "sort": {"type": "string", "enum": ["stars", "forks", "updated"], "default": "stars", "description": "Sort field"},
        },
        "required": ["query"],
    }

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        import httpx
        params: Dict[str, Any] = dict(tool_input.parameters)
        query = params.get("query", "")
        language = params.get("language")
        sort = params.get("sort", "stars")

        q = query
        if language:
            q += f" language:{language}"

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    "https://api.github.com/search/repositories",
                    params={"q": q, "sort": sort, "order": "desc", "per_page": 10},
                    headers={"Accept": "application/vnd.github.v3+json"},
                )
                resp.raise_for_status()
                data = resp.json()
                results = [
                    {
                        "name": item["name"],
                        "owner": item["owner"]["login"],
                        "stars": item["stargazers_count"],
                        "forks": item["forks_count"],
                        "url": item["html_url"],
                        "description": item.get("description"),
                    }
                    for item in data.get("items", [])
                ]
                return ToolOutput(success=True, result={"total_count": data.get("total_count"), "repositories": results})
        except Exception as e:
            return ToolOutput(success=False, error=str(e))


class GitHubGetRepoTool(BaseTool):
    name = "github__get_repo"
    description = "Get detailed information about a specific GitHub repository."
    parameters_schema = {
        "type": "object",
        "properties": {
            "owner": {"type": "string", "description": "Repository owner username or organization"},
            "repo": {"type": "string", "description": "Repository name"},
        },
        "required": ["owner", "repo"],
    }

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        import httpx
        params = dict(tool_input.parameters)
        owner = params.get("owner")
        repo = params.get("repo")

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    f"https://api.github.com/repos/{owner}/{repo}",
                    headers={"Accept": "application/vnd.github.v3+json"},
                )
                resp.raise_for_status()
                data = resp.json()
                return ToolOutput(success=True, result={
                    "name": data["name"],
                    "owner": data["owner"]["login"],
                    "description": data.get("description"),
                    "stars": data["stargazers_count"],
                    "forks": data["forks_count"],
                    "open_issues": data["open_issues_count"],
                    "language": data.get("language"),
                    "url": data["html_url"],
                    "created_at": data.get("created_at"),
                    "updated_at": data.get("updated_at"),
                })
        except Exception as e:
            return ToolOutput(success=False, error=str(e))
