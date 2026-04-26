"""Browser Environment — real browser UI automation via Playwright."""
import asyncio
import functools
import os
import re
import sys
import tempfile
import time
import urllib.parse
from typing import Optional, Dict, Any, List, Callable, TypeVar
from playwright.async_api import (
    async_playwright,
    Page,
    Browser,
    BrowserContext,
    Locator,
    TimeoutError as PlaywrightTimeoutError,
    Error as PlaywrightError,
)

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


def _is_transient_playwright_error(exc: Exception) -> bool:
    """Return True if the exception is a transient network/timeout error."""
    if isinstance(exc, PlaywrightTimeoutError):
        return True
    msg = str(exc).lower()
    transient_keywords = ("net::", "err_network", "timeout", "connection", "socket")
    return any(k in msg for k in transient_keywords)


T = TypeVar("T")


def _retry(max_retries: int = 3, base_delay: float = 1.0, max_delay: float = 10.0):
    """Async retry decorator for transient Playwright errors with exponential backoff."""

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception: Optional[Exception] = None
            for attempt in range(1, max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as exc:
                    last_exception = exc
                    if not _is_transient_playwright_error(exc):
                        raise
                    delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
                    logger.warning(
                        f"BrowserSession: transient error on {func.__name__} "
                        f"(attempt {attempt}/{max_retries}): {exc}. Retrying in {delay}s..."
                    )
                    await asyncio.sleep(delay)
            raise last_exception  # type: ignore[misc]

        return wrapper

    return decorator


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

    async def bind_to_browser(self, browser: Browser):
        """Bind to an existing browser instance (context-only mode)."""
        self._browser = browser
        self._context = await browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        self._page = await self._context.new_page()
        await self._page.bring_to_front()
        logger.info(f"BrowserSession[{self.task_id}]: created new context in persistent browser")

    async def launch(self, headless: bool = False) -> ToolOutput:
        if await self.is_alive():
            logger.info(f"BrowserSession[{self.task_id}]: already alive, skipping launch")
            return ToolOutput(success=True, result={"message": "Browser already launched"})
        from .browser_env import browser_session_manager
        session = await browser_session_manager.get_or_create_session(self.task_id)
        self._browser = session._browser
        self._context = session._context
        self._page = session._page
        return ToolOutput(success=True, result={"message": "Browser bound to persistent instance"})

    async def is_alive(self) -> bool:
        if self._page is None or self._page.is_closed():
            return False
        if self._browser is not None:
            try:
                if not self._browser.is_connected():
                    return False
            except Exception:
                return False
        # Structural check only: can we talk to the page?
        try:
            await self._page.evaluate("1 + 1")
        except Exception:
            return False
        return True

    async def has_content(self) -> bool:
        """Return True if the page has meaningful content (not about:blank)."""
        if self._page is None or self._page.is_closed():
            return False
        try:
            url = self._page.url
            if url in ("about:blank", "", None):
                return False
            html_len = await self._page.evaluate("document.body ? document.body.innerHTML.length : 0")
            if html_len < 50:
                return False
        except Exception:
            return False
        return True

    async def _ensure_page(self) -> Page:
        if await self.is_alive():
            return self._page
        logger.warning(f"BrowserSession[{self.task_id}]: page closed, attempting recovery")
        if self._context:
            self._page = await self._context.new_page()
            await self._page.bring_to_front()
            if self._current_url:
                await self._page.goto(self._current_url, wait_until="domcontentloaded")
                logger.info(f"BrowserSession[{self.task_id}]: recovered to {self._current_url}")
            return self._page
        # Full recovery needed
        await self.launch(headless=self._headless)
        return self._page

    @_retry(max_retries=3, base_delay=1.0)
    async def navigate(self, url: str) -> ToolOutput:
        if not url:
            return ToolOutput(success=False, error="Navigate requires a 'url' parameter but none was provided.")
        try:
            page = await self._ensure_page()
            # Try networkidle for SPAs, fall back to domcontentloaded, then load
            load_states = ["networkidle", "domcontentloaded", "load"]
            last_err = None
            for state in load_states:
                try:
                    await page.goto(url, wait_until=state, timeout=30000)
                    break
                except PlaywrightTimeoutError as exc:
                    last_err = exc
                    logger.warning(
                        f"BrowserSession[{self.task_id}]: navigate wait_until={state} timed out, trying next fallback"
                    )
                    continue
            else:
                # All fallbacks exhausted within one attempt — let the retry decorator handle it
                raise last_err

            await page.bring_to_front()
            self._current_url = page.url
            title = await page.title()

            # Content verification after navigation
            await asyncio.sleep(0.3)
            try:
                verify_url = page.url
                html_len = await page.evaluate("document.body ? document.body.innerHTML.length : 0")
                # about:blank is a valid destination; only flag error if we expected real content
                is_blank = verify_url in ("", None) or (verify_url != "about:blank" and html_len < 50)
                if is_blank:
                    screenshot_path = os.path.join(tempfile.gettempdir(), f"agentos_blank_{self.task_id}.png")
                    await page.screenshot(path=screenshot_path, full_page=True)
                    logger.error(f"BrowserSession[{self.task_id}]: blank page detected. Screenshot: {screenshot_path}")
                    return ToolOutput(
                        success=False,
                        error=f"Browser page remained blank after navigating to {verify_url}. Screenshot: {screenshot_path}",
                    )
            except Exception as e:
                logger.warning(f"BrowserSession[{self.task_id}]: content verification error: {e}")

            return ToolOutput(
                success=True,
                result={"url": self._current_url, "title": title},
                visibility={"type": "browser_navigated", "url": self._current_url, "title": title},
            )
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

    @_retry(max_retries=3, base_delay=1.0)
    async def search(self, query: str) -> ToolOutput:
        import re
        page = await self._ensure_page()

        # If the browser is still on about:blank, navigate to a search engine first
        if page.url in ("about:blank", "", None):
            logger.info(f"BrowserSession[{self.task_id}]: search called on blank page; navigating to Google")
            await page.goto("https://www.google.com", wait_until="domcontentloaded", timeout=30000)
            self._current_url = page.url

        # Dismiss Google/YouTube consent or cookie interstitials first
        await self._dismiss_interstitials(page)

        domain = self._detect_domain()
        selectors = DOMAIN_SELECTORS.get(domain, []) + FALLBACK_SELECTORS

        last_error = None
        for attempt in range(2):  # Hydration retry loop
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
                    return ToolOutput(
                        success=True,
                        result={
                            "query": query,
                            "domain": domain,
                            "selector_used": selector,
                            "page_title": title,
                            "message": f"Searched for '{query}' on {domain}",
                        },
                        visibility={"type": "browser_search", "query": query, "domain": domain, "page_title": title},
                    )
                except Exception as e:
                    last_error = e
                    continue
            # SPA hydration fallback: short sleep before second attempt
            if attempt == 0:
                logger.info(f"BrowserSession[{self.task_id}]: search retrying after short hydration delay")
                await asyncio.sleep(1.5)

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
                return ToolOutput(
                    success=True,
                    result={
                        "query": query,
                        "domain": domain,
                        "selector_used": "semantic_locator",
                        "page_title": title,
                        "message": f"Searched for '{query}' on {domain}",
                    },
                    visibility={"type": "browser_search", "query": query, "domain": domain, "page_title": title},
                )
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

    @_retry(max_retries=3, base_delay=1.0)
    async def click(self, selector: str) -> ToolOutput:
        try:
            page = await self._ensure_page()
            await page.wait_for_selector(selector, state="visible", timeout=10000)
            await page.click(selector)
            self._current_url = page.url
            return ToolOutput(
                success=True,
                result={"message": f"Clicked {selector}"},
                visibility={"type": "browser_click", "selector": selector},
            )
        except Exception as e:
            return ToolOutput(success=False, error=str(e))

    @_retry(max_retries=3, base_delay=1.0)
    async def type_text(self, selector: str, text: str) -> ToolOutput:
        try:
            page = await self._ensure_page()
            await page.wait_for_selector(selector, state="visible", timeout=10000)
            await page.fill(selector, text)
            return ToolOutput(
                success=True,
                result={"message": f"Typed into {selector}"},
                visibility={"type": "browser_type", "selector": selector},
            )
        except Exception as e:
            return ToolOutput(success=False, error=str(e))

    async def screenshot(self, path: Optional[str] = None) -> ToolOutput:
        try:
            page = await self._ensure_page()
            if not path:
                path = os.path.join(tempfile.gettempdir(), f"agentos_screenshot_{self.task_id}.png")
            await page.screenshot(path=path, full_page=True)
            return ToolOutput(
                success=True,
                result={"path": path, "message": f"Screenshot saved to {path}"},
                visibility={"type": "browser_screenshot", "path": path},
            )
        except Exception as e:
            return ToolOutput(success=False, error=str(e))

    async def get_text(self, selector: Optional[str] = None) -> ToolOutput:
        try:
            page = await self._ensure_page()
            if selector:
                text = await page.inner_text(selector)
            else:
                text = await page.inner_text("body")
            return ToolOutput(
                success=True,
                result={"text": text[:5000]},
                visibility={"type": "browser_text", "text_preview": text[:100]},
            )
        except Exception as e:
            return ToolOutput(success=False, error=str(e))

    async def get_url(self) -> ToolOutput:
        try:
            page = await self._ensure_page()
            return ToolOutput(
                success=True,
                result={"url": page.url},
                visibility={"type": "browser_url", "url": page.url},
            )
        except Exception as e:
            return ToolOutput(success=False, error=str(e))

    async def get_title(self) -> ToolOutput:
        try:
            page = await self._ensure_page()
            title = await page.title()
            return ToolOutput(
                success=True,
                result={"title": title},
                visibility={"type": "browser_title", "title": title},
            )
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

    async def close_context_only(self) -> ToolOutput:
        """Close only the context, not the shared browser."""
        try:
            if self._context:
                await self._context.close()
                self._context = None
            self._page = None
            logger.info(f"BrowserSession[{self.task_id}]: context closed")
            return ToolOutput(success=True, result={"message": "Browser context closed"})
        except Exception as e:
            return ToolOutput(success=False, error=str(e))

    async def health_check(self) -> Dict[str, str]:
        try:
            page = await self._ensure_page()
            url = page.url
            title = await page.title()
            html_len = await page.evaluate("document.body ? document.body.innerHTML.length : 0")
            if url in ("about:blank", "", None) or html_len < 50:
                return {"status": "unhealthy", "message": f"Page appears blank (url={url}, html_len={html_len})"}
            return {"status": "healthy", "message": f"Browser active (url={url}, title={title})"}
        except Exception as e:
            return {"status": "unhealthy", "message": str(e)}


class BrowserSessionManager:
    """Manages browser sessions per task_id."""

    def __init__(self):
        self._sessions: Dict[str, BrowserSession] = {}
        self._playwright = None
        self._browser = None
        self._lock = asyncio.Lock()

    async def _ensure_browser(self):
        if self._browser and self._browser.is_connected():
            return
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"]
        )
        logger.info("BrowserSessionManager: launched persistent browser process")
        if sys.platform == "win32":
            try:
                import pygetwindow as gw
                time.sleep(0.5)
                windows = [w for w in gw.getAllWindows() if "Chromium" in w.title or "chrome" in w.title.lower()]
                if windows:
                    win = windows[0]
                    if hasattr(win, 'isMinimized') and win.isMinimized:
                        win.restore()
                    if hasattr(win, 'activate'):
                        win.activate()
                    logger.info("BrowserSessionManager: brought Chromium window to foreground")
            except Exception as e:
                logger.warning(f"BrowserSessionManager: could not foreground window: {e}")

    async def get_or_create_session(self, task_id: str) -> BrowserSession:
        session = self._sessions.get(task_id)
        if session and await session.is_alive():
            logger.info(f"BrowserSessionManager: reusing session for task {task_id}")
            return session
        if session:
            logger.warning(f"BrowserSessionManager: session dead for task {task_id}, recreating")
            try:
                await session.close_context_only()
            except Exception:
                pass

        await self._ensure_browser()
        session = BrowserSession(task_id)
        await session.bind_to_browser(self._browser)
        self._sessions[task_id] = session
        return session

    def get_session(self, task_id: str) -> Optional[BrowserSession]:
        return self._sessions.get(task_id)

    async def close_session(self, task_id: str) -> ToolOutput:
        session = self._sessions.pop(task_id, None)
        if session:
            return await session.close_context_only()
        return ToolOutput(success=True, result={"message": "No session to close"})

    async def close_all(self):
        for task_id, session in list(self._sessions.items()):
            try:
                await session.close_context_only()
            except Exception:
                pass
        self._sessions.clear()
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None


browser_session_manager = BrowserSessionManager()
