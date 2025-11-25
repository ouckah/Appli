import hashlib
from bs4 import BeautifulSoup
from typing import Dict, Any
from core.dom_realizer.realizer import load_and_clean


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


def is_hidden_element(tag):
    # direct hidden attribute
    if tag.has_attr("hidden"):
        return True

    # input type="hidden"
    if tag.name == "input" and tag.get("type") == "hidden":
        return True

    # style="display:none", "visibility:hidden", "opacity:0"
    style = tag.get("style", "") or ""
    style_lower = style.replace(" ", "").lower()

    if "display:none" in style_lower:
        return True
    if "visibility:hidden" in style_lower:
        return True
    if "opacity:0" in style_lower:
        return True

    return False


# check if the element is effectively hidden (parent is also hidden)
def is_effectively_hidden(tag):
    cur = tag
    while cur is not None and cur.name != "[document]":
        if is_hidden_element(cur):
            return True
        cur = cur.parent
    return False


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
        "aria": extract_aria(tag)
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

        # Support wrapping labels: <label>Text <input/></label> or <label>Text <textarea/></label>
        inp = lbl.find("input")
        if inp and inp.get("id"):
            mapping[inp["id"]] = get_text_clean(lbl)
        
        textarea = lbl.find("textarea")
        if textarea and textarea.get("id"):
            mapping[textarea["id"]] = get_text_clean(lbl)

    # Also map labels that are siblings or in parent divs
    # Look for inputs/textareas and find nearby labels
    for field in soup.find_all(["input", "textarea"]):
        field_id = field.get("id")
        if not field_id:
            continue
        
        # If already mapped, skip
        if field_id in mapping:
            continue
        
        # Look for label in parent div or previous sibling
        parent = field.parent
        if parent:
            # Check if parent div has a label as a child (before the field)
            for child in parent.children:
                if child == field:
                    break
                if hasattr(child, 'name') and child.name == "label":
                    label_text = get_text_clean(child)
                    if label_text:
                        mapping[field_id] = label_text
                        break
            
            # Also check for labels in parent's previous siblings
            if field_id not in mapping:
                for sibling in parent.previous_siblings:
                    if hasattr(sibling, 'name'):
                        if sibling.name == "label":
                            label_text = get_text_clean(sibling)
                            if label_text:
                                mapping[field_id] = label_text
                                break
                        # Also check if sibling contains a label
                        elif sibling.find("label"):
                            label = sibling.find("label")
                            label_text = get_text_clean(label)
                            if label_text:
                                mapping[field_id] = label_text
                                break

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
        if is_effectively_hidden(form):
            continue

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
            if is_effectively_hidden(inp):
                continue

            meta = extract_element(inp, role="input", form_id=form_id)

            # attach label text if exists
            if meta["id"] in label_map:
                meta["label"] = label_map[meta["id"]]

            form_data["inputs"].append(meta)
        
        # Textareas (multi-line text inputs)
        for textarea in form.find_all("textarea"):
            if is_effectively_hidden(textarea):
                continue

            meta = extract_element(textarea, role="input", form_id=form_id)
            meta["type"] = "textarea"  # Mark as textarea

            # attach label text if exists
            if meta["id"] in label_map:
                meta["label"] = label_map[meta["id"]]

            form_data["inputs"].append(meta)

        # Buttons
        for b in form.find_all(["button", "input"], recursive=True):
            if is_effectively_hidden(b):
                continue
            if b.name == "button" or b.get("type") in ("submit", "button", "reset"):
                form_data["buttons"].append(extract_element(b, role="button", form_id=form_id))

        # Selects + option extraction
        for s in form.find_all("select"):
            if is_effectively_hidden(s):
                continue

            meta = extract_element(s, role="select", form_id=form_id)

            # Get *all* options, but skip hidden ones
            all_options = [
                opt for opt in s.find_all("option")
                if not is_effectively_hidden(opt)
            ]

            # Store counts + overflow indicator
            meta["option_count"] = len(all_options)
            meta["has_more_options"] = len(all_options) > 10

            # Preview only first 10
            meta["options"] = [
                {
                    "value": opt.get("value") if opt.has_attr("value") else get_text_clean(opt),
                    "text": get_text_clean(opt),
                }
                for opt in all_options[:10]
            ]

            # Remove the 'text' field for selects - it contains all option texts concatenated
            # which can be thousands of options. We already have the options array for preview.
            meta["text"] = None

            meta["multiple"] = s.has_attr("multiple")
            meta["required"] = s.has_attr("required")

            form_data["selects"].append(meta)

        # Labels
        for lbl in form.find_all("label"):
            if is_effectively_hidden(lbl):
                continue
            form_data["labels"].append(extract_element(lbl, role="label", form_id=form_id))

        results["forms"].append(form_data)

    # ===================================================
    # Standalone elements (outside forms)
    # ===================================================
    # Standalone inputs
    for inp in soup.find_all("input"):
        if is_effectively_hidden(inp):
            continue
        if inp.find_parent("form") is None:
            meta = extract_element(inp, role="input")
            if meta["id"] in label_map:
                meta["label"] = label_map[meta["id"]]
            results["standalone"]["inputs"].append(meta)
    
    # Standalone textareas
    for textarea in soup.find_all("textarea"):
        if is_effectively_hidden(textarea):
            continue
        if textarea.find_parent("form") is None:
            meta = extract_element(textarea, role="input")
            meta["type"] = "textarea"
            if meta["id"] in label_map:
                meta["label"] = label_map[meta["id"]]
            results["standalone"]["inputs"].append(meta)

    # Standalone buttons
    for b in soup.find_all("button"):
        if is_effectively_hidden(b):
            continue
        if b.find_parent("form") is None:
            results["standalone"]["buttons"].append(extract_element(b, role="button"))

    # Standalone selects
    for s in soup.find_all("select"):
        if is_effectively_hidden(s):
            continue
        if s.find_parent("form") is None:

            meta = extract_element(s, role="select")

            # collect visible options only
            all_options = [
                opt for opt in s.find_all("option")
                if not is_effectively_hidden(opt)
            ]

            meta["option_count"] = len(all_options)
            meta["has_more_options"] = len(all_options) > 10

            # preview first 10
            meta["options"] = [
                {
                    "value": opt.get("value") if opt.has_attr("value") else get_text_clean(opt),
                    "text": get_text_clean(opt)
                }
                for opt in all_options[:10]
            ]

            # Remove the 'text' field for selects - it contains all option texts concatenated
            # which can be thousands of options. We already have the options array for preview.
            meta["text"] = None

            meta["multiple"] = s.has_attr("multiple")
            meta["required"] = s.has_attr("required")

            results["standalone"]["selects"].append(meta)

    # Links (anchors)
    for a in soup.find_all("a"):
        if is_effectively_hidden(a):
            continue
        if a.find_parent("form") is None:
            results["standalone"]["links"].append(extract_element(a, role="link"))

    # Clickable: anything with role="button" or tabindex="0"
    for el in soup.find_all():
        if is_effectively_hidden(b):
            continue
        if el.name in ("button", "a"):
            continue
        if el.get("role") == "button" or el.get("tabindex") == "0":
            results["standalone"]["clickables"].append(extract_element(el, role="clickable"))

    return results