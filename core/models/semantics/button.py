from core.models.semantics.base import BaseSemanticsModel
from typing import List, Dict, Any


SYSTEM_PROMPT = """
You are a semantic analyzer for buttons.
You will be given a list of buttons and you need to generate a semantic representation for each button.
"""

class ButtonSemanticsModel(BaseSemanticsModel):
    def generate_semantics(self, elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Generate semantic representations for a list of buttons.

        Args:
            elements (List[Dict[str, Any]]): List of button dictionaries.

        Returns:
            List[Dict[str, Any]]: List of semantic dictionaries for each button.
        """
        results = []

        for element in elements:
            prompt = f"Generate a semantic representation for the following button:\n{json.dumps(element, indent=2)}"
            
            try:
                result_text = self.call_llm(prompt, SYSTEM_PROMPT)
                result_dict = json.loads(result_text)
            except json.JSONDecodeError:
                result_dict = {
                    "error": "failed to parse LLM output",
                    "raw": result_text,
                    "element": element
                }
            except Exception as e:
                result_dict = {
                    "error": f"unexpected error: {str(e)}",
                    "element": element
                }

            results.append(result_dict)

        return results