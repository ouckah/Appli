from .cleaners import remove_overlays, expand_collapsed_sections
from .playwright_utils import launch_browser, get_page_content, new_page, close_browser

def load_and_clean(url: str):
    playwright, browser = launch_browser()
    page = new_page(browser)
    page.goto(url)

    expand_collapsed_sections(page)

    html = get_page_content(page)
    html = remove_overlays(html)

    close_browser(playwright, browser)
    return html