from typing import Dict, Any
from core.dom_realizer.realizer import load_and_clean
from core.html_parser.parser import parse_html_semantics
from core.models.semantics import SemanticsModel


def extract_semantics(elements: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert parsed HTML elements into semantic-rich structures
    ready for Playwright plan generation.
    """
    model = SemanticsModel()

    results = {
        "forms": [],
        "standalone": {
            "inputs": [],
            "buttons": [],
            "selects": [],
            "labels": [],
            "links": [],
            "clickables": []
        }
    }

    # -----------------------------
    # Process forms
    # -----------------------------
    for form in elements.get("forms", []):
        form_result = {
            "form_id": form.get("form_id"),
            "xpath": form.get("xpath"),
            "inputs": model.generate_semantics(form.get("inputs", [])),
            "buttons": model.generate_semantics(form.get("buttons", [])),
            "selects": model.generate_semantics(form.get("selects", [])),
            "labels": model.generate_semantics(form.get("labels", []))
        }
        results["forms"].append(form_result)

    # -----------------------------
    # Process standalone elements
    # -----------------------------
    for key in results["standalone"].keys():
        results["standalone"][key] = model.generate_semantics(
            elements.get("standalone", {}).get(key, [])
        )

    return results


def main():
    url = "https://www.google.com"
    html = load_and_clean(url)
    
    # Parse the HTML and extract raw elements
    elements = parse_html_semantics(html)

    # Convert to semantic-rich structures
    semantics = extract_semantics(elements)

    # Pretty print
    import json
    print(json.dumps(semantics, indent=4))


if __name__ == "__main__":
    main()