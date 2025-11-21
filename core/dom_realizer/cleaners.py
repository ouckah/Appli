from bs4 import BeautifulSoup

def remove_overlays(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for overlay in soup.select(".overlay, .modal, .popup"):
        overlay.decompose()
    return str(soup)

def expand_collapsed_sections(page):
    # playwright interactions
    page.eval_on_selector_all("details", "els => els.forEach(el => el.open = true)")