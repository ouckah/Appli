from typing import List, Dict, Any
from core.dom_realizer.realizer import load_and_clean
from core.html_parser.parser import parse_for_raw_elements
from core.models.semantics.input_field import InputFieldSemanticsModel


def extract_semantics(elements: Dict[str, Any]) -> List[Dict[str, Any]]:
    print(elements["standalone"])


def main():
    html = load_and_clean("https://www.google.com")
    elements = parse_for_raw_elements(html)
    extract_semantics(elements)

if __name__ == "__main__":
    main()
    