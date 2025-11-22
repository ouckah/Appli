import hashlib
from bs4 import BeautifulSoup
from typing import Dict, Any


# =======================================================
# Helpers
# =======================================================

def get_text_clean(el):
    """Extract readable text content."""
    if el is None:
        return None
    text = el.get_text(strip=True)
    return text if text else None


def extract_aria(el):
    """Return all aria-* properties."""
    return {k: v for k, v in el.attrs.items() if k.startswith("aria-")}


def get_xpath(element):
    """Compute basic XPath for stable referencing."""
    path = []
    current = element

    while current is not None and current.name != "[document]":
        siblings = [sib for sib in current.parent.find_all(current.name, recursive=False)]
        if len(siblings) == 1:
            path.append(current.name)
        else:
            index = siblings.index(current) + 1
            path.append(f"{current.name}[{index}]")
        current = current.parent

    return "/" + "/".join(path[::-1])


def generate_stable_form_id(form):
    """Generate a reproducible ID for forms without IDs."""
    raw = (
        get_xpath(form)
        + (form.get("action") or "")
        + (form.get("method") or "")
        + form.decode_contents()
    )

    sig = hashlib.sha256(raw.encode()).hexdigest()[:12]
    return f"form_{sig}"


# =======================================================
# Element Extractor
# =======================================================

def extract_element(tag, role: str, form_id=None) -> Dict[str, Any]:
    """Universal extractor for any interactable element."""
    return {
        "role": role,
        "tag": tag.name,
        "id": tag.get("id"),
        "name": tag.get("name"),
        "type": tag.get("type"),
        "class_list": tag.get("class", []),
        "placeholder": tag.get("placeholder"),
        "text": get_text_clean(tag),
        "xpath": get_xpath(tag),
        "form_id": form_id,
        "aria": extract_aria(tag),
        "html": str(tag)
    }


# =======================================================
# Label Mapping
# =======================================================

def map_labels(soup):
    """Return mapping: target-id → readable label text."""
    mapping = {}

    for lbl in soup.find_all("label"):
        target = lbl.get("for")
        if target:
            mapping[target] = get_text_clean(lbl)

        # Support wrapping labels: <label>Text <input/></label>
        inp = lbl.find("input")
        if inp and inp.get("id"):
            mapping[inp["id"]] = get_text_clean(lbl)

    return mapping


# =======================================================
# Main Parser
# =======================================================

def parse_html_semantics(html: str) -> Dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    label_map = map_labels(soup)

    results = {
        "forms": [],
        "standalone": {
            "inputs": [],
            "buttons": [],
            "selects": [],
            "links": [],
            "clickables": []
        }
    }

    # ===================================================
    # Forms
    # ===================================================
    for form in soup.find_all("form"):
        real_id = form.get("id")
        form_id = real_id if real_id else generate_stable_form_id(form)

        form_data = {
            "form_id": form_id,
            "xpath": get_xpath(form),
            "inputs": [],
            "buttons": [],
            "selects": [],
            "labels": []
        }

        # Inputs
        for inp in form.find_all("input"):
            meta = extract_element(inp, role="input", form_id=form_id)

            # attach label text if exists
            if meta["id"] in label_map:
                meta["label"] = label_map[meta["id"]]

            form_data["inputs"].append(meta)

        # Buttons
        for b in form.find_all(["button", "input"], recursive=True):
            if b.name == "button" or b.get("type") in ("submit", "button", "reset"):
                form_data["buttons"].append(extract_element(b, role="button", form_id=form_id))

        # Selects + option extraction
        for s in form.find_all("select"):
            meta = extract_element(s, role="select", form_id=form_id)
            meta["options"] = [
                {
                    "value": opt.get("value"),
                    "text": get_text_clean(opt)
                }
                for opt in s.find_all("option")
            ]
            form_data["selects"].append(meta)

        # Labels
        for lbl in form.find_all("label"):
            form_data["labels"].append(extract_element(lbl, role="label", form_id=form_id))

        results["forms"].append(form_data)

    # ===================================================
    # Standalone elements (outside forms)
    # ===================================================
    # Standalone inputs
    for inp in soup.find_all("input"):
        if inp.find_parent("form") is None:
            results["standalone"]["inputs"].append(extract_element(inp, role="input"))

    # Standalone buttons
    for b in soup.find_all("button"):
        if b.find_parent("form") is None:
            results["standalone"]["buttons"].append(extract_element(b, role="button"))

    # Standalone selects
    for s in soup.find_all("select"):
        if s.find_parent("form") is None:
            meta = extract_element(s, role="select")
            meta["options"] = [
                {
                    "value": opt.get("value"),
                    "text": get_text_clean(opt)
                }
                for opt in s.find_all("option")
            ]
            results["standalone"]["selects"].append(meta)

    # Links (anchors)
    for a in soup.find_all("a"):
        if a.find_parent("form") is None:
            results["standalone"]["links"].append(extract_element(a, role="link"))

    # Clickable: anything with role="button" or tabindex="0"
    for el in soup.find_all():
        if el.name in ("button", "a"):
            continue
        if el.get("role") == "button" or el.get("tabindex") == "0":
            results["standalone"]["clickables"].append(extract_element(el, role="clickable"))

    return results