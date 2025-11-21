from playwright.sync_api import sync_playwright

def launch_browser(headless=False):
    """Launch a browser and return the Playwright browser instance."""
    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(headless=headless)
    return playwright, browser

def new_page(browser, viewport={"width": 1280, "height": 800}):
    """Open a new page with optional viewport size."""
    page = browser.new_page(viewport=viewport)
    return page

def get_page_content(page):
    """Return the page HTML as a string."""
    return page.content()

def close_browser(playwright, browser):
    """Close the browser and stop Playwright."""
    browser.close()
    playwright.stop()