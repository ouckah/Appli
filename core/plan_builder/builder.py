from typing import List, Dict, Any
from core.models.plans import PlanBuilderModel
from core.dom_realizer.realizer import load_and_clean
from core.html_parser.parser import parse_html_semantics


def build_plan(elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Build a plan for a list of elements.
    """
    model = PlanBuilderModel()
    return model.build_plan(elements)


def main():
    url = "https://www.google.com"
    html = load_and_clean(url)
    elements = parse_html_semantics(html)
    plan = build_plan(elements)
    print(plan)

if __name__ == "__main__":
    main()