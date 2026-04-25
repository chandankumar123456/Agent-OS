"""Browser Environment — real browser UI automation via Playwright."""
import os
import re
import tempfile
import urllib.parse
from typing import Optional, Dict, Any, List
from playwright.async_api import async_playwright, Page, Browser, BrowserContext, Locator

from ..logs.logger import logger
from ..tools.base import ToolInput, ToolOutput


# Domain-specific search input selectors
DOMAIN_SELECTORS: Dict[str, List[str]] = {
    "google.com": [
        'textarea[name="q"]',
        'input[name="q"]',
        '#APjFqb',
        'input[aria-label="Search"]',
    ],
    "youtube.com": [
        'input[name="search_query"]',
        'input#search',
        'ytd-searchbox input',
        '#search-input input',
    ],
    "amazon.com": [
        '#twotabsearchtextbox',
        '#nav-bb-search input',
        '#nav-search-field input',
        'input[name="field-keywords"]',
    ],
    "amazon.in": [
        '#twotabsearchtextbox',
        '#nav-bb-search input',
        'input[name="field-keywords"]',
    ],
    "bing.com": [
        'textarea[name="q"]',
        'input[name="q"]',
        '#sb_form_q',
    ],
    "duckduckgo.com": [
        'input[name="q"]',
        '#search_form_input',
    ],
}

FALLBACK_SELECTORS: List[str] = [
    'input[type="search"]',
    'input[placeholder*="search" i]',
    '[role="searchbox"]',
    'input[name*="query" i]',
    'input[name*="search" i]',
    'input[name*="q" i]',
    'textarea[name*="q" i]',
    'form input',
    'input',
]


