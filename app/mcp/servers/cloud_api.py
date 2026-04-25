"""MCP Cloud API Server — provides HTTP and search APIs to agents."""
import json
import urllib.request
import urllib.parse
from typing import Optional, Dict, Any

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("cloud_api")

USER_AGENT = "AgentOS-Browser/1.0"


@mcp.tool()
async def http_request(
    url: str,
    method: str = "GET",
    headers: Optional[str] = None,
    body: Optional[str] = None,
    timeout: int = 30,
) -> str:
    """Make an HTTP request and return the response body.

    Args:
        url: Target URL
        method: HTTP method (GET, POST, PUT, DELETE, etc.)
        headers: JSON string of headers
        body: Request body string
        timeout: Request timeout in seconds
    """
    try:
        req_headers = {"User-Agent": USER_AGENT}
        if headers:
            parsed = json.loads(headers)
            if isinstance(parsed, dict):
                req_headers.update(parsed)

        data = body.encode("utf-8") if body else None
        req = urllib.request.Request(url, data=data, method=method.upper(), headers=req_headers)

        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content = resp.read().decode("utf-8", errors="ignore")
            return content
    except urllib.error.HTTPError as e:
        return f"HTTP Error {e.code}: {e.reason}"
    except urllib.error.URLError as e:
        return f"URL Error: {e.reason}"
    except Exception as e:
        return f"Error making request: {e}"


@mcp.tool()
async def scrape_page(url: str, selector: Optional[str] = None) -> str:
    """Fetch and extract text content from a web page.

    Args:
        url: Page URL
        selector: CSS selector to extract specific elements (optional)
    """
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")

            if selector:
                elements = soup.select(selector)
                texts = [el.get_text(strip=True) for el in elements]
                return "\n\n".join(texts) if texts else f"No elements matched selector: {selector}"
            else:
                # Remove script/style tags
                for tag in soup(["script", "style", "nav", "footer"]):
                    tag.decompose()
                return soup.get_text(separator="\n", strip=True)
        except ImportError:
            # Fallback: basic HTML tag stripping
            import re
            text = re.sub(r"<[^>]+>", "", html)
            return text.strip()
    except Exception as e:
        return f"Error scraping page: {e}"


@mcp.tool()
async def search_web(query: str, max_results: int = 5) -> str:
    """Search the web using DuckDuckGo HTML interface.

    Args:
        query: Search query
        max_results: Maximum number of results (default 5)
    """
    try:
        from bs4 import BeautifulSoup
        encoded = urllib.parse.quote_plus(query)
        url = f"https://html.duckduckgo.com/html/?q={encoded}"

        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        soup = BeautifulSoup(html, "html.parser")
        results = []
        for result in soup.select(".result"):
            title_el = result.select_one(".result__title")
            snippet_el = result.select_one(".result__snippet")
            url_el = result.select_one(".result__url")

            title = title_el.get_text(strip=True) if title_el else ""
            snippet = snippet_el.get_text(strip=True) if snippet_el else ""
            link = url_el.get_text(strip=True) if url_el else ""

            if title:
                results.append(f"{title}\n{snippet}\n{link}\n")

            if len(results) >= max_results:
                break

        return "\n".join(results) if results else "No results found"
    except ImportError:
        return "Error: beautifulsoup4 is required for web search. Install it with: pip install beautifulsoup4"
    except Exception as e:
        return f"Error searching web: {e}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
