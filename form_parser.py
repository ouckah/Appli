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
        })

    # ===== BUTTONS =====
    for tag in soup.find_all(["button", "a"]):
        if not is_visible(tag):
            continue
        text = tag.get_text(strip=True)
        if text:  # ignore empty
            buttons.append({
                "text": text,
                "id": tag.get("id"),
                "role": tag.get("role") or "button"
            })

    # ===== TEXTAREAS =====
    for tag in soup.find_all("textarea"):
        if is_visible(tag):
            textareas.append({
                "id": tag.get("id"),
                "name": tag.get("name"),
                "label": find_label(tag, soup),
            })

    # ===== SELECTS =====
    for tag in soup.find_all("select"):
        if is_visible(tag):
            options = [o.get_text(strip=True) for o in tag.find_all("option")]
            selects.append({
                "id": tag.get("id"),
                "options": options,
                "label": find_label(tag, soup),
            })

    return {
        "inputs": inputs,
        "textareas": textareas,
        "selects": selects,
        "buttons": buttons,
    }