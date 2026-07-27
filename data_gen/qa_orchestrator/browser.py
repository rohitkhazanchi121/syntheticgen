from playwright.sync_api import sync_playwright, Browser, Page, BrowserContext
from typing import Optional, Dict, Any

class BrowserManager:
    """
    Manages Playwright browser instances and contexts.
    """
    def __init__(self, headless: bool = True, browser_type: str = "chromium"):
        self.headless = headless
        self.browser_type = browser_type
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

    def start(self):
        """Starts the browser session."""
        self.playwright = sync_playwright().start()
        if self.browser_type == "chromium":
            self.browser = self.playwright.chromium.launch(headless=self.headless)
        elif self.browser_type == "firefox":
            self.browser = self.playwright.firefox.launch(headless=self.headless)
        elif self.browser_type == "webkit":
            self.browser = self.playwright.webkit.launch(headless=self.headless)
        else:
            raise ValueError(f"Unsupported browser type: {self.browser_type}")

    def stop(self):
        """Stops the browser session."""
        if self.context:
            self.context.close()
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()

    def new_page(self, **context_args) -> Page:
        """Video recording, viewport size, user agent, etc."""
        if not self.browser:
            self.start()
        self.context = self.browser.new_context(**context_args)
        self.page = self.context.new_page()
        return self.page
