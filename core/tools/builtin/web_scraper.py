from ..base import BaseTool, ToolInput, ToolOutput


class WebScraperExtractTextTool(BaseTool):
    name = "web_scraper__extract_text"
    description = "Extract text content from a webpage using BeautifulSoup. Optionally filter by CSS selector."
    parameters_schema = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL of the webpage to scrape"},
            "selector": {"type": "string", "description": "Optional CSS selector to target specific elements"},
        },
        "required": ["url"],
    }

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        import httpx
        from bs4 import BeautifulSoup

        params = dict(tool_input.parameters)
        url = params.get("url")
        selector = params.get("selector")

        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                resp = await client.get(url, headers={"User-Agent": "AgentOS/1.0"})
                resp.raise_for_status()
                html = resp.text

            soup = BeautifulSoup(html, "html.parser")

            # Remove script and style elements
            for tag in soup(["script", "style", "noscript"]):
                tag.decompose()

            if selector:
                elements = soup.select(selector)
                texts = [el.get_text(separator=" ", strip=True) for el in elements if el.get_text(strip=True)]
                return ToolOutput(success=True, result={"url": url, "selector": selector, "texts": texts, "count": len(texts)})
            else:
                text = soup.get_text(separator="\n", strip=True)
                lines = [line.strip() for line in text.splitlines() if line.strip()]
                return ToolOutput(success=True, result={"url": url, "text": "\n".join(lines[:200]), "line_count": len(lines)})
        except Exception as e:
            return ToolOutput(success=False, error=str(e))
