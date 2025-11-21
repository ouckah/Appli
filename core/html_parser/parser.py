from bs4 import BeautifulSoup
from typing import Dict, Any


def extract_element(tag, element_type: str, parent_form_id=None) -> Dict[str, Any]:
    """Return minimal metadata + raw HTML snippet for any interactable element."""
    return {
        "type": element_type,
        "id": tag.get("id"),
        "name": tag.get("name"),
        "element_type": (tag.get("type") or element_type).lower() if element_type == "input" else element_type,
        "form_id": parent_form_id,
        "html": str(tag)
    }


def parse_for_raw_elements(html: str) -> Dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")

    results = {
        "forms": [],
        "standalone": {
            "inputs": [],
            "buttons": [],
            "selects": [],
            "labels": []
        }
    }

    # -----------------
    # Elements inside forms
    # -----------------
    for form in soup.find_all("form"):
        form_id = form.get("id")
        form_data = {
            "form_id": form_id,
            "inputs": [],
            "buttons": [],
            "selects": [],
            "labels": []
        }

        # Inputs
        for inp in form.find_all("input"):
            t = (inp.get("type") or "text").lower()
            if t in ("submit", "button", "reset"):
                form_data["buttons"].append(extract_element(inp, "button", parent_form_id=form_id))
            else:
                form_data["inputs"].append(extract_element(inp, "input", parent_form_id=form_id))

        # Buttons
        for b in form.find_all("button"):
            form_data["buttons"].append(extract_element(b, "button", parent_form_id=form_id))

        # Selects
        for s in form.find_all("select"):
            form_data["selects"].append(extract_element(s, "select", parent_form_id=form_id))

        # Labels
        for lbl in form.find_all("label"):
            form_data["labels"].append(extract_element(lbl, "label", parent_form_id=form_id))

        results["forms"].append(form_data)

    # -----------------
    # Standalone elements (not inside forms)
    # -----------------
    for inp in soup.find_all("input"):
        if inp.find_parent("form") is None:
            results["standalone"]["inputs"].append(extract_element(inp, "input"))

    for b in soup.find_all("button"):
        if b.find_parent("form") is None:
            results["standalone"]["buttons"].append(extract_element(b, "button"))

    for s in soup.find_all("select"):
        if s.find_parent("form") is None:
            results["standalone"]["selects"].append(extract_element(s, "select"))

    for lbl in soup.find_all("label"):
        if lbl.find_parent("form") is None:
            results["standalone"]["labels"].append(extract_element(lbl, "label"))

    return results