class BrowserSession:
    """A single browser session scoped to one task."""

    def __init__(self, task_id: str):
        self.task_id = task_id
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._headless = False
        self._current_url: Optional[str] = None

    async def launch(self, headless: bool = False) -> ToolOutput:
        if self.is_alive():
            logger.info(f"BrowserSession[{self.task_id}]: already alive, skipping launch")
            return ToolOutput(success=True, result={"message": "Browser already launched"})

        self._headless = headless
        try:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=self._headless,
                args=["--disable-blink-features=AutomationControlled"]
            )
            self._context = await self._browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            self._page = await self._context.new_page()
            logger.info(f"BrowserSession[{self.task_id}]: launched new browser instance")
            return ToolOutput(success=True, result={"message": "Browser launched"})
        except Exception as e:
            logger.error(f"BrowserSession[{self.task_id}]: launch failed: {e}")
            return ToolOutput(success=False, error=str(e))

    def is_alive(self) -> bool:
        return self._page is not None and not self._page.is_closed()

    async def _ensure_page(self) -> Page:
        if self.is_alive():
            return self._page
        logger.warning(f"BrowserSession[{self.task_id}]: page closed, attempting recovery")
        if self._context:
            self._page = await self._context.new_page()
            if self._current_url:
                await self._page.goto(self._current_url, wait_until="domcontentloaded")
                logger.info(f"BrowserSession[{self.task_id}]: recovered to {self._current_url}")
            return self._page
        # Full recovery needed
        await self.launch(headless=self._headless)
        return self._page

    async def navigate(self, url: str) -> ToolOutput:
        try:
            page = await self._ensure_page()
            # Try networkidle for SPAs, fall back to domcontentloaded if it hangs
            try:
                await page.goto(url, wait_until="networkidle", timeout=30000)
            except Exception:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            self._current_url = page.url
            title = await page.title()
            return ToolOutput(success=True, result={"url": self._current_url, "title": title})
        except Exception as e:
            logger.error(f"BrowserSession[{self.task_id}]: navigate error: {e}")
            return ToolOutput(success=False, error=str(e))

    async def _dismiss_interstitials(self, page: Page) -> None:
        """Click common consent / cookie / age-gate buttons so the real page surface is reachable."""
        consent_buttons = [
            'button:has-text("Accept all")',
            'button:has-text("Reject all")',
            'button:has-text("I agree")',
            'button:has-text("Agree")',
            'button:has-text("Continue")',
            'button[aria-label*="Accept" i]',
            'form[action*="consent"] button',
            '[data-testid="reject-all-button"]',
        ]
        for sel in consent_buttons:
            try:
                btn = page.locator(sel).first
                await btn.wait_for(state="visible", timeout=3000)
                await btn.click()
                await page.wait_for_load_state("networkidle", timeout=10000)
                logger.info(f"BrowserSession[{self.task_id}]: dismissed interstitial ({sel})")
                return
            except Exception:
                continue

    async def search(self, query: str) -> ToolOutput:
        import re
        page = await self._ensure_page()

        # Dismiss Google/YouTube consent or cookie interstitials first
        await self._dismiss_interstitials(page)

        domain = self._detect_domain()
        selectors = DOMAIN_SELECTORS.get(domain, []) + FALLBACK_SELECTORS

        last_error = None
        for idx, selector in enumerate(selectors):
            try:
                # Give heavy SPAs (YouTube) more time on the first few selectors
                timeout = 10000 if idx < 3 else 5000
                await page.wait_for_selector(selector, timeout=timeout, state="visible")
                await page.fill(selector, query)
                await page.press(selector, "Enter")
                await page.wait_for_load_state("networkidle", timeout=15000)
                self._current_url = page.url
                title = await page.title()
                return ToolOutput(success=True, result={
                    "query": query,
                    "domain": domain,
                    "selector_used": selector,
                    "page_title": title,
                    "message": f"Searched for '{query}' on {domain}"
                })
            except Exception as e:
                last_error = e
                continue

        # Semantic locators (bypass shadow DOM via accessibility tree)
        semantic_strategies = [
            lambda p: p.get_by_role("combobox", name=re.compile("Search", re.IGNORECASE)),
            lambda p: p.get_by_placeholder(re.compile("Search", re.IGNORECASE)),
            lambda p: p.get_by_label(re.compile("Search", re.IGNORECASE)),
        ]
        for strategy in semantic_strategies:
            try:
                locator = strategy(page)
                await locator.fill(query, timeout=5000)
                await locator.press("Enter")
                await page.wait_for_load_state("networkidle", timeout=15000)
                self._current_url = page.url
                title = await page.title()
                return ToolOutput(success=True, result={
                    "query": query,
                    "domain": domain,
                    "selector_used": "semantic_locator",
                    "page_title": title,
                    "message": f"Searched for '{query}' on {domain}"
                })
            except Exception as e:
                last_error = e
                continue

        # Improved failure diagnostics
        screenshot_path = os.path.join(tempfile.gettempdir(), f"agentos_search_fail_{self.task_id}.png")
        try:
            await page.screenshot(path=screenshot_path, full_page=True)
        except Exception:
            screenshot_path = None

        # Use JS to pierce shadow DOM so we don't falsely report "no inputs"
        inputs_info = []
        try:
            inputs_info = await page.evaluate("""() => {
                function deepQuery(root, selector) {
                    let results = Array.from(root.querySelectorAll(selector));
                    root.querySelectorAll('*').forEach(el => {
                        if (el.shadowRoot) {
                            results = results.concat(deepQuery(el.shadowRoot, selector));
                        }
                    });
                    return results;
                }
                return deepQuery(document, 'input, textarea').map(el => ({
                    tag: el.tagName.toLowerCase(),
                    type: el.type,
                    name: el.name,
                    placeholder: el.placeholder,
                    id: el.id,
                    class: el.className,
                    ariaLabel: el.getAttribute('aria-label')
                }));
            }""")
        except Exception:
            pass

        current_url = page.url
        current_title = await page.title()
        error_msg = (
            f"Search failed on '{domain}' (url={current_url}, title={current_title}). "
            f"Tried {len(selectors)} CSS selectors and {len(semantic_strategies)} semantic locators. "
            f"Last error: {last_error}. Available inputs: {inputs_info}"
        )
        if screenshot_path:
            error_msg += f". Screenshot: {screenshot_path}"
        logger.error(f"BrowserSession[{self.task_id}]: {error_msg}")
        return ToolOutput(success=False, error=error_msg)

    def _detect_domain(self) -> str:
        if not self._page:
            return "unknown"
        url = self._page.url
        try:
            host = urllib.parse.urlparse(url).hostname or ""
            # Strip www. prefix
            if host.startswith("www."):
                host = host[4:]
            return host.lower()
        except Exception:
            return "unknown"

    async def click(self, selector: str) -> ToolOutput:
        try:
            page = await self._ensure_page()
            await page.click(selector)
            self._current_url = page.url
            return ToolOutput(success=True, result={"message": f"Clicked {selector}"})
        except Exception as e:
            return ToolOutput(success=False, error=str(e))

    async def type_text(self, selector: str, text: str) -> ToolOutput:
        try:
            page = await self._ensure_page()
            await page.fill(selector, text)
            return ToolOutput(success=True, result={"message": f"Typed into {selector}"})
        except Exception as e:
            return ToolOutput(success=False, error=str(e))

    async def screenshot(self, path: Optional[str] = None) -> ToolOutput:
        try:
            page = await self._ensure_page()
            if not path:
                path = os.path.join(tempfile.gettempdir(), f"agentos_screenshot_{self.task_id}.png")
            await page.screenshot(path=path, full_page=True)
            return ToolOutput(success=True, result={"path": path, "message": f"Screenshot saved to {path}"})
        except Exception as e:
            return ToolOutput(success=False, error=str(e))

    async def get_text(self, selector: Optional[str] = None) -> ToolOutput:
        try:
            page = await self._ensure_page()
            if selector:
                text = await page.inner_text(selector)
            else:
                text = await page.inner_text("body")
            return ToolOutput(success=True, result={"text": text[:5000]})
        except Exception as e:
            return ToolOutput(success=False, error=str(e))

    async def close(self) -> ToolOutput:
        try:
            if self._browser:
                await self._browser.close()
                self._browser = None
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None
            self._page = None
            self._context = None
            logger.info(f"BrowserSession[{self.task_id}]: browser closed")
            return ToolOutput(success=True, result={"message": "Browser closed"})
        except Exception as e:
            return ToolOutput(success=False, error=str(e))

    async def health_check(self) -> Dict[str, str]:
        try:
            page = await self._ensure_page()
            await page.goto("about:blank")
            return {"status": "healthy", "message": "Browser session active"}
        except Exception as e:
            return {"status": "unhealthy", "message": str(e)}


class BrowserSessionManager:
    """Manages browser sessions per task_id."""

    def __init__(self):
        self._sessions: Dict[str, BrowserSession] = {}

    async def get_or_create_session(self, task_id: str) -> BrowserSession:
        session = self._sessions.get(task_id)
        if session and session.is_alive():
            logger.info(f"BrowserSessionManager: reusing session for task {task_id}")
            return session
        if session:
            logger.warning(f"BrowserSessionManager: session dead for task {task_id}, recreating")
            await session.close()
        session = BrowserSession(task_id)
        await session.launch()
        self._sessions[task_id] = session
        return session

    def get_session(self, task_id: str) -> Optional[BrowserSession]:
        return self._sessions.get(task_id)

    async def close_session(self, task_id: str) -> ToolOutput:
        session = self._sessions.pop(task_id, None)
        if session:
            return await session.close()
        return ToolOutput(success=True, result={"message": "No session to close"})

    async def close_all(self):
        for task_id, session in list(self._sessions.items()):
            await session.close()
        self._sessions.clear()


browser_session_manager = BrowserSessionManager()
