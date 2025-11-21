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
        label_text = find_label(tag, soup)
        field_name = tag.get("name")
        label_selector = f"label:has-text('{label_text}')" if label_text else None
        label_xpath = (
            f"//label[normalize-space()='{label_text}']"
            if label_text else None
        )

        relationship = None
        if label_text and field_name:
            relationship = (
                f"{label_selector} >> .. >> [name='{field_name}']"
                if label_selector else None
            )

        # Detect custom dropdowns (readonly inputs, comboboxes, etc.)
        readonly = tag.has_attr("readonly") or tag.has_attr("readOnly")
        role = tag.get("role", "").lower()
        aria_haspopup = tag.get("aria-haspopup", "").lower()
        aria_expanded = tag.get("aria-expanded")
        class_name = tag.get("class", [])
        class_str = " ".join(class_name).lower() if isinstance(class_name, list) else (class_name or "").lower()
        id_str = (tag.get("id") or "").lower()
        
        # Strong indicators of a custom dropdown
        is_custom_dropdown = (
            readonly or
            role == "combobox" or
            aria_haspopup in ("listbox", "menu", "true") or
            aria_expanded is not None or
            any(pattern in class_str for pattern in ["select", "dropdown", "picker", "combobox", "menu-trigger"]) or
            any(pattern in id_str for pattern in ["select", "dropdown", "picker", "combobox"])
        )

        input_data = {
            "id": tag.get("id"),
            "name": field_name,
            "type": tag.get("type", "text"),
            "placeholder": tag.get("placeholder"),
            "label": label_text,
            "xpath": get_xpath(tag),
            "css": get_css_text_selector(tag),
            "label_selector": label_selector,
            "label_xpath": label_xpath,
            "label_to_input": relationship,
        }
        
        # Add dropdown detection metadata
        if is_custom_dropdown:
            input_data["is_dropdown"] = True
            input_data["readonly"] = readonly
            if role:
                input_data["role"] = role
            if aria_haspopup:
                input_data["aria-haspopup"] = aria_haspopup

        inputs.append(input_data)

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