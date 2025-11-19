from contextlib import asynccontextmanager

from playwright.async_api import async_playwright


@asynccontextmanager
async def launch_browser():
    """Context manager to launch and tear down a Playwright browser."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        try:
            yield browser
        finally:
            await browser.close()


async def load_page_html(url: str, *, wait_until: str = "networkidle") -> str:
    """Load a URL in Chromium and return the full page HTML."""
    async with launch_browser() as browser:
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto(url, wait_until=wait_until)
        html = await page.content()
        await context.close()
        return html