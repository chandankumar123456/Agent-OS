"""Browser Environment — real browser UI automation via Playwright."""
import os
import tempfile
from typing import Optional, Dict, Any
from playwright.async_api import async_playwright, Page, Browser, BrowserContext

from ..logs.logger import logger
from ..tools.base import ToolInput, ToolOutput


class BrowserEnvironment:
    def __init__(self):
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._headless = False

    async def _ensure_browser(self) -> Page:
        if self._page and not self._page.is_closed():
            return self._page

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self._headless,
            args=["--disable-blink-features=AutomationControlled"]
        )
        self._context = await self._browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        self._page = await self._context.new_page()
        logger.info("BrowserEnvironment: launched new browser instance")
        return self._page

    async def launch(self, url: Optional[str] = None, headless: bool = False) -> ToolOutput:
        self._headless = headless
        page = await self._ensure_browser()
        if url:
            await page.goto(url, wait_until="domcontentloaded")
            logger.info(f"BrowserEnvironment: navigated to {url}")
            return ToolOutput(success=True, result={"message": f"Launched browser and navigated to {url}"})
        return ToolOutput(success=True, result={"message": "Browser launched"})

    async def navigate(self, url: str) -> ToolOutput:
        page = await self._ensure_browser()
        await page.goto(url, wait_until="domcontentloaded")
        title = await page.title()
        return ToolOutput(success=True, result={"url": url, "title": title})

    async def search(self, query: str) -> ToolOutput:
        page = await self._ensure_browser()
        await page.goto("https://www.google.com", wait_until="domcontentloaded")
        try:
            await page.click('button:has-text("Accept all")', timeout=3000)
        except Exception:
            pass
        await page.fill('textarea[name="q"]', query)
        await page.press('textarea[name="q"]', "Enter")
        await page.wait_for_load_state("networkidle")
        title = await page.title()
        return ToolOutput(success=True, result={"query": query, "page_title": title, "message": f"Searched for '{query}' in browser"})

    async def click(self, selector: str) -> ToolOutput:
        page = await self._ensure_browser()
        await page.click(selector)
        return ToolOutput(success=True, result={"message": f"Clicked {selector}"})

    async def type_text(self, selector: str, text: str) -> ToolOutput:
        page = await self._ensure_browser()
        await page.fill(selector, text)
        return ToolOutput(success=True, result={"message": f"Typed into {selector}"})

    async def screenshot(self, path: Optional[str] = None) -> ToolOutput:
        page = await self._ensure_browser()
        if not path:
            path = os.path.join(tempfile.gettempdir(), "agentos_screenshot.png")
        await page.screenshot(path=path, full_page=True)
        return ToolOutput(success=True, result={"path": path, "message": f"Screenshot saved to {path}"})

    async def get_text(self, selector: Optional[str] = None) -> ToolOutput:
        page = await self._ensure_browser()
        if selector:
            text = await page.inner_text(selector)
        else:
            text = await page.inner_text("body")
        return ToolOutput(success=True, result={"text": text[:5000]})

    async def close(self) -> ToolOutput:
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        self._page = None
        self._context = None
        logger.info("BrowserEnvironment: browser closed")
        return ToolOutput(success=True, result={"message": "Browser closed"})

    async def health_check(self) -> Dict[str, str]:
        try:
            page = await self._ensure_browser()
            await page.goto("about:blank")
            return {"status": "healthy", "message": "Browser launched successfully"}
        except Exception as e:
            return {"status": "unhealthy", "message": str(e)}


browser_environment = BrowserEnvironment()
