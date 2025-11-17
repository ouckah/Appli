from bs4 import BeautifulSoup

# Helper functions for parsing the DOM
def find_label(tag, soup):
    tag_id = tag.get("id")
    if tag_id:
        label = soup.find("label", attrs={"for": tag_id})
        if label:
            return label.get_text(strip=True)
    # fallback: look at parent text
    parent_text = tag.parent.get_text(strip=True)
    return parent_text if parent_text else None


def is_visible(tag):
    return tag.get("aria-hidden") != "true" and tag.get("aria-disabled") != "true"


def get_xpath(tag):
    """
    Generates a simple XPath for the tag using its text content or position.
    """
    if tag.name == "button":
        text = tag.get_text(strip=True)
        if text:
            return f"//button[text()='{text}']"
    elif tag.name == "a":
        text = tag.get_text(strip=True)
        if text:
            return f"//a[text()='{text}']"
    elif tag.name in ["input", "textarea", "select"]:
        if tag.get("id"):
            return f"//*[@id='{tag.get('id')}']"
        elif tag.get("name"):
            return f"//*[@name='{tag.get('name')}']"
    # fallback: tag type and position
    siblings = [s for s in tag.parent.find_all(tag.name)]
    index = siblings.index(tag) + 1
    return f"//{tag.name}[{index}]"


def get_css_text_selector(tag):
    """
    Generates a Playwright-compatible CSS selector based on text content (best for buttons/links).
    """
    text = tag.get_text(strip=True)
    if text:
        return f"{tag.name}:has-text('{text}')"
    return None


# Main function to extract the semantic DOM
def extract_semantic_dom(html: str):
    soup = BeautifulSoup(html, "html.parser")

    inputs = []
    buttons = []
    selects = []
    textareas = []

    # ===== INPUTS =====
    for tag in soup.find_all("input"):
        if not is_visible(tag):
            continue
        inputs.append({
            "id": tag.get("id"),
            "name": tag.get("name"),
            "type": tag.get("type", "text"),
            "placeholder": tag.get("placeholder"),
            "label": find_label(tag, soup),
            "xpath": get_xpath(tag),
            "css": get_css_text_selector(tag)
        })

    # ===== BUTTONS =====
    for tag in soup.find_all(["button", "a"]):
        if not is_visible(tag):
            continue
        text = tag.get_text(strip=True)
        if text:
            buttons.append({
                "text": text,
                "id": tag.get("id"),
                "role": tag.get("role") or "button",
                "xpath": get_xpath(tag),
                "css": get_css_text_selector(tag)
            })

    # ===== TEXTAREAS =====
    for tag in soup.find_all("textarea"):
        if is_visible(tag):
            textareas.append({
                "id": tag.get("id"),
                "name": tag.get("name"),
                "label": find_label(tag, soup),
                "xpath": get_xpath(tag),
                "css": get_css_text_selector(tag)
            })

    # ===== SELECTS =====
    for tag in soup.find_all("select"):
        if is_visible(tag):
            options = [o.get_text(strip=True) for o in tag.find_all("option")]
            selects.append({
                "id": tag.get("id"),
                "options": options,
                "label": find_label(tag, soup),
                "xpath": get_xpath(tag),
                "css": get_css_text_selector(tag)
            })

    return {
        "inputs": inputs,
        "textareas": textareas,
        "selects": selects,
        "buttons": buttons,
    